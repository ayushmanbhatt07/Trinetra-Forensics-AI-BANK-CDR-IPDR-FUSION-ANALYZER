# Risk & Anomaly Detection Engine

Tri-Netra Forensics employs a multi-stage, hybrid Risk Engine (`backend/risk/`) to automatically flag money laundering, mule rings, and behavioral anomalies without requiring manual analyst searching.

---

## 1. 11-Model Machine Learning Ensemble (`backend/risk/ensemble.py`)

To eliminate single-point-of-failure heuristic rules, the platform deploys a concurrent **11-model hybrid ensemble**:

### 🔵 Unsupervised Detectors (7 Models — Cold Start / Unlabeled Data)
All unsupervised detectors evaluate normalized feature matrices in real-time:
1. **Isolation Forest** (`sklearn.ensemble`): Isolates structural outliers across multidimensional transaction volumes and velocity spaces.
2. **Local Outlier Factor (LOF)** (`sklearn.neighbors`): Measures local density variations against peer account distributions.
3. **DBSCAN** (`sklearn.cluster`): Identifies dense normal clusters and isolates irregular noise points.
4. **HDBSCAN** (`hdbscan`): Hierarchical density clustering capable of adapting to varying dataset distributions.
5. **One-Class SVM** (`sklearn.svm`): RBF-kernel margin outlier detection for nonlinear transaction boundaries.
6. **PCA Reconstruction Error** (`sklearn.decomposition`): Flags accounts with high reconstruction loss in the principal subspace.
7. **Z-Score Baseline** (`numpy`): Extreme-value statistical thresholding for transaction volumes and burst rates.

### 🟠 Supervised Ground-Truth Detectors (4 Models — Active Benchmarking)
Fitted dynamically when evaluating against ground-truth validation splits:
1. **Random Forest Classifier** (`sklearn.ensemble`): Non-linear decision tree voting over 20+ forensic account features.
2. **XGBoost** (`xgboost`): Gradient-boosted decision trees optimized for sparse financial indicators.
3. **LightGBM** (`lightgbm`): Fast histogram-based gradient boosting.
4. **CatBoost** (`catboost`): High-accuracy categorical handling for telecom carrier and IFSC features.

---

## 2. Deterministic Scenario Typology Classifier (`backend/risk/scenarios.py`)

Translates mathematical anomaly scores into the language of legal and financial investigators:
- **Rapid In-and-Out**: Funds deposited and >90% withdrawn/transferred within 10 minutes (mule signature).
- **Structuring / Smurfing**: High-frequency transactions deliberately sized just below statutory reporting thresholds (e.g. ₹49,000).
- **Layering**: Funds transferred across $\ge 3$ intermediate accounts in rapid succession ($A \to B \to C \to D$).
- **Circular Flow**: Funds originating from Account A pass through intermediary nodes and return to Account A.
- **Call-Assisted Fraud**: Voice or SMS communications immediately preceding a high-value transfer.
- **Shared Device Fraud**: Multiple distinct bank accounts accessed via the same IMEI, IMSI, or IP address.
- **SIM Swap / Device Change**: Cellular IMSI/IMEI identifiers changing shortly before high-value withdrawals.
- **Dormant Account Activation**: Long-inactive bank accounts suddenly experiencing high-velocity credit inflows.

---

## 3. Hybrid Risk Composite Scoring (`backend/risk/hybrid.py`)

Computes a calibrated 0–100 risk score with per-component explainability:
$$\text{Composite Score} = w_{\text{rules}} S_{\text{rules}} + w_{\text{ML}} S_{\text{ML}} + w_{\text{beh}} S_{\text{beh}} + w_{\text{temp}} S_{\text{temp}} + w_{\text{tel}} S_{\text{tel}} + w_{\text{net}} S_{\text{net}}$$

- **Banding**:
  - `CRITICAL`: Score $\ge 75$ (Immediate priority alert)
  - `HIGH`: Score $50 - 74$ (Elevated risk)
  - `MEDIUM`: Score $25 - 49$ (Monitoring required)
  - `LOW`: Score $< 25$ (Normal baseline)
- **Explainability**: Every alert includes concrete forensic reasons, model components, and evidence pointers.
