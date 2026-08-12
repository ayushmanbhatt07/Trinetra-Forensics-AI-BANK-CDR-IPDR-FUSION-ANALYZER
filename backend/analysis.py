"""Lightweight forensic analysis helpers used by the anomalies workbench:

- account × hour activity heatmap over the fused bank corpus,
- relationship model between user-selected transactions (multi-select in the
  fused-records table): money-flow legs, shared accounts/phones, and
  time-proximity links with plain-English edge kinds.

Everything here is O(n) over the bank list and needs no ML state, so it stays
fast even on 100k+ transaction bundles (scalability criterion).
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional


def txn_ts(row: dict) -> Optional[float]:
    """Unix timestamp of a bank row (best effort, mirrors the fused table)."""
    ts = row.get("ts")
    if isinstance(ts, (int, float)) and ts:
        return float(ts)
    date = row.get("date") or ""
    time_part = row.get("time") or ""
    if date:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S",
                    "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(f"{date} {time_part}".strip(), fmt).timestamp()
            except ValueError:
                continue
    return None


def _hour_of(ts: Optional[float]) -> Optional[int]:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).hour
    except Exception:
        return None


def account_hour_heatmap(bundle: dict, account: str = "",
                         max_accounts: int = 30) -> dict:
    """Account × hour-of-day activity heatmap.

    Cells carry transaction count and total amount; accounts are ranked by
    total moved so the most interesting ones surface first.
    """
    bank = bundle.get("bank", [])
    if account:
        bank = [r for r in bank
                if str(r.get("account_no") or "") == account]
    if not bank:
        return {"accounts": [], "hours": list(range(24)), "cells": []}

    agg: dict[str, list[list]] = {}
    order: dict[str, float] = {}
    for row in bank:
        acc = str(row.get("account_no") or "?")
        h = _hour_of(txn_ts(row))
        if h is None:
            continue
        amt = float(row.get("credit") or row.get("debit") or 0)
        cell = agg.setdefault(acc, [[0, 0.0] for _ in range(24)])
        cell[h][0] += 1
        cell[h][1] += amt
        order[acc] = order.get(acc, 0.0) + amt

    ranked = sorted(order, key=order.get, reverse=True)[:max_accounts]
    cells = [{"account": acc, "hours": [[c[0], round(c[1], 2)] for c in agg[acc]]}
             for acc in ranked]
    return {
        "accounts": ranked,
        "hours": list(range(24)),
        "cells": cells,
        "total_txns": sum(c[0] for cell in cells for c in cell["hours"]),
        "total_amount": round(sum(c[1] for cell in cells for c in cell["hours"]), 2),
    }


def relationship_model(bundle: dict, transaction_ids: list[str],
                       window_min: int = 30) -> dict:
    """Relationship model between selected transactions.

    Two transactions are linked when they:
      - move money into each other (receiver_account == account_no) → "money",
      - share the same account or a phone → "shared",
      - happen within `window_min` minutes of each other → "time".
    Edge strength = number of distinct dimensions that linked them.
    """
    bank = bundle.get("bank", [])
    wanted = {t: True for t in transaction_ids}
    txns: list[dict] = []
    seen = set()
    for row in bank:
        tid = str(row.get("txn_id") or row.get("transaction_id") or "")
        if tid in wanted and tid not in seen:
            seen.add(tid)
            txns.append(row)
            if len(txns) == len(wanted):
                break

    by_id = {str(r.get("txn_id") or r.get("transaction_id") or ""): r
             for r in txns}
    ids = list(by_id)
    ts_by_id = {tid: txn_ts(r) or 0.0 for tid, r in by_id.items()}

    nodes = []
    for tid in ids:
        r = by_id[tid]
        amt = float(r.get("credit") or r.get("debit") or 0)
        nodes.append({
            "id": tid,
            "account_no": str(r.get("account_no") or ""),
            "amount": round(amt, 2),
            "direction": "credit" if (r.get("credit") or 0) else "debit",
            "mode": r.get("mode") or "",
            "date": f"{r.get('date') or ''} {r.get('time') or ''}".strip(),
            "receiver_account": str(r.get("receiver_account") or ""),
            "sender_phone": str(r.get("sender_phone") or ""),
            "receiver_phone": str(r.get("receiver_phone") or ""),
        })

    edges = []
    for i, a in enumerate(ids):
        for j in range(i + 1, len(ids)):
            b = ids[j]
            ra, rb = by_id[a], by_id[b]
            kinds = []
            details = []
            if ra.get("receiver_account") and \
                    str(ra.get("receiver_account")) == str(rb.get("account_no")):
                kinds.append("money")
                details.append(f"₹{float(ra.get('credit') or 0):,.0f} flows {a} → {b}")
            if rb.get("receiver_account") and \
                    str(rb.get("receiver_account")) == str(ra.get("account_no")):
                kinds.append("money")
                details.append(f"₹{float(rb.get('credit') or 0):,.0f} flows {b} → {a}")
            if ra.get("account_no") and \
                    str(ra.get("account_no")) == str(rb.get("account_no")):
                kinds.append("shared")
                details.append(f"same account {ra.get('account_no')}")
            sa, sb = str(ra.get("sender_phone") or ""), str(rb.get("sender_phone") or "")
            if sa and sa == sb:
                kinds.append("shared")
                details.append(f"same phone {sa}")
            if ts_by_id[a] and ts_by_id[b] and abs(ts_by_id[a] - ts_by_id[b]) <= window_min * 60:
                kinds.append("time")
                details.append(f"within {window_min} min")
            if kinds:
                edges.append({
                    "source": a,
                    "target": b,
                    "kinds": kinds,
                    "kind": kinds[0],
                    "strength": len(kinds),
                    "window_min": window_min,
                    "details": details,
                })

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "selected": len(nodes),
            "links": len(edges),
            "money_links": sum(1 for e in edges if "money" in e["kinds"]),
            "shared_links": sum(1 for e in edges if "shared" in e["kinds"]),
            "time_links": sum(1 for e in edges if "time" in e["kinds"]),
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def quick_txn_risk(bundle: dict) -> dict:
    """Cheap per-transaction risk proxy for the heatmap/relationship UI:
    linked calls, IPDR sessions, NCRP hit, amount vs account average.
    Real hybrid scores stay on the /hybrid endpoints; this never blocks."""
    bank = bundle.get("bank", [])
    ncrp_accounts = {str(c.get("account_no") or "") for c in
                     bundle.get("complaints", [])}
    out = {}
    for r in bank:
        tid = str(r.get("txn_id") or r.get("transaction_id") or "")
        if not tid:
            continue
        amt = float(r.get("credit") or r.get("debit") or 0)
        risk = 0
        if str(r.get("account_no") or "") in ncrp_accounts:
            risk += 40
        if r.get("linked_calls"):
            risk += 20
        if r.get("linked_sessions"):
            risk += 10
        if amt >= 100000:
            risk += 15
        out[tid] = min(100, risk)
    return out
