"""Scenario Detection Layer.

Maps the outputs of every intelligence engine (rules, ML, behaviour,
temporal, telecom, internet, money-flow, entity) onto *named fraud
scenarios* — the language investigators speak — instead of generic
"anomaly" labels.

Every detection carries:

  * scenario      — canonical name,
  * description   — one-line explanation,
  * severity      — LOW / MEDIUM / HIGH / CRITICAL,
  * confidence    — 0..1 (weight of corroborating evidence),
  * evidence      — concrete strings the investigator can verify,
  * engines       — which intelligence engines contributed.
"""

from __future__ import annotations

from .moneyflow import money_flow_analysis
from .entity_risk import entity_risk

_SCENARIO_META = {
    "Rapid In-Out": "Funds deposited and withdrawn almost immediately",
    "Structuring": "Transactions sized to stay below reporting thresholds",
    "Smurfing": "Many small payouts splitting a large sum across beneficiaries",
    "Layering": "Funds moved through multiple intermediate accounts to obscure origin",
    "Circular Flow": "Money returns to the source through a ring of accounts",
    "Money Mule": "Account acts as a pass-through pocket for third-party funds",
    "Shared Device Fraud": "One device/IMEI driving multiple accounts",
    "Shared Beneficiary": "Many accounts paying into one common beneficiary",
    "Call Assisted Fraud": "A call immediately precedes a transfer (social engineering)",
    "SIM Swap": "SIM (IMSI) changed around suspicious activity",
    "Device Change": "New device (IMEI) appeared around suspicious activity",
    "Location Jump": "Phone relocated to an unknown cell near the transaction",
    "Burst Transactions": "Abnormal velocity of transactions in a short window",
    "Fraud Ring": "Accounts form a dense coordinated community",
    "Cross Bank Fraud": "Funds hop across multiple banks in quick succession",
    "Cross Operator Fraud": "Activity spans multiple telecom operators",
    "Telecom Coordinated Fraud": "Calls and transfers coordinated across many numbers",
    "Internet Coordinated Fraud": "Data sessions and transfers coordinated over shared IPs",
    "Dormant Account Activation": "Long-dormant account suddenly became active",
    "Account Takeover": "Profile deviation consistent with a hijacked account",
    "Unknown Behaviour": "Statistically extreme activity with no named pattern",
}


def _severity(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _confidence(factors: list[bool], base: float = 0.5) -> float:
    """Confidence grows with the number of corroborating signals."""
    hits = sum(1 for f in factors if f)
    return round(min(0.97, base + 0.12 * hits), 2)


def _add(out: list[dict], name: str, severity: str, confidence: float,
         evidence: list[str], engines: list[str]) -> None:
    out.append({
        "scenario": name,
        "description": _SCENARIO_META.get(name, ""),
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "engines": engines,
    })


def detect_transaction_scenarios(txn: dict, engine_out: dict) -> list[dict]:
    """Scenario detections for one transaction.

    `engine_out` must contain: behavioural breakdown, profile deviation,
    temporal, telecom, internet, plus account-level money-flow / entity info
    (precomputed once per bundle by `scenario_engine`).
    """
    out: list[dict] = []
    tid = txn.get("txn_id") or ""
    ts = float(txn.get("ts") or 0.0)
    amt = float(txn.get("debit") or txn.get("credit") or 0.0)
    acc = txn.get("account_no") or ""
    cust = txn.get("customer_id") or acc
    mode = (txn.get("mode") or "").upper()

    breakdown = engine_out.get("breakdown", {}).get(tid, [])
    rules = {b.get("rule") for b in breakdown}
    profile = engine_out.get("profile", {}).get(tid, {})
    temporal = engine_out.get("temporal", {}).get(tid, {})
    telecom = engine_out.get("telecom", {}).get(tid, {})
    internet = engine_out.get("internet", {}).get(tid, {})
    flow = engine_out.get("moneyflow", {}).get(acc, {})
    exposure = engine_out.get("entity", {}).get(acc, {})

    night = "ODD_HOUR_TRANSACTION" in rules
    spike = "CUSTOMER_RELATIVE_AMOUNT_SPIKE" in rules
    burst = "AMOUNT_VELOCITY_SPIKE" in rules
    new_ben = "NEW_BENEFICIARY" in rules
    round_amt = "ROUND_AMOUNT" in rules
    call_ctx = "UNUSUAL_CALL_BEFORE_TRANSACTION" in rules or \
               "REPEATED_CALLS_BEFORE_TRANSACTION" in rules
    new_dev = "NEW_DEVICE_AROUND_TRANSACTION" in rules
    new_pair = "IMSI_IMEI_PAIR_NOVELTY" in rules
    loc_ctx = "UNUSUAL_LOCATION_CONTEXT" in rules
    net_burst = "NETWORK_SESSION_BURST_AROUND_TRANSACTION" in rules
    prof_score = float(profile.get("score", 0.0))
    prof_reasons = profile.get("reasons", [])
    temp_score = float(temporal.get("temporal_score", 0.0))
    call_score = float(telecom.get("call_assist_score", 0.0))
    net_score = float(internet.get("internet_score", 0.0))
    net_reasons = internet.get("reasons", [])

    # ---- Rapid In-Out / Burst ----
    if burst or temp_score >= 40:
        ev = [f"{temporal.get('calls_in_window', 0)} calls + "
              f"{temporal.get('sessions_in_window', 0)} sessions in window"]
        _add(out, "Rapid In-Out", _severity(40 + temp_score),
             _confidence([burst, temp_score >= 40, call_ctx], 0.55),
             ["Velocity burst rule fired"] + ev,
             ["rules", "temporal"])
    if burst and amt >= 100000:
        _add(out, "Burst Transactions", "CRITICAL",
             _confidence([True, night], 0.6),
             [f"{amt:,.0f} moved during a velocity burst"],
             ["rules", "temporal"])

    # ---- Structuring / Smurfing ----
    if round_amt:
        _add(out, "Structuring", _severity(30 + (25 if night else 0)),
             _confidence([round_amt, night], 0.5),
             [f"Round amount Rs {amt:,.0f} in {'odd hours' if night else 'regular hours'}"],
             ["rules"])
    if round_amt and new_ben:
        _add(out, "Smurfing", "HIGH",
             _confidence([round_amt, new_ben], 0.6),
             [f"Round payout Rs {amt:,.0f} to a first-time beneficiary"],
             ["rules"])

    # ---- Layering / Money Mule ----
    if flow.get("layering_depth", 0) >= 2 or flow.get("mule_chain"):
        _add(out, "Layering",
             _severity(45 + 15 * flow.get("layering_depth", 0)),
             _confidence([flow.get("layering_depth", 0) >= 2,
                          flow.get("mule_chain", False)], 0.5),
             flow.get("reasons", [])[:3],
             ["moneyflow", "graph"])
    if flow.get("rapid_forward") or (flow.get("cash_out_payouts", 0) >= 4 and amt >= 25000):
        _add(out, "Money Mule", "HIGH",
             _confidence([flow.get("rapid_forward", False),
                          flow.get("cash_out_payouts", 0) >= 4], 0.55),
             flow.get("reasons", [])[:3],
             ["moneyflow", "graph"])

    # ---- Shared Device / Beneficiary ----
    if exposure.get("shared_entities", 0) >= 3:
        _add(out, "Shared Device Fraud", _severity(40 + 10 * exposure.get("shared_entities", 0)),
             _confidence([new_dev, exposure.get("shared_entities", 0) >= 5], 0.5),
             exposure.get("reasons", [])[:3],
             ["entity", "internet"])
    if new_dev:
        _add(out, "Device Change", _severity(40 + (15 if spike else 0)),
             _confidence([new_dev, new_pair], 0.5),
             [r for r in net_reasons if "device" in r.lower()] or
             ["Novel IMEI observed near transaction"],
             ["internet", "rules"])
    if new_pair:
        _add(out, "SIM Swap", _severity(45 + (10 if new_dev else 0)),
             _confidence([new_pair, new_dev], 0.55),
             ["Novel (IMSI, IMEI) pair around transaction"],
             ["internet", "rules"])

    # ---- Location / Telecom coordination ----
    if loc_ctx:
        _add(out, "Location Jump", _severity(40 + (15 if spike else 0)),
             _confidence([loc_ctx, net_burst], 0.5),
             ["Phone at a cell never seen before near txn time"],
             ["rules", "internet"])
    if call_ctx or call_score >= 40:
        ev = [f"{call_score:g} call-assist score", f"{call_score >= 40 and '3+ calls before txn' or ''}"]
        _add(out, "Call Assisted Fraud", _severity(40 + call_score * 0.3),
             _confidence([call_ctx, call_score >= 40, new_ben, spike], 0.55),
             [e for e in ev if e],
             ["telecom", "rules"])
    if call_ctx and new_ben:
        _add(out, "Telecom Coordinated Fraud", "HIGH",
             _confidence([call_ctx, new_ben, spike], 0.6),
             ["Call immediately before a first-time beneficiary transfer"],
             ["telecom", "rules"])

    # ---- Internet coordination ----
    if net_burst and any("shared IP" in r for r in net_reasons):
        _add(out, "Internet Coordinated Fraud", "HIGH",
             _confidence([net_burst, net_score >= 25], 0.55),
             net_reasons[:3],
             ["internet", "temporal"])

    # ---- Dormant activation / takeover ----
    if any("dormant" in r.lower() for r in prof_reasons):
        _add(out, "Dormant Account Activation", _severity(40 + prof_score * 0.3),
             _confidence([prof_score >= 30, spike, new_ben], 0.5),
             prof_reasons[:2],
             ["behaviour"])
    if prof_score >= 50 and (spike or night or new_ben):
        _add(out, "Account Takeover", _severity(45 + prof_score * 0.3),
             _confidence([spike, new_ben, night, prof_score >= 70], 0.55),
             prof_reasons[:3],
             ["behaviour"])

    # ---- Fallback ----
    if not out and (spike or burst or prof_score >= 40 or temp_score >= 40):
        _add(out, "Unknown Behaviour", _severity(max(30, prof_score, temp_score)),
             _confidence([spike, burst, prof_score >= 40], 0.45),
             [f"statistical anomaly: profile {prof_score:g}, temporal {temp_score:g}"],
             ["ml", "behaviour", "temporal"])

    return sorted(out, key=lambda s: (-s["confidence"], s["severity"]))


def detect_account_scenarios(acc: str, info: dict) -> list[dict]:
    """Account-level scenario detections.

    `info` carries the account's aggregate signals (money-flow, entity
    exposure, profile deviation, graph metadata, behavioural flags).
    """
    out: list[dict] = []
    flow = info.get("moneyflow", {})
    exposure = info.get("entity", {})
    profile = info.get("profile", {})
    graph = info.get("graph", {})

    if flow.get("circular"):
        _add(out, "Circular Flow", _severity(50 + 20),
             _confidence([True, flow.get("layering_depth", 0) >= 2], 0.6),
             flow.get("reasons", []),
             ["moneyflow", "graph"])
    if flow.get("layering_depth", 0) >= 3:
        _add(out, "Layering", "HIGH",
             _confidence([flow.get("layering_depth", 0) >= 3,
                          flow.get("mule_chain", False)], 0.55),
             flow.get("reasons", []),
             ["moneyflow", "graph"])
    if flow.get("cash_out_payouts", 0) >= 8:
        _add(out, "Money Mule", "HIGH",
             _confidence([flow.get("cash_out_payouts", 0) >= 8,
                          flow.get("rapid_forward", False)], 0.55),
             flow.get("reasons", []),
             ["moneyflow", "graph"])
    if exposure.get("shared_entities", 0) >= 4:
        _add(out, "Shared Beneficiary",
             _severity(35 + 8 * exposure.get("shared_entities", 0)),
             _confidence([exposure.get("shared_entities", 0) >= 6], 0.5),
             exposure.get("reasons", []),
             ["entity"])
    if graph.get("community_size", 1) >= 30 and graph.get("betweenness", 0) > 0:
        _add(out, "Fraud Ring", _severity(40 + min(30, graph.get("community_size", 0) // 2)),
             _confidence([graph.get("community_size", 0) >= 50], 0.5),
             [f"member of a {graph.get('community_size', 0)}-account community "
              "with high betweenness"],
             ["graph"])
    if profile.get("dormant_activated"):
        _add(out, "Dormant Account Activation", "HIGH",
             _confidence([True, profile.get("deviating_share", 0) >= 0.3], 0.55),
             profile.get("reasons", [])[:2],
             ["behaviour"])

    return sorted(out, key=lambda s: (-s["confidence"], s["severity"]))


def scenario_engine(bundle: dict, engine_out: dict,
                    moneyflow: dict | None = None,
                    entity: dict | None = None) -> dict:
    """Full-bundle scenario pass.

    `moneyflow` / `entity` may be precomputed (the hybrid orchestrator does
    this to avoid re-running the expensive passes).

    Returns {txn: {txn_id: [scenario...]},
             account: {account_no: [scenario...]},
             stats: {txn_scenarios, account_scenarios, top_scenarios}}
    """
    if moneyflow is None:
        moneyflow = money_flow_analysis(bundle)
    if entity is None:
        entity = entity_risk(bundle)

    txn_scenarios: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for t in bundle.get("bank", []):
        tid = t.get("txn_id") or ""
        if not tid:
            continue
        acc = t.get("account_no") or ""
        merged = dict(engine_out)
        merged["moneyflow"] = moneyflow["accounts"].get(acc, {})
        merged["entity"] = entity["account_exposure"].get(acc, {})
        det = detect_transaction_scenarios(t, merged)
        if det:
            txn_scenarios[tid] = det
            for d in det:
                counts[d["scenario"]] = counts.get(d["scenario"], 0) + 1

    acc_scenarios: dict[str, list[dict]] = {}
    for acc, flow in moneyflow["accounts"].items():
        info = {
            "moneyflow": flow,
            "entity": entity["account_exposure"].get(acc, {}),
            "profile": engine_out.get("acc_profile", {}).get(acc, {}),
            "graph": engine_out.get("graph", {}).get(acc, {}),
        }
        det = detect_account_scenarios(acc, info)
        if det:
            acc_scenarios[acc] = det
            for d in det:
                counts[d["scenario"]] = counts.get(d["scenario"], 0) + 1

    top = sorted(counts.items(), key=lambda kv: -kv[1])[:10]
    return {
        "txn": txn_scenarios,
        "account": acc_scenarios,
        "moneyflow": moneyflow,
        "entity": entity,
        "stats": {"txn_scenarios": sum(len(v) for v in txn_scenarios.values()),
                  "account_scenarios": sum(len(v) for v in acc_scenarios.values()),
                  "scenario_types": len(counts),
                  "top_scenarios": [{"scenario": k, "count": v} for k, v in top]},
    }
