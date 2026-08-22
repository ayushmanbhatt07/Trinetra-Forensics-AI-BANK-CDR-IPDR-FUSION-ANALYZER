"""Centralised feature library for the risk engine.

Every signal used by the ML ensemble and the graph scorer lives here so the
definitions are consistent across the codebase (they were previously
duplicated with subtle bugs in behavioural.py / ml.py / fusion.py):

  * local hour  — IST hour from the statement clock, else IST (not UTC),
  * round amount — >= Rs 1000 and a multiple of 5000,
  * proper median — mean of the two middle values (not upper-middle),
  * day granularity — whether timestamps carry HH:MM precision at all,
  * account feature matrix — aggregation of bundle["bank"] per account,
  * transaction feature matrix — per-transaction vectors for txn-level ML.
"""

from __future__ import annotations

import bisect
import datetime as _dt
import statistics
from collections import Counter, defaultdict

import numpy as np

_IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
_ROUND_FLOOR = 1000.0
_ROUND_STEP = 5000.0
_BURST_WINDOW = 1800.0


def local_hour(rec: dict) -> int:
    """Hour of a record in stated local time (IST), or -1 when unknown."""
    hh = str(rec.get("time") or "")
    if len(hh) >= 2 and hh[:2].isdigit():
        return int(hh[:2])
    ts = float(rec.get("ts") or 0.0)
    if not ts:
        return -1
    return _dt.datetime.fromtimestamp(ts, _IST).hour


def ts_day(ts: float) -> str:
    """IST calendar day for a unix timestamp (matches statement `date`)."""
    if not ts:
        return ""
    return _dt.datetime.fromtimestamp(ts, _IST).strftime("%Y-%m-%d")


def is_odd_hour(rec: dict) -> bool:
    h = local_hour(rec)
    return 0 <= h != -1 and (h >= 22 or h < 6)


def is_round_amount(amount: float) -> bool:
    return amount >= _ROUND_FLOOR and amount % _ROUND_STEP == 0


def proper_median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def day_granular(bank: list[dict]) -> bool:
    """True when fewer than half the records carry HH:MM clock time."""
    if not bank:
        return False
    with_time = sum(1 for r in bank if (str(r.get("time") or "")[:2]).isdigit())
    return with_time / len(bank) < 0.5


def txn_amount(r: dict) -> float:
    return float(r.get("debit") or r.get("credit") or 0.0)


def prior_transaction_ids(rows: list[dict]) -> dict[str, int]:
    """txn_id -> number of earlier transactions for the same customer."""
    out: dict[str, int] = {}
    seen: dict[str, int] = {}
    for r in rows:
        cust = r.get("customer_id") or r.get("account_no") or ""
        tid = r.get("txn_id") or ""
        if tid:
            out[tid] = seen.get(cust, 0)
        seen[cust] = seen.get(cust, 0) + 1
    return out


def _round_share(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if is_round_amount(txn_amount(r))) / len(rows)


def _night_share(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if is_odd_hour(r)) / len(rows)


def _credit_debit_split(rows: list[dict]) -> tuple[float, float]:
    cred = sum(float(r.get("credit") or 0.0) for r in rows)
    deb = sum(float(r.get("debit") or 0.0) for r in rows)
    return cred, deb


ACCOUNT_FEATURES = (
    "txn_count", "total_credit", "total_debit", "avg_amount", "max_amount",
    "p99_amount", "std_amount", "uniq_counterparties", "uniq_phones",
    "uniq_upi", "round_share", "night_share", "credit_share",
    "max_daily_count", "avg_daily_count", "new_beneficiary_share",
    "call_linkage_share", "ipdr_linkage_share", "midnight_spike",
    "max_single_burst",
)


def account_features(bundle: dict) -> list[dict]:
    """Per-account feature matrix over the bank ledger.

    Fixes over the previous ml.py implementation: night share uses the real
    IST hour (22:00-06:00, matching behavioural.py), round share uses the
    shared round-amount definition, and new cross-domain features
    (call/IPDR linkage, daily-velocity, burst) are included.
    """
    bank = bundle.get("bank", [])
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])
    calls_by_phone: dict[str, int] = defaultdict(int)
    for c in cdr:
        ph = c.get("a_number") or ""
        if ph and int(c.get("duration_sec") or 0) >= 20:
            calls_by_phone[ph] += 1
    sessions_by_phone: dict[str, int] = defaultdict(int)
    for i in ipdr:
        ph = i.get("msisdn") or ""
        if ph:
            sessions_by_phone[ph] += 1

    rows: list[dict] = []
    by_acc: dict[str, list[dict]] = defaultdict(list)
    for r in bank:
        acc = r.get("account_no") or ""
        if acc:
            by_acc[acc].append(r)

    for acc, rows_acc in sorted(by_acc.items()):
        amounts = [txn_amount(r) for r in rows_acc]
        n = max(1, len(rows_acc))
        cred, deb = _credit_debit_split(rows_acc)
        counterparties = {r.get("receiver_account") for r in rows_acc
                          if r.get("receiver_account")}
        phones = {p for r in rows_acc for p in
                  (r.get("receiver_phone"), r.get("sender_phone"))
                  if p}
        upis = {r.get("upi_id") for r in rows_acc if r.get("upi_id")}

        daily: Counter = Counter()
        days_by_cust: dict[str, Counter] = defaultdict(Counter)
        per_phone_calls = 0
        per_phone_sessions = 0
        for r in rows_acc:
            day = r.get("date") or ts_day(float(r.get("ts") or 0.0))
            if day:
                daily[day] += 1
            cust = r.get("customer_id") or acc
            if day:
                days_by_cust[cust][day] += 1
            for ph in (r.get("sender_phone"), r.get("receiver_phone")):
                if not ph:
                    continue
                per_phone_calls += calls_by_phone.get(ph, 0)
                per_phone_sessions += sessions_by_phone.get(ph, 0)

        prior_ben: set[str] = set()
        new_ben = 0
        for r in sorted(rows_acc, key=lambda x: float(x.get("ts") or 0.0)):
            recv = r.get("receiver_account") or ""
            if recv:
                if recv not in prior_ben:
                    new_ben += 1
                prior_ben.add(recv)
        new_ben_share = (new_ben / n) if n else 0.0

        times = sorted(float(r.get("ts") or 0.0) for r in rows_acc
                       if r.get("ts"))
        max_burst = 0
        if times:
            for i, ts in enumerate(times):
                j = i
                while j + 1 < len(times) and times[j + 1] - ts <= 1800:
                    j += 1
                max_burst = max(max_burst, j - i + 1)

        max_daily = max(daily.values()) if daily else 0
        daily_counts = [count for cust in days_by_cust
                        for count in days_by_cust[cust].values()]
        avg_daily = sum(daily_counts) / len(daily_counts) if daily_counts else 0.0
        midnight = sum(1 for r in rows_acc if local_hour(r) in (0, 1, 2, 3))

        arr = np.array(amounts, dtype=float)
        rows.append({
            "account_no": acc,
            "txn_count": n,
            "total_credit": round(cred, 2),
            "total_debit": round(deb, 2),
            "avg_amount": round(float(arr.mean()), 2),
            "max_amount": round(float(arr.max()), 2) if len(arr) else 0.0,
            "p99_amount": round(float(np.percentile(arr, 99)), 2)
                          if len(arr) else 0.0,
            "std_amount": round(float(arr.std()), 2) if len(arr) else 0.0,
            "uniq_counterparties": len(counterparties),
            "uniq_phones": len(phones),
            "uniq_upi": len(upis),
            "round_share": round(_round_share(rows_acc), 4),
            "night_share": round(_night_share(rows_acc), 4),
            "credit_share": round(cred / (cred + deb), 4)
                            if (cred + deb) else 0.5,
            "max_daily_count": max_daily,
            "avg_daily_count": round(avg_daily, 3),
            "new_beneficiary_share": round(new_ben_share, 4),
            "call_linkage_share": round(per_phone_calls / n, 4),
            "ipdr_linkage_share": round(per_phone_sessions / n, 4),
            "midnight_spike": midnight,
            "max_single_burst": max_burst,
        })
    return rows


def _feature_matrix(rows: list[dict]) -> np.ndarray:
    return np.array([[float(r[f]) for f in ACCOUNT_FEATURES]
                     for r in rows], dtype=float)


def account_feature_matrix(bundle: dict) -> tuple[list[dict], np.ndarray]:
    rows = account_features(bundle)
    if not rows:
        return [], np.zeros((0, len(ACCOUNT_FEATURES)))
    return rows, _feature_matrix(rows)


def _safe_log1p(matrix: np.ndarray) -> np.ndarray:
    return np.log1p(np.abs(matrix))


# ---------------------------------------------------------------- txn level

_CALL_MIN_DUR = 10
_VOICE_TYPES = ("VOICE", "INCOMING", "OUTGOING")

TXN_FEATURES = (
    "log_amount", "log_ratio", "hour_dev", "round_flag", "burst_count",
    "new_beneficiary", "call_count", "ipdr_sessions", "novel_imei",
    "novel_cell", "prior_n", "night_flag",
)


def _is_call_record(r: dict) -> bool:
    ct = str(r.get("call_type") or "").upper()
    if ct in _VOICE_TYPES:
        return True
    return int(r.get("duration_sec") or 0) >= _CALL_MIN_DUR


def transaction_features(bundle: dict) -> tuple[list[dict], np.ndarray]:
    """Per-transaction feature matrix for txn-level anomaly scoring."""
    bank = bundle.get("bank", [])
    if not bank:
        return [], np.zeros((0, len(TXN_FEATURES)))
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])

    by_cust: dict[str, list[dict]] = defaultdict(list)
    for r in bank:
        by_cust[r.get("customer_id") or r.get("account_no") or ""].append(r)
    medians: dict[str, float] = {}
    hour_modes: dict[str, int | None] = {}
    times_by_cust: dict[str, list[float]] = {}
    for cust, rows in by_cust.items():
        amts = [txn_amount(r) for r in rows]
        medians[cust] = proper_median(amts) if amts else 0.0
        hc: Counter = Counter(local_hour(r) for r in rows if local_hour(r) >= 0)
        hour_modes[cust] = hc.most_common(1)[0][0] if hc else None
        t = [float(x.get("ts") or 0.0) for x in rows]
        t.sort()
        times_by_cust[cust] = t

    calls_by_phone: dict[str, list[float]] = defaultdict(list)
    for c in cdr:
        if not float(c.get("ts") or 0.0) or not _is_call_record(c):
            continue
        for ph in (c.get("a_number") or "", c.get("b_number") or ""):
            if ph:
                calls_by_phone[ph].append(float(c["ts"]))
    for ph in calls_by_phone:
        calls_by_phone[ph].sort()

    sess_by_phone: dict[str, list[float]] = defaultdict(list)
    for i in ipdr:
        ph = i.get("msisdn") or ""
        ts = float(i.get("start_ts") or 0.0)
        if ph and ts:
            sess_by_phone[ph].append(ts)
    for ph in sess_by_phone:
        sess_by_phone[ph].sort()

    imei_by_phone: dict[str, list[tuple]] = defaultdict(list)
    for c in cdr:
        ph = c.get("a_number") or ""
        if ph and c.get("imei"):
            imei_by_phone[ph].append((float(c.get("ts") or 0.0), c["imei"]))
    for ph in imei_by_phone:
        imei_by_phone[ph].sort(key=lambda x: x[0])

    cell_by_phone: dict[str, list[tuple]] = defaultdict(list)
    for c in cdr:
        ph = c.get("a_number") or ""
        cell = c.get("bts_location_first") or c.get("cell_id_first")
        if ph and cell:
            cell_by_phone[ph].append((float(c.get("ts") or 0.0), cell))
    for ph in cell_by_phone:
        cell_by_phone[ph].sort(key=lambda x: x[0])

    first_seen_imei: dict[str, dict[str, float]] = defaultdict(dict)
    for ph, hist in imei_by_phone.items():
        for t, im in hist:
            if im not in first_seen_imei[ph]:
                first_seen_imei[ph][im] = t

    first_seen_cell: dict[str, dict[str, float]] = defaultdict(dict)
    for ph, hist in cell_by_phone.items():
        for t, cl in hist:
            if cl not in first_seen_cell[ph]:
                first_seen_cell[ph][cl] = t

    prior_n: dict[str, int] = {}
    for cust, rows in by_cust.items():
        rows.sort(key=lambda x: float(x.get("ts") or 0.0))
        seen: set = set()
        for i, r in enumerate(rows):
            tid = r.get("txn_id") or ""
            prior_n[tid] = i
            recv = r.get("receiver_account") or ""
            if recv:
                seen.add(recv)

    rows_out: list[dict] = []
    for r in bank:
        tid = r.get("txn_id") or ""
        cust = r.get("customer_id") or r.get("account_no") or ""
        amt = txn_amount(r)
        ts = float(r.get("ts") or 0.0)
        phone = r.get("sender_phone") or ""
        recv = r.get("receiver_account") or ""
        base = medians.get(cust) or 0.0
        ratio = (amt / base) if base > 0 else 0.0
        h = local_hour(r)
        mode = hour_modes.get(cust)
        hdev = abs(h - mode) if (h >= 0 and mode is not None) else -1.0
        pn = prior_n.get(tid, 0)
        burst = 0
        times = times_by_cust.get(cust, [])
        if ts:
            burst = (bisect.bisect_right(times, ts + _BURST_WINDOW)
                     - bisect.bisect_left(times, ts - _BURST_WINDOW))
        calls = 0
        if ts:
            for ph in (phone, r.get("receiver_phone") or ""):
                if not ph:
                    continue
                lst = calls_by_phone.get(ph) or []
                calls += (bisect.bisect_left(lst, ts)
                          - bisect.bisect_left(lst, ts - 3600))
        sess = 0
        if ts and phone:
            lst = sess_by_phone.get(phone) or []
            sess = (bisect.bisect_right(lst, ts + 1800)
                    - bisect.bisect_left(lst, ts - 1800))
        novel_imei = 0
        if ts and phone:
            hist = imei_by_phone.get(phone) or []
            if hist:
                i_prior = bisect.bisect_left(hist, (ts, ""))
                imei_lookup = first_seen_imei.get(phone, {})
                for t, v in hist[i_prior:]:
                    if t >= ts + 3600:
                        break
                    if imei_lookup.get(v, 0.0) >= ts:
                        novel_imei = 1
                        break
        novel_cell = 0
        if ts and phone:
            hist = cell_by_phone.get(phone) or []
            if hist:
                i_prior = bisect.bisect_left(hist, (ts, ""))
                cell_lookup = first_seen_cell.get(phone, {})
                for t, v in hist[i_prior:]:
                    if t >= ts + 3600:
                        break
                    if cell_lookup.get(v, 0.0) >= ts:
                        novel_cell = 1
                        break
        rows_out.append({
            "txn_id": tid,
            "log_amount": float(np.log1p(amt)),
            "log_ratio": float(np.log1p(max(ratio, 0.0))),
            "hour_dev": hdev,
            "round_flag": 1.0 if is_round_amount(amt) else 0.0,
            "burst_count": float(burst),
            "new_beneficiary": 0.0,
            "call_count": float(calls),
            "ipdr_sessions": float(sess),
            "novel_imei": float(novel_imei),
            "novel_cell": float(novel_cell),
            "prior_n": float(pn),
            "night_flag": 1.0 if is_odd_hour(r) else 0.0,
        })
    if not rows_out:
        return [], np.zeros((0, len(TXN_FEATURES)))
    mat = np.array([[float(r[f]) for f in TXN_FEATURES] for r in rows_out])
    return rows_out, mat


def txn_ml_scores(bundle: dict, cap_z: float = 8.0) -> dict[str, float]:
    """Per-txn 0-100 ML score from the extreme-feature magnitude.

    z-magnitude scale (absolute, not rank): z=2 -> 0, z=3 -> ~17, z=5 -> 50,
    z=8 -> 100.  Only genuinely extreme transactions score high enough to
    lift the composite past the alert thresholds.
    """
    rows, mat = transaction_features(bundle)
    if len(rows) < 2:
        return {}
    std = mat.std(axis=0)
    std[std == 0] = 1.0
    z = np.abs((mat - np.nanmean(mat, axis=0)) / std)
    z = np.nan_to_num(z, nan=0.0)
    z = np.minimum(z, cap_z)
    magnitude = np.clip((z.max(axis=1) - 2.0) * (100.0 / 6.0), 0.0, 100.0)
    magnitude = np.nan_to_num(magnitude, nan=0.0)
    return {r["txn_id"]: round(float(magnitude[i]), 2)
            for i, r in enumerate(rows) if r["txn_id"]}
