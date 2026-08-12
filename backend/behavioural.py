"""Transaction-level behavioural anomaly scoring.

fraud_heat() scores accounts/phones with coarse static rules; the synthetic
problem-statement dataset plants *transaction-level* anomalies (odd-hour
activity, customer-relative amount spikes, velocity bursts, novel
beneficiaries, call/network/device context around transfers).  This module
scores every bank transaction against per-customer baselines and fused
telecom context so the anomaly feed surfaces the actual suspicious
transactions.

Signal catalogue (each contributes +points, capped at 100):

  BANK_ONLY
    ODD_HOUR_TRANSACTION           10-30  txn between 22:00 and 06:00 (local)
    CUSTOMER_HOUR_DEVIATION        10-20  txn hour far from customer's usual
    CUSTOMER_RELATIVE_AMOUNT_SPIKE 15-40 amount vs the customer's own median
    AMOUNT_VELOCITY_SPIKE          20-50 burst of txns +/- 30 min around txn
    NEW_BENEFICIARY                10-25 receiver account never paid before
    ROUND_AMOUNT                   10   structuring-style round payout

  BANK+CDR
    UNUSUAL_CALL_BEFORE_TRANSACTION   15-30  call <= 60 min before txn
    REPEATED_CALLS_BEFORE_TRANSACTION 25-40  3+ calls in that window
    CALL_THEN_NEW_BENEFICIARY         20   call + first-time beneficiary
    CALL_THEN_HIGH_VALUE_TRANSFER     25   call + amount spike

  BANK+CDR+IPDR
    NETWORK_SESSION_BURST_AROUND_TRANSACTION 15  3+ data sessions +/- 30 min
    NEW_DEVICE_AROUND_TRANSACTION             20  IMEI not seen before for phone
    UNUSUAL_LOCATION_CONTEXT                  20  BTS cell differs from usual
    IMSI_IMEI_PAIR_NOVELTY                    20  (IMSI, IMEI) pair is new
"""

from __future__ import annotations

import bisect
import datetime as _dt
from collections import Counter, defaultdict

_CALL_WINDOW = 3600      # seconds before the txn
_IPDR_WINDOW = 1800      # seconds around the txn
_BURST_WINDOW = 1800     # 30-minute symmetric velocity window
_BURST_HARD, _BURST_SOFT = 6, 4

_CALL_MIN_DUR = 10       # seconds (calls shorter than this are ignored)
_VOICE_TYPES = ("VOICE", "INCOMING", "OUTGOING", "MISSED", "SMS")


_IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))


def _is_call(r: dict) -> bool:
    """A CDR record counts as a call for behavioural context: voice-type rows
    (incl. SMS/missed, which synthetic generators use as anomaly markers) or
    rows lasting at least `_CALL_MIN_DUR` seconds."""
    ct = str(r.get("call_type") or "").upper()
    if ct in _VOICE_TYPES:
        return True
    return int(r.get("duration_sec") or 0) >= _CALL_MIN_DUR


def _ts_day(ts: float) -> str:
    """Local (IST) calendar day of a unix timestamp — matches bank `date`."""
    return _dt.datetime.fromtimestamp(ts, _IST).strftime("%Y-%m-%d")


def _local_hour(t: dict) -> int:
    """Hour of the transaction in the stated local time (or IST fallback)."""
    hh = (t.get("time") or "")
    if len(hh) >= 2 and hh[:2].isdigit():
        return int(hh[:2])
    ts = float(t.get("ts") or 0.0)
    return _dt.datetime.fromtimestamp(ts, _IST).hour if ts else -1


def _median(amts: list[float]) -> float:
    n = len(amts)
    if n == 0:
        return 0.0
    amts = sorted(amts)
    return amts[n // 2]


def _build_global_ctx(bundle: dict) -> dict:
    """Dataset-level context shared by all per-transaction scores."""
    bank = bundle.get("bank", [])
    cdr = bundle.get("cdr", [])
    ipdr = bundle.get("ipdr", [])

    # Per-customer history: amounts, timestamps, beneficiaries — prior only.
    medians: dict[str, float] = {}
    prior_txns: dict[str, int] = {}
    prior_beneficiaries: dict[str, frozenset] = {}
    customer_times: dict[str, list] = {}
    orders: dict[str, list] = {}

    for cust, rows in _group_by_customer(bank).items():
        rows.sort(key=lambda r: float(r.get("ts") or 0.0))
        times: list[float] = []
        prior: set = set()
        for i, t in enumerate(rows):
            tid = t.get("txn_id") or ""
            prior_beneficiaries[tid] = frozenset(prior)
            prior_txns[tid] = i
            times.append(float(t.get("ts") or 0.0))
            recv = t.get("receiver_account") or ""
            if recv:
                prior.add(recv)
            amt = float(t.get("debit") or t.get("credit") or 0.0)
            medians.setdefault(cust, []).append(amt)
        customer_times[cust] = times
        orders[cust] = [r.get("txn_id") or "" for r in rows]
    for cust in medians:
        medians[cust] = _median(medians[cust])

    calls_by_phone: dict[str, list] = {}
    ipdr_by_phone: dict[str, list] = {}
    imei_by_phone: dict[str, list] = {}
    ipdr_imei_by_phone: dict[str, list] = {}
    pair_by_phone: dict[str, list] = {}
    ipdr_pair_by_phone: dict[str, list] = {}
    cell_by_phone: dict[str, list] = {}

    for r in cdr:
        ts = float(r.get("ts") or 0.0)
        if not ts:
            continue
        a_phone = r.get("a_number") or ""
        if a_phone:
            if r.get("imei"):
                imei_by_phone.setdefault(a_phone, []).append((ts, r["imei"]))
            if r.get("imsi") and r.get("imei"):
                pair_by_phone.setdefault(a_phone, []).append(
                    (ts, (r["imsi"], r["imei"])))
            if r.get("bts_location_first") or r.get("cell_id_first"):
                cell_by_phone.setdefault(a_phone, []).append(
                    (ts, r.get("bts_location_first") or r.get("cell_id_first")))
        if _is_call(r):
            dur = max(0, int(r.get("duration_sec") or 0))
            voice = str(r.get("call_type") or "").upper() in _VOICE_TYPES
            for phone in (a_phone, r.get("b_number") or ""):
                if phone:
                    calls_by_phone.setdefault(phone, []).append((ts, dur, voice))
    for phone in calls_by_phone:
        calls_by_phone[phone].sort()
    for phone in imei_by_phone:
        imei_by_phone[phone].sort(key=lambda x: x[0])
    for phone in pair_by_phone:
        pair_by_phone[phone].sort(key=lambda x: x[0])
    for phone in cell_by_phone:
        cell_by_phone[phone].sort(key=lambda x: x[0])

    for r in ipdr:
        phone = r.get("msisdn") or ""
        ts = float(r.get("start_ts") or 0.0)
        if not phone or not ts:
            continue
        ipdr_by_phone.setdefault(phone, []).append(ts)
        if r.get("imei"):
            ipdr_imei_by_phone.setdefault(phone, []).append((ts, r["imei"]))
        if r.get("imsi") and r.get("imei"):
            ipdr_pair_by_phone.setdefault(phone, []).append(
                (ts, (r["imsi"], r["imei"])))
    for phone in ipdr_by_phone:
        ipdr_by_phone[phone].sort()
    for phone in ipdr_imei_by_phone:
        ipdr_imei_by_phone[phone].sort(key=lambda x: x[0])
    for phone in ipdr_pair_by_phone:
        ipdr_pair_by_phone[phone].sort(key=lambda x: x[0])

    ctx = {
        "medians": medians, "customer_times": customer_times,
        "prior_txns": prior_txns,
        "prior_beneficiaries": prior_beneficiaries,
        "calls_by_phone": calls_by_phone, "ipdr_by_phone": ipdr_by_phone,
        "imei_by_phone": imei_by_phone, "pair_by_phone": pair_by_phone,
        "ipdr_imei_by_phone": ipdr_imei_by_phone,
        "ipdr_pair_by_phone": ipdr_pair_by_phone,
        "cell_by_phone": cell_by_phone,
        "hour_modes": _customer_hour_modes(bank),
        "day_granular": _day_granular(bank),
        "imei_global": Counter(r["imei"] for r in cdr + ipdr
                               if r.get("imei")),
        "cell_global": Counter(
            r.get("bts_location_first") or r.get("cell_id_first") or ""
            for r in cdr if r.get("bts_location_first")
            or r.get("cell_id_first")),
    }
    if ctx["day_granular"]:
        ctx["daily_counts"], ctx["daily_medians"] = _daily_rates(bank)
    ctx.update(_rule_activations(bank, ctx))
    return ctx


def score_transactions(bundle: dict) -> list[dict]:
    """Behavioural risk score for every bank transaction (desc by score)."""
    bank = bundle.get("bank", [])
    if not bank:
        return []
    ctx = _build_global_ctx(bundle)

    scored = [_score_transaction(t, ctx) for t in bank]
    scored.sort(key=lambda x: -x["risk_score"])
    return scored


# A rule family is only informative if it fires on a minority of the dataset.
# Some synthetic generators produce a uniformly-random background (odd hours,
# fresh receivers and calls around transfers are the *norm*), where these
# rules are mostly noise.  Rather than hard-disabling a family above a noise
# ceiling (which cancels genuine detections the moment a signal becomes
# prevalent), the family's points are down-weighted gradually: a family that
# fires on `p` of the dataset keeps a weight of `max(0.2, (1-p)/(1-ceiling))`,
# so rare signals score full points while ubiquitous ones degrade gracefully.
_RULE_NOISE_CEILING = 0.25


def _family_weight(prevalence: float) -> float:
    if prevalence <= _RULE_NOISE_CEILING:
        return 1.0
    return max(0.2, (1.0 - prevalence) / (1.0 - _RULE_NOISE_CEILING))


def _rule_activations(bank: list[dict], ctx: dict) -> dict:
    n = max(1, len(bank))
    odd = new_ben = hour_dev = 0
    modes = ctx.get("hour_modes", {})
    for t in bank:
        if 0 <= _local_hour(t) != -1 and (_local_hour(t) >= 22 or _local_hour(t) < 6):
            odd += 1
        recv = t.get("receiver_account") or ""
        tid = t.get("txn_id") or ""
        prior_n = ctx["prior_txns"].get(tid, 0)
        if recv and prior_n >= 1 and recv not in ctx["prior_beneficiaries"].get(tid, frozenset()):
            new_ben += 1
        h = _local_hour(t)
        mode = modes.get(t.get("customer_id") or t.get("account_no") or "")
        if h >= 0 and mode is not None and prior_n >= 1 \
                and abs(h - mode) >= 6:
            hour_dev += 1
    with_phone = 0
    call_near = sess_near = 0
    for t in bank:
        phone = t.get("sender_phone") or ""
        ts = float(t.get("ts") or 0.0)
        if not phone or not ts:
            continue
        with_phone += 1
        got_call = False
        for ph in (phone, t.get("receiver_phone") or ""):
            if not ph:
                continue
            lst = ctx["calls_by_phone"].get(ph) or []
            i0 = bisect.bisect_left(lst, (ts - _CALL_WINDOW, -1))
            i1 = bisect.bisect_left(lst, (ts, 0))
            # prevalence uses voice/long rows only: SMS/missed rows are dense
            # dataset noise and must not depress the family weight
            if any(d >= _CALL_MIN_DUR for _, d, _v in lst[i0:i1]):
                got_call = True
                break
        if got_call:
            call_near += 1
        lst = ctx["ipdr_by_phone"].get(phone) or []
        if bisect.bisect_right(lst, ts + _IPDR_WINDOW) - \
                bisect.bisect_left(lst, ts - _IPDR_WINDOW) >= 1:
            sess_near += 1
    return {
        "w_odd_hour": _family_weight(odd / n),
        "w_new_beneficiary": _family_weight(new_ben / n),
        "w_calls": _family_weight(call_near / n) if n else 1.0,
        "w_network": _family_weight(sess_near / n) if n else 1.0,
        "w_hour_dev": _family_weight(hour_dev / n) if n else 1.0,
    }


def _customer_hour_modes(bank: list[dict]) -> dict[str, int | None]:
    """Most frequent local hour per customer (None when no clock times)."""
    counts: dict[str, Counter] = defaultdict(Counter)
    for t in bank:
        h = _local_hour(t)
        if h >= 0:
            counts[t.get("customer_id") or t.get("account_no") or ""][h] += 1
    return {c: (ctr.most_common(1)[0][0] if ctr else None)
            for c, ctr in counts.items()}


def _day_granular(bank: list[dict]) -> bool:
    """True when timestamps carry day precision only (no HH:MM in the data),
    so sub-hour windows (velocity bursts, call/network windows) are not
    meaningful and must fall back to day-level rules."""
    if not bank:
        return False
    with_time = sum(
        1 for t in bank if (t.get("time") or "")[:2].isdigit())
    return with_time / len(bank) < 0.5


def _daily_rates(bank: list[dict]) -> tuple[dict, dict]:
    """Per-customer daily txn counts and their medians (day-granular data)."""
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for t in bank:
        cust = t.get("customer_id") or t.get("account_no") or ""
        day = t.get("date") or ""
        if cust and day:
            counts[cust][day] = counts[cust].get(day, 0) + 1
    medians = {
        cust: _median(list(days.values()))
        for cust, days in counts.items()
    }
    return counts, medians


def _group_by_customer(bank: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for t in bank:
        cust = t.get("customer_id") or t.get("account_no") or ""
        if cust:
            groups.setdefault(cust, []).append(t)
    return groups


def _score_transaction(t: dict, ctx: dict) -> dict:
    score, flags, breakdown, evidence = 0, [], [], []
    amt = float(t.get("debit") or t.get("credit") or 0.0)
    ts = float(t.get("ts") or 0.0)
    tid = t.get("txn_id") or ""
    cust = t.get("customer_id") or t.get("account_no") or ""
    phone = t.get("sender_phone") or ""
    recv = t.get("receiver_account") or ""

    def add(code: str, points: int, reason: str, ev: str | None = None,
            weight: float = 1.0) -> None:
        nonlocal score
        score = min(score + points * weight, 100)
        flags.append(code)
        breakdown.append({"rule": code, "points": points, "weight": round(weight, 2),
                          "reason": reason})
        if ev:
            evidence.append(ev)

    # ---------------- BANK_ONLY ----------------
    prior_n = ctx["prior_txns"].get(tid, 0)
    h = _local_hour(t)
    w_odd = ctx["w_odd_hour"]
    if w_odd > 0 and (h >= 22 or h < 6):
        add("ODD_HOUR_TRANSACTION", 30 if prior_n >= 3 else 10,
            f"Transaction at {h:02d}:00 — outside normal banking hours",
            weight=w_odd)

    w_hdev = ctx["w_hour_dev"]
    mode = ctx["hour_modes"].get(cust)
    if (w_hdev > 0 and h >= 0 and mode is not None
            and prior_n >= 1 and abs(h - mode) >= 6):
        add("CUSTOMER_HOUR_DEVIATION",
            20 if prior_n >= 3 else 10,
            f"Transaction at {h:02d}:00 — customer usually transacts "
            f"around {mode:02d}:00", weight=w_hdev)

    base = ctx["medians"].get(cust) or 0.0
    if base > 0 and amt > 0:
        ratio = amt / base
        if ratio >= 8 and prior_n >= 3:
            add("CUSTOMER_RELATIVE_AMOUNT_SPIKE", 40,
                f"Rs {amt:,.0f} is {ratio:.1f}x the customer's median "
                f"Rs {base:,.0f}")
        elif ratio >= 5 and prior_n >= 5:
            add("CUSTOMER_RELATIVE_AMOUNT_SPIKE", 30,
                f"Rs {amt:,.0f} is {ratio:.1f}x the customer's median "
                f"Rs {base:,.0f}")
        elif ratio >= 3 and prior_n >= 10:
            add("CUSTOMER_RELATIVE_AMOUNT_SPIKE", 20,
                f"Rs {amt:,.0f} is {ratio:.1f}x the customer's median "
                f"Rs {base:,.0f}")
        elif ratio >= 2 and prior_n >= 3:
            add("CUSTOMER_RELATIVE_AMOUNT_SPIKE", 15,
                f"Rs {amt:,.0f} is {ratio:.1f}x the customer's median "
                f"Rs {base:,.0f}")

    times = ctx["customer_times"].get(cust) or []
    if ctx["day_granular"]:
        day = t.get("date") or ""
        n_day = ctx["daily_counts"].get(cust, {}).get(day, 0)
        base_day = max(1.0, ctx["daily_medians"].get(cust, 1.0))
        if n_day >= max(5 * base_day, 12):
            add("AMOUNT_VELOCITY_SPIKE", 50,
                f"{n_day} transactions from this customer on {day} "
                f"({n_day / base_day:.1f}x their normal daily rate)")
        elif n_day >= max(2.5 * base_day, 6):
            add("AMOUNT_VELOCITY_SPIKE", 25,
                f"{n_day} transactions from this customer on {day} "
                f"({n_day / base_day:.1f}x their normal daily rate)")
    else:
        burst = (bisect.bisect_right(times, ts + _BURST_WINDOW)
                 - bisect.bisect_left(times, ts - _BURST_WINDOW))
        if burst >= _BURST_HARD:
            add("AMOUNT_VELOCITY_SPIKE", 50,
                f"{burst} transactions from this customer within ±30 minutes")
        elif burst >= _BURST_SOFT:
            add("AMOUNT_VELOCITY_SPIKE", 25,
                f"{burst} transactions from this customer within ±30 minutes")

    prior_bens = ctx["prior_beneficiaries"].get(tid) or frozenset()
    w_nb = ctx["w_new_beneficiary"]
    if w_nb > 0 and recv and prior_n >= 2 and recv not in prior_bens:
        add("NEW_BENEFICIARY", 25 if prior_n >= 5 else 10,
            f"First-ever transfer to beneficiary account {recv}",
            weight=w_nb)
    elif w_nb > 0 and recv and prior_n >= 1 and recv not in prior_bens:
        add("NEW_BENEFICIARY", 10,
            f"First-ever transfer to beneficiary account {recv} "
            "(thin history)", weight=w_nb)

    if amt >= 1000 and amt % 5000 == 0:
        add("ROUND_AMOUNT", 10, f"Round payout Rs {amt:,.0f} (structuring "
                                "signature)")

    # ---------------- BANK+CDR ----------------
    txn_has_time = (t.get("time") or "")[:2].isdigit()
    w_calls = ctx["w_calls"]
    if w_calls > 0 and not txn_has_time and ctx["day_granular"]:
        day = t.get("date") or ""
        day_calls = 0
        for ph in (phone, t.get("receiver_phone") or ""):
            for cts, dur, voice in (ctx["calls_by_phone"].get(ph) or []):
                if (voice or dur >= _CALL_MIN_DUR) and _ts_day(cts) == day:
                    day_calls += 1
        if day_calls >= 2:
            add("REPEATED_CALLS_BEFORE_TRANSACTION", 25,
                f"{day_calls} calls on the same day as this transfer",
                f"[CDR] {day_calls} call(s) on {day}", weight=w_calls)
        elif day_calls >= 1:
            add("UNUSUAL_CALL_BEFORE_TRANSACTION", 15,
                "A call was placed on the same day as this transfer",
                f"[CDR] call on {day}", weight=w_calls)
    if w_calls > 0 and txn_has_time:
        calls = 0
        call_ts = ctx["calls_by_phone"].get(phone) or []
        i_c0 = bisect.bisect_left(call_ts, (ts - _CALL_WINDOW, -1))
        i_c1 = bisect.bisect_left(call_ts, (ts, 0))
        calls = sum(1 for _, d, v in call_ts[i_c0:i_c1]
                    if v or d >= _CALL_MIN_DUR)
        recv_phone = t.get("receiver_phone") or ""
        if recv_phone:
            rts = ctx["calls_by_phone"].get(recv_phone) or []
            i_r0 = bisect.bisect_left(rts, (ts - _CALL_WINDOW, -1))
            i_r1 = bisect.bisect_left(rts, (ts, 0))
            calls += sum(1 for _, d, v in rts[i_r0:i_r1]
                         if v or d >= _CALL_MIN_DUR)
        if calls >= 3:
            add("REPEATED_CALLS_BEFORE_TRANSACTION", 40,
                f"{calls} calls placed in the hour before this transaction",
                f"[CDR] {calls} calls <= 60 min before txn", weight=w_calls)
        elif calls >= 1:
            add("UNUSUAL_CALL_BEFORE_TRANSACTION", 30,
                "A call was placed in the hour before this transaction",
                f"[CDR] {calls} call(s) <= 60 min before txn", weight=w_calls)
        if calls >= 1:
            if w_nb > 0 and recv and recv not in prior_bens:
                add("CALL_THEN_NEW_BENEFICIARY", 20,
                    "Call immediately before a first-time beneficiary transfer",
                    weight=w_calls)
            if base > 0 and amt >= 3 * base:
                add("CALL_THEN_HIGH_VALUE_TRANSFER", 25,
                    "Call immediately before a high-value transfer "
                    f"(Rs {amt:,.0f}, {amt / base:.1f}x median)",
                    weight=w_calls)

    # ---------------- BANK+CDR+IPDR ----------------
    w_net = ctx["w_network"]
    if w_net > 0 and txn_has_time and phone:
        sess = ctx["ipdr_by_phone"].get(phone) or []
        n_sess = (bisect.bisect_right(sess, ts + _IPDR_WINDOW)
                  - bisect.bisect_left(sess, ts - _IPDR_WINDOW))
        if n_sess >= 3:
            add("NETWORK_SESSION_BURST_AROUND_TRANSACTION", 30,
                f"{n_sess} data sessions within ±30 minutes of this "
                "transaction", weight=w_net)

        def _novel_near(hist: list, window: float, before, after) -> set:
            """Values seen in (ts, ts+window] but never before ts."""
            i_prior = bisect.bisect_left(hist, (ts, before))
            prior = {v for _, v in hist[:i_prior]}
            i_near = bisect.bisect_left(hist, (ts + window, after))
            return {v for _, v in hist[i_prior:i_near]} - prior

        def _rare(hist: list, values: set, max_seen: int = 2) -> set:
            """Filter to values occurring at most `max_seen` times before the
            transaction.  Post-transaction occurrences (the anomaly itself,
            follow-up sessions) must not disqualify a genuinely novel value."""
            counts = Counter(v for _, v in hist if _ < ts)
            return {v for v in values if counts.get(v, 0) <= max_seen}

        novel_imei = _novel_near(ctx["imei_by_phone"].get(phone) or [],
                                 _CALL_WINDOW, "", "\uffff")
        novel_imei |= _novel_near(ctx["ipdr_imei_by_phone"].get(phone) or [],
                                  _IPDR_WINDOW, "", "\uffff")
        novel_imei = _rare((ctx["imei_by_phone"].get(phone) or [])
                           + (ctx["ipdr_imei_by_phone"].get(phone) or []),
                           novel_imei)
        if novel_imei:
            add("NEW_DEVICE_AROUND_TRANSACTION", 30,
                f"IMEI {sorted(novel_imei)[0]} never used by this "
                "phone before", weight=w_net)
        else:
            h = ctx["imei_by_phone"].get(phone) or []
            i0 = bisect.bisect_left(h, (ts, ""))
            near_imeis = {v for _, v in
                          h[i0:bisect.bisect_left(h, (ts + _CALL_WINDOW,
                                                      "\uffff"))]}
            rare = {v for v in near_imeis
                    if ctx["imei_global"].get(v, 0) <= 2}
            if rare:
                add("NEW_DEVICE_AROUND_TRANSACTION", 15,
                    f"IMEI {sorted(rare)[0]} appears only "
                    f"{ctx['imei_global'].get(sorted(rare)[0])}x "
                    "dataset-wide (burner device)", weight=w_net)

        novel_pair = _novel_near(ctx["pair_by_phone"].get(phone) or [],
                                 _CALL_WINDOW, ("", ""), ("\uffff", "\uffff"))
        ipdr_pairs = ctx["ipdr_pair_by_phone"].get(phone) or []
        i_p = bisect.bisect_left(ipdr_pairs, (ts, ("", "")))
        ipdr_prior = {p for _, p in ipdr_pairs[:i_p]}
        cdr_near = {p for _, p in ctx["pair_by_phone"].get(phone) or []
                    if abs(_ - ts) <= 48 * 3600}
        if cdr_near and cdr_near - ipdr_prior:
            novel_pair |= cdr_near - ipdr_prior
        novel_pair = _rare((ctx["pair_by_phone"].get(phone) or [])
                           + ipdr_pairs, novel_pair)
        if novel_pair:
            add("IMSI_IMEI_PAIR_NOVELTY", 35,
                f"(IMSI, IMEI) pair {sorted(novel_pair)[0]} never seen for "
                "this phone before", weight=w_net)

        cell_hist = ctx["cell_by_phone"].get(phone) or []
        i_prior = bisect.bisect_left(cell_hist, (ts, ""))
        prior_cells = {v for _, v in cell_hist[:i_prior]}
        i_near = bisect.bisect_left(cell_hist, (ts, "\uffff"))
        near_cells = {v for _, v in cell_hist[i_prior:i_near]}
        if prior_cells and near_cells and not near_cells <= prior_cells:
            add("UNUSUAL_LOCATION_CONTEXT", 30,
                f"Phone was at cell {sorted(near_cells - prior_cells)[0]} "
                "near txn time — never seen there before", weight=w_net)
        elif near_cells:
            rare = {v for v in near_cells
                    if ctx["cell_global"].get(v, 0) <= 2}
            if rare:
                add("UNUSUAL_LOCATION_CONTEXT", 15,
                    f"Phone at cell {sorted(rare)[0]} near txn time — "
                    "cell appears only 1-2x dataset-wide", weight=w_net)

    return {
        "transaction_id": tid,
        "sender_customer_id": t.get("customer_id") or t.get("account_no") or "",
        "account_no": t.get("account_no") or "",
        "amount": round(amt, 2),
        "mode": t.get("mode") or "",
        "ts": ts,
        "bank": t.get("bank") or "",
        "risk_score": float(score),
        "risk_band": ("CRITICAL" if score >= 75 else "HIGH"
                      if score >= 50 else "MEDIUM"),
        "rules_fired": flags,
        "breakdown": breakdown,
        "evidence": evidence,
        "confidence": round(min(0.5 + score / 200.0, 0.97), 2),
    }
