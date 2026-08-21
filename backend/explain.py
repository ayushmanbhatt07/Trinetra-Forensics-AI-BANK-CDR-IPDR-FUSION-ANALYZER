"""Plain-English explainability for Tri-Netra Forensics (flagship spec).

Every rule and ML detector name emitted by the behavioural engine, the
hybrid risk engine and the fusion layer maps to an investigator-grade
sentence, so the anomaly feed and the co-pilot answer always say WHY a
transaction, account or call is suspicious — not just that it scored high.
"""

from __future__ import annotations

from typing import Any
import math

# Rule id -> plain-English explanation (verb phrase, lower case start).
RULE_PLAIN: dict[str, str] = {
    # --- behavioural rules ---
    "AMOUNT_VELOCITY_SPIKE": "the account suddenly moved far more money in a short window than it ever does, a classic mule-account acceleration",
    "TRANSACTION_BURST": "many transactions fired in a rapid burst around the same minute, typical of automated cash-out tools",
    "ROUND_AMOUNT": "the amount is an exact round figure, a known structuring trick used to evade value thresholds",
    "NEW_BENEFICIARY": "the money went to a beneficiary this customer had never paid before, with no prior relationship on record",
    "AMOUNT_PLUS_NEW_BENEFICIARY": "a large sum went to a brand-new beneficiary, combining two high-risk signals at once",
    "CUSTOMER_RELATIVE_AMOUNT_SPIKE": "the amount is far above this customer's own normal transaction size for the account",
    "ODD_HOUR_TRANSACTION": "the transaction happened at an unusual hour for this customer, outside their established activity pattern",
    "CUSTOMER_HOUR_DEVIATION": "the transaction time deviates sharply from the hours this customer normally transacts",
    "CALL_THEN_HIGH_VALUE_TRANSFER": "a call was made immediately before a high-value transfer, matching the classic scam coordination pattern",
    "CALL_THEN_NEW_BENEFICIARY": "a call to a previously unknown number was followed by money moving to a new beneficiary",
    "REPEATED_CALLS_BEFORE_TRANSACTION": "the phone repeatedly called numbers just before money moved, signalling live instruction between caller and receiver",
    "UNUSUAL_CALL_BEFORE_TRANSACTION": "an out-of-pattern call happened right before the transaction, linking telecom activity to the money movement",
    "UNUSUAL_LOCATION_CONTEXT": "the phone/device was seen in a location far outside this customer's usual geography near the transaction time",
    "NEW_DEVICE_AROUND_TRANSACTION": "a device the customer has never used before became active around the moment of the transaction",
    "IMSI_IMEI_PAIR_NOVELTY": "the IMSI/IMEI pairing was never seen before, indicating a new or cloned SIM in a different device",
    "NETWORK_SESSION_BURST_AROUND_TRANSACTION": "an internet session burst occurred on the device right around the transaction, matching online-fraud behaviour",
    "SUBTLE_MULTI_SOURCE_SUSPICIOUS_PATTERN": "several weak signals aligned across bank, call and network records — the combined pattern is unusual even though each signal alone is subtle",
    "NCRP_FRAUD_ACCOUNT": "the account is listed in the NCRP police fraud complaint ledger, so it carries a hard complaint boost",
    # --- fusion / money-flow rules ---
    "RAPID_PAYOUT": "money is being withdrawn or forwarded very quickly after it arrives, the signature of an off-ramp/mule account",
    "CIRCULAR_FLOW": "money moved in a circle through related accounts, an arrangement designed to make the trail look like legitimate commerce",
    "STRUCTURING": "amounts are kept just below reporting thresholds across many small deposits",
    "LAYERING": "funds are split and moved through several accounts in layers to obscure the original source",
    "DORMANT_ACTIVATED": "a long-dormant account suddenly became active with large volumes, often a rented or stolen account",
    "ACCOUNT_EXPOSURE": "the account appears across many unrelated transactions, suggesting shared control or a common operator",
    "COMPLAINT_HIT": "the entity matches the NCRP police complaint ledger",
    # --- ML ensemble detectors ---
    "isolation_forest": "the ML isolation-forest detector ranked this record among the most unusual in the dataset",
    "lof": "the local-outlier-factor detector found this record isolated from its neighbours' normal behaviour",
    "dbscan": "the density-based detector found this record in sparse, noise-like territory with few similar records around it",
    "hdbscan": "the hierarchical density detector assigned this record a high outlier score",
    "one_class_svm": "the one-class SVM model classified this record as outside the learned normal boundary",
    "pca": "the PCA reconstruction-error detector found this record poorly explained by the main data patterns",
    "random_forest": "the supervised random-forest model voted this record fraudulent",
    "xgboost": "the XGBoost model voted this record fraudulent",
    "lightgbm": "the LightGBM model voted this record fraudulent",
    "catboost": "the CatBoost model voted this record fraudulent",
    "ensemble_score": "the combined ML ensemble score is well above the dataset norm",
}

# Detector-level fallbacks for the risk engine's per-detector breakdown.
DETECTOR_PLAIN: dict[str, str] = {
    "behaviour": "behavioural rule scoring",
    "rules": "rule-based pattern checks",
    "temporal": "time-series anomaly checks",
    "profile": "customer-profile deviation checks",
    "moneyflow": "money-flow network checks",
    "graph": "graph-centrality and linkage checks",
    "ml": "the ML ensemble (isolation forest, LOF, DBSCAN, HDBSCAN, one-class SVM, PCA)",
    "entity": "entity-risk concentration checks",
}


def _lookup(rule: str, fallback: str = "") -> str:
    key = rule.strip()
    phrase = RULE_PLAIN.get(key) or RULE_PLAIN.get(key.lower())
    if phrase:
        return phrase
    if fallback:
        return fallback
    return f"the signal '{key}' was triggered by the detection engine"


def plain_reason(rules: Any, breakdown: Any = None, amount: float = 0.0,
                 transaction_id: str = "", confidence: float = 0.0) -> str:
    """Build one plain-English paragraph explaining why a record is flagged.

    ``rules`` may be a list, a stringified list, or None. ``breakdown`` is
    the optional per-rule [{rule, points, reason}] detail list.
    """
    if isinstance(rules, str):
        cleaned = rules.replace("[", "").replace("]", "").replace("'", "")
        rule_list = [r.strip() for r in cleaned.split(",") if r.strip()]
    else:
        rule_list = [r for r in (rules or []) if r]

    reason_by_rule: dict[str, str] = {}
    for d in breakdown or []:
        if isinstance(d, dict) and d.get("rule"):
            reason_by_rule[str(d["rule"]).strip()] = str(d.get("reason") or "")

    phrases = [_lookup(r, reason_by_rule.get(r.strip(), "")) for r in rule_list]

    amount_txt = ""
    if amount:
        try:
            val = float(amount)
            if math.isfinite(val):
                amount_txt = f" of ₹{val:,.0f}"
        except (ValueError, TypeError):
            pass
            
    head = (f"Transaction {transaction_id} is flagged suspicious{amount_txt} because: "
            if transaction_id else "This record is flagged suspicious because: ")
    if not phrases:
        tail = ("the combined risk model scored it far outside the normal "
                "behaviour of similar records in this dataset.")
    elif len(phrases) == 1:
        tail = phrases[0] + "."
    else:
        tail = "; ".join(f"({i}) {p}" for i, p in enumerate(phrases, 1)) + "."
        
    if confidence:
        try:
            cval = float(confidence)
            if math.isfinite(cval):
                tail += f" Model confidence is {cval * 100:.0f}%."
        except (ValueError, TypeError):
            pass
            
    return head + tail


def _safe_amount(r: dict[str, Any]) -> float:
    """Extract the best numeric amount from a copilot result row.

    Checks every known column name and robustly parses strings with commas,
    currency symbols, etc.  Returns 0.0 when nothing is found.
    """
    # Check in priority order — SQL results use 'transaction_amount',
    # the risk engine uses 'amount', aggregations use 'total_amount'.
    for key in ("transaction_amount", "amount", "total_amount",
                "max_leg", "amount_usd"):
        raw = r.get(key)
        if raw is None:
            continue
        try:
            if isinstance(raw, (int, float)):
                return float(raw)
            cleaned = str(raw).replace(",", "").replace("₹", "").replace("Rs", "").replace("INR", "").strip()
            if cleaned:
                return float(cleaned)
        except (TypeError, ValueError):
            continue
    return 0.0


def plain_explainability(envelope: dict[str, Any], query: str = "") -> str:
    """Intelligent plain-English explainability block for co-pilot answers."""
    risk_sum = envelope.get("risk_summary") or ""
    # If the LLM already provided a detailed, grounded forensic rationale, use it directly!
    if risk_sum and len(risk_sum.strip()) > 30 and not risk_sum.startswith("According to the risk engine"):
        return risk_sum.strip()

    records = envelope.get("records") or []
    top = records[:5]
    parts: list[str] = []

    if top:
        leads = []
        max_score = 0.0
        critical_evidence = []
        
        for r in top:
            txn = r.get("transaction_id") or r.get("txn_id") or ""
            acc = (r.get("receiver_account_number") or r.get("sender_account_number")
                   or r.get("account_no") or r.get("receiver_account") or "")
            amt_val = _safe_amount(r)
            who = f"Account {acc}" if acc else (f"Transaction {txn}" if txn else "Record")
            amt = f"Transfer of ₹{amt_val:,.2f}" if amt_val > 0 else "Transaction"
            mode = r.get("transaction_mode") or r.get("mode") or ""
            mode_txt = f" via {mode}" if mode else ""
            
            # Extract anomaly score
            score = float(r.get("risk_score") or r.get("composite_score") or 0.0)
            if score > max_score:
                max_score = score
            
            reasons = []
            # 1. Check if record contains rule breakdown from risk engine
            if isinstance(r.get("breakdown"), list) and r["breakdown"]:
                for b in r["breakdown"]:
                    if isinstance(b, dict) and b.get("reason"):
                        reasons.append(b["reason"])
                    elif isinstance(b, dict) and b.get("rule"):
                        reasons.append(_lookup(b["rule"]))
            elif r.get("rules_fired"):
                rules = r["rules_fired"]
                if isinstance(rules, str):
                    rules = [x.strip() for x in rules.replace("[", "").replace("]", "").replace("'", "").split(",") if x.strip()]
                for rf in rules:
                    reasons.append(_lookup(rf))
            
            # 2. Extract evidence strings (e.g. [CDR] 6 calls <= 60 min)
            if isinstance(r.get("evidence"), list):
                for ev in r["evidence"]:
                    if ev and ev not in critical_evidence:
                        critical_evidence.append(str(ev))
            
            # 3. Check value and mode threshold heuristics if no rules fired
            if not reasons:
                if amt_val >= 500000:
                    reasons.append("High-Value Transfer Exceeding ₹5,00,000")
                elif amt_val >= 90000:
                    reasons.append("Regulatory Reporting Threshold Proximity (₹1,00,000)")
                if "CASH" in str(mode).upper():
                    reasons.append("Cash Channel / Source Anonymity Risk")
                elif "UPI" in str(mode).upper() and amt_val >= 50000:
                    reasons.append("Rapid Velocity Retail Channel")
                
            reason_str = f" — *{'; '.join(reasons[:2])}*" if reasons else ""
            score_badge = f" [Risk: {score:.0f}/100]" if score > 0 else ""
            leads.append(f"• **{who}**: {amt}{mode_txt}{score_badge}{reason_str}")
            
        parts.append("**Forensic Evidence Breakdown:**\n" + "\n".join(leads))
        if critical_evidence:
            parts.append("**Telecom & Linkage Evidence:**\n" + "\n".join(f"• {ev}" for ev in critical_evidence[:3]))

    if risk_sum and not risk_sum.startswith("According to the risk engine"):
        parts.append(f"**Risk Assessment:** {risk_sum}")
    elif max_score >= 70:
        parts.append(f"**Risk Assessment:** Critical/High-risk anomaly pattern flagged (Risk Score: {max_score:.0f}/100). Exhibits behavioral deviations and telecom coordination.")
    elif len(records) > 0:
        parts.append("**Risk Assessment:** Activity exhibits high transaction value or volume velocity requiring active forensic verification.")

    return "\n\n".join(parts) if parts else "No critical anomalies detected for this entity."
