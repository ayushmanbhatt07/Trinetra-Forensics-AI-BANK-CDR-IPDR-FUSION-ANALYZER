# ERH26_PS_03 — Official Problem Statement

**Sr. No:** 3  
**Problem Statement ID:** ERH26_PS_03  
**Definition:** AI-Powered Financial & Telecom Dataset Analyzer (Bank, CDR, and IPDR Fusion)  
**Domain:** Big Data and Analytics

---

## Background

Financial cybercrime investigations require correlating multiple high-volume, heterogeneous datasets. Bank statements, Call Detail Records (CDR), and Internet Protocol Detail Records (IPDR) each arrive in different formats from different providers, and the decisive evidence usually lies at their intersection — the exact moment a suspect was on a call, online from a particular IP, and moving money. Doing this by hand across thousands of rows is an overwhelming data-science task for a standard investigator.

## Problem Statement

Cybercrimes and financial scams involve parsing mountains of raw data across different formats — thousands of rows of bank statements (Excel/PDF), Call Detail Records (CDR), and Internet Protocol Detail Records (IPDR). Manually cross-referencing these logs to find the exact moment a suspect talked on the phone, used an IP address, and moved money is an overwhelming challenge. There is a need for a tool that ingests all three dataset types, normalizes them onto a common timeline and entity model, and automatically surfaces correlations, anomalies, and money-flow networks.

## Key Objectives

- Ingest and parse bank statements (Excel/PDF/CSV), CDR, and IPDR from multiple provider formats.
- Normalize records onto a unified entity (number/account/IP) and time model.
- Automatically correlate events across the three datasets on a common timeline.
- Detect suspicious patterns and visualize money-and-communication networks.
- Produce an investigation-ready report.

## Functional Requirements

### I. Multi-Format Ingestion

- a. Parse heterogeneous bank statement layouts (Excel, PDF, CSV).
- b. Parse CDR and IPDR exports from major Indian telecom operators.
- c. Schema mapping/auto-detection to a canonical internal model.

### II. Cross-Dataset Fusion

- a. Build a unified timeline linking calls, IP series, and transactions per entity.
- b. Detect temporal coincidences (e.g., call + IP + transfer within a window).
- c. Link accounts and numbers via shared identifiers (UPI ID, IP, IMEI, beneficiary).

### III. Anomaly & Pattern Detection

- a. Rules + ML for layering, rapid in-and-out transfers, structuring, and circular flows.
- b. Risk scoring for accounts/numbers.
- c. Detection of mule-account behavioral signatures.

### IV. Visualization & Reporting

- a. Money-flow and communication network graphs with drill-down.
- b. Filter/search by entity, amount, time window, or location.
- c. Exportable forensic report (PDF/Word) with charts and the evidentiary timeline.

## Evaluation Criteria

- Accuracy and robustness of multi-format parsing.
- Quality of cross-dataset correlation on the unified timeline.
- Relevance of detected anomalies (true vs. false positives).
- Clarity of network and timeline visualizations.
- Performance and scalability on large datasets.

## Suggested Tools / Technologies

- Python, Pandas, NetworkX / Neo4j
- Scikit-learn / PyTorch (anomaly detection)
- PDF parsing (pdfplumber / Apache PDFBox), OpenpyXL
- Elasticsearch, PostgreSQL / MongoDB
- React.js + D3.js (timeline and graph visualization)

## Bonus Points

- Automated Suspicious Transaction Report (STR) generation.
- Cross-bank and cross-operator network visualization with risk heat maps.
- Natural-language query ("show every transfer within 10 minutes of a call to X").

## Deliverables

- Working prototype/demo ingesting all three dataset types.
- Fusion dashboard with a worked correlation example.
- Sample forensic report and visual exports.
- Documentation (parsers, correlation logic, scoring rules).
