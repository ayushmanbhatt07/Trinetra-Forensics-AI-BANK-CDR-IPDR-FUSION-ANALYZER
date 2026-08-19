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

## 2. Machine Learning Anomaly Detection (`ensemble.py`)

Deterministic rules can be evaded by careful criminals. The ML engine establishes behavioral baselines and flags statistical deviations.

### Ensemble Approach
* **Isolation Forest**: Used to isolate extreme outliers in transaction velocity (count per hour) and volume (amount distribution). It assigns an anomaly score from 0 to 1 to every entity.
* **Local Outlier Factor (LOF)**: Measures local density deviations, identifying accounts that behave drastically differently from their immediate network peers.

## 3. Risk Scoring & Aggregation
The Risk Engine aggregates signals from both the rules and the ML models to produce a final `risk_score` (0.0 to 1.0) for every entity.
- Base score + (Rule weight * triggers) + (ML anomaly score * weight).
Entities exceeding a defined threshold (e.g., 0.75) are surfaced to the top of the investigator's Anomaly Feed.
