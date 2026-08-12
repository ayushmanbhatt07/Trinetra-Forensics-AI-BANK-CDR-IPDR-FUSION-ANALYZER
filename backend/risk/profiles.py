"""Behavioural Profiling Engine.

Builds a per-customer behavioural profile from the fused bundle:

  * value statistics — avg / median / p95 / daily & monthly totals,
  * temporal habits — preferred hour band, weekday, active days,
  * preference sets — preferred bank, beneficiary, device (IMEI), IP,
    merchant/UPI, phone;
  * state — dormant days, last activity, txn cadence.

Each subsequent transaction is scored against the profile: the deviation
contributes a 0-100 `behaviour_score` with a plain-language reason, so the
ensemble can lift customers who "suddenly change behaviour" (the LOF-style
local anomaly is handled at the ML layer; here we explain it behaviourally).

Two operating modes:

  * profile_deviation(bundle) — per-transaction deviation scores
  * account_profile_deviation(bundle) — per-account aggregate deviation
    (share of deviating txns, max deviation, dormant-account activity)
"""

from __future__ import annotations

from collections import Counter, defaultdict

_IST_NIGHT = (22, 6)
_DORMANT_DAYS = 30
_WEEKEND = {5, 6}  # Saturday, Sunday (datetime.weekday())


def _hour_of(t: dict) -> int:
    hh = (t.get("time") or "")
    if len(hh) >= 2 and hh[:2].isdigit():
        return int(hh[:2])
    import datetime as _dt
    ts = float(t.get("ts") or 0.0)
    if not ts:
        return -1
    return _dt.datetime.fromtimestamp(ts,
        _dt.timezone(_dt.timedelta(hours=5, minutes=30))).hour


def _amount(t: dict) -> float:
    return float(t.get("debit") or t.get("credit") or 0.0)


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    vals = sorted(vals)
    i = min(len(vals) - 1, int(len(vals) * p))
    return vals[i]


def build_profiles(bundle: dict) -> dict:
    """Customer profiles keyed by customer_id (falls back to account_no)."""
    bank = bundle.get("bank", [])
    profiles: dict[str, dict] = {}

    for t in bank:
        cust = t.get("customer_id") or t.get("account_no") or ""
        if not cust:
            continue
        p = profiles.setdefault(cust, {
            "customer_id": cust, "amounts": [], "days": set(),
            "banks": Counter(), "beneficiaries": Counter(), "modes": Counter(),
            "hours": Counter(), "weekdays": Counter(), "phones": Counter(),
            "imeis": Counter(), "ips": Counter(), "upis": Counter(),
            "merchants": Counter(), "txn_count": 0, "first_ts": None,
            "last_ts": None, "ncrp_hit": False,
        })
        amt = _amount(t)
        p["amounts"].append(amt)
        p["txn_count"] += 1
        ts = float(t.get("ts") or 0.0)
        if ts:
            import datetime as _dt
            dt = _dt.datetime.fromtimestamp(ts,
                _dt.timezone(_dt.timedelta(hours=5, minutes=30)))
            day = dt.strftime("%Y-%m-%d")
            p["days"].add(day)
            p["hours"][dt.hour] += 1
            p["weekdays"][dt.weekday()] += 1
            p["first_ts"] = min(p["first_ts"] or ts, ts)
            p["last_ts"] = max(p["last_ts"] or 0.0, ts)
        day = t.get("date") or ""
        if day:
            p["days"].add(day)
        if t.get("bank"):
            p["banks"][t["bank"]] += 1
        if t.get("receiver_account"):
            p["beneficiaries"][t["receiver_account"]] += 1
        if t.get("mode"):
            p["modes"][t["mode"]] += 1
        for ph in (t.get("sender_phone"), t.get("receiver_phone")):
            if ph:
                p["phones"][ph] += 1
        if t.get("imei"):
            p["imeis"][t["imei"]] += 1
        if t.get("ip"):
            p["ips"][t["ip"]] += 1
        if t.get("upi_id"):
            p["upis"][t["upi_id"]] += 1
        if t.get("merchant") or t.get("merchant_name"):
            p["merchants"][t.get("merchant") or t.get("merchant_name")] += 1

    for cust in profiles:
        p = profiles[cust]
        n = max(1, len(p["amounts"]))
        p["avg_amount"] = sum(p["amounts"]) / n
        p["median_amount"] = _median(p["amounts"])
        p["p95_amount"] = _pct(p["amounts"], 0.95)
        p["max_amount"] = max(p["amounts"])
        p["total_amount"] = sum(p["amounts"])
        p["preferred_bank"] = p["banks"].most_common(1)[0][0] if p["banks"] else ""
        p["preferred_beneficiary"] = (
            p["beneficiaries"].most_common(1)[0][0] if p["beneficiaries"] else "")
        p["preferred_mode"] = p["modes"].most_common(1)[0][0] if p["modes"] else ""
        p["preferred_hour"] = p["hours"].most_common(1)[0][0] if p["hours"] else -1
        p["preferred_weekday"] = (
            p["weekdays"].most_common(1)[0][0] if p["weekdays"] else -1)
        p["preferred_phone"] = p["phones"].most_common(1)[0][0] if p["phones"] else ""
        p["preferred_imei"] = p["imeis"].most_common(1)[0][0] if p["imeis"] else ""
        p["preferred_ip"] = p["ips"].most_common(1)[0][0] if p["ips"] else ""
        p["preferred_upi"] = p["upis"].most_common(1)[0][0] if p["upis"] else ""
        p["preferred_merchant"] = (
            p["merchants"].most_common(1)[0][0] if p["merchants"] else "")
        p["day_count"] = len(p["days"])
        p["active_days_span"] = p["day_count"]

    return profiles


def _dormant_days(p: dict, ts: float) -> float:
    if not ts or not p.get("last_ts"):
        return 0.0
    last = float(p["last_ts"])
    if last >= ts:
        return 0.0
    return max(0.0, (ts - last) / 86400.0)


def deviation_signal(t: dict, profile: dict) -> tuple[float, list[str]]:
    """Score one transaction against its customer profile (0-100, capped).

    Returns (score, reasons).  Deviations only count when the profile has
    enough history to be meaningful (>= 3 prior txns).
    """
    amt = _amount(t)
    ts = float(t.get("ts") or 0.0)
    reasons: list[str] = []
    score = 0.0

    if not profile or profile["txn_count"] < 3:
        return 0.0, ["profile too thin (fewer than 3 prior transactions)"]

    def add(points: float, why: str) -> None:
        nonlocal score
        score = min(score + points, 100.0)
        reasons.append(why)

    med = profile["median_amount"]
    if med > 0 and amt > 0:
        ratio = amt / med
        if ratio >= 10:
            add(35, f"amount Rs {amt:,.0f} is {ratio:.1f}x the customer median Rs {med:,.0f}")
        elif ratio >= 5:
            add(25, f"amount Rs {amt:,.0f} is {ratio:.1f}x the customer median Rs {med:,.0f}")
        elif ratio >= 3:
            add(15, f"amount Rs {amt:,.0f} is {ratio:.1f}x the customer median Rs {med:,.0f}")

    h = _hour_of(t)
    ph = profile["preferred_hour"]
    if h >= 0 and ph >= 0 and abs(h - ph) >= 6:
        add(10, f"transaction at {h:02d}:00 deviates from preferred hour ~{ph:02d}:00")
    night = (h >= _IST_NIGHT[0] or (0 <= h < _IST_NIGHT[1])) if h >= 0 else False
    if night and profile.get("night_share", 0.5) <= 0.2:
        add(8, "night-hour transaction (22:00-06:00) outside customer habit")

    recv = t.get("receiver_account") or ""
    pref_ben = profile["preferred_beneficiary"]
    if recv and pref_ben and recv != pref_ben:
        add(6, f"transfer to beneficiary {recv} — not the customer's usual {pref_ben}")

    if t.get("bank") and profile["preferred_bank"] \
            and t["bank"] != profile["preferred_bank"]:
        add(5, f"bank {t['bank']} differs from preferred {profile['preferred_bank']}")

    if t.get("mode") and profile["preferred_mode"] \
            and t["mode"] != profile["preferred_mode"]:
        add(5, f"mode {t['mode']} differs from preferred {profile['preferred_mode']}")

    for phone_key, pref_key, label in (
        ("sender_phone", "preferred_phone", "phone"),
        ("imei", "preferred_imei", "device IMEI"),
        ("ip", "preferred_ip", "IP"),
        ("upi_id", "preferred_upi", "UPI id"),
        ("merchant", "preferred_merchant", "merchant"),
    ):
        val = t.get(phone_key)
        pref = profile[pref_key]
        if val and pref and str(val) != str(pref):
            add(6, f"{label} {val} not seen before in this customer's history")

    dormant = _dormant_days(profile, ts)
    if dormant >= _DORMANT_DAYS:
        add(30, f"account dormant for {dormant:.0f} days before this transaction"
                " — sudden reactivation")
        reasons.insert(0, f"dormant {dormant:.0f}d")

    weekend = False
    import datetime as _dt
    if ts:
        weekend = _dt.datetime.fromtimestamp(ts,
            _dt.timezone(_dt.timedelta(hours=5, minutes=30))).weekday() in _WEEKEND
    pw = profile["preferred_weekday"]
    if weekend and pw >= 0 and pw not in _WEEKEND:
        add(4, "weekend transaction outside customer habit")

    return round(min(score, 100.0), 2), reasons


def profile_deviation(bundle: dict) -> dict[str, dict]:
    """Per-transaction behavioural deviation: txn_id -> {score, reasons}."""
    profiles = build_profiles(bundle)
    out: dict[str, dict] = {}
    for t in bundle.get("bank", []):
        tid = t.get("txn_id") or ""
        if not tid:
            continue
        cust = t.get("customer_id") or t.get("account_no") or ""
        score, reasons = deviation_signal(t, profiles.get(cust))
        out[tid] = {"score": score, "reasons": reasons,
                    "customer_id": cust}
    return out


def account_profile_deviation(bundle: dict) -> dict[str, dict]:
    """Per-account aggregate deviation signals for the account ensemble.

    Returns account_no -> {behaviour_score, deviating_share, max_deviation,
    reasons, dormant_activated, profile_txn_count}.
    """
    prof_dev = profile_deviation(bundle)
    by_acc: dict[str, dict] = {}
    for t in bundle.get("bank", []):
        tid = t.get("txn_id") or ""
        acc = t.get("account_no") or ""
        if not tid or not acc:
            continue
        d = by_acc.setdefault(acc, {"n": 0, "deviating": 0, "scores": [],
                                    "reasons": []})
        d["n"] += 1
        sig = prof_dev.get(tid, {})
        sc = float(sig.get("score", 0.0))
        d["scores"].append(sc)
        if sc >= 30:
            d["deviating"] += 1
            d["reasons"].extend(sig.get("reasons", [])[:2])
    out = {}
    for acc, d in by_acc.items():
        n = max(1, d["n"])
        max_dev = max(d["scores"]) if d["scores"] else 0.0
        mean_dev = sum(d["scores"]) / len(d["scores"]) if d["scores"] else 0.0
        share = d["deviating"] / n
        # Blend magnitude + prevalence into a 0-100 account signal.
        score = round(min(100.0, 0.5 * max_dev + 25.0 * share + 0.25 * mean_dev), 2)
        dormant_activated = any("dormant" in r.lower() for r in d["reasons"])
        out[acc] = {
            "behaviour_score": score,
            "deviating_share": round(share, 3),
            "max_deviation": round(max_dev, 2),
            "profile_txn_count": d["n"],
            "dormant_activated": dormant_activated,
            "reasons": list(dict.fromkeys(d["reasons"]))[:5],
        }
    return out
