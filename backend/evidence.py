"""Evidence intelligence: entity KPI cards, edge intelligence, evidence graphs.

Investigator-grade enrichment over the fused bundle:

- entity_intelligence(): a digital-forensic KPI card for any entity (account,
  phone, UPI, IMEI, IMSI, IP, name) — risk + explainable breakdown, activity,
  volumes, links, suspicious patterns and recent records.
- relationship_intelligence(): the evidence behind a graph edge — call stats,
  money flows, coincidence windows and laundering indicators.
- evidence_egonet(): context-aware subgraph — keeps only calls that are
  investigate-worthy (high-risk endpoints, calls inside suspicious-transaction
  windows, shared-device links), never the full call history.
- device_graph() / ip_graph(): IMEI and IP relationship layers.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx

from .fusion import (BANK_TXN_WINDOW_SEC, account_analysis, circular_flows,
                     fraud_heat, phone_analysis, rapid_in_out, rapid_payouts)
from .graphs import phone_call_graph

_MAX_NODES = 90
_RISK_BANDS = lambda s: "CRITICAL" if s >= 75 else ("HIGH" if s >= 50 else ("MEDIUM" if s >= 25 else "LOW"))


def _ts_label(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""


def _with_risk(out: dict, h: dict | None) -> dict:
    if h:
        out["risk_score"] = int(h["score"])
        out["risk_band"] = _RISK_BANDS(h["score"])
        out["confidence"] = round(min(0.5 + h["score"] / 200.0, 0.97), 2)
        out["flags"] = h.get("flags", [])
        out["breakdown"] = h.get("breakdown", [])
    return out


def entity_intelligence(bundle: dict, kind: str, value: str) -> dict | None:
    """Full evidence card for one entity; None when nothing references it."""
    bank = bundle.get("bank", [])
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])
    complaints = bundle.get("complaints", [])
    heat = fraud_heat(bundle)
    acc_heat = {a["account_no"]: a for a in heat["accounts"]}
    ph_heat = {p["phone"]: p for p in heat["phones"]}
    value = str(value or "")
    if not value:
        return None

    out = {
        "kind": kind, "value": value, "risk_score": 0, "risk_band": "LOW",
        "confidence": 0.0, "flags": [], "breakdown": [],
        "counts": {"transactions": 0, "calls": 0, "sms": 0, "ip_sessions": 0},
        "volumes": {"credit": 0.0, "debit": 0.0, "avg_amount": 0.0,
                    "max_amount": 0.0, "txns": 0, "round_amounts": 0},
        "activity": {"first": None, "last": None},
        "links": {}, "patterns": [], "ncrp": [], "records": [],
    }

    def _add_record(kind_, ts, date, time, label, amount=None):
        if len(out["records"]) >= 15:
            return
        out["records"].append({"kind": kind_, "ts": ts, "date": date or "",
                               "time": time or "", "label": label or "",
                               "amount": amount})

    # ------------------------------------------------------------- account
    if kind == "account":
        txns = [r for r in bank if str(r.get("account_no") or "") == value]
        if not txns:
            return None
        prof = account_analysis(bank, complaints).get(value) or {}
        _with_risk(out, acc_heat.get(value))
        out["counts"]["transactions"] = len(txns)
        credits = sum(r.get("credit") or 0 for r in txns)
        debits = sum(r.get("debit") or 0 for r in txns)
        amts = [(r.get("credit") or r.get("debit")) or 0 for r in txns]
        rounds = sum(1 for r in txns if (r.get("debit") or 0) >= 1000
                     and (r.get("debit") or 0) % 5000 == 0)
        out["volumes"] = {"credit": credits, "debit": debits,
                          "avg_amount": round(sum(amts) / max(len(amts), 1), 2),
                          "max_amount": max(amts) if amts else 0.0,
                          "txns": len(txns), "round_amounts": rounds}
        out["activity"] = {"first": _ts_label(prof.get("first_ts")),
                           "last": _ts_label(prof.get("last_ts"))}
        out["links"] = {
            "phones": list((prof.get("phones") or {}).keys()),
            "upi_ids": list((prof.get("upi_ids") or {}).keys()),
            "counterparties": list((prof.get("counterparties") or {}).keys()),
            "receiver_accounts": sorted({r.get("receiver_account") or ""
                                         for r in txns if r.get("receiver_account")})[:20],
        }
        out["ncrp"] = [c for c in complaints
                       if str(c.get("account_no") or "") == value]
        # suspicious patterns
        if prof.get("ncrp"):
            out["patterns"].append({"label": "NCRP FRAUD ACCOUNT",
                                    "evidence": "Account is listed in the NCRP "
                                                "complaint ledger"})
        if rounds:
            out["patterns"].append({"label": "STRUCTURED PAYOUTS",
                                    "evidence": f"{rounds} round-amount debits "
                                                "(multiples of Rs 5,000)"})
        for x in rapid_payouts(bundle):
            if x["account_no"] == value:
                out["patterns"].append({
                    "label": "RAPID CASH-OUT",
                    "evidence": f"{x['count']} debits within {x['window_min']} min, "
                                f"total Rs {x['total']:,.0f} "
                                f"({_ts_label(x['start_ts'])} → {_ts_label(x['end_ts'])})"})
        for x in rapid_in_out(bundle):
            if x["account_no"] == value:
                out["patterns"].append({
                    "label": "RAPID IN-AND-OUT (mule signature)",
                    "evidence": f"Rs {x['in_amount']:,.0f} in, "
                                f"Rs {x['out_amount']:,.0f} out within "
                                f"{x['window_min']} min"})
        for cyc in circular_flows(bundle, min_amount=0):
            if value in cyc["accounts"]:
                out["patterns"].append({
                    "label": "CIRCULAR FLOW",
                    "evidence": " → ".join(cyc["accounts"]) +
                                f" (total Rs {cyc['total_flow']:,.0f})"})
        hits = correlate_hits_for_account(bundle, value)
        if hits:
            out["patterns"].append({
                "label": "BANK↔TELECOM COINCIDENCE",
                "evidence": f"{hits} transaction(s) with CDR activity on the "
                            f"same phone within {BANK_TXN_WINDOW_SEC // 60} min"})
        for r in sorted(txns, key=lambda r: r.get("ts") or 0, reverse=True):
            _add_record("bank", r.get("ts"), r.get("date"), r.get("time"),
                        f"{r.get('txn_type')} {r.get('mode')} — "
                        f"{(r.get('narration') or '')[:70]}",
                        r.get("credit") if r.get("credit") else r.get("debit"))
        return out

    # --------------------------------------------------------------- phone
    if kind == "phone":
        prof = phone_analysis(cdr).get(value) or {}
        calls = [r for r in cdr
                 if str(r.get("a_number") or "") == value
                 or str(r.get("b_number") or "") == value]
        txns = [r for r in bank
                if str(r.get("receiver_phone") or "") == value
                or str(r.get("sender_phone") or "") == value]
        sessions = [r for r in ipdr if str(r.get("msisdn") or "") == value]
        if not calls and not txns and not sessions:
            return None
        _with_risk(out, ph_heat.get(value))
        out["counts"]["calls"] = prof.get("contacts", 0)
        out["counts"]["sms"] = prof.get("sms", 0)
        out["counts"]["transactions"] = len(txns)
        out["counts"]["ip_sessions"] = len(sessions)
        amts = [(r.get("credit") or r.get("debit")) or 0 for r in txns]
        out["volumes"] = {"credit": sum(r.get("credit") or 0 for r in txns),
                          "debit": sum(r.get("debit") or 0 for r in txns),
                          "avg_amount": round(sum(amts) / max(len(amts), 1), 2),
                          "max_amount": max(amts) if amts else 0.0,
                          "txns": len(txns),
                          "round_amounts": sum(1 for r in txns
                                               if (r.get("debit") or 0) >= 1000
                                               and (r.get("debit") or 0) % 5000 == 0)}
        out["activity"] = {"first": _ts_label(prof.get("first_ts")),
                           "last": _ts_label(prof.get("last_ts"))}
        contacts = Counter(str(r.get("b_number") or r.get("a_number") or "")
                           for r in calls
                           if str(r.get("b_number") or r.get("a_number") or "") != value)
        imeis = Counter(str(r.get("imei") or "") for r in calls + sessions if r.get("imei"))
        ips = Counter(str(r.get("source_ip") or "") for r in sessions if r.get("source_ip"))
        out["links"] = {
            "accounts": sorted({r.get("account_no") or "" for r in txns if r.get("account_no")}),
            "contacts": list(dict(contacts.most_common(12)).keys()),
            "imeis": list(dict(imeis.most_common(8)).keys()),
            "ips": list(dict(ips.most_common(8)).keys()),
            "towers": list((prof.get("towers") or {}).keys()),
        }
        # suspicious patterns
        if txns and prof.get("contacts"):
            out["patterns"].append({
                "label": "BANK↔TELECOM OVERLAP",
                "evidence": f"{len(txns)} bank transaction(s) reference this "
                            f"phone; {prof['contacts']} CDR records"})
        hits = [h for h in correlate_hits_for_phone(bundle, value)
                if h.get("window_count")]
        if hits:
            out["patterns"].append({
                "label": "CALLS NEAR SUSPICIOUS TRANSACTIONS",
                "evidence": f"{sum(h['window_count'] for h in hits)} CDR event(s) "
                            f"inside ±{BANK_TXN_WINDOW_SEC // 60} min of money "
                            f"movement"})
        shared = shared_imei_phones(bundle, value)
        if shared:
            out["patterns"].append({
                "label": "SHARED DEVICE",
                "evidence": f"IMEI shared with: {', '.join(shared[:5])}"})
        for r in sorted(calls, key=lambda r: r.get("ts") or 0, reverse=True):
            _add_record("cdr", r.get("ts"), r.get("date"), r.get("time"),
                        f"{r.get('call_type') or 'CALL'} → "
                        f"{r.get('b_number')} · {r.get('duration_sec')}s")
        for r in sorted(txns, key=lambda r: r.get("ts") or 0, reverse=True):
            _add_record("bank", r.get("ts"), r.get("date"), r.get("time"),
                        f"{r.get('txn_type')} {r.get('mode')} · Rs "
                        f"{r.get('credit') or r.get('debit')} · "
                        f"{(r.get('narration') or '')[:60]}")
        for r in sorted(sessions, key=lambda r: r.get("start_ts") or 0, reverse=True):
            _add_record("ipdr", r.get("start_ts"), r.get("date"), r.get("start_time"),
                        f"IP session {r.get('source_ip')} → "
                        f"{r.get('dest_ip')} · {r.get('duration_sec')}s")
        return out

    # ------------------------------------------------------- generic kinds
    if kind in ("imei", "imsi"):
        if kind == "imei":
            calls = [r for r in cdr if str(r.get("imei") or "") == value]
            sessions = [r for r in ipdr if str(r.get("imei") or "") == value]
        else:
            calls = [r for r in cdr if str(r.get("imsi") or "") == value]
            sessions = [r for r in ipdr if str(r.get("imsi") or "") == value]
        if not calls and not sessions:
            return None
        phones = Counter(str(r.get("a_number") or r.get("msisdn") or "")
                         for r in calls + sessions if r.get("a_number") or r.get("msisdn"))
        out["counts"]["calls"] = len(calls)
        out["counts"]["ip_sessions"] = len(sessions)
        out["links"] = {"phones": list(dict(phones.most_common(15)).keys())}
        for r in sorted(calls + sessions, key=lambda r: r.get("ts") or r.get("start_ts") or 0,
                        reverse=True)[:15]:
            _add_record("cdr" if r.get("a_number") else "ipdr",
                        r.get("ts") or r.get("start_ts"),
                        r.get("date"), r.get("time") or r.get("start_time"),
                        f"{r.get('a_number') or r.get('msisdn')} · {value}")
        return out

    if kind == "ip":
        sessions = [r for r in ipdr if str(r.get("source_ip") or "") == value]
        if not sessions:
            return None
        msisdns = Counter(str(r.get("msisdn") or "") for r in sessions if r.get("msisdn"))
        out["counts"]["ip_sessions"] = len(sessions)
        out["links"] = {"phones": list(dict(msisdns.most_common(15)).keys())}
        for r in sorted(sessions, key=lambda r: r.get("start_ts") or 0, reverse=True)[:15]:
            _add_record("ipdr", r.get("start_ts"), r.get("date"), r.get("start_time"),
                        f"{r.get('msisdn')} · {r.get('dest_ip')} · "
                        f"{r.get('duration_sec')}s")
        return out

    if kind == "upi":
        txns = [r for r in bank if str(r.get("upi_id") or "") == value]
        if not txns:
            return None
        accounts = Counter(str(r.get("account_no") or "") for r in txns if r.get("account_no"))
        phones = Counter(str(r.get("receiver_phone") or "") for r in txns if r.get("receiver_phone"))
        out["counts"]["transactions"] = len(txns)
        amts = [(r.get("credit") or r.get("debit")) or 0 for r in txns]
        out["volumes"] = {"credit": sum(r.get("credit") or 0 for r in txns),
                          "debit": sum(r.get("debit") or 0 for r in txns),
                          "avg_amount": round(sum(amts) / max(len(amts), 1), 2),
                          "max_amount": max(amts) if amts else 0.0,
                          "txns": len(txns), "round_amounts": 0}
        out["links"] = {"accounts": list(dict(accounts.most_common(12)).keys()),
                        "phones": list(dict(phones.most_common(8)).keys())}
        for r in sorted(txns, key=lambda r: r.get("ts") or 0, reverse=True)[:15]:
            _add_record("bank", r.get("ts"), r.get("date"), r.get("time"),
                        f"UPI {r.get('txn_type')} · "
                        f"{(r.get('narration') or '')[:60]}",
                        r.get("credit") or r.get("debit"))
        return out

    if kind == "name":
        txns = [r for r in bank if value.lower()
                in str(r.get("counterparty_name") or "").lower()]
        if not txns:
            return None
        accounts = Counter(str(r.get("account_no") or "") for r in txns if r.get("account_no"))
        phones = Counter(str(r.get("receiver_phone") or "") for r in txns if r.get("receiver_phone"))
        out["counts"]["transactions"] = len(txns)
        out["links"] = {"accounts": list(dict(accounts.most_common(12)).keys()),
                        "phones": list(dict(phones.most_common(8)).keys())}
        for r in sorted(txns, key=lambda r: r.get("ts") or 0, reverse=True)[:15]:
            _add_record("bank", r.get("ts"), r.get("date"), r.get("time"),
                        f"{(r.get('narration') or '')[:70]}",
                        r.get("credit") or r.get("debit"))
        return out

    return None


def correlate_hits_for_account(bundle: dict, account_no: str) -> list[dict]:
    """Coincidence hits where the bank side is `account_no`."""
    from .fusion import correlate_phones
    return [h for h in correlate_phones(bundle)["hits"]
            if h.get("account_no") == account_no]


def correlate_hits_for_phone(bundle: dict, phone: str) -> list[dict]:
    from .fusion import correlate_phones
    return [h for h in correlate_phones(bundle)["hits"] if h.get("phone") == phone]


def shared_imei_phones(bundle: dict, phone: str) -> list[str]:
    """Other phones that have used one of this phone's IMEIs."""
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])
    my_imeis = {str(r.get("imei")) for r in cdr + ipdr
                if str(r.get("a_number") or r.get("msisdn") or "") == phone
                and r.get("imei")}
    if not my_imeis:
        return []
    others = Counter()
    for r in cdr + ipdr:
        imei = str(r.get("imei") or "")
        ph = str(r.get("a_number") or r.get("msisdn") or "")
        if imei in my_imeis and ph and ph != phone:
            others[ph] += 1
    return list(dict(others.most_common(10)).keys())


def relationship_intelligence(bundle: dict, a: str, b: str) -> dict:
    """Evidence behind one edge: calls, money, IP overlap, indicators."""
    bank = bundle.get("bank", [])
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])
    a, b = str(a), str(b)
    accounts = {str(r.get("account_no") or "") for r in bank}
    phones = {str(r.get("a_number") or "") for r in cdr}
    heat = fraud_heat(bundle)
    ph_heat = {p["phone"]: p for p in heat["phones"]}

    out = {"a": a, "b": b, "relationship": None, "calls": None,
           "money": None, "coincidences": [], "indicators": [],
           "evidence": []}

    # ------------------------------------------------ phone ↔ phone (calls)
    if a in phones and b in phones:
        both = [r for r in cdr
                if {str(r.get("a_number") or ""), str(r.get("b_number") or "")}
                == {a, b}]
        both += [r for r in cdr
                 if str(r.get("a_number") or "") == b
                 and str(r.get("b_number") or "") == a]
        if both:
            out["relationship"] = "call"
            durs = [r.get("duration_sec") or 0 for r in both]
            types = Counter(str(r.get("call_type") or "CALL") for r in both)
            ts = sorted((r.get("ts") or 0) for r in both)
            out["calls"] = {
                "count": len(both),
                "total_seconds": sum(durs),
                "avg_seconds": round(sum(durs) / max(len(durs), 1), 1),
                "max_seconds": max(durs) if durs else 0,
                "first": _ts_label(ts[0]) if ts else None,
                "last": _ts_label(ts[-1]) if ts else None,
                "by_type": dict(types),
            }
            if len(both) >= 10 and (ts[-1] - ts[0]) <= 60 * 60:
                out["indicators"].append({
                    "code": "CALL_BURST",
                    "label": "Call burst",
                    "evidence": f"{len(both)} calls inside one hour"})
            for r in sorted(both, key=lambda r: r.get("ts") or 0,
                            reverse=True)[:10]:
                out["evidence"].append(
                    f"[CDR {_ts_label(r.get('ts'))}] {r.get('call_type')} "
                    f"{a}↔{b} · {r.get('duration_sec')}s · "
                    f"cell {r.get('cell_id_first') or '—'}")
    # ------------------------------------------- account ↔ account (money)
    elif a in accounts and b in accounts:
        fwd = [r for r in bank
               if str(r.get("account_no") or "") == a
               and str(r.get("receiver_account") or "") == b]
        rev = [r for r in bank
               if str(r.get("account_no") or "") == b
               and str(r.get("receiver_account") or "") == a]
        if fwd or rev:
            out["relationship"] = "money"
            def _leg(rows, direction):
                amts = [r.get("debit") or 0 for r in rows]
                return {"direction": direction, "count": len(rows),
                        "total": round(sum(amts), 2),
                        "avg": round(sum(amts) / max(len(amts), 1), 2),
                        "max": max(amts) if amts else 0.0,
                        "round_amounts": sum(1 for r in rows
                                             if (r.get("debit") or 0) >= 1000
                                             and (r.get("debit") or 0) % 5000 == 0),
                        "modes": dict(Counter(str(r.get("mode") or "OTHER")
                                              for r in rows)),
                        "first": _ts_label(min((r.get("ts") or 0) for r in rows))
                        if rows else None,
                        "last": _ts_label(max((r.get("ts") or 0) for r in rows))
                        if rows else None}
            legs = [_leg(fwd, f"{a}→{b}")]
            if rev:
                legs.append(_leg(rev, f"{b}→{a}"))
            out["money"] = {"legs": legs,
                            "net": round(sum(l["total"] for l in legs if "→" + a in l["direction"])
                                         - sum(l["total"] for l in legs if l["direction"].startswith(a + "→")), 2)}
            for l in legs:
                if l["round_amounts"]:
                    out["indicators"].append({
                        "code": "STRUCTURING",
                        "label": "Structuring",
                        "evidence": f"{l['round_amounts']} round-amount "
                                    f"transfers on leg {l['direction']}"})
            for cyc in circular_flows(bundle, min_amount=0):
                if a in cyc["accounts"] and b in cyc["accounts"]:
                    out["indicators"].append({
                        "code": "CIRCULAR_FLOW",
                        "label": "Circular money flow",
                        "evidence": " → ".join(cyc["accounts"]) +
                                    f" (Rs {cyc['total_flow']:,.0f})"})
            if len(fwd) >= 3 and rev:
                out["indicators"].append({
                    "code": "RETURN_FLOW",
                    "label": "Layering / return flow",
                    "evidence": f"{len(fwd)} transfers {a}→{b} and "
                                f"{len(rev)} back {b}→{a}"})
            for r in sorted(fwd + rev, key=lambda r: r.get("ts") or 0,
                            reverse=True)[:10]:
                out["evidence"].append(
                    f"[BANK {_ts_label(r.get('ts'))}] Rs {r.get('debit'):,.0f} "
                    f"{r.get('mode')} · {(r.get('narration') or '')[:60]}")
    # ----------------------------------------------------- phone ↔ account
    else:
        acct, ph = (a, b) if a in accounts else (b, a)
        if not (acct and ph):
            return out
        txns = [r for r in bank
                if str(r.get("account_no") or "") == acct
                and (str(r.get("receiver_phone") or "") == ph
                     or str(r.get("sender_phone") or "") == ph)]
        if txns:
            out["relationship"] = "money"
            amts = [(r.get("credit") or r.get("debit")) or 0 for r in txns]
            out["money"] = {"legs": [{
                "direction": f"{acct}↔{ph}", "count": len(txns),
                "total": round(sum(amts), 2),
                "avg": round(sum(amts) / max(len(amts), 1), 2),
                "max": max(amts) if amts else 0.0,
                "round_amounts": sum(1 for r in txns
                                     if (r.get("debit") or 0) >= 1000
                                     and (r.get("debit") or 0) % 5000 == 0),
                "modes": dict(Counter(str(r.get("mode") or "OTHER")
                                      for r in txns)),
                "first": _ts_label(min((r.get("ts") or 0) for r in txns)),
                "last": _ts_label(max((r.get("ts") or 0) for r in txns)),
            }], "net": round(sum(amts), 2)}
            for r in sorted(txns, key=lambda r: r.get("ts") or 0,
                            reverse=True)[:10]:
                out["evidence"].append(
                    f"[BANK {_ts_label(r.get('ts'))}] Rs "
                    f"{r.get('debit') or r.get('credit'):,.0f} {r.get('mode')} · "
                    f"{(r.get('narration') or '')[:60]}")
        # calls on the phone near those transactions
        call_times = [(r.get("ts"), r.get("call_type"), r.get("b_number"))
                      for r in cdr if str(r.get("a_number") or "") == ph]
        for r in txns:
            ts = r.get("ts")
            if not ts:
                continue
            near = [(c, t, b) for c, t, b in call_times
                    if c and abs(c - ts) <= BANK_TXN_WINDOW_SEC]
            if near:
                out["coincidences"].append({
                    "txn_ts": _ts_label(ts),
                    "amount": r.get("credit") or r.get("debit"),
                    "mode": r.get("mode"),
                    "calls_in_window": [{
                        "ts": _ts_label(c), "type": t, "b": b
                    } for c, t, b in near[:5]],
                    "window_min": BANK_TXN_WINDOW_SEC // 60,
                })
                out["relationship"] = out["relationship"] or "mixed"
        # IP overlap for the pair
        if a in phones or b in phones:
            phn = a if (a in phones or a.isdigit() and len(a) >= 10) else b
            shared = shared_imei_phones(bundle, phn)
            if a in shared or b in shared:
                out["indicators"].append({
                    "code": "SHARED_DEVICE",
                    "label": "Shared device",
                    "evidence": f"{phn} shares an IMEI with the other entity"})
    return out


def _risky_phones(bundle: dict, heat: dict, min_score: int = 50) -> set:
    """Phones that score high, or that are tied to high-risk accounts."""
    risky = {p["phone"] for p in heat["phones"] if p["score"] >= min_score}
    risky_accs = {a["account_no"] for a in heat["accounts"]
                  if a["score"] >= min_score}
    for r in bundle.get("bank", []):
        if str(r.get("account_no") or "") in risky_accs:
            ph = r.get("receiver_phone") or ""
            if ph:
                risky.add(ph)
    return risky


def evidence_egonet(bundle: dict, phone: str, depth: int = 1,
                    window_sec: int = BANK_TXN_WINDOW_SEC,
                    max_nodes: int = _MAX_NODES) -> dict:
    """Ego network of `phone` restricted to investigate-worthy calls.

    Keeps only edges where at least one endpoint is high-risk, or where the
    call falls inside a suspicious money window (round payouts, high-risk
    account movements, rapid cash-out accounts).
    """
    phone = str(phone)
    heat = fraud_heat(bundle)
    risky = _risky_phones(bundle, heat)
    # suspicious money windows keyed by receiver phone
    suspicious: dict[str, list[tuple]] = defaultdict(list)
    acc_heat = {a["account_no"]: a for a in heat["accounts"]}
    fast_accs = {x["account_no"] for x in rapid_payouts(bundle)}
    for r in bundle.get("bank", []):
        ph = r.get("receiver_phone") or ""
        ts = r.get("ts")
        acc = str(r.get("account_no") or "")
        if not ph or not ts:
            continue
        amt = r.get("debit") or 0
        if (acc in acc_heat and acc_heat[acc]["score"] >= 50) or \
           acc in fast_accs or \
           (amt >= 1000 and amt % 5000 == 0):
            suspicious[ph].append(
                (ts, f"Rs {amt:,.0f} {r.get('mode')} "
                     f"({r.get('txn_id') or ''}) on account {acc[-6:]}"))

    calls: dict[tuple, dict] = {}
    for r in bundle.get("cdr", []):
        a = str(r.get("a_number") or "")
        b = str(r.get("b_number") or "")
        if not a or not b:
            continue
        calls.setdefault((a, b), {"weight": 0, "seconds": 0,
                                  "ts": r.get("ts") or 0,
                                  "evidence": []})
        e = calls[(a, b)]
        e["weight"] += 1
        e["seconds"] += r.get("duration_sec") or 0
        e["ts"] = min(e["ts"], r.get("ts") or e["ts"]) if e["ts"] else (r.get("ts") or 0)
        ts = r.get("ts")
        if ts:
            for ph, label in suspicious.get(a, []):
                if abs(ts - ph) <= window_sec:
                    e["evidence"].append(f"call {a}→{b} {abs(ts - ph) // 60}min after {label}")
            for ph, label in suspicious.get(b, []):
                if abs(ts - ph) <= window_sec:
                    e["evidence"].append(f"call {a}→{b} {abs(ts - ph) // 60}min near {label}")

    total_edges = len(calls)
    kept = {k: v for k, v in calls.items()
            if (k[0] in risky or k[1] in risky or v["evidence"])}
    g = nx.DiGraph()
    for (a, b), e in kept.items():
        if a not in g:
            g.add_node(a, kind="phone")
        if b not in g:
            g.add_node(b, kind="phone")
        g.add_edge(a, b, weight=e["weight"], seconds=e["seconds"],
                   evidence=e["evidence"][:4])

    try:
        nodes = set(nx.ego_graph(g, phone, radius=depth))
    except (nx.NetworkXError, nx.NodeNotFound):
        nodes = set()

    ph_heat = {p["phone"]: p for p in heat["phones"]}
    out_nodes = []
    for n in sorted(nodes)[:max_nodes]:
        out_nodes.append({
            "id": n, "kind": "phone",
            "degree": g.degree(n),
            "risk": int(ph_heat.get(n, {}).get("score", 0)),
        })
    out_edges = []
    for u, v, d in g.edges(nodes, data=True):
        if len(out_edges) >= max_nodes * 3:
            break
        out_edges.append({
            "source": u, "target": v, "weight": d.get("weight", 1),
            "seconds": d.get("seconds", 0), "amount": 0,
            "evidence": d.get("evidence", []),
        })
    fallback = not out_nodes and not out_edges
    if fallback:
        # No investigate-worthy links for this phone: fall back to its top
        # direct contacts by call volume (bounded, never the full history).
        g_full = phone_call_graph(bundle.get("cdr", []))
        top = sorted(((u, v, d) for u, v, d in g_full.edges(phone, data=True)),
                     key=lambda e: e[2].get("weight", 0), reverse=True)[:12]
        for u, v, d in top:
            out_nodes.append({
                "id": v, "kind": "phone", "degree": g_full.degree(v),
                "risk": int(ph_heat.get(v, {}).get("score", 0)),
            })
            out_edges.append({
                "source": phone, "target": v, "weight": d.get("weight", 1),
                "seconds": d.get("seconds", 0), "amount": 0,
                "evidence": ["Top contact by call volume — no suspicious "
                             "links found for this phone"] + d.get("evidence", [])[:2],
            })
    return {"node": phone, "nodes": out_nodes, "edges": out_edges,
            "filtered": True, "kept": len(kept), "total": total_edges,
            "fallback": fallback, "window_min": window_sec // 60}


def device_graph(bundle: dict, phone: str, max_nodes: int = _MAX_NODES) -> dict:
    """IMEI layer: phone -> devices it used -> other phones on those devices."""
    phone = str(phone)
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])
    my_imeis = Counter(str(r.get("imei") or "") for r in cdr + ipdr
                       if str(r.get("a_number") or r.get("msisdn") or "") == phone
                       and r.get("imei"))
    if not my_imeis:
        return {"node": phone, "nodes": [], "edges": [], "filtered": True,
                "kept": 0, "total": 0}
    users: dict[str, Counter] = defaultdict(Counter)
    for r in cdr + ipdr:
        imei = str(r.get("imei") or "")
        ph = str(r.get("a_number") or r.get("msisdn") or "")
        if imei and ph:
            users[imei][ph] += 1
    heat = fraud_heat(bundle)
    ph_heat = {p["phone"]: p for p in heat["phones"]}
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    nodes[phone] = {"id": phone, "kind": "phone",
                    "risk": int(ph_heat.get(phone, {}).get("score", 0))}
    for imei, count in my_imeis.most_common(6):
        if not imei:
            continue
        if imei not in nodes and len(nodes) < max_nodes:
            nodes[imei] = {"id": imei, "kind": "device", "risk": 0}
        edges.append({"source": phone, "target": imei,
                      "weight": count, "amount": 0, "kind": "uses",
                      "evidence": [f"{count} sessions on device"]})
        for other, cnt in users[imei].most_common(8):
            if other == phone:
                continue
            if other not in nodes and len(nodes) < max_nodes:
                nodes[other] = {"id": other, "kind": "phone",
                                "risk": int(ph_heat.get(other, {}).get("score", 0))}
            if len(edges) >= max_nodes * 3:
                break
            edges.append({"source": imei, "target": other,
                          "weight": cnt, "amount": 0, "kind": "shared",
                          "evidence": [f"device also used by {other}"]})
    return {"node": phone, "nodes": list(nodes.values()), "edges": edges,
            "filtered": True, "kept": len(edges), "total": len(my_imeis)}


def ip_graph(bundle: dict, phone: str, max_nodes: int = _MAX_NODES) -> dict:
    """IP layer: phone -> source IPs -> other phones behind those IPs."""
    phone = str(phone)
    ipdr = bundle.get("ipdr", [])
    my_ips = Counter(str(r.get("source_ip") or "") for r in ipdr
                     if str(r.get("msisdn") or "") == phone and r.get("source_ip"))
    if not my_ips:
        return {"node": phone, "nodes": [], "edges": [], "filtered": True,
                "kept": 0, "total": 0}
    users: dict[str, Counter] = defaultdict(Counter)
    for r in ipdr:
        ip = str(r.get("source_ip") or "")
        ph = str(r.get("msisdn") or "")
        if ip and ph:
            users[ip][ph] += 1
    heat = fraud_heat(bundle)
    ph_heat = {p["phone"]: p for p in heat["phones"]}
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    nodes[phone] = {"id": phone, "kind": "phone",
                    "risk": int(ph_heat.get(phone, {}).get("score", 0))}
    for ip, count in my_ips.most_common(6):
        if not ip:
            continue
        if ip not in nodes and len(nodes) < max_nodes:
            nodes[ip] = {"id": ip, "kind": "ip", "risk": 0}
        edges.append({"source": phone, "target": ip,
                      "weight": count, "amount": 0, "kind": "uses",
                      "evidence": [f"{count} sessions from this IP"]})
        for other, cnt in users[ip].most_common(8):
            if other == phone:
                continue
            if other not in nodes and len(nodes) < max_nodes:
                nodes[other] = {"id": other, "kind": "phone",
                                "risk": int(ph_heat.get(other, {}).get("score", 0))}
            if len(edges) >= max_nodes * 3:
                break
            edges.append({"source": ip, "target": other,
                          "weight": cnt, "amount": 0, "kind": "shared",
                          "evidence": [f"IP also used by {other}"]})
    return {"node": phone, "nodes": list(nodes.values()), "edges": edges,
            "filtered": True, "kept": len(edges), "total": len(my_ips)}
