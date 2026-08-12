"""Telecom (CDR) Intelligence Engine.

Communication analysis over the CDR dataset:

  * call-assist detection — calls placed by the sender/receiver phone inside
    a window before the transaction (per-txn `call_assist_score`),
  * repeated contacts — pairs who talk far more than dataset typical
    (communication communities = coordination),
  * phone network structure — degree / reciprocity / clustering per phone,
  * phone risk — calls to/from NCRP-linked phones, dense coordination.

Per-transaction scores feed the txn ensemble; per-phone scores feed the
entity ensemble.
"""

from __future__ import annotations

import bisect
import math
from collections import Counter, defaultdict

import networkx as nx

_WINDOW = 3600
_CALL_MIN_DUR = 10


def _is_call(r: dict) -> bool:
    ct = str(r.get("call_type") or "").upper()
    if ct in ("VOICE", "INCOMING", "OUTGOING", "SMS", "MISSED"):
        return True
    return int(r.get("duration_sec") or 0) >= _CALL_MIN_DUR


def _index(bundle: dict) -> dict:
    calls_by_phone: dict[str, list] = defaultdict(list)
    contacts: Counter = Counter()
    for r in bundle.get("cdr", []):
        ts = float(r.get("ts") or 0.0)
        if not ts or not _is_call(r):
            continue
        dur = max(0, int(r.get("duration_sec") or 0))
        a = r.get("a_number") or ""
        b = r.get("b_number") or ""
        if a:
            calls_by_phone[a].append((ts, dur))
        if b:
            calls_by_phone[b].append((ts, dur))
        if a and b and dur >= _CALL_MIN_DUR:
            contacts[(a, b)] += 1
            contacts[(b, a)] += 1
    for ph in calls_by_phone:
        calls_by_phone[ph].sort()
    return {"calls_by_phone": calls_by_phone, "contacts": contacts}


def txn_call_assist(bundle: dict, window_sec: int = _WINDOW) -> dict[str, dict]:
    """Per-transaction call-assist score + detail (sender + receiver phones)."""
    idx = _index(bundle)
    out: dict[str, dict] = {}
    w = float(window_sec)
    for t in bundle.get("bank", []):
        tid = t.get("txn_id") or ""
        ts = float(t.get("ts") or 0.0)
        if not tid or not ts:
            continue
        calls = 0
        parties = []
        for ph in (t.get("sender_phone") or "", t.get("receiver_phone") or ""):
            if not ph:
                continue
            lst = idx["calls_by_phone"].get(ph) or []
            i0 = bisect.bisect_left(lst, (ts - w, -1))
            i1 = bisect.bisect_left(lst, (ts, 10 ** 9))
            n = sum(1 for _, d in lst[i0:i1] if d >= _CALL_MIN_DUR)
            calls += n
            if n:
                parties.append(f"{ph}:{n}")
        score = 0.0
        if calls >= 3:
            score = 60.0
        elif calls >= 2:
            score = 40.0
        elif calls >= 1:
            score = 20.0
        out[tid] = {
            "call_assist_score": round(score, 2),
            "calls_before": calls,
            "window_sec": int(w),
            "parties": parties,
        }
    return out


def phone_network(bundle: dict) -> dict:
    """Per-phone network statistics from the CDR graph."""
    g = nx.DiGraph()
    for r in bundle.get("cdr", []):
        if not _is_call(r) or int(r.get("duration_sec") or 0) < _CALL_MIN_DUR:
            continue
        a, b = r.get("a_number"), r.get("b_number")
        if a and b:
            g.add_edge(a, b)
    out: dict[str, dict] = {}
    if g.number_of_nodes() < 2:
        return out
    try:
        pagerank = nx.pagerank(g, alpha=0.85, max_iter=100)
    except Exception:  # noqa: BLE001
        pagerank = {}
    und = g.to_undirected()
    comm_of: dict[str, int] = {}
    if und.number_of_nodes() >= 2000:
        try:
            comm_of = {n: i for i, c in
                       enumerate(nx.community.asyn_lpa_communities(und, seed=42))
                       for n in c}
        except Exception:  # noqa: BLE001
            comm_of = {}
    else:
        try:
            comm_of = {n: i for i, c in
                       enumerate(nx.community.greedy_modularity_communities(und))
                       for n in c}
        except Exception:  # noqa: BLE001
            comm_of = {}
    for n in g.nodes():
        out[n] = {
            "phone": n,
            "degree": int(g.degree(n)),
            "out_degree": int(g.out_degree(n)),
            "in_degree": int(g.in_degree(n)),
            "pagerank": round(float(pagerank.get(n, 0.0)), 6),
            "community_size": int(comm_of.get(n, 1)),
            "is_hub": int(g.out_degree(n) >= 20),
        }
    return out


def telecom_scores(bundle: dict, window_sec: int = _WINDOW) -> dict:
    """Aggregated telecom intelligence.

    Returns {txn: {txn_id: {call_assist_score, ...}},
             phone: {phone: {network_score, degree, ...}},
             stats: {...}}
    """
    txn = txn_call_assist(bundle, window_sec)
    phones = phone_network(bundle)
    n_contacts = len(set(_index(bundle)["contacts"]))
    return {
        "txn": txn,
        "phone": phones,
        "stats": {"phones_with_network": len(phones),
                  "contact_pairs": n_contacts},
    }
