"""Configurable ensemble weights for the hybrid fraud detection engine.

The Master Prompt requires the ensemble to be *configurable* rather than
hard-coded: every intelligence engine (rules, ML, behaviour, temporal,
graph, entity, telecom, internet, money-flow) contributes a normalised
0-100 score and the final composite is a weighted combination.

Weights are read from `APP_HYBRID_*` environment variables so operators can
re-weight the engine without code changes (e.g. a telecom-heavy dataset can
raise the telecom weight).  Unknown/empty entries fall back to the defaults.
"""

from __future__ import annotations

import os
import re

_DEFAULTS = {
    # Transaction-level composite (weights renormalised to 1.0 internally).
    "txn_rules": 0.30,       # deterministic rule engine
    "txn_ml": 0.20,          # txn-level ML (extreme-feature z-magnitude)
    "txn_behaviour": 0.25,   # customer behavioural profile deviation
    "txn_temporal": 0.10,    # sliding-window temporal correlation
    "txn_telecom": 0.10,     # call-assist / communication context
    "txn_internet": 0.05,    # IPDR / device context
    # Account-level composite.
    "acc_rules": 0.30,       # fraud_heat deterministic rules
    "acc_ml": 0.25,          # ML ensemble (IF, LOF, DBSCAN, HDBSCAN, OCSVM, PCA)
    "acc_behaviour": 0.10,   # behavioural profile deviation
    "acc_temporal": 0.05,    # temporal concentration
    "acc_graph": 0.15,       # money-flow graph analytics
    "acc_entity": 0.10,      # unified entity risk (shared phone/IMEI/IP/beneficiary)
    "acc_moneyflow": 0.05,   # N-hop money-flow scenarios
    # Entity-level composite.
    "ent_ml": 0.35,          # shared-entity concentration anomalies
    "ent_graph": 0.30,       # entity graph centrality/community
    "ent_temporal": 0.10,    # temporal concentration
    "ent_telecom": 0.15,     # call-network structure
    "ent_internet": 0.10,    # IP/device sharing
}

_NAME_RE = re.compile(r"^APP_HYBRID_([A-Z_]+)$")


_CACHED_WEIGHTS: dict[str, float] | None = None

def _env_weights() -> dict[str, float]:
    out = {}
    for key, value in os.environ.items():
        if key.startswith("APP_HYBRID_"):
            name = key[11:].lower()
            if name in _DEFAULTS:
                try:
                    out[name] = max(0.0, float(value))
                except ValueError:
                    pass
    return out


def hybrid_weights() -> dict[str, float]:
    global _CACHED_WEIGHTS
    if _CACHED_WEIGHTS is None:
        weights = dict(_DEFAULTS)
        weights.update(_env_weights())
        _CACHED_WEIGHTS = weights
    return _CACHED_WEIGHTS


def clear_weights_cache() -> None:
    global _CACHED_WEIGHTS
    _CACHED_WEIGHTS = None


def weight(name: str) -> float:
    return hybrid_weights().get(name, 0.0)


def renormalise(values: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Weighted sum of present scores, renormalised by the weight total.

    Missing engines simply drop out of the sum (their weight is excluded),
    so a bundle without IPDR data never loses score mass.
    """
    if weights is None:
        weights = hybrid_weights()
    num = sum(weights[k] * (v if 0.0 <= v <= 100.0 else max(0.0, min(100.0, v)))
              for k, v in values.items())
    den = sum(weights[k] for k in values)
    if den <= 0:
        return 0.0
    return round(min(100.0, num / den), 2)
