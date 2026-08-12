"""Hybrid risk engine: unified account/transaction risk scoring.

The engine fuses three independent signal families into a single 0-100
composite score with a SAFE / LOW / MEDIUM / HIGH / CRITICAL taxonomy:

  * deterministic rules       — behavioural transaction rules + account
                                fraud_heat (fusion layer),
  * ML ensemble               — IsolationForest, LOF, DBSCAN, HDBSCAN,
                                One-Class SVM, PCA reconstruction error, and
                                (when ground truth is available) supervised
                                RandomForest / XGBoost / LightGBM / CatBoost,
  * graph analytics           — PageRank / degree / betweenness / community
                                features plus Node2Vec embedding signals
                                over the account money-flow network.

On top of the composite sits the **Hybrid Multi-Stage Fraud Detection
Engine** (`hybrid.py`): behavioural profiling, temporal sliding windows,
telecom/internet correlation, money-flow N-hop analysis, unified entity
risk, named scenario detection and per-decision explainability — fused
through configurable weights (`weights.py`).
"""

from .engine import (account_risk, clear_cache, risk_band,
                     top_transactions, transaction_risk,
                     cached_account_risk, cached_transaction_risk)
from .features import (account_features, transaction_features, txn_ml_scores)
from .graph_features import graph_features, graph_score
from .hybrid import (clear_cache as clear_hybrid_cache, hybrid_account_risk,
                     hybrid_analyze, hybrid_analyze_fast, hybrid_entity_risk,
                     hybrid_transaction_risk,
                     explanations_for_account, explanations_for_entity,
                     explanations_for_txn)
from .weights import hybrid_weights, weight

__all__ = ["account_risk", "clear_cache", "risk_band", "top_transactions",
           "transaction_risk", "cached_account_risk", "cached_transaction_risk",
           "account_features", "transaction_features",
           "txn_ml_scores", "graph_features", "graph_score",
           "hybrid_analyze", "hybrid_analyze_fast", "hybrid_transaction_risk", "hybrid_account_risk",
           "hybrid_entity_risk", "explanations_for_txn",
           "explanations_for_account", "explanations_for_entity",
           "hybrid_weights", "weight", "clear_hybrid_cache"]
