"""Unified risk engine: fuses rules + ML ensemble + graph analytics.

Per account:  A = w_rule*rule_heat + w_ml*ml_ensemble + w_graph*graph_score
Per txn:      T = max(behavioural_score, w_acc * account_composite,
                      w_ml_txn * txn_ml_score)

The max() preserves the deterministic behavioural ordering (so genuinely
rule-flagged transactions never lose their alert) while account-level ML and
graph signals lift suspicious mule accounts and the txn-level ML lifts
statistically extreme transactions whose signals are too subtle for the
rules alone.

Risk taxonomy: SAFE [0,25) | LOW [25,50) | MEDIUM [50,70) | HIGH [70,85)
| CRITICAL [85,100].
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from ..behavioural import score_transactions
from ..fusion import fraud_heat
from .ensemble import ensemble_scores
from .features import txn_ml_scores
from .graph_features import graph_features, graph_score

logger = logging.getLogger(__name__)

_W_RULE, _W_ML, _W_GRAPH = 0.40, 0.35, 0.25
_W_ACC_LIFT = 0.60
_W_TXN_ML = 0.70

BAND_LABELS = ("SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
BAND_THRESHOLDS = (25, 50, 70, 85)


def risk_band(score: float) -> str:
    if score < BAND_THRESHOLDS[0]:
        return BAND_LABELS[0]
    if score < BAND_THRESHOLDS[1]:
        return BAND_LABELS[1]
    if score < BAND_THRESHOLDS[2]:
        return BAND_LABELS[2]
    if score < BAND_THRESHOLDS[3]:
        return BAND_LABELS[3]
    return BAND_LABELS[4]


def account_risk(bundle: dict, gt_transaction_ids: Optional[set] = None) -> dict:
    """Composite 0-100 risk per account with per-source breakdown."""
    heat = fraud_heat(bundle)
    heat_by_acc = {a["account_no"]: a for a in heat["accounts"]}

    ens = ensemble_scores(bundle, gt_transaction_ids)
    ml_by_acc = {a["account_no"]: a for a in ens["accounts"]}

    gfeats, gmeta = graph_features(bundle)
    gscore = graph_score(gfeats)

    accounts: list[dict] = []
    all_accs = set(heat_by_acc) | set(ml_by_acc) | set(gscore)
    for acc in sorted(all_accs):
        rule = float(heat_by_acc.get(acc, {}).get("score", 0.0))
        ml = float(ml_by_acc.get(acc, {}).get("ensemble_score", 0.0))
        graph = float(gscore.get(acc, 0.0))
        rule, ml, graph = (0.0 if not math.isfinite(x) else x
                           for x in (rule, ml, graph))
        w_rule = _W_RULE if heat_by_acc.get(acc) else 0.0
        w_ml = _W_ML if acc in ml_by_acc else 0.0
        w_graph = _W_GRAPH if acc in gscore else 0.0
        w_sum = w_rule + w_ml + w_graph
        if w_sum <= 0:
            composite = 0.0
        else:
            composite = (w_rule * rule + w_ml * ml + w_graph * graph) / w_sum
        composite = round(min(composite, 100.0), 2)
        accounts.append({
            "account_no": acc,
            "risk_score": composite,
            "risk_band": risk_band(composite),
            "components": {
                "rules": round(rule, 2),
                "ml_ensemble": round(ml, 2),
                "graph": round(graph, 2),
            },
            "ml_detectors": list(ml_by_acc.get(acc, {}).get("per_detector", {})),
            "flags": heat_by_acc.get(acc, {}).get("flags", []),
        })
    accounts.sort(key=lambda a: -a["risk_score"])
    return {
        "accounts": accounts,
        "detectors": ens.get("detectors", []),
        "graph": gmeta,
        "ensemble_fitted": ens.get("fitted", False),
    }


def transaction_risk(bundle: dict, gt_transaction_ids: Optional[set] = None,
                     min_score: float = 0.0) -> list[dict]:
    """Composite 0-100 risk per transaction, sorted descending.

    Extends the behavioural scorer output with `composite_score`,
    `account_risk` and `risk_components`; `risk_score` is the composite.
    """
    bank = bundle.get("bank", [])
    if not bank:
        return []
    behavioural = score_transactions(bundle)
    acc_risk = account_risk(bundle, gt_transaction_ids)
    by_acc = {a["account_no"]: a for a in acc_risk["accounts"]}
    txn_ml = txn_ml_scores(bundle)

    out = []
    for s in behavioural:
        acc = s.get("account_no") or ""
        acc_r = by_acc.get(acc, {})
        acc_score = float(acc_r.get("risk_score", 0.0))
        tml = float(txn_ml.get(s.get("transaction_id", ""), 0.0))
        composite = max(float(s["risk_score"]), _W_ACC_LIFT * acc_score,
                        _W_TXN_ML * tml)
        composite = round(min(composite, 100.0), 2)
        out.append({
            **s,
            "risk_score": composite,
            "risk_band": risk_band(composite),
            "composite_score": composite,
            "account_risk": acc_score,
            "txn_ml_score": tml,
            "risk_components": {
                "behavioural": float(s["risk_score"]),
                "txn_ml": tml,
                "account_composite": acc_score,
                "account_components": acc_r.get("components", {}),
            },
        })
    out.sort(key=lambda s: (-s["risk_score"], -s["txn_ml_score"],
                            -s["account_risk"]))
    if min_score > 0:
        out = [s for s in out if s["risk_score"] >= min_score]
    return out


def top_transactions(bundle: dict, limit: int = 50,
                     gt_transaction_ids: Optional[set] = None) -> list[dict]:
    return transaction_risk(bundle, gt_transaction_ids)[:limit]


# ---------------------------------------------------------------- caching

_cache: dict[tuple, dict] = {}


def _fingerprint(bundle: dict) -> tuple:
    bank = bundle.get("bank", [])
    ids = [r.get("txn_id") for r in bank[:3]]
    return (len(bank), len(bundle.get("cdr", [])), len(bundle.get("ipdr", [])),
            len(bundle.get("complaints", [])), tuple(ids))


def cached_account_risk(bundle: dict) -> dict:
    key = ("accounts", _fingerprint(bundle))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    result = account_risk(bundle)
    _cache[key] = result
    return result


def cached_transaction_risk(bundle: dict, min_score: float = 0.0) -> list[dict]:
    key = ("txns", _fingerprint(bundle), min_score)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    result = transaction_risk(bundle, min_score=min_score)
    _cache[key] = result
    return result


def clear_cache() -> None:
    _cache.clear()
