"""Fusion: cross-domain correlation of bank, CDR and IPDR records.

Products:
- a single sorted event timeline (money + calls + sessions) for investigation
- per-phone CDR profiles (contact counts, towers, activity windows)
- per-account bank profiles (flows, modes, counterparties, NCRP flag)
- phone <-> bank linking: phones recovered from bank narrations matched against
  CDR subscribers, with temporal coincidence windows
- composite risk heat for accounts and phones (consumed by scoring + reports)
"""

from __future__ import annotations

import bisect
import math
import re
import threading
from collections import Counter, defaultdict

BANK_TXN_WINDOW_SEC = 3600
MIN_CONTACTS = 3


def build_timeline(bundle: dict) -> list[dict]:
    """Merge every event with a usable timestamp into one sorted timeline."""
    events = []
    for r in bundle.get("bank", []):
        ts = r.get("ts")
        if not ts:
            continue
        events.append({
            "ts": ts, "date": r.get("date"), "time": r.get("time") or "",
            "kind": "bank", "record_id": r.get("txn_id"),
            "entity": r.get("account_no") or "",
            "label": r.get("narration", "")[:80],
            "amount": r.get("credit") if r.get("credit") else r.get("debit"),
            "direction": "C" if r.get("txn_type") == "C" else "D",
            "mode": r.get("mode") or "",
            "phone": r.get("receiver_phone") or "",
            "upi_id": r.get("upi_id") or "",
        })
    for r in bundle.get("cdr", []):
        ts = r.get("ts")
        if not ts:
            continue
        events.append({
            "ts": ts, "date": r.get("date"), "time": r.get("time") or "",
            "kind": "cdr", "record_id": r.get("cdr_id"),
            "entity": r.get("a_number") or "",
            "label": f"{r.get('call_type','')} {r.get('b_number','')}",
            "amount": None, "direction": r.get("call_type"),
            "mode": r.get("service_type") or "",
            "phone": r.get("b_number") or "",
            "upi_id": "",
        })
    for r in bundle.get("ipdr", []):
        ts = r.get("start_ts")
        if not ts:
            continue
        events.append({
            "ts": ts, "date": r.get("date"), "time": r.get("start_time") or "",
            "kind": "ipdr", "record_id": r.get("ipdr_id"),
            "entity": r.get("msisdn") or "",
            "label": r.get("source_ip") or "",
            "amount": None, "direction": "",
            "mode": "IPDR",
            "phone": r.get("msisdn") or "",
            "upi_id": "",
        })
    events.sort(key=lambda e: e["ts"])
    return events


def phone_analysis(cdr: list[dict]) -> dict:
    """Per-target phone profile from CDR records."""
    out: dict[str, dict] = {}
    for r in cdr:
        a = r.get("a_number") or ""
        if not a:
            continue
        p = out.setdefault(a, {
            "phone": a, "contacts": 0, "unique_contacts": 0, "sms": 0,
            "voice": 0, "first_ts": None, "last_ts": None,
            "towers": Counter(), "contact_set": set(), "records": 0,
        })
        b = r.get("b_number") or ""
        p["contacts"] += 1
        p["records"] += 1
        if b:
            p["contact_set"].add(b)
        if "SMS" in (r.get("call_type") or "").upper():
            p["sms"] += 1
        else:
            p["voice"] += 1
        ts = r.get("ts")
        if ts:
            p["first_ts"] = ts if p["first_ts"] is None else min(p["first_ts"], ts)
            p["last_ts"] = ts if p["last_ts"] is None else max(p["last_ts"], ts)
        cell = r.get("cell_id_first") or r.get("cell_id_last") or ""
        if cell:
            p["towers"][cell] += 1
    for p in out.values():
        p["unique_contacts"] = len(p["contact_set"])
        p["towers"] = dict(p["towers"].most_common(5))
        p.pop("contact_set")
    return out


def account_analysis(bank: list[dict], complaints: list[dict]) -> dict:
    """Per-account profile from canonical bank records."""
    ncrp = defaultdict(list)
    for c in complaints:
        if c.get("account_no"):
            ncrp[c["account_no"]].append(c)
    out: dict[str, dict] = {}
    for r in bank:
        acc = r.get("account_no") or ""
        if not acc:
            continue
        a = out.setdefault(acc, {
            "account_no": acc, "bank": r.get("bank") or "", "txns": 0,
            "credit": 0.0, "debit": 0.0, "modes": Counter(),
            "counterparties": Counter(), "phones": Counter(),
            "upi_ids": Counter(), "first_ts": None, "last_ts": None,
            "ncrp": 0, "ncrp_states": [],
        })
        a["txns"] += 1
        a["credit"] += r.get("credit") or 0.0
        a["debit"] += r.get("debit") or 0.0
        mode = r.get("mode") or "OTHER"
        a["modes"][mode] += 1
        name = (r.get("counterparty_name") or "").strip()
        if name:
            a["counterparties"][name[:40]] += 1
        phone = r.get("receiver_phone") or r.get("sender_phone") or ""
        if phone:
            a["phones"][phone] += 1
        upi = r.get("upi_id") or ""
        if upi:
            a["upi_ids"][upi] += 1
        ts = r.get("ts")
        if ts:
            a["first_ts"] = ts if a["first_ts"] is None else min(a["first_ts"], ts)
            a["last_ts"] = ts if a["last_ts"] is None else max(a["last_ts"], ts)
        if acc in ncrp:
            a["ncrp"] += 1
    for acc, a in out.items():
        a["modes"] = dict(a["modes"].most_common(6))
        a["counterparties"] = dict(a["counterparties"].most_common(8))
        a["phones"] = dict(a["phones"].most_common(8))
        a["upi_ids"] = dict(a["upi_ids"].most_common(8))
        if acc in ncrp:
            a["ncrp"] = len(ncrp[acc])
            a["ncrp_states"] = sorted({c.get("state") or "" for c in ncrp[acc] if c.get("state")})
    return out


def correlate_phones(bundle: dict, window_sec: int = BANK_TXN_WINDOW_SEC) -> dict:
    """Link bank counterparty phones to CDR activity.

    For every phone recovered from a bank narration that is also a CDR
    subscriber, report the money window around each CDR event of that phone:
    - same-phone money movement within +/- window of call activity
    - CDR profile stats for the phone
    """
    cdr_by_a: dict[str, list[dict]] = defaultdict(list)
    for r in bundle.get("cdr", []):
        a = r.get("a_number") or ""
        if a and r.get("ts"):
            cdr_by_a[a].append(r)
    cdr_keys: dict[str, list[float]] = {}
    for ph in cdr_by_a:
        cdr_by_a[ph].sort(key=lambda x: x["ts"])
        cdr_keys[ph] = [c["ts"] for c in cdr_by_a[ph]]
    phones = phone_analysis(bundle.get("cdr", []))
    hits = []
    for r in bundle.get("bank", []):
        ph = r.get("receiver_phone") or ""
        if not ph or ph not in cdr_by_a:
            continue
        txn_ts = r.get("ts")
        window = []
        if txn_ts:
            c_list = cdr_by_a[ph]
            keys = cdr_keys[ph]
            idx_start = bisect.bisect_left(keys, txn_ts - window_sec)
            idx_end = bisect.bisect_right(keys, txn_ts + window_sec)
            for c in c_list[idx_start:idx_end]:
                window.append({
                    "ts": c["ts"], "type": c.get("call_type"),
                    "b": c.get("b_number"), "dur": c.get("duration_sec"),
                })
            window.sort(key=lambda e: e["ts"])
        hits.append({
            "phone": ph,
            "account_no": r.get("account_no"),
            "txn_id": r.get("txn_id"),
            "txn_date": r.get("date"),
            "txn_ts": txn_ts,
            "direction": r.get("txn_type"),
            "amount": r.get("credit") if r.get("txn_type") == "C" else r.get("debit"),
            "mode": r.get("mode"),
            "narration": (r.get("narration") or "")[:120],
            "upi_id": r.get("upi_id"),
            "phone_cdr_records": len(cdr_by_a[ph]),
            "phone_contacts": phones.get(ph, {}).get("contacts", 0),
            "window_hits": window[:20],
            "window_count": len(window),
        })
    hits.sort(key=lambda h: (h["phone"], h["txn_ts"] or 0))
    return {"hits": hits, "window_sec": window_sec}


_ROUND_RE = re.compile(r"^[5]?0000(0{1,4})$|^\d0000(0+)$|^[125]\d{4,}$")


def _is_round(amount: float) -> bool:
    if amount is None:
        return False
    a = abs(amount)
    return a >= 1000 and (a % 5000 == 0)


def fraud_heat(bundle: dict) -> dict:
    """Composite risk indicators for accounts, phones and UPI ids."""
    complaints = bundle.get("complaints", [])
    ncrp_accounts = {c.get("account_no") for c in complaints if c.get("account_no")}
    accounts = account_analysis(bundle.get("bank", []), complaints)
    cdr = bundle.get("cdr", [])
    phones = phone_analysis(cdr)
    cdr_targets = Counter(r.get("a_number") or "" for r in cdr)

    account_flags: list[dict] = []
    for acc, a in accounts.items():
        score = 0
        flags = []
        breakdown = []
        if acc in ncrp_accounts:
            score += 60
            flags.append("NCRP_FRAUD_ACCOUNT")
            breakdown.append({"rule": "NCRP_FRAUD_ACCOUNT", "points": 60,
                              "reason": "Account is listed in the NCRP "
                                        "complaint ledger"})
        modes = a.get("modes") or {}
        if modes.get("UPI", 0) and modes.get("UPI", 0) >= a["txns"] * 0.8 and a["txns"] >= 10:
            score += 10
            flags.append("UPI_HEAVY")
            breakdown.append({"rule": "UPI_HEAVY", "points": 10,
                              "reason": "Over 80% of transactions are UPI "
                                        "(rapid-money signature)"})
        if (a["credit"] or 0) >= 100000 and a["txns"] >= 10:
            score += 10
            flags.append("HIGH_VOLUME")
            breakdown.append({"rule": "HIGH_VOLUME", "points": 10,
                              "reason": f"Credits ≥ Rs 100,000 across "
                                        f"{a['txns']} transactions"})
        if any(c.startswith(("0", "1")) for c in (a.get("counterparties") or {})) and a["txns"] >= 20:
            pass
        if len(a.get("counterparties") or {}) >= 15 and a["txns"] >= 25:
            score += 15
            flags.append("MANY_COUNTERPARTIES")
            breakdown.append({"rule": "MANY_COUNTERPARTIES", "points": 15,
                              "reason": f"{len(a['counterparties'])} distinct "
                                        "counterparties — money-funnel pattern"})
        if a.get("phones") and len(a["phones"]) >= 5:
            score += 10
            flags.append("MANY_PHONES")
            breakdown.append({"rule": "MANY_PHONES", "points": 10,
                              "reason": f"{len(a['phones'])} phone numbers "
                                        "linked to this account"})
        acct_phone = a.get("phones") or {}
        if any(p in cdr_targets for p in acct_phone):
            score += 20
            flags.append("PHONE_IN_CDR")
            breakdown.append({"rule": "PHONE_IN_CDR", "points": 20,
                              "reason": "Account phone appears in telecom CDR "
                                        "records (cross-domain link)"})
        account_flags.append({
            "account_no": acc, "bank": a["bank"], "txns": a["txns"],
            "credit": a["credit"], "debit": a["debit"],
            "score": min(score, 100), "flags": flags,
            "breakdown": breakdown,
            "confidence": round(min(0.5 + score / 200.0, 0.97), 2),
            "ncrp_states": a.get("ncrp_states", []),
        })
    account_flags.sort(key=lambda x: -x["score"])

    phone_flags: list[dict] = []
    for ph, p in phones.items():
        score = 0
        flags = []
        breakdown = []
        if p["records"] >= 50:
            score += 15
            flags.append("HIGH_ACTIVITY")
            breakdown.append({"rule": "HIGH_ACTIVITY", "points": 15,
                              "reason": f"{p['records']} CDR records — "
                                        "heavy activity"})
        if p["contacts"] and p["unique_contacts"] and p["unique_contacts"] >= 25:
            score += 15
            flags.append("MANY_CONTACTS")
            breakdown.append({"rule": "MANY_CONTACTS", "points": 15,
                              "reason": f"{p['unique_contacts']} unique "
                                        "contacts"})
        if (p["last_ts"] or 0) - (p["first_ts"] or 0) > 60 * 86400:
            score += 5
            flags.append("LONG_ACTIVITY_SPAN")
            breakdown.append({"rule": "LONG_ACTIVITY_SPAN", "points": 5,
                              "reason": "Activity spans more than 60 days"})
        phone_flags.append({
            "phone": ph, "records": p["records"], "contacts": p["contacts"],
            "unique_contacts": p["unique_contacts"], "sms": p["sms"],
            "voice": p["voice"], "score": min(score, 100), "flags": flags,
            "breakdown": breakdown,
            "confidence": round(min(0.5 + score / 200.0, 0.97), 2),
        })
    phone_flags.sort(key=lambda x: -x["score"])

    round_payouts = [
        {"txn_id": r.get("txn_id"), "account_no": r.get("account_no"),
         "date": r.get("date"), "amount": r.get("credit") or r.get("debit"),
         "mode": r.get("mode"), "phone": r.get("receiver_phone"),
         "narration": (r.get("narration") or "")[:100]}
        for r in bundle.get("bank", [])
        if r.get("txn_type") == "D" and _is_round(r.get("debit"))
    ]
    round_payouts.sort(key=lambda x: x.get("amount") or 0, reverse=True)

    return {
        "accounts": account_flags,
        "phones": phone_flags,
        "round_payouts": round_payouts[:200],
        "cdr_targets": dict(cdr_targets),
    }


def rapid_payouts(bundle: dict, threshold: int = 5, window_min: int = 60) -> list[dict]:
    """Accounts paying out >= threshold times within a window (cash-out pattern)."""
    by_acc: dict[str, list[dict]] = defaultdict(list)
    for r in bundle.get("bank", []):
        if r.get("txn_type") != "D" or not r.get("ts"):
            continue
        by_acc[r.get("account_no") or ""].append(r)
    out = []
    for acc, rs in by_acc.items():
        rs.sort(key=lambda r: r["ts"])
        i, j, n = 0, 0, len(rs)
        while i < n:
            while j < n and rs[j]["ts"] - rs[i]["ts"] <= window_min * 60:
                j += 1
            if j - i >= threshold:
                out.append({
                    "account_no": acc,
                    "window_min": window_min,
                    "count": j - i,
                    "start_ts": rs[i]["ts"], "end_ts": rs[j - 1]["ts"],
                    "total": sum((r.get("debit") or 0) for r in rs[i:j]),
                    "txns": [{"txn_id": r["txn_id"], "ts": r["ts"],
                              "amount": r.get("debit"),
                              "mode": r.get("mode")} for r in rs[i:j]][:15],
                })
                break
            i += 1
    out.sort(key=lambda x: -x["count"])
    return out


def circular_flows(bundle: dict, min_amount: float = 10000,
                   max_len: int = 6, cap: int = 50) -> list[dict]:
    """Detect money loops between accounts (A->B->A, A->B->C->A, ...).

    Layering and circular flows move money between controlled accounts so the
    trail loops back. Cycles are only meaningful between real accounts, so the
    graph is built from `receiver_account` edges with a significant amount.
    """
    import itertools

    import networkx as nx

    g = nx.DiGraph()
    for r in bundle.get("bank", []):
        acc = r.get("account_no")
        tgt = r.get("receiver_account")
        amt = r.get("debit") or 0
        if not acc or not tgt or amt < min_amount:
            continue
        if g.has_edge(acc, tgt):
            g[acc][tgt]["amount"] += amt
            g[acc][tgt]["count"] += 1
        else:
            g.add_edge(acc, tgt, amount=amt, count=1)
    # prune trivial/isolated nodes before cycle search (performance guard)
    keep = {n for n in g.nodes if g.degree(n) >= 1 and
            any(g[u][v]["count"] >= 1 for u, v in g.edges(n))}
    g = g.subgraph(keep).copy()

    out = []
    
    def dfs(start, current, path):
        if len(out) >= cap or len(path) > max_len:
            return
            
        for nxt in g.successors(current):
            if nxt == start and len(path) >= 2:
                cyc = list(path)
                edges = list(zip(cyc, cyc[1:] + cyc[:1]))
                min_amt = min(g[u][v]["amount"] for u, v in edges)
                total = sum(g[u][v]["amount"] for u, v in edges)
                out.append({
                    "accounts": cyc,
                    "length": len(cyc),
                    "total_flow": round(total, 2),
                    "min_leg": round(min_amt, 2),
                })
            elif nxt > start and nxt not in path:
                path.append(nxt)
                dfs(start, nxt, path)
                path.pop()

    for node in g.nodes():
        dfs(node, node, [node])
        if len(out) >= cap:
            break

    out.sort(key=lambda x: -x["total_flow"])
    return out


def rapid_in_out(bundle: dict, window_min: int = 15) -> list[dict]:
    """Accounts that receive and then fully send out money within minutes —
    classic money-mule cash-through (rapid in-and-out)."""
    bank = bundle.get("bank", [])
    if not bank:
        return []
    by_acc: dict[str, list[dict]] = defaultdict(list)
    for r in bank:
        if not r.get("ts"):
            continue
        by_acc[r.get("account_no") or ""].append(r)
    out = []
    for acc, rs in by_acc.items():
        rs.sort(key=lambda r: r["ts"])
        debits = [(r["ts"], r.get("debit") or 0, r) for r in rs if (r.get("debit") or 0) > 0]
        debit_tss = [d[0] for d in debits]
        
        for i, r in enumerate(rs):
            c = r.get("credit") or 0
            if c <= 0:
                continue
            ts = r["ts"]
            idx = bisect.bisect_right(debit_tss, ts)
            for j in range(idx, len(debits)):
                d_ts, d_val, d_r = debits[j]
                if d_ts - ts > window_min * 60:
                    break
                if d_val >= c * 0.95:
                    out.append({
                        "account_no": acc,
                        "in_ts": ts, "out_ts": d_ts,
                        "window_min": window_min,
                        "in_amount": c, "out_amount": d_val,
                        "in_txn": r.get("txn_id"), "out_txn": d_r.get("txn_id"),
                        "mode": r.get("mode") or d_r.get("mode"),
                    })
                    break
    out.sort(key=lambda x: x["out_ts"] - x["in_ts"])
    return out[:100]


def search_bundle(bundle: dict, q: str, limit: int = 50) -> dict:
    """Cross-entity search: accounts, phones, UPI ids, IMEI, IMSI, IPs,
    counterparty names, transactions and NCRP complaints."""
    q = (q or "").strip().lower()
    if not q:
        return {"query": q, "total": 0, "results": []}
    bank = bundle.get("bank", [])
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])
    complaints = bundle.get("complaints", [])
    entities = bundle.get("entities", {})
    results = []

    def hit(kind: str, key: str, label: str, extra: dict | None = None) -> None:
        if len(results) >= limit:
            return
        results.append({"kind": kind, "key": key, "label": label,
                        **(extra or {})})

    account_stats = bundle.get("_account_stats")
    if account_stats is None:
        account_stats = {}
        for r in bank:
            acc = r.get("account_no")
            if acc:
                st = account_stats.setdefault(acc, {"count": 0, "bank": r.get("bank"), "holder": r.get("holder")})
                st["count"] += 1
                if not st["bank"]: st["bank"] = r.get("bank")
                if not st["holder"]: st["holder"] = r.get("holder")
        bundle["_account_stats"] = account_stats

    for acct in entities.get("accounts") or []:
        if q in str(acct).lower():
            st = account_stats.get(acct, {})
            hit("account", acct, f"Account {acct} · {st.get('bank') or ''} "
                f"· {st.get('holder') or ''}",
                {"txns": st.get("count", 0)})
    for ph in entities.get("phones") or []:
        if q in str(ph).lower():
            hit("phone", ph, f"Phone {ph}")
    for u in entities.get("upi_ids") or []:
        if q in str(u).lower():
            hit("upi", u, f"UPI {u}")
    for imei in entities.get("imeis") or []:
        if q in str(imei).lower():
            hit("imei", imei, f"IMEI {imei}")
    for imsi in entities.get("imsis") or []:
        if q in str(imsi).lower():
            hit("imsi", imsi, f"IMSI {imsi}")
    for ip in entities.get("ips") or []:
        if q in str(ip).lower():
            hit("ip", ip, f"IP {ip}")
    for c in complaints:
        hay = " ".join(str(v) for v in (c.get("account_no"), c.get("phone"),
                                        c.get("upi"), c.get("state"),
                                        c.get("bank_name"))).lower()
        if q in hay:
            hit("complaint", c.get("account_no") or c.get("complaint_id") or "",
                f"NCRP complaint · {c.get('state') or ''} · "
                f"{c.get('account_no') or ''}", {"bank": c.get("bank_name")})
    for r in bank:
        hay = " ".join(str(r.get(k) or "") for k in (
            "txn_id", "narration", "counterparty_name", "receiver_account",
            "upi_id", "receiver_phone", "sender_phone", "holder")).lower()
        if q in hay:
            hit("transaction", r.get("txn_id") or "", 
                f"Txn {str(r.get('txn_id'))[:26]} · {r.get('date')} · "
                f"Rs {r.get('debit') or r.get('credit')} · "
                f"{(r.get('narration') or '')[:48]}",
                {"account_no": r.get("account_no"), "amount": r.get("debit")
                 or r.get("credit"), "date": r.get("date")})
    if len(results) >= limit:
        results = results[:limit]
    return {"query": q, "total": len(results), "results": results}


def _fuse_norm10(phone) -> str:
    """Last-10-digits phone normaliser shared by the fused-table linker."""
    if not phone:
        return ""
    if type(phone) is int:
        digits = str(phone)
    else:
        digits = str(phone)
        if not digits.isdigit():
            digits = "".join(filter(str.isdigit, digits))
    if len(digits) >= 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else ""


def _compute_fused_base(bundle: dict) -> list[dict]:
    """Fused bank x CDR x IPDR preview rows for the anomaly tab.

    Each bank transaction is enriched with the CDR calls and IPDR sessions
    linked to its phones inside the correlation windows, an NCRP complaint
    flag, and (when a precomputed score map is supplied) risk annotation.
    """
    bank = bundle.get("bank", [])
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])
    ncrp = {str(c.get("account_no") or "").strip()
            for c in bundle.get("complaints", [])}
    ncrp.discard("")

    # Phone -> sorted (ts, seq) indices so the per-txn window match is a
    # binary search instead of a linear scan (60k CDRs x 20k txns otherwise).
    # The second tuple element is an int seq into the original list, so the
    # bisect sentinels (-1 / 10**18) compare exactly at both boundaries.
    cdr_by_phone: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for seq, c in enumerate(cdr):
        cts = c.get("ts")
        if cts is None:
            continue
        for p in (_fuse_norm10(c.get("a_number")), _fuse_norm10(c.get("b_number"))):
            if p:
                cdr_by_phone[p].append((float(cts), seq))
    for lst in cdr_by_phone.values():
        lst.sort()

    ipdr_by_msisdn: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for seq, i in enumerate(ipdr):
        its = i.get("start_ts")
        if its is None:
            continue
        p = _fuse_norm10(i.get("msisdn"))
        if p:
            ipdr_by_msisdn[p].append((float(its), seq))
    for lst in ipdr_by_msisdn.values():
        lst.sort()

    def _window_hits(index, txn_ts, window_sec):
        """(ts, seq) entries inside [ts-window, ts+window] via bisect;
        inclusive at both boundaries."""
        lo = bisect.bisect_left(index, (txn_ts - window_sec, -1))
        hi = bisect.bisect_right(index, (txn_ts + window_sec, 10 ** 18))
        return index[lo:hi]

    rows = []
    for r in bank:
        txn_ts = r.get("ts")
        phones = {_fuse_norm10(r.get("sender_phone")),
                  _fuse_norm10(r.get("receiver_phone"))}
        phones.discard("")
        calls, seen_calls = [], set()
        if txn_ts:
            for p in phones:
                for _cts, seq in _window_hits(cdr_by_phone.get(p, ()),
                                              float(txn_ts), 300):
                    c = cdr[seq]
                    key = c.get("cdr_id")
                    if key in seen_calls:
                        continue
                    seen_calls.add(key)
                    calls.append({
                        "cdr_id": key, "ts": c.get("ts"),
                        "type": c.get("call_type") or "",
                        "dur": c.get("duration_sec"),
                        "bts": c.get("bts_location_first") or "",
                        "phone": p,
                    })
        sessions, seen_ipdr = [], set()
        if txn_ts:
            for p in phones:
                for _its, seq in _window_hits(ipdr_by_msisdn.get(p, ()),
                                              float(txn_ts), 900):
                    i = ipdr[seq]
                    key = i.get("ipdr_id")
                    if key in seen_ipdr:
                        continue
                    seen_ipdr.add(key)
                    sessions.append({
                        "ipdr_id": key, "ts": i.get("start_ts"),
                        "ip": i.get("source_ip") or "",
                        "dur": i.get("duration_sec"),
                    })
        calls.sort(key=lambda e: e["ts"] or 0)
        sessions.sort(key=lambda e: e["ts"] or 0)

        acc = str(r.get("account_no") or "")
        amount = r.get("credit") if r.get("txn_type") == "C" else r.get("debit")
        rows.append({
            "transaction_id": r.get("txn_id") or "",
            "date": r.get("date") or "",
            "time": r.get("time") or "",
            "ts": txn_ts,
            "mode": r.get("mode") or "",
            "amount": amount,
            "direction": r.get("txn_type") or "",
            "account_no": acc,
            "account_name": r.get("account_name") or "",
            "bank": r.get("bank") or "",
            "counterparty_name": r.get("counterparty_name") or "",
            "counterparty_bank": r.get("counterparty_bank") or "",
            "receiver_account": r.get("receiver_account") or "",
            "sender_phone": r.get("sender_phone") or "",
            "receiver_phone": r.get("receiver_phone") or "",
            "linked_calls": calls[:10],
            "call_count": len(calls),
            "linked_sessions": sessions[:10],
            "ipdr_count": len(sessions),
            "ncrp": acc in ncrp,
            "risk_score": None,
            "risk_band": None,
        })
    rows.sort(key=lambda r: (r["ts"] is None, r["ts"] or 0), reverse=True)
    return rows

def cached_fused_base(bundle: dict) -> list[dict]:
    key = ("fused_base", _fingerprint(bundle))
    hit = _fusion_cache.get(key)
    if hit is not None:
        return hit
        
    with _fusion_cache_lock:
        hit = _fusion_cache.get(key)
        if hit is not None:
            return hit
        result = _compute_fused_base(bundle)
        _fusion_cache[key] = result
        return result

def fused_table(bundle: dict, offset: int = 0, limit: int = 100,
                q: str = "", account: str = "", mode: str = "", scored: dict | None = None) -> dict:
    base_rows = cached_fused_base(bundle)
    q_low = (q or "").strip().lower()
    account_low = (account or "").strip().lower()
    mode_low = (mode or "").strip().lower()
    
    if q_low or account_low or mode_low:
        kept = []
        for row in base_rows:
            if account_low and account_low not in str(row["account_no"]).lower():
                continue
            if mode_low:
                m = str(row.get("mode") or "").strip().lower()
                if mode_low not in m:
                    continue
            if q_low:
                hay = " ".join(str(row.get(k) or "") for k in (
                    "transaction_id", "account_no", "account_name",
                    "counterparty_name", "receiver_account",
                    "sender_phone", "receiver_phone", "bank")).lower()
                if q_low not in hay:
                    continue
            kept.append(row)
    else:
        kept = base_rows

    total = len(kept)
    page_rows = [dict(r) for r in kept[offset:offset + limit]]
    
    if scored:
        for row in page_rows:
            s = scored.get(row["transaction_id"]) or {}
            row["risk_score"] = s.get("risk_score")
            row["risk_band"] = s.get("risk_band")
            row["explain_plain"] = s.get("explain_plain")
            row["rules_fired"] = str(s.get("rules_fired", []))
            row["ncrp_states"] = s.get("ncrp_states", [])
            
    return {"total": total, "offset": offset, "limit": limit,
            "rows": page_rows}

# ---------------------------------------------------------------- caching

_fusion_cache: dict[tuple, dict | list] = {}
_fusion_cache_lock = threading.Lock()

def _fingerprint(bundle: dict) -> tuple:
    bank = bundle.get("bank", [])
    ids = [r.get("txn_id") for r in bank[:3]]
    return (len(bank), len(bundle.get("cdr", [])), len(bundle.get("ipdr", [])),
            len(bundle.get("complaints", [])), tuple(ids))

def cached_fraud_heat(bundle: dict) -> dict:
    key = ("fraud_heat", _fingerprint(bundle))
    hit = _fusion_cache.get(key)
    if hit is not None:
        return hit
    result = fraud_heat(bundle)
    with _fusion_cache_lock:
        _fusion_cache[key] = result
    return result

def cached_build_timeline(bundle: dict) -> list[dict]:
    key = ("build_timeline", _fingerprint(bundle))
    hit = _fusion_cache.get(key)
    if hit is not None:
        return hit
    result = build_timeline(bundle)
    with _fusion_cache_lock:
        _fusion_cache[key] = result
    return result


def clear_fusion_cache() -> None:
    with _fusion_cache_lock:
        _fusion_cache.clear()
