# Requirements Traceability Matrix

This document maps the official functional requirements from **ERH26_PS_03** to their actual implementation modules within the Tri-Netra Forensics codebase.

## I. Multi-Format Ingestion
| Requirement | Actual Module | UI Location | Explanation |
|---|---|---|---|
| Parse heterogeneous bank statements (Excel, PDF, CSV) | `backend/parsers/parsers_bank.py` | Evidence Ingestion | Uses `pdfplumber` for PDF table extraction and `pandas` for Excel/CSV parsing. |
| Parse CDR and IPDR from major operators | `backend/parsers/parsers_cdr.py`, `parsers_ipdr.py` | Evidence Ingestion | Supports Jio, Airtel, Vi, BSNL formats. |
| Schema mapping/auto-detection | `backend/detect/fingerprints.py` | Backend Pipeline | Inspects file headers/geometry to assign the correct parser dynamically. |

## II. Cross-Dataset Fusion
| Requirement | Actual Module | UI Location | Explanation |
|---|---|---|---|
| Unified timeline linking calls, IPs, and transactions | `backend/events.py` | Unified Timeline | All parsed records are cast to the Unified Event model. |
| Detect temporal coincidences | `backend/fusion.py` | Fused Transactions | Scans the timeline using sliding temporal windows (e.g., 5-minute overlaps). |
| Link accounts and numbers via shared identifiers | `backend/normalise.py`, `backend/fusion.py` | Entity Search / Graph | Standardizes identifiers to E.164 and links entities sharing those identifiers. |

## III. Anomaly & Pattern Detection
| Requirement | Actual Module | UI Location | Explanation |
|---|---|---|---|
| Rules + ML for layering, rapid in/out, structuring | `backend/risk/scenarios.py`, `ensemble.py` | Anomaly Feed | Implements 22 deterministic rules alongside Isolation Forest and LOF ML models. |
| Risk scoring for accounts/numbers | `backend/risk/ensemble.py` | Entity Dossier | Aggregates rule triggers and ML signals into a single normalized score (0-1). |
| Mule-account behavioral signatures | `backend/behavioural.py` | Anomaly Feed | Detects classic mule patterns (high velocity, zero sustained balance). |

## IV. Visualization & Reporting
| Requirement | Actual Module | UI Location | Explanation |
|---|---|---|---|
| Money-flow and communication network graphs | `backend/graphs.py` | Network Intelligence | Constructs NetworkX graphs rendered in the UI via React Flow / Three.js. |
| Filter/search by entity | `backend/api.py` (`/api/entities/search`) | Entity Search | Global search bar supporting partial canonical matching. |
| Exportable forensic report | `backend/report.py` | Reports | Generates printable case dossiers summarizing the evidence. |

## Bonus Requirements Implemented
| Requirement | Actual Module | UI Location | Explanation |
|---|---|---|---|
| Suspicious Transaction Report (STR) | `backend/report_intelligence.py` | STR Generator | Automatically generates the regulatory STR layout based on flagged entities. |
| Natural-language query | `investigative_copilot/` | AI Copilot | Extracts intents and translates NLP queries to SQL/Graph operations for grounded answers. |
