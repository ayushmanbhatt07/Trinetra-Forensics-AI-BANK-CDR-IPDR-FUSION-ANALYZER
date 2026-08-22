"""Hybrid ML ensemble of anomaly detectors.

Each detector emits a per-account anomaly score normalised to 0-100 by
rank-percentile (the fraction of accounts that are *less* anomalous), so
every model's output is comparable regardless of distribution.  The
ensemble score is the mean of the available detectors.

Unsupervised detectors (always available):
  * IsolationForest          — sklearn.ensemble
  * LOF                      — local outlier factor (sklearn.neighbors)
  * DBSCAN                   — noise points + distance-to-nearest-core
  * HDBSCAN                  — hdbscan.outlier_scores_
  * One-Class SVM            — negative decision function (RBF)
  * PCA                      — reconstruction error in the principal subspace
  * z-score                  — extreme-feature baseline

Supervised detectors (fitted only when ground-truth transaction ids are
provided, e.g. by the validation harness — never in the live API):
  * RandomForest / XGBoost / LightGBM / CatBoost classifiers over account
    features, trained on a stratified train split of the GT and scored with
    the positive-class probability.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import time

from .features import ACCOUNT_FEATURES, account_features, _safe_log1p

logger = logging.getLogger(__name__)

UNSUPERVISED_DETECTORS = (
    "isolation_forest", "lof", "dbscan", "hdbscan", "one_class_svm", "pca",
    "zscore",
)
SUPERVISED_DETECTORS = ("random_forest", "xgboost", "lightgbm", "catboost")
ALL_DETECTORS = UNSUPERVISED_DETECTORS + SUPERVISED_DETECTORS

_GT_TRAIN_FRAC = 0.7
_GT_RANDOM_STATE = 42


# Pre-import all heavy ML dependencies at module level to prevent CPython thread import race conditions
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor, NearestNeighbors
    from sklearn.cluster import DBSCAN
    from sklearn.svm import OneClassSVM
    from sklearn.decomposition import PCA
except Exception as _e:
    logger.warning("Error pre-importing sklearn models: %s", _e)

try:
    import hdbscan
except Exception:
    hdbscan = None


def _rank_normalise(anomaly: np.ndarray) -> np.ndarray:
    """0-100 score = percentile rank of anomaly strength."""
    if anomaly.size == 0:
        return np.zeros(0)
    order = anomaly.argsort()
    ranks = np.empty_like(anomaly, dtype=float)
    ranks[order] = np.arange(anomaly.size)
    if anomaly.size > 1:
        ranks /= anomaly.size - 1
    return ranks * 100.0


def _run_unsupervised(X: np.ndarray) -> dict[str, np.ndarray]:
    """Returns detector -> 0-100 anomaly score per row (lower = normal).
    
    All independent detectors run concurrently to reduce wall-clock time.
    """
    out: dict[str, np.ndarray] = {}
    n = len(X)
    if n < 4:
        return out

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from backend import config

    def _isolation_forest():
        t0 = time.time()
        logger.info("[ANOMALY] IsolationForest started")
        try:
            forest = IsolationForest(n_estimators=50, max_samples=min(512, n),
                                     contamination=0.1, random_state=42, n_jobs=1)
            pred = forest.fit_predict(X)
            raw = -forest.score_samples(X)
            raw[pred == 1] = 0.0
            logger.info(f"[ANOMALY] IsolationForest finished: {time.time() - t0:.2f}s")
            return "isolation_forest", _rank_normalise(raw)
        except Exception as exc:
            logger.warning("[ANOMALY] IsolationForest failed: %s", exc)
            return None

    def _lof():
        t0 = time.time()
        logger.info("[ANOMALY] LOF started")
        try:
            lof = LocalOutlierFactor(n_neighbors=min(20, max(2, n - 1)),
                                     contamination=0.1, novelty=False, n_jobs=1)
            lof.fit_predict(X)
            logger.info(f"[ANOMALY] LOF finished: {time.time() - t0:.2f}s")
            return "lof", _rank_normalise(-lof.negative_outlier_factor_)
        except Exception as exc:
            logger.warning("[ANOMALY] LOF failed: %s", exc)
            return None

    def _dbscan():
        t0 = time.time()
        logger.info("[ANOMALY] DBSCAN started")
        try:
            db = DBSCAN(eps=1.5, min_samples=5, n_jobs=1).fit(X)
            labels = db.labels_
            core = db.core_sample_indices_
            raw_db = np.zeros(n)
            noise_mask = (labels == -1)
            if noise_mask.any() and len(core) > 0:
                nn = NearestNeighbors(n_neighbors=1, algorithm='auto', n_jobs=1).fit(X[core])
                dists, _ = nn.kneighbors(X[noise_mask])
                raw_db[noise_mask] = np.maximum(0.0, 3.0 - dists.flatten())
            elif noise_mask.any():
                raw_db[noise_mask] = 3.0
            logger.info(f"[ANOMALY] DBSCAN finished: {time.time() - t0:.2f}s")
            return "dbscan", _rank_normalise(raw_db)
        except Exception as exc:
            logger.warning("[ANOMALY] DBSCAN failed: %s", exc)
            return None

    def _hdbscan():
        t0 = time.time()
        logger.info("[ANOMALY] HDBSCAN started")
        try:
            if hdbscan is None:
                return None
            hd = hdbscan.HDBSCAN(min_cluster_size=min(10, max(3, n // 20)),
                                 prediction_data=True, core_dist_n_jobs=1)
            hd.fit(X)
            raw_hd = getattr(hd, "outlier_scores_", np.zeros(n))
            if raw_hd is None or len(raw_hd) != n:
                raw_hd = np.zeros(n)
            logger.info(f"[ANOMALY] HDBSCAN finished: {time.time() - t0:.2f}s")
            return "hdbscan", _rank_normalise(raw_hd)
        except Exception as exc:
            logger.warning("[ANOMALY] HDBSCAN failed: %s", exc)
            return None

    def _ocsvm():
        t0 = time.time()
        logger.info("[ANOMALY] OneClassSVM started")
        try:
            max_svm = 1500
            if n > max_svm:
                idx = np.random.default_rng(42).choice(n, max_svm, replace=False)
                X_sub = X[idx]
            else:
                X_sub = X
            svm = OneClassSVM(nu=0.1, kernel="rbf", gamma="scale")
            svm.fit(X_sub)
            logger.info(f"[ANOMALY] OneClassSVM finished: {time.time() - t0:.2f}s")
            return "one_class_svm", _rank_normalise(-svm.decision_function(X))
        except Exception as exc:
            logger.warning("[ANOMALY] OneClassSVM failed: %s", exc)
            return None

    def _pca():
        t0 = time.time()
        logger.info("[ANOMALY] PCA started")
        try:
            k = min(12, max(2, X.shape[1] - 1), n - 1)
            pca = PCA(n_components=k)
            proj = pca.fit_transform(X)
            recon = pca.inverse_transform(proj)
            logger.info(f"[ANOMALY] PCA finished: {time.time() - t0:.2f}s")
            return "pca", _rank_normalise(np.linalg.norm(X - recon, axis=1))
        except Exception as exc:
            logger.warning("[ANOMALY] PCA failed: %s", exc)
            return None

    def _zscore():
        t0 = time.time()
        logger.info("[ANOMALY] ZScore started")
        try:
            z = np.abs((X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9))
            logger.info(f"[ANOMALY] ZScore finished: {time.time() - t0:.2f}s")
            return "zscore", _rank_normalise(z.max(axis=1))
        except Exception as exc:
            logger.warning("[ANOMALY] ZScore failed: %s", exc)
            return None

    # Removed _lof, _dbscan, and _hdbscan (O(N^2) distance calculations) for latency optimization
    detectors = [_isolation_forest, _ocsvm, _pca, _zscore]
    with ThreadPoolExecutor(max_workers=config.max_workers()) as ex:
        futures = [ex.submit(fn) for fn in detectors]
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    name, scores = result
                    out[name] = scores
            except Exception as exc:
                logger.warning("[ANOMALY] Detector worker raised: %s", exc)

    return out


def _run_supervised(X: np.ndarray, y: np.ndarray,
                    detectors: tuple[str, ...]) -> dict[str, np.ndarray]:
    """Train supervised models on a stratified split; score every row."""
    out: dict[str, np.ndarray] = {}
    n = len(X)
    if n < 16 or y.sum() < 5 or (y == 0).sum() < 5:
        return out
    from sklearn.model_selection import train_test_split
    X_tr, _, y_tr, _ = train_test_split(
        X, y, test_size=1 - _GT_TRAIN_FRAC,
        stratify=y, random_state=_GT_RANDOM_STATE)
    if y_tr.sum() < 3 or (y_tr == 0).sum() < 3:
        return out

    def proba(fit, X_all):
        return fit.predict_proba(X_all)[:, 1]

    for name in detectors:
        try:
            if name == "random_forest":
                from sklearn.ensemble import RandomForestClassifier
                m = RandomForestClassifier(n_estimators=200, random_state=42,
                                           n_jobs=1, class_weight="balanced")
            elif name == "xgboost":
                from xgboost import XGBClassifier
                m = XGBClassifier(n_estimators=200, max_depth=4, seed=42,
                                  n_jobs=1, eval_metric="logloss",
                                  verbosity=0)
            elif name == "lightgbm":
                from lightgbm import LGBMClassifier
                m = LGBMClassifier(n_estimators=200, max_depth=4,
                                   random_state=42, n_jobs=1, verbose=-1)
            else:  # catboost
                from catboost import CatBoostClassifier
                m = CatBoostClassifier(iterations=200, depth=4,
                                       random_seed=42, verbose=False)
            m.fit(X_tr, y_tr)
            out[name] = _rank_normalise(proba(m, X))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s unavailable: %s", name, exc)
    return out


def ensemble_scores(bundle: dict, gt_transaction_ids: Optional[set] = None,
                    min_txns: int = 1) -> dict:
    """Per-account ensemble anomaly scores.

    Returns {
      "fitted": bool,
      "accounts": [{account_no, ensemble_score, per_detector: {name: score}}],
      "detectors": [names actually fitted],
    }
    """
    rows = account_features(bundle)
    rows = [r for r in rows if r["txn_count"] >= min_txns]
    if len(rows) < 4:
        return {"fitted": False, "accounts": [], "detectors": []}

    X = _safe_log1p(np.array(
        [[float(r[f]) for f in ACCOUNT_FEATURES] for r in rows]))
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)

    per_det = _run_unsupervised(X)
    if gt_transaction_ids:
        bank = bundle.get("bank", [])
        by_acc: dict[str, set] = {}
        for r in bank:
            acc = r.get("account_no") or ""
            tid = r.get("txn_id") or ""
            if acc and tid:
                by_acc.setdefault(acc, set()).add(tid)
        y = np.array([1 if by_acc.get(r["account_no"], set())
                      & gt_transaction_ids else 0 for r in rows])
        per_det.update(_run_supervised(X, y, SUPERVISED_DETECTORS))

    accounts = []
    for i, r in enumerate(rows):
        det = {name: round(float(score[i]), 2)
               for name, score in per_det.items()}
        scores = [v for v in det.values() if v >= 0]
        ensemble = round(float(np.mean(scores)), 2) if scores else 0.0
        accounts.append({
            "account_no": r["account_no"],
            "ensemble_score": ensemble,
            "per_detector": det,
        })
    accounts.sort(key=lambda a: -a["ensemble_score"])
    return {"fitted": True, "accounts": accounts,
            "detectors": list(per_det.keys())}
