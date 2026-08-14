# Risk & Anomaly Engine

Tri-Netra Forensics employs a multi-stage Risk Engine (`backend/risk/`) to automatically flag suspicious activity without requiring manual analyst queries. It combines deterministic rules with unsupervised machine learning.

## 1. Deterministic Rule Engine (`scenarios.py`)

The rule engine executes rigid, logic-based checks against the fused dataset. It contains 22 predefined laundering and mule-account scenarios.

### Key Scenarios Supported:
* **Rapid In-and-Out**: Funds arrive in an account and >90% are withdrawn or transferred to a secondary account within 10 minutes.
* **Structuring (Smurfing)**: Multiple small deposits just below the reporting threshold (e.g., ₹49,000) over a short period.
* **Layering**: A rapid chain of transfers across 3 or more accounts ($A \to B \to C \to D$).
* **Odd-Hour Activity**: High-volume transactions occurring between 1:00 AM and 4:00 AM local time.
* **Circular Flow**: Funds originate at Account A, pass through intermediary accounts, and return to Account A (detected via Graph Intelligence).

## 2. 11-Model Machine Learning Anomaly Detection (`ensemble.py`)

Deterministic rules can be evaded by careful criminals. The ML engine establishes behavioral baselines and flags statistical deviations using an **11-model hybrid ensemble**:

### Unsupervised Cold-Start Detectors (7 Models)
- **Isolation Forest**: Identifies global structural outliers in transaction velocity and volume.
- **Local Outlier Factor (LOF)**: Measures local density deviations vs. network peers.
- **DBSCAN & HDBSCAN**: Identifies dense cluster baselines and flags isolated noise points.
- **One-Class SVM**: RBF-kernel margin outlier detection in high-dimensional feature space.
- **PCA Reconstruction Error**: Identifies accounts unrepresentable in the principal subspace.
- **Z-Score Baseline**: Extreme-feature statistical thresholding.

### Supervised Detectors (4 Models - Ground Truth Mode)
- **Random Forest**, **XGBoost**, **LightGBM**, **CatBoost** classifiers trained dynamically on ground-truth feedback.

## 3. High-Performance Behavioral Optimization & Background Prefetching
- **Indexed Temporal Checks**: $O(1)$ constant-time bisected range checks and `calls_by_phone_day` pre-indexing eliminate legacy $O(N_{\text{calls}} \times N_{\text{txns}})$ loops.
- **Proactive Background Prefetching**: When the pipeline hits `ANOMALIES_READY`, alerts are pre-warmed in the background. Clicking the Anomaly tab loads instantly with **0ms delay**.

## 4. Risk Scoring & Aggregation
The Risk Engine aggregates signals from rules, ML models, temporal patterns, and telecom/IPDR metadata to produce a final `risk_score` (0.0 to 100.0) for every transaction, account, and phone entity. Thresholds automatically surface high-risk alerts to the investigator's Anomaly Feed.
