<p align="center">
  <img src="docs/screenshots/project-icon.jpg" width="180" alt="TRI-NETRA FORENSICS Logo" style="border-radius: 50%;">
</p>

<h1 align="center">TRI-NETRA FORENSICS</h1>

<p align="center">
  <strong>Enterprise AI-Powered Financial & Telecom Investigation Workspace</strong><br>
  <em>Next-Generation Fusion & Anomaly Detection for Bank Statements, CDR, and IPDR Data</em>
</p>

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,fastapi,ts,react,nextjs,tailwind,threejs,docker,nginx&theme=dark" alt="Core Tech Stack" />
</p>
<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/pandas/pandas-original.svg" height="40" alt="Pandas" style="margin: 0 8px;" title="Pandas" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/scikitlearn/scikitlearn-original.svg" height="40" alt="Scikit-Learn" style="margin: 0 8px;" title="Scikit-Learn" />
  <img src="https://img.shields.io/badge/XGBoost-FF6600?style=for-the-badge&logo=xgboost&logoColor=white" height="35" alt="XGBoost" title="XGBoost" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/numpy/numpy-plain-wordmark.svg" height="40" alt="NumPy" style="margin: 0 8px;" title="NumPy" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/d3js/d3js-original.svg" height="40" alt="D3.js" style="margin: 0 8px;" title="D3.js" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/sqlite/sqlite-original.svg" height="40" alt="SQLite" style="margin: 0 8px;" title="SQLite" />
</p>

---

## 🔍 Executive Summary

Cyber-financial crimes and syndicates operate across fragmented channels—scattering evidence across bank statements (PDF/Excel), Call Detail Records (CDR), and Internet Protocol Detail Records (IPDR). The critical forensic breakthrough lies at the intersection: **the exact moment a suspect communicates with a target, logs into an IP session, and moves illicit funds**.

**Tri-Netra Forensics** solves **ERH26_PS_03** by automating the entire forensic data science workflow:
1. **Heterogeneous Ingestion**: Automatically detects and parses 14 Indian banking layout dialects (PDF/Excel/CSV), telecom CDRs (Airtel, Jio, Vi, SDR), IPDR session logs, and NCRP cybercrime complaints.
2. **Canonical Fusion**: Maps entities (accounts, phones, IMEIs, IMSIs, IPs, UPI handles) onto a unified chronological timeline with temporal coincidence correlation ($\pm 3600\text{s}$).
3. **11-Model Machine Learning Ensemble**: Concurrently executes 7 unsupervised anomaly detectors and 4 supervised classifiers alongside 22 deterministic typology checks (Rapid In-Out, Structuring, Mule Rings, Circular Flows, Call-Assisted Fraud).
4. **Graph & Syndicate Intelligence**: Visualizes complex 2D and 3D network topologies, money laundering hops, and caller-subscriber communities.
5. **Grounded AI Copilot**: Multi-lingual (English/Hindi/Gujarati) RAG assistant with Groq/OpenRouter multi-key rotation and an interactive 3D semantic reasoning tree.
6. **FIU-IND STR Generation**: Generates court-admissible forensic dossiers and regulatory Suspicious Transaction Reports in PDF and DOCX formats with a single click.

---

## 💻 Tech Stack & Architecture

| Layer | Technologies | Description |
| :--- | :--- | :--- |
| **Frontend UI** | **Next.js 16 (React 18)**, **TypeScript**, **Tailwind CSS** | Ultra-responsive SSR interface with dark-mode glassmorphic aesthetics, real-time pipeline status polling, and modular investigation views. |
| **Visualizations** | **Three.js**, **D3.js**, **React Flow** | **Three.js**: 3D force-directed money-flow topologies and 3D semantic copilot reasoning trees.<br>**D3.js**: High-density interactive chronological timeline.<br>**React Flow**: Node-based transaction graph exploration. |
| **Backend API** | **Python 3.11+**, **FastAPI**, **Uvicorn / Gunicorn** | High-throughput asynchronous REST backend with JWT authentication, multi-threaded parsing, and streaming responses. |
| **Data Science** | **Pandas**, **NumPy**, **pdfplumber**, **OpenPyXL** | Geometric table extraction from bank statements, vector-matrix operations, and robust CSV/XLSX normalizers. |
| **Machine Learning** | **Scikit-Learn**, **XGBoost**, **LightGBM**, **CatBoost**, **HDBSCAN** | 11-model hybrid risk ensemble calculating multidimensional anomaly scores and legal AML typologies. |
| **Graph AI** | **NetworkX** | Directed multigraph computation: PageRank, betweenness centrality, degree distribution, and circular flow cycles. |
| **Generative AI** | **Groq API**, **OpenRouter**, **NVIDIA Nemotron**, **Llama 3.3 70B** | Dual-pathway grounded RAG with zero hallucination, automated multi-key rotation, and read-only SQL execution. |
| **Database & Cache** | **SQLite (In-Memory + File)** | Ephemeral and persistent session databases, fast memory-mapped JSON bundles, and thread-safe caches. |

---

## 🧠 11-Model Machine Learning & Risk Ensemble

Rather than relying on a single algorithm, the Tri-Netra Risk Engine (`backend/risk/ensemble.py`) concurrently executes an **11-model hybrid ensemble** to evaluate behavioral anomalies:

```mermaid
flowchart LR
    subgraph DataInput["Fused Entity Features"]
        F1["Velocity & Burst Metrics"]
        F2["Volume & Balance Movements"]
        F3["Temporal Telecom Coincidence"]
        F4["Graph Centrality & Degree"]
    end

    subgraph Unsupervised["7 Unsupervised Detectors (Cold Start)"]
        M1["Isolation Forest"]
        M2["Local Outlier Factor (LOF)"]
        M3["DBSCAN Clustering"]
        M4["HDBSCAN Hierarchy"]
        M5["One-Class SVM (RBF)"]
        M6["PCA Reconstruction Error"]
        M7["Z-Score Statistical Baseline"]
    end

    subgraph Supervised["4 Supervised Classifiers (Ground Truth)"]
        M8["Random Forest"]
        M9["XGBoost"]
        M10["LightGBM"]
        M11["CatBoost"]
    end

    subgraph Output["Composite Risk & Typologies"]
        Score["Calibrated 0-100 Composite Score\n(CRITICAL / HIGH / MEDIUM / LOW)"]
        Scen["Named Forensic Typologies\n(Mule / Structuring / Layering)"]
    end

    DataInput --> Unsupervised & Supervised
    Unsupervised & Supervised --> Score & Scen
```

### 🔵 Unsupervised Detectors (7 Models — Zero Labeled Data Needed)
| Icon | Model | Library | Forensic Detection Specialty |
|:---:|:---|:---|:---|
| 🌲 | **Isolation Forest** | `sklearn.ensemble` | Global structural volume outliers and transaction velocity spikes |
| 📍 | **Local Outlier Factor (LOF)** | `sklearn.neighbors` | Local density deviations against peer cluster distributions |
| 🔵 | **DBSCAN** | `sklearn.cluster` | Dense normal behavioral clusters; flags isolated noise transactions |
| 🔶 | **HDBSCAN** | `hdbscan` | Hierarchical density clustering across variable log densities |
| ⚡ | **One-Class SVM** | `sklearn.svm` | RBF-kernel nonlinear boundary margin outliers |
| 📐 | **PCA Reconstruction Error** | `sklearn.decomposition` | Accounts unrepresentable in the principal linear subspace |
| 📊 | **Z-Score Baseline** | `numpy` | Extreme statistical thresholding on amounts and frequency |

### 🟠 Supervised Detectors (4 Models — Active Benchmarking Mode)
| Icon | Model | Library | Specialization |
|:---:|:---|:---|:---|
| 🌳 | **Random Forest Classifier** | `sklearn.ensemble` | Non-linear ensemble tree voting on account features |
| ⚡ | **XGBoost** | `xgboost` | Gradient-boosted decision trees optimized for sparse financial features |
| 💡 | **LightGBM** | `lightgbm` | Fast histogram-based gradient boosting for large-scale transaction logs |
| 🐱 | **CatBoost** | `catboost` | Native categorical handling for telecom carrier and IFSC features |

---

## 🏛️ End-to-End Pipeline Architecture

```mermaid
flowchart TB
    subgraph S1["1. Multi-Format Ingestion"]
        A1["Bank Statements\n(14 Dialects: Axis, HDFC, SBI, PNB, ICICI...)"]
        A2["Telecom CDR Logs\n(Airtel, Jio, Vi, SDR)"]
        A3["IPDR Session Logs\n(IPv4/IPv6, Ports, IMEI, IMSI)"]
        A4["NCRP Complaint Ledger\n(Victim ACK, Police Station)"]
    end

    subgraph S2["2. Canonical Normalization & Fusion"]
        B1["Entity Cleaners\n(Phone, IMEI, IP, UPI)"]
        B2["Unified Timestamp Epoch Engine"]
        B3["Cross-Dataset Timeline\n(Calls + IP + Transfers)"]
        B4["Temporal Correlator\n(+/- 3600s Window)"]
    end

    subgraph S3["3. Hybrid Intelligence Engine"]
        C1["22 AML Rule Scenarios\n(Layering, Rapid In-Out, Structuring)"]
        C2["11-Model ML Risk Ensemble"]
        C3["NetworkX Graph Topology\n(Cycles, PageRank, Degree)"]
    end

    subgraph S4["4. User Workspace & Reporting"]
        D1["Next.js 16 Dashboard\n(Overview, Ingest, Timeline, Anomalies)"]
        D2["2D & 3D Network Graphs\n(Three.js / React Flow)"]
        D3["Autonomous AI Copilot\n(Dual-Pathway RAG + 3D Tree)"]
        D4["FIU-IND STR Reports\n(Court-Ready PDF & DOCX)"]
    end

    S1 --> S2 --> S3 --> S4
```

---

## 📸 Platform Walkthrough & Feature Showcase

### 1. Investigation Command Center
<img src="docs/screenshots/03-overview.png" width="100%" alt="Overview Command Center">
<em>Unified command dashboard displaying total parsed nodes, active risk flags, and real-time model confidence.</em>

### 2. Cross-Domain Evidence Ingestion
<img src="docs/screenshots/04-ingestion.png" width="100%" alt="Data Ingestion">
<em>Multi-format drag-and-drop ingestion interface supporting heterogeneous files with automated schema detection.</em>

### 3. Fused Transactions & Unified Chronological Timeline
<img src="docs/screenshots/05-fused-transactions.png" width="100%" alt="Fused Transactions">
<em>Cross-dataset fused event log mapping financial transactions directly alongside suspect telecom communications.</em>

<img src="docs/screenshots/11-timeline.png" width="100%" alt="Unified Timeline">
<em>Unified interactive D3.js timeline overlaying calls, SMS, IP sessions, and transfers simultaneously.</em>

### 4. 2D & 3D Network & Syndicate Intelligence
<img src="docs/screenshots/06-money-flow.png" width="100%" alt="Money Flow Graph">
<em>Directed money flow topology tracking laundering hops, intermediary mule accounts, and circular flow rings.</em>

<img src="docs/screenshots/07-call-network.png" width="100%" alt="Communication Network">
<em>Telecom communication network mapping interactions and subscriber communities between suspect numbers.</em>

### 5. Anomaly Feed & ML Risk Profiling
<img src="docs/screenshots/08-anomalies.png" width="100%" alt="Anomaly Feed">
<em>Anomaly Feed detailing multi-stage risk alerts generated concurrently by the 11-model ML ensemble.</em>

<img src="docs/screenshots/09-anomaly-detail.png" width="100%" alt="Transaction Intelligence Card">
<em>Deep-dive transaction card providing exact component breakdown, mathematical scores, and red flags.</em>

### 6. Autonomous Investigative Copilot (Grounded RAG)
<img src="docs/screenshots/12-copilot-response.png" width="100%" alt="Copilot Response">
<em>Natural language queries (English/Hindi/Gujarati) grounded in case data returning evidence-backed answers with zero hallucination.</em>

### 7. 3D LLM Semantic Reasoning Tree (USP)
<img src="docs/screenshots/13-copilot-graph.png" width="100%" alt="3D LLM Tree with Nodes">
<em>Interactive 3D WebGL semantic tree visualizing anomalous entities, reasoning branches, and corroborating evidence nodes.</em>

### 8. Automated FIU-IND STR Generation & Reporting
<img src="docs/screenshots/14-reports-overview.png" width="100%" alt="Reports Overview">
<em>One-click generation of court-ready forensic dossiers and official FIU-IND Suspicious Transaction Reports (STR).</em>

---

## 📖 Deep-Dive Technical Documentation

Every subsystem of Tri-Netra Forensics is thoroughly documented with architecture blueprints, API schemas, and mathematical specifications:

| Document | Description |
| :--- | :--- |
| 📘 **[System Architecture Blueprint](docs/architecture.md)** | End-to-end multi-tier architectural specifications, data flow, and security models. |
| 🔌 **[REST API Reference](docs/api.md)** | Full FastAPI endpoint documentation, request/response models, and auth contexts. |
| 🗄️ **[Canonical Data & Entity Model](docs/data-model.md)** | Dataclass definitions, schema mappings, and unified entity relationship schemas. |
| 📑 **[Parsers Ecosystem](docs/parsers.md)** | Ingestion mechanics for 14 bank layout dialects, CDR carriers, and IPDR logs. |
| 🔄 **[Canonical Normalization Pipeline](docs/normalization.md)** | Identifier standardization (E.164, IPv4/v6, IMEI, UPI) and timestamp alignment. |
| ⚡ **[Cross-Dataset Fusion Engine](docs/fusion.md)** | Timeline synthesis algorithms, temporal coincidence windows, and multi-domain linking. |
| 🧠 **[11-Model Risk & Anomaly Engine](docs/risk-engine.md)** | Mathematical formulation of the 11 ML models, scoring weights, and 22 AML typologies. |
| 🤖 **[Investigative Copilot Architecture](docs/copilot.md)** | Dual-pathway RAG design, key rotation, prompt fencing, and 3D semantic tree specs. |
| 💾 **[Database & Storage Architecture](docs/database.md)** | In-memory SQLite replica structure, JSON bundles, and persistence layers. |
| 🚀 **[Production & Cloud Deployment Guide](docs/deployment.md)** | Docker Compose setups, Nginx reverse proxy configuration, and scaling guidelines. |
| 📋 **[Requirements Traceability Matrix](docs/requirements-matrix.md)** | Line-by-line verification against the official **ERH26_PS_03** problem statement. |
| 🏛️ **[Bank Pattern & Parsing Catalog](docs/bank-pattern-catalog.md)** | Layout specifications and heuristics for Axis, HDFC, SBI, ICICI, PNB, and others. |
| 🗺️ **[Repository File & Codebase Map](docs/FILE_MAP.md)** | Complete file directory mapping and architectural layer index. |
| ⚖️ **[Attribution & Open Source Licenses](docs/attribution.md)** | Attribution for third-party libraries, external APIs (Groq/OpenRouter), and MIT license terms. |
| 🎯 **[Official ERH26_PS_03 Problem Statement](docs/ERH26_PS_03_Problem_Statement.md)** | Exact problem statement definition and hackathon evaluation criteria. |
| 🛠️ **[System Troubleshooting & FAQ](docs/troubleshooting.md)** | Diagnostic steps, error recovery, and common configuration fixes. |

---

## 🚀 Quick Start & Evaluator Walkthrough

### Prerequisites
* **Python**: 3.11+ (Conda / Virtualenv recommended)
* **Node.js**: 18.x+ (Next.js 16)

### 1. Start the Backend API
```bash
cd backend
pip install -r requirements.txt
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start the Frontend Workspace
```bash
cd frontend
npm install
npm run dev
```
Navigate to `http://localhost:3000` in your browser.

---

### 🎯 Step-by-Step Evaluator Demo Guide (5-Minute Winning Flow)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              EVALUATION DEMO WORKFLOW                                  │
│                                                                                        │
│   [1. Ingestion]  ──►  [2. Fusion Timeline]  ──►  [3. 3D Network Graph]               │
│   (Upload Bank+CDR+IPDR)   (Inspect +/-3600s Call)    (Identify Mule Ring / Cycles)     │
│                                                                                        │
│            ▼                         ▼                         ▼                       │
│   [4. Anomaly Feed] ──►  [5. AI Copilot RAG] ──►  [6. One-Click STR Export]            │
│   (11-Model ML Breakdown)   (Ask NLQ & View 3D Tree)   (Download FIU-IND PDF Dossier)   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **Step 1 — Ingest Evidence**: Open the **Data Ingestion** tab and drag-and-drop the sample Bank statement, CDR, and IPDR CSV files. Watch the real-time stage machine transition from *PARSING $\to$ FUSING $\to$ SCORING $\to$ READY*.
2. **Step 2 — Inspect Fused Timeline**: Navigate to the **Timeline** tab. Filter by phone number to observe a voice call occurring 3 minutes before a high-value money transfer.
3. **Step 3 — Visualize Network**: Open the **Network Graph** tab. Toggle to **3D Mode** and click **Detect Cycles** to highlight circular money-flow laundering rings.
4. **Step 4 — Review Anomalies**: Open the **Anomaly Detection** tab. Click into any high-risk transaction to view the exact component scores from the **11-model ML ensemble**.
5. **Step 5 — Query the AI Copilot**: Click the **Copilot** icon. Ask: *"Show all high-risk transfers above 50,000 rupees and their linked phone numbers"*. Observe the instant, grounded answer and the interactive **3D Semantic Reasoning Tree**.
6. **Step 6 — Export STR**: Click **"Generate STR"** to download the official, court-ready FIU-IND Suspicious Transaction Report PDF.

---

## 📄 License & Compliance

Distributed under the **MIT License**. See [docs/attribution.md](docs/attribution.md) for details on third-party libraries, AI provider terms, and compliance standards.
