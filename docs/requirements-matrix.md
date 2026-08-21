# Requirements Traceability Matrix

This document maps every official requirement from **ERH26_PS_03** to its implementation in the Tri-Netra Forensics codebase.

---

## I. Multi-Format Ingestion
| Requirement | Implemented In | UI Location | Capability & Forensic Coverage |
| :--- | :--- | :--- | :--- |
| **Heterogeneous Bank Statements** (PDF, Excel, CSV) | `backend/parsers_bank.py`<br>`backend/parsers/bank.py` | `Ingest Page` | Supports 14 bank layout dialects (Axis, HDFC, SBI, ICICI, PNB, Kotak, Bandhan, Federal, Union, Utkarsh, Yes, Associate, City Union, Central Bank) with `pdfplumber` geometric layout extraction. |
| **CDR & IPDR Ingestion** | `backend/parsers_cdr.py`<br>`backend/parsers_ipdr.py` | `Ingest Page` | Native ingestion for Airtel, Jio (Nodal & VVM), Vodafone Idea (Vi), SDR, and IPv4/IPv6 IPDR logs. |
| **Schema Auto-Detection** | `backend/detect/engine.py`<br>`backend/detect/fingerprints.py` | `Pipeline Status` | Automatic format classification via token fingerprints, IFSC patterns, and layout geometry. |
| **Cybercrime Complaint Ledger** | `backend/pipeline.py` | `Ingest / Risk` | Parses NCRP `all_account_complain.csv` logs, linking known criminal beneficiary accounts. |

---

## II. Cross-Dataset Fusion
| Requirement | Implemented In | UI Location | Capability & Forensic Coverage |
| :--- | :--- | :--- | :--- |
| **Unified Event Timeline** | `backend/fusion.py`<br>`backend/events.py` | `Timeline Page` | Unified chronological stream merging bank transactions, voice calls, SMS, and IP sessions. |
| **Temporal Coincidence Window** | `backend/fusion.py`<br>`backend/risk/temporal.py` | `Fused View`<br>`Anomalies` | Correlates events within a sliding window ($\pm 3600\text{s}$) to detect Call-Assisted Fraud. |
| **Cross-Domain Entity Linking** | `backend/normalise.py`<br>`backend/fusion.py` | `Entity Search`<br>`Network Graph` | Resolves links across Bank Account $\leftrightarrow$ Phone $\leftrightarrow$ CDR Target $\leftrightarrow$ IMEI/IMSI $\leftrightarrow$ IPDR Session. |

---

## III. Anomaly & Pattern Detection
| Requirement | Implemented In | UI Location | Capability & Forensic Coverage |
| :--- | :--- | :--- | :--- |
| **11-Model Machine Learning Ensemble** | `backend/risk/ensemble.py`<br>`backend/risk/ml.py` | `Anomaly Feed`<br>`Scoring Panel` | 7 Unsupervised (Isolation Forest, LOF, DBSCAN, HDBSCAN, OCSVM, PCA, Z-Score) + 4 Supervised (Random Forest, XGBoost, LightGBM, CatBoost). |
| **Deterministic Scenario Typologies** | `backend/risk/scenarios.py` | `Anomaly Feed` | 22 named legal/forensic typologies: Rapid In-Out, Structuring, Smurfing, Layering, Circular Flow, Mule, SIM Swap, Device Change. |
| **Risk Scoring & Aggregation** | `backend/risk/hybrid.py` | `Entity Dossier`<br>`Anomalies` | Calibrated 0–100 risk score with per-component breakdowns (`rules`, `ml`, `behaviour`, `temporal`, `telecom`, `internet`). |
| **Mule Account Signatures** | `backend/behavioural.py`<br>`backend/risk/moneyflow.py` | `Overview`<br>`Network Graph` | Identifies zero-balance pass-through accounts and high-velocity money dispersion. |

---

## IV. Visualization & Reporting
| Requirement | Implemented In | UI Location | Capability & Forensic Coverage |
| :--- | :--- | :--- | :--- |
| **Money Flow & Communication Graphs** | `backend/graphs.py`<br>`frontend/components/` | `Network Graph` | NetworkX directed multigraphs rendered in 2D and 3D with force-directed physics, community clustering, and circular flow detection. |
| **Global Entity Search & Filtering** | `backend/api.py`<br>`frontend/app/` | `Entity Search`<br>`Global Filter` | Multi-field search across Phone, Account, IFSC, IMEI, IMSI, IP, and Beneficiary Name with date/amount range filters. |
| **Exportable Forensic Reports** | `backend/report.py`<br>`backend/str_engine.py` | `Reports Page` | High-fidelity, court-admissible PDF & DOCX reports with automated evidence ledgers. |

---

## V. Bonus Features Implemented
| Requirement | Implemented In | UI Location | Capability & Forensic Coverage |
| :--- | :--- | :--- | :--- |
| **Automated FIU-IND STR Generation** | `backend/str_engine.py`<br>`backend/str_narrative.py` | `STR Generator` | Generates official Suspicious Transaction Reports with automated forensic narratives, AML typology mapping, and regulatory layouts. |
| **Autonomous AI Copilot (Dual-Pathway)** | `investigative_copilot/` | `AI Copilot Modal` | Grounded RAG with Groq/OpenRouter multi-key rotation, multi-language support (English/Hindi/Gujarati), and zero hallucination. |
| **3D Semantic Reasoning Tree (USP)** | `investigative_copilot/`<br>`frontend/components/` | `AI Copilot View` | Dynamic 3D WebGL semantic tree displaying case entities, anomaly branches, and supporting evidence nodes. |
