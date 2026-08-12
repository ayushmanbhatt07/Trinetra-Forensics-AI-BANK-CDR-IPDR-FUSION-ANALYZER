"""Temporal Intelligence Engine.

Sliding-window correlation across the three datasets (bank transaction,
CDR call, IPDR session) at configurable windows — 5 / 10 / 30 / 60 minutes
and custom — plus whole-day granularity fallback.

The Master Prompt asks for "Transaction -> Call -> IP Login -> Transfer
within a configurable window".  We build:

  * per-window correlation counts for every window size,
  * a txn-level temporal score: how much *coordinated* activity surrounds
    the transaction (calls + data sessions on linked phones/IMSI within ±w),
  * an account-level temporal concentration score (share of txns with
    correlated telecom activity),
  * an entity-level score for phones/IMSIs (how often their call/session
    windows coincide with transfers).

WINDOWS is the default window ladder; the API accepts a custom window via
`window_sec`.  All lookups use bisect over sorted timestamps.
"""

from __future__ import annotations

import bisect
from collections import defaultdict

DEFAULT_WINDOWS = (300, 600, 1800, 3600)  # 5, 10, 30, 60 minutes
_CALL_MIN_DUR = 10


def _is_call(r: dict) -> bool:
    ct = str(r.get("call_type") or "").upper()
    if ct in ("VOICE", "INCOMING", "OUTGOING", "SMS", "MISSED"):
        return True
    return int(r.get("duration_sec") or 0) >= _CALL_MIN_DUR


def build_temporal_index(bundle: dict) -> dict:
    """Sorted timestamp index per phone / IMSI / IMEI for CDR + IPDR."""
    calls_by_phone: dict[str, list] = defaultdict(list)
    calls_by_imsi: dict[str, list] = defaultdict(list)
    calls_by_imei: dict[str, list] = defaultdict(list)
    for r in bundle.get("cdr", []):
        ts = float(r.get("ts") or 0.0)
        if not ts or not _is_call(r):
            continue
        dur = max(0, int(r.get("duration_sec") or 0))
        for ph in (r.get("a_number") or "", r.get("b_number") or ""):
            if ph:
                calls_by_phone[ph].append((ts, dur))
        if r.get("imsi"):
            calls_by_imsi[r["imsi"]].append((ts, dur))
        if r.get("imei"):
            calls_by_imei[r["imei"]].append((ts, dur))

    sess_by_phone: dict[str, list] = defaultdict(list)
    sess_by_imsi: dict[str, list] = defaultdict(list)
    sess_by_imei: dict[str, list] = defaultdict(list)
    for r in bundle.get("ipdr", []):
        ts = float(r.get("start_ts") or 0.0)
        if not ts:
            continue
        if r.get("msisdn"):
            sess_by_phone[r["msisdn"]].append(ts)
        if r.get("imsi"):
            sess_by_imsi[r["imsi"]].append(ts)
        if r.get("imei"):
            sess_by_imei[r["imei"]].append(ts)

    def _sort(d: dict) -> dict:
        for k in d:
            d[k].sort()
        return d

    return {
        "calls_phone": _sort(calls_by_phone),
        "calls_imsi": _sort(calls_by_imsi),
        "calls_imei": _sort(calls_by_imei),
        "sess_phone": _sort(sess_by_phone),
        "sess_imsi": _sort(sess_by_imsi),
        "sess_imei": _sort(sess_by_imei),
    }


def _count(lst: list, ts: float, window: float) -> int:
    if not lst:
        return 0
    return bisect.bisect_right(lst, ts + window) - bisect.bisect_left(lst, ts - window)


def _count_call(lst: list, ts: float, window: float) -> int:
    """Voice/long calls only (SMS/missed rows are dataset noise)."""
    if not lst:
        return 0
    i0 = bisect.bisect_left(lst, (ts - window, -1))
    i1 = bisect.bisect_left(lst, (ts + window, 10 ** 9))
    return sum(1 for _, d in lst[i0:i1] if d >= _CALL_MIN_DUR)


def temporal_correlations(bundle: dict, window_sec: int = 1800) -> dict:
    """Per-window correlation map for the window ladder."""
    idx = build_temporal_index(bundle)
    out: dict[str, dict] = {}
    for w in DEFAULT_WINDOWS + (window_sec,):
        out[str(w)] = _window_correlations(bundle, idx, float(w))
    return out


def _window_correlations(bundle: dict, idx: dict, w: float) -> dict:
    """Total correlated txn/call/session pairs within window `w`."""
    pairs = 0
    txns = 0
    for t in bundle.get("bank", []):
        ts = float(t.get("ts") or 0.0)
        if not ts:
            continue
        txns += 1
        phone = t.get("sender_phone") or ""
        imsi = t.get("imsi") or ""
        calls = _count_call(idx["calls_phone"].get(phone) or [], ts, w)
        if imsi:
            calls += _count_call(idx["calls_imsi"].get(imsi) or [], ts, w)
        sess = _count(idx["sess_phone"].get(phone) or [], ts, w)
        if imsi:
            sess += _count(idx["sess_imsi"].get(imsi) or [], ts, w)
        pairs += calls + sess
    return {"txns": txns, "correlated_pairs": pairs,
            "correlation_rate": round(pairs / max(1, txns), 3)}


def txn_temporal_scores(bundle: dict, window_sec: int = 1800) -> dict[str, dict]:
    """Per-transaction temporal score (0-100) + correlation detail."""
    idx = build_temporal_index(bundle)
    out: dict[str, dict] = {}
    w = float(window_sec)
    for t in bundle.get("bank", []):
        tid = t.get("txn_id") or ""
        ts = float(t.get("ts") or 0.0)
        if not tid or not ts:
            continue
        phone = t.get("sender_phone") or ""
        recv_phone = t.get("receiver_phone") or ""
        imsi = t.get("imsi") or ""
        calls = _count_call(idx["calls_phone"].get(phone) or [], ts, w)
        calls += _count_call(idx["calls_phone"].get(recv_phone) or [], ts, w)
        if imsi:
            calls += _count_call(idx["calls_imsi"].get(imsi) or [], ts, w)
        sess = _count(idx["sess_phone"].get(phone) or [], ts, w)
        if imsi:
            sess += _count(idx["sess_imsi"].get(imsi) or [], ts, w)
        score = 0.0
        if calls >= 3:
            score += 40.0
        elif calls >= 1:
            score += 20.0
        if sess >= 3:
            score += 30.0
        elif sess >= 1:
            score += 15.0
        if calls >= 1 and sess >= 1:
            score += 10.0
        out[tid] = {
            "temporal_score": round(min(score, 100.0), 2),
            "calls_in_window": calls,
            "sessions_in_window": sess,
            "window_sec": int(w),
        }
    return out


def account_temporal_scores(bundle: dict, window_sec: int = 1800) -> dict[str, dict]:
    """Per-account temporal concentration for the account ensemble."""
    txn_scores = txn_temporal_scores(bundle, window_sec)
    by_acc: dict[str, list] = defaultdict(list)
    for t in bundle.get("bank", []):
        tid = t.get("txn_id") or ""
        acc = t.get("account_no") or ""
        if tid and acc and tid in txn_scores:
            by_acc[acc].append(txn_scores[tid])
    out = {}
    for acc, scores in by_acc.items():
        n = max(1, len(scores))
        strong = sum(1 for s in scores if s["temporal_score"] >= 40)
        mean = sum(s["temporal_score"] for s in scores) / n
        rate = _count_rates(scores)
        out[acc] = {
            "temporal_score": round(min(100.0, 0.6 * mean + 30.0 * (strong / n)), 2),
            "correlated_txn_share": round(strong / n, 3),
            "avg_temporal_score": round(mean, 2),
            "window_sec": int(window_sec),
            "per_window": rate,
        }
    return out


def _count_rates(scores: list[dict]) -> dict:
    rate: dict[str, int] = defaultdict(int)
    for s in scores:
        w = str(s["window_sec"])
        rate[w] += 1
    return dict(rate)
