"""Explainability Engine.

Every risk decision is explained: which rules fired, which ML detectors
agreed, which features dominated, what the timeline looked like, and a
plain-language summary an investigator can paste into an STR or FIR.

Three levels:

  * `explain_transaction` — per-transaction breakdown,
  * `explain_account` — per-account breakdown,
  * `explain_entity` — per-entity (phone / IMEI / IP ...) breakdown.
"""

from __future__ import annotations


def _nl(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return "No unusual signals detected."
    return " ".join(parts[:1]) + " " + " ".join(
        "Also, " + p.lower().lstrip() if i == 1 else p
        for i, p in enumerate(parts[1:], start=1))


def explain_transaction(txn_id: str, txn: dict, info: dict) -> dict:
    """Human-readable explanation for one transaction."""
    rules = info.get("rules", [])
    breakdown = info.get("breakdown", [])
    scenarios = info.get("scenarios", [])
    profile = info.get("profile", {})
    temporal = info.get("temporal", {})
    telecom = info.get("telecom", {})
    internet = info.get("internet", {})

    parts: list[str] = []
    if scenarios:
        top = scenarios[0]
        parts.append(f"Flagged as {top['scenario']} "
                     f"(confidence {top['confidence']:.0%}).")
    if breakdown:
        top_rule = max(breakdown, key=lambda b: b["points"])
        parts.append(f"Strongest rule: {top_rule['rule']} "
                     f"(+{top_rule['points']} pts — {top_rule['reason']}).")
    if profile.get("score", 0) >= 30:
        parts.append("Behavioural profile deviation "
                     f"({profile['score']:g}/100).")
    if temporal.get("temporal_score", 0) >= 20:
        parts.append(f"Temporal correlation: {temporal.get('calls_in_window', 0)} "
                     "calls and "
                     f"{temporal.get('sessions_in_window', 0)} data sessions "
                     "within the window.")
    if telecom.get("call_assist_score", 0) >= 20:
        parts.append(f"Call-assisted: {telecom.get('calls_before', 0)} calls "
                     "immediately before the transfer.")
    if internet.get("internet_score", 0) >= 20:
        parts.append(f"Internet context ({internet['internet_score']:g}/100): "
                     + "; ".join(internet.get("reasons", [])[:2]))

    feature_importance = sorted(
        ((b["points"], b["rule"]) for b in breakdown), reverse=True)[:5]

    return {
        "transaction_id": txn_id,
        "narrative": _nl(parts),
        "triggered_rules": rules,
        "triggered_models": info.get("models", []),
        "top_features": [{"feature": r, "weight": p}
                         for p, r in feature_importance],
        "scenarios": scenarios,
        "evidence": info.get("evidence", []),
        "neighbour_analysis": info.get("neighbours", []),
        "timeline": info.get("timeline", []),
        "graph_explanation": info.get("graph_explanation", ""),
        "recommendations": info.get("recommendations", []),
    }


def explain_account(acc: str, info: dict) -> dict:
    """Human-readable explanation for one account."""
    scenarios = info.get("scenarios", [])
    flow = info.get("moneyflow", {})
    exposure = info.get("entity", {})
    graph = info.get("graph", {})
    profile = info.get("profile", {})

    parts: list[str] = []
    if scenarios:
        top = scenarios[0]
        parts.append(f"Account-level scenario: {top['scenario']} "
                     f"(confidence {top['confidence']:.0%}).")
    if flow.get("layering_depth", 0) >= 2:
        parts.append(f"Funds layer through {flow['layering_depth']} hops.")
    if flow.get("circular"):
        parts.append("Account sits inside a circular money-flow ring.")
    if flow.get("cash_out_payouts", 0) >= 4:
        parts.append(f"Radiates {flow['cash_out_payouts']} high-value payouts.")
    if exposure.get("shared_entities", 0) >= 3:
        parts.append(f"Shares identifiers with {exposure['shared_entities']} "
                     "other accounts.")
    if graph.get("community_size", 1) >= 20:
        parts.append(f"Member of a {graph['community_size']}-account community.")
    if profile.get("dormant_activated"):
        parts.append("Long-dormant account was reactivated.")

    return {
        "account_no": acc,
        "narrative": _nl(parts),
        "scenarios": scenarios,
        "moneyflow": {
            "layering_depth": flow.get("layering_depth", 0),
            "circular": flow.get("circular", False),
            "cash_out_payouts": flow.get("cash_out_payouts", 0),
            "rapid_forward": flow.get("rapid_forward", False),
        },
        "entity_exposure": exposure,
        "graph_metrics": {
            "community_size": graph.get("community_size", 1),
            "betweenness": graph.get("betweenness", 0),
            "pagerank": graph.get("pagerank", 0),
            "degree": graph.get("degree", 0),
        },
        "profile": profile,
        "recommendations": info.get("recommendations", []),
    }


def explain_entity(entity: str, kind: str, info: dict) -> dict:
    """Human-readable explanation for one identifier (phone/IMEI/IP/UPI...)."""
    parts: list[str] = []
    accounts = info.get("accounts", [])
    if len(accounts) >= 3:
        parts.append(f"{kind} {entity} is shared by {len(accounts)} accounts.")
    if info.get("ncrp"):
        parts.append("One of the sharing accounts is in the NCRP complaint ledger.")
    for r in info.get("reasons", []):
        parts.append(r)
    return {
        "entity": entity,
        "kind": kind,
        "narrative": _nl(parts),
        "accounts": accounts,
        "account_count": len(accounts),
        "ncrp": info.get("ncrp", False),
        "reasons": info.get("reasons", []),
    }
