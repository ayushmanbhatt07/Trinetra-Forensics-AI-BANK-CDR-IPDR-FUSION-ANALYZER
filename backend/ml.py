"""Unsupervised anomaly detection layer (scikit-learn).

fraud_heat() applies deterministic rules; this module adds the ML component
of the "Rules + ML" requirement — an IsolationForest over account-level
behavioural features:

  * txn count, total credit/debit, average and max amount,
  * unique counterparties, phones and UPI ids (entity breadth),
  * round-amount share, night-hour share, rapid payout count.

Output is a z-scored anomaly score per account; the detector is refit on
every request over the current bundle so it adapts to the dataset at hand
and never sees labels (fully unsupervised, cold-start safe).
"""

from __future__ import annotations

import numpy as np
import logging
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler

from .fusion import rapid_payouts

logger = logging.getLogger(__name__)

_FEATURES = (
    "txn_count", "total_credit", "total_debit", "avg_amount",
    "max_amount", "uniq_counterparties", "uniq_phones", "uniq_upi",
    "round_share", "night_share", "rapid_payouts",
    "dormant_activation", "merchant_diversity", "burst_indicator"
)


def _account_features(bundle: dict) -> list[dict]:
    bank = bundle.get("bank", [])
    night = 0
    agg: dict[str, dict] = {}
    for r in bank:
        acc = r.get("account_no") or ""
        if not acc:
            continue
        d = agg.setdefault(acc, {
            "account_no": acc, "credit": 0.0, "debit": 0.0, "amounts": [],
            "counterparties": set(), "phones": set(), "upis": set(),
            "round": 0, "night": 0, "txns": 0,
        })
        d["txns"] += 1
        amt = r.get("credit") or r.get("debit") or 0.0
        d["amounts"].append(amt)
        if r.get("credit"):
            d["credit"] += r["credit"]
        if r.get("debit"):
            d["debit"] += r["debit"]
        if r.get("receiver_account"):
            d["counterparties"].add(r["receiver_account"])
        for ph in (r.get("receiver_phone"), r.get("sender_phone")):
            if ph:
                d["phones"].add(ph)
        if r.get("upi_id"):
            d["upis"].add(r["upi_id"])
        if (r.get("debit") or 0) >= 1000 and (r.get("debit") or 0) % 5000 == 0:
            d["round"] += 1
        t = r.get("time") or ""
        if t and len(t) >= 5 and t[0] == "2":
            try:
                if int(t[:2]) >= 20:
                    d["night"] += 1
            except ValueError:
                pass

    rapids = {rp["account_no"] for rp in rapid_payouts(bundle)}
    rows = []
    for acc, d in agg.items():
        n = max(d["txns"], 1)
        rows.append({
            "account_no": acc,
            "txn_count": d["txns"],
            "total_credit": d["credit"],
            "total_debit": d["debit"],
            "avg_amount": sum(d["amounts"]) / n,
            "max_amount": max(d["amounts"]),
            "uniq_counterparties": len(d["counterparties"]),
            "uniq_phones": len(d["phones"]),
            "uniq_upi": len(d["upis"]),
            "round_share": d["round"] / n,
            "night_share": d["night"] / n,
            "rapid_payouts": 1 if acc in rapids else 0,
            
            # Incorporate new semantic features at the account level
            "merchant_diversity": len({r.get("merchant_name") for r in bank if r.get("account_no") == acc and r.get("merchant_name")}),
            "burst_indicator": max([r.get("feat_burst_indicator", 0) for r in bank if r.get("account_no") == acc] + [0]),
            "dormant_activation": max([r.get("feat_dormant_activation", 0) for r in bank if r.get("account_no") == acc] + [0]),
        })
    return rows


def _zscore_outliers(matrix: np.ndarray, contamination: float) -> set[int]:
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std[std == 0] = 1.0
    z = np.abs((matrix - mean) / std)
    mask = z.max(axis=1) >= 3.0
    return set(np.where(mask)[0].tolist())


def ml_outliers(bundle: dict, contamination: float = 0.05,
                min_txns: int = 5, cap: int = 100) -> dict:
    """Fit Ensemble (IsolationForest, LOF, OCSVM) over account features; return flagged accounts."""
    rows = _account_features(bundle)
    rows = [r for r in rows if r["txn_count"] >= min_txns]
    if len(rows) < 8:
        return {"fitted": False, "accounts": []}

    X = np.array([[float(r[f]) for f in _FEATURES] for r in rows])
    
    # Scale features for distance-based models (LOF, SVM)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(np.log1p(np.abs(X)))

    # 1. Isolation Forest
    iso = IsolationForest(n_estimators=200, contamination=contamination, random_state=42, n_jobs=1)
    iso_pred = iso.fit_predict(X_scaled)
    iso_scores = -iso.score_samples(X_scaled)  # higher is more anomalous
    
    # 2. Local Outlier Factor
    # Avoid n_neighbors > n_samples error
    n_neighbors = min(20, len(X_scaled) - 1)
    lof = LocalOutlierFactor(n_neighbors=n_neighbors, contamination=contamination, novelty=False)
    lof_pred = lof.fit_predict(X_scaled)
    lof_scores = -lof.negative_outlier_factor_
    
    # 3. One-Class SVM
    svm = OneClassSVM(nu=min(contamination, 0.5), kernel="rbf", gamma="scale")
    svm_pred = svm.fit_predict(X_scaled)
    svm_scores = -svm.score_samples(X_scaled)
    
    # Normalize scores to 0-1 for unified score
    def _norm(arr):
        mn, mx = arr.min(), arr.max()
        return (arr - mn) / (mx - mn + 1e-9)
        
    iso_n = _norm(iso_scores)
    lof_n = _norm(lof_scores)
    svm_n = _norm(svm_scores)
    
    # Unified Fraud Score (Ensemble average)
    unified_scores = (iso_n + lof_n + svm_n) / 3.0
    
    # Z-score extreme fallback
    z_flagged = _zscore_outliers(X_scaled, contamination)

    flagged = set(np.where(iso_pred == -1)[0].tolist()) | set(np.where(lof_pred == -1)[0].tolist()) | set(np.where(svm_pred == -1)[0].tolist()) | z_flagged

    accounts = []
    for i in sorted(flagged):
        r = rows[i]
        
        # Generate an AI-ready explanation block for this account's anomaly
        reasons = []
        if iso_pred[i] == -1: reasons.append("Isolation Forest (Global Shape Deviation)")
        if lof_pred[i] == -1: reasons.append("Local Outlier Factor (Density Deviation)")
        if svm_pred[i] == -1: reasons.append("One-Class SVM (Margin Outlier)")
        if r.get("rapid_payouts"): reasons.append("Rapid Payout Sequence Detected")
        if r.get("dormant_activation"): reasons.append("Dormant Account Reactivation")
        
        accounts.append({
            "account_no": r["account_no"],
            "txn_count": r["txn_count"],
            "total_credit": round(r["total_credit"], 2),
            "total_debit": round(r["total_debit"], 2),
            "avg_amount": round(r["avg_amount"], 2),
            "max_amount": round(r["max_amount"], 2),
            "counterparties": r["uniq_counterparties"],
            "phones": r["uniq_phones"],
            "round_share": round(r["round_share"], 3),
            "night_share": round(r["night_share"], 3),
            "rapid_payouts": r["rapid_payouts"],
            "unified_score": round(float(unified_scores[i] * 100), 2),
            "anomaly_explanation": f"Marked suspicious due to: {', '.join(reasons)}."
        })
        
    accounts.sort(key=lambda a: (-a["unified_score"], -a["max_amount"]))
    return {"fitted": True, "method": "ensemble_iso_lof_svm", "accounts": accounts[:cap]}
