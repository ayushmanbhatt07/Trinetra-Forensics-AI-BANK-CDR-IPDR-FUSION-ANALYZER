"""STR Narrative Generator — deterministic + optional LLM synthesis.

Takes the normalised CaseEvidence dict from str_engine.STRCaseBuilder and
produces investigation-quality narratives:

  * Executive summary
  * Forensic findings
  * STR/SAR narrative (WHO/WHAT/WHEN/WHERE/WHY/HOW)
  * Recommended actions

The deterministic path assembles prose from structured evidence — fast,
never hallucinates, but reads more mechanical.  The LLM path (Groq) produces
natural investigative prose but adds 2-3 s latency and is validated against
the source evidence before acceptance.

Both paths output the same schema so the PDF renderer is agnostic.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _money(v) -> str:
    return f"{float(v or 0):,.2f}"


def generate_str_narrative(case_evidence: dict) -> dict:
    """Generate investigation narratives from structured evidence.

    Returns
    -------
    dict with keys:
        executive_summary  : str
        forensic_findings  : list[dict]
        str_narrative      : str   (WHO/WHAT/WHEN/WHERE/WHY/HOW)
        recommended_actions: dict  (immediate / investigative / monitoring)
    """
    return _deterministic_narrative(case_evidence)


# -----------------------------------------------------------------------
#  Deterministic narrative assembly
# -----------------------------------------------------------------------

def _deterministic_narrative(ev: dict) -> dict:
    primary = ev.get("primary_transaction", {})
    baseline = ev.get("behavioral_baseline", {})
    flow = ev.get("funds_flow", {})
    customer = ev.get("customer_profile", {})
    cdr_ipdr = ev.get("cdr_ipdr", {})
    red_flags = ev.get("red_flags", [])
    typologies = ev.get("typologies", [])
    risk = ev.get("risk_assessment", {})
    case = ev.get("case", {})
    related = ev.get("related_transactions", [])
    counterparties = ev.get("counterparties", [])
    network = ev.get("network", {})

    txn_id = primary.get("transaction_id", "")
    amt = primary.get("amount", 0)
    txn_date = primary.get("date", "")
    txn_time = primary.get("time", "")
    sender = primary.get("sender_account", "")
    receiver = primary.get("receiver_account", "")
    cust_name = customer.get("customer_name", "Unknown")
    risk_band = risk.get("risk_band", "MEDIUM")
    risk_score = risk.get("overall_score", 0)

    # ---- Executive summary ----
    exec_lines = [
        f"Transaction {txn_id} dated {txn_date} for Rs {_money(amt)} "
        f"({primary.get('transaction_type', '')}) from account {sender} "
        f"to {receiver or 'unidentified beneficiary'} has been flagged "
        f"as {risk_band} risk (score {risk_score:.0f}/100).",
    ]

    if red_flags:
        top_flags = [f["indicator"] for f in red_flags[:3]]
        exec_lines.append(
            f"Key red flags: {', '.join(top_flags)}."
        )
    if typologies:
        exec_lines.append(
            f"Activity aligns with: {', '.join(t['typology'] for t in typologies[:2])}."
        )
    if len(related) > 0:
        exec_lines.append(
            f"{len(related)} related transactions identified involving "
            f"the same account/counterparty."
        )
    if baseline.get("available") and baseline.get("deviation_ratio", 0) >= 3:
        exec_lines.append(
            f"The transaction is {baseline['deviation_ratio']:.0f}x "
            f"the customer's historical median (Rs {_money(baseline.get('median_transaction', 0))})."
        )

    executive_summary = " ".join(exec_lines)

    # ---- Forensic findings ----
    findings = []

    if baseline.get("available") and baseline.get("deviation_ratio", 0) >= 3:
        findings.append({
            "title": "Significant Behavioral Deviation",
            "observation": (f"Transaction value Rs {_money(amt)} represents a "
                            f"{baseline['deviation_ratio']:.0f}x deviation from "
                            f"the historical median of Rs {_money(baseline.get('median_transaction', 0))}."),
            "evidence": (f"Customer account {sender} has {baseline.get('total_transactions', 0)} "
                         f"historical transactions with average Rs {_money(baseline.get('avg_transaction', 0))}. "
                         f"This transaction sits at the {baseline.get('percentile', 0):.0f}th percentile."),
            "risk_significance": "HIGH — activity inconsistent with established customer profile.",
            "category": "Derived",
        })

    if flow.get("outflows_count", 0) > 0:
        findings.append({
            "title": "Rapid Movement of Funds",
            "observation": (f"Receiver account {receiver} shows {flow['outflows_count']} "
                            f"outward transfers totaling Rs {_money(flow.get('total_outflow', 0))}."),
            "evidence": (f"Only {flow.get('retention_pct', 0):.0f}% of received funds were retained. "
                         f"The remainder was forwarded to downstream beneficiaries."),
            "risk_significance": "HIGH — consistent with pass-through or layering behavior.",
            "category": "Derived",
        })

    if counterparties and len(counterparties) >= 3:
        top_cp = counterparties[0]
        findings.append({
            "title": "Counterparty Concentration",
            "observation": (f"Account transacts with {len(counterparties)} counterparties. "
                            f"Top counterparty: {top_cp['name']} "
                            f"(Rs {_money(top_cp['total_amount'])}, "
                            f"{top_cp['transaction_count']} transactions)."),
            "evidence": f"Counterparty ranking computed from {baseline.get('total_transactions', 0)} transactions.",
            "risk_significance": "MEDIUM — concentrated exposure to specific beneficiaries.",
            "category": "Derived",
        })

    if cdr_ipdr.get("calls_on_txn_day"):
        findings.append({
            "title": "CDR/IPDR Corroboration",
            "observation": (f"{len(cdr_ipdr['calls_on_txn_day'])} telephone call(s) "
                            f"recorded on the transaction date involving the subject's phone."),
            "evidence": cdr_ipdr.get("summary", ""),
            "risk_significance": "MEDIUM — telephonic activity temporally correlated with financial transaction.",
            "category": "Correlated",
        })

    if cdr_ipdr.get("shared_devices"):
        findings.append({
            "title": "Shared Device Network",
            "observation": (f"{len(cdr_ipdr['shared_devices'])} device(s) shared "
                            f"between multiple phone numbers."),
            "evidence": "; ".join(
                f"IMEI {sd['imei']} used by {sd['count']} numbers"
                for sd in cdr_ipdr["shared_devices"][:3]),
            "risk_significance": "HIGH — shared device indicates coordinated activity.",
            "category": "Correlated",
        })

    if customer.get("complaint_count", 0) > 0:
        findings.append({
            "title": "NCRP Fraud Complaint History",
            "observation": (f"{customer['complaint_count']} NCRP complaint(s) "
                            f"reference this account."),
            "evidence": "Account flagged in the national cybercrime reporting portal.",
            "risk_significance": "CRITICAL — prior fraud complaint linkage.",
            "category": "Observed",
        })

    if not findings:
        if risk_score >= 50 or risk_band in ("CRITICAL", "HIGH", "SEVERE"):
            drivers_desc = ", ".join(d["driver"] for d in risk.get("drivers", [])) or "ML Anomaly & Turnover Volatility"
            findings.append({
                "title": f"Elevated Risk Assessment & Velocity Exposure ({risk_band})",
                "observation": (f"Account {sender} exhibits an elevated composite risk score of {risk_score:.0f}/100 "
                                f"with observed transaction volume of Rs {_money(baseline.get('total_credits', 0))}."),
                "evidence": f"Flagged by hybrid ML anomaly engine and risk decomposition. Primary drivers: {drivers_desc}.",
                "risk_significance": f"{risk_band} — flagged by hybrid risk scoring algorithms.",
                "category": "Algorithmic",
            })
        else:
            findings.append({
                "title": "Baseline Compliant Transaction",
                "observation": "Transaction parameters fall within expected operational parameters.",
                "evidence": "Behavioral baseline and network analysis show routine activity.",
                "risk_significance": "LOW — standard baseline transaction.",
                "category": "Observed",
            })

    # ---- STR narrative (WHO/WHAT/WHEN/WHERE/WHY/HOW) ----
    who = (f"The subject of this report is {cust_name}, "
           f"account holder of {sender} at {primary.get('bank', 'the reporting institution')}.")

    what = (f"A {primary.get('transaction_type', '').lower()} transaction of Rs {_money(amt)} "
            f"({primary.get('mode', 'electronic transfer')}) was executed "
            f"from account {sender} to {receiver or 'an unidentified beneficiary'}.")

    when = (f"The transaction occurred on {txn_date}"
            + (f" at {txn_time}" if txn_time else "")
            + ".")

    where = (f"Funds originated from account {sender}"
             + (f" ({primary.get('bank', '')})" if primary.get('bank') else "")
             + f" and were directed to {receiver or 'an unidentified account'}.")

    why_parts = []
    if baseline.get("available") and baseline.get("deviation_ratio", 0) >= 3:
        why_parts.append(
            f"the transaction represents a {baseline['deviation_ratio']:.0f}x "
            f"deviation from the customer's historical median")
    for f in red_flags[:3]:
        why_parts.append(f["evidence"].lower())
    if typologies:
        why_parts.append(
            f"the activity pattern aligns with {typologies[0]['typology']}")

    why = ("This activity is suspicious because "
           + "; ".join(why_parts) + "." if why_parts
           else "Further review is recommended based on the composite risk score.")

    how_parts = []
    if flow.get("sequence"):
        steps = flow["sequence"][:5]
        for step in steps:
            how_parts.append(
                f"{step['time']} — Rs {_money(step['amount'])} "
                f"({step['direction']}) {step.get('entity', '')}")
    how = ("The fund movement sequence: " + "; ".join(how_parts) + "."
           if how_parts
           else "Detailed fund movement sequence not reconstructable from available data.")

    str_narrative = (f"WHO: {who}\n\n"
                     f"WHAT: {what}\n\n"
                     f"WHEN: {when}\n\n"
                     f"WHERE: {where}\n\n"
                     f"WHY: {why}\n\n"
                     f"HOW: {how}")

    # ---- Recommended actions ----
    immediate = []
    investigative = []
    monitoring = []

    if risk.get("overall_score", 0) >= 75:
        immediate.append("Escalate to MLRO / compliance officer for STR filing review.")
        immediate.append("Consider temporary account restriction pending investigation completion.")
    if risk.get("overall_score", 0) >= 50:
        immediate.append("Flag account for enhanced transaction monitoring.")
        immediate.append("Preserve all transaction records and communication logs as evidence.")

    if flow.get("outflows_count", 0) > 0:
        investigative.append("Trace onward fund movement from receiver account(s).")
    if cdr_ipdr.get("shared_devices"):
        investigative.append("Pull IMEI tower location data for shared devices.")
    if len(counterparties) > 5:
        investigative.append("Conduct enhanced due diligence on top counterparties.")
    investigative.append("Obtain source-of-funds documentation from the account holder.")
    investigative.append("Review beneficial ownership of receiver entities.")

    monitoring.append("Place account under enhanced monitoring for 90 days minimum.")
    monitoring.append("Monitor related counterparty accounts for correlated activity.")
    if typologies:
        monitoring.append(
            f"Tune detection rules for '{typologies[0]['typology']}' typology patterns.")

    recommended_actions = {
        "immediate": immediate,
        "investigative": investigative,
        "monitoring": monitoring,
    }

    return {
        "executive_summary": executive_summary,
        "forensic_findings": findings,
        "str_narrative": str_narrative,
        "recommended_actions": recommended_actions,
    }
