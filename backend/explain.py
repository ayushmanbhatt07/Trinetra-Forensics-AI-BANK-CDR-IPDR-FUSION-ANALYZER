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
    currency symbols, etc. Returns 0.0 when nothing is found.
    """
    for key in ("transaction_amount", "amount", "total_amount",
                "max_leg", "amount_usd", "credit", "debit", "volume"):
        raw = r.get(key)
        if raw is None:
            continue
        try:
            if isinstance(raw, (int, float)):
                val = float(raw)
                if math.isfinite(val):
                    return val
            cleaned = str(raw).replace(",", "").replace("₹", "").replace("Rs", "").replace("INR", "").strip()
            if cleaned:
                val = float(cleaned)
                if math.isfinite(val):
                    return val
        except (TypeError, ValueError):
            continue
    return 0.0


def plain_explainability(envelope: dict[str, Any], query: str = "") -> str:
    """Deterministic plain-English explainability block for co-pilot answers.

    Uses whatever evidence/records the query returned so the LLM narrative
    always has a grounded, human-readable companion summary.
    """
    records = envelope.get("records") or []
    top = records[:5]
    parts: list[str] = []

    if envelope.get("intent"):
        parts.append(f"Forensic Focus: {envelope['intent']}")

    if top:
        leads = []
        for r in top:
            txn = str(r.get("transaction_id") or r.get("txn_id") or r.get("id") or "").strip()
            acc = str(r.get("receiver_account_number") or r.get("sender_account_number")
                      or r.get("account_no") or r.get("receiver_account") or r.get("sender_account") or "").strip()
            name = str(r.get("receiver_customer_name") or r.get("sender_customer_name")
                       or r.get("customer_name") or r.get("name") or "").strip()
            phone = str(r.get("a_party_number") or r.get("b_party_number") or r.get("sender_phone_number")
                        or r.get("receiver_phone_number") or r.get("phone") or r.get("mobile") or "").strip()
            amt_val = _safe_amount(r)
            amt_str = f"₹{amt_val:,.2f}" if amt_val > 0 else ""
            mode = str(r.get("transaction_mode") or r.get("mode") or "").strip().upper()
            date_time = str(r.get("timestamp") or r.get("date") or r.get("call_start_time") or "").strip()

            tokens = []
            if acc:
                tokens.append(f"Account {acc}" + (f" ({name})" if name else ""))
            elif name:
                tokens.append(f"Entity {name}")
            elif phone:
                tokens.append(f"Phone {phone}")
            elif txn:
                tokens.append(f"Txn {txn}")
            else:
                tokens.append("Observation Node")

            if amt_str:
                tokens.append(f"Amount {amt_str}")
            if mode:
                tokens.append(f"Channel {mode}")
            if date_time:
                tokens.append(f"Time {date_time[:19]}")
            if txn and acc:
                tokens.append(f"ID: {txn}")
            if r.get("tx_count"):
                tokens.append(f"{r['tx_count']} txns")

            leads.append("• " + " | ".join(tokens))
        parts.append("Key Evidentiary Records:\n" + "\n".join(leads))

    if envelope.get("risk_summary"):
        parts.append(f"\nRisk Assessment: {envelope['risk_summary']}")
    elif envelope.get("executive_summary"):
        parts.append(f"\nExecutive Rationale: {envelope['executive_summary']}")

    if not parts:
        return ""
    return "\n\n".join(parts)

