

<p align="center">
  <img src="docs/screenshots/project-icon.jpg" width="180" alt="TRI-NETRA FORENSICS Logo" style="border-radius: 50%;">
</p>

<h1 align="center">TRI-NETRA FORENSICS</h1>

<p align="center">
  <strong>Enterprise AI-Powered Financial & Telecom Investigation Workspace</strong>
</p>

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,fastapi,ts,react,nextjs,tailwind,threejs,docker,nginx&theme=dark" alt="Core Tech Stack" />
</p>
<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/pandas/pandas-original.svg" height="45" alt="Pandas" style="margin: 0 10px;" title="Pandas" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/scikitlearn/scikitlearn-original.svg" height="45" alt="Scikit-Learn" style="margin: 0 10px;" title="Scikit-Learn" />
  <img src="https://img.shields.io/badge/XGBoost-FF6600?style=for-the-badge&logo=xgboost&logoColor=white" height="45" alt="XGBoost" title="XGBoost" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/numpy/numpy-plain-wordmark.svg" height="45" alt="NumPy" style="margin: 0 10px;" title="NumPy" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/d3js/d3js-original.svg" height="45" alt="D3.js" style="margin: 0 10px;" title="D3.js" />
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/sqlite/sqlite-original.svg" height="45" alt="SQLite" style="margin: 0 10px;" title="SQLite" />
</p>

---

## 🔍 Executive Summary

Cybercrimes and financial scams involve parsing mountains of raw data across different formats—thousands of rows of Bank Statements (Excel/PDF), Call Detail Records (CDR), and Internet Protocol Detail Records (IPDR). The decisive evidence usually lies at the intersection of these datasets: the exact moment a suspect was on a call, online from a particular IP, and transferring money. 

**Tri-Netra Forensics** automates the forensic data science workflow. It ingests multi-format records, normalizes them onto a canonical timeline, and runs a massive 11-model Machine Learning ensemble to detect money laundering, mule accounts, and structural anomalies.

---

## 💻 Tech Stack & Core Frameworks

Tri-Netra is built on a modern, high-performance web and data-science stack.

| Category | Technology | Description |
| :--- | :--- | :--- |
| **Frontend UI** | <img src="https://skillicons.dev/icons?i=nextjs,react,ts,tailwind" height="24" align="absmiddle" /> **Next.js 16 (React 18)** | Server-side rendering (SSR), highly responsive interface routing, and utility-first styling with glassmorphism via **Tailwind CSS**. |
| **Visualizations** | <img src="https://skillicons.dev/icons?i=threejs&theme=dark" height="24" align="absmiddle" /> **Three.js** &nbsp; <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/d3js/d3js-original.svg" height="24" align="absmiddle" /> **D3.js** | **Three.js & React Flow**: 2D and 3D force-directed layout engines for rendering complex communication and money-flow syndicates.<br>**D3.js**: SVG-based rendering for the interactive, multi-axis unified chronological timeline. |
| **Backend Core** | <img src="https://skillicons.dev/icons?i=python,fastapi" height="24" align="absmiddle" /> **FastAPI** | High-throughput asynchronous REST APIs handling large concurrent data uploads, deployed via **Uvicorn / Gunicorn**. |
| **Data Science** | <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/pandas/pandas-original.svg" height="24" align="absmiddle" /> **Pandas** <br> <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/numpy/numpy-original.svg" height="24" align="absmiddle" /> **NumPy** | High-performance memory-mapped tabular data parsing and complex matrix vectorization. **pdfplumber** handles geometric PDF table extraction. |
| **Machine Learning**| <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/scikitlearn/scikitlearn-original.svg" height="24" align="absmiddle" /> **Scikit-Learn** | Foundation for the massive 11-model Risk Ensemble (Isolation Forest, SVM, DBSCAN, Random Forest) analyzing behavioral metadata. |
| **Graph AI** | <img src="https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/networkx/networkx-original.svg" height="24" align="absmiddle" /> **NetworkX** | In-memory graph processing to calculate centrality, circular flows, and layering hops in real-time. |
| **Infra & Data** | <img src="https://skillicons.dev/icons?i=docker,nginx,sqlite" height="24" align="absmiddle" /> **Docker & SQLite** | Containerized architecture for seamless local and cloud deployment. **SQLite JSON bundles** provide portable, highly-concurrent state management. |

---

## 🧠 11-Model Machine Learning & AI Ensemble

Rather than relying on a single algorithm, the Tri-Netra Risk Engine (`backend/risk/ensemble.py`) concurrently executes an **11-model hybrid ensemble** to evaluate behavioral anomalies, ensuring high-confidence alerts that evade simple deterministic rules.

### 🔵 Unsupervised Detectors — Cold Start (7 Models)

| | Model | Library | What it Detects |
|:---:|:---|:---|:---|
| 🌲 | **Isolation Forest** | `sklearn.ensemble` | Global shape deviations & structural outliers |
| 📍 | **Local Outlier Factor (LOF)** | `sklearn.neighbors` | Local density deviations vs. peer accounts |
| 🔵 | **DBSCAN** | `sklearn.cluster` | Dense behavioral clusters; flags noise points |
| 🔶 | **HDBSCAN** | `hdbscan` | Hierarchical density clustering for variable datasets |
| ⚡ | **One-Class SVM** | `sklearn.svm` | RBF-kernel margin outliers in feature space |
| 📐 | **PCA Reconstruction Error** | `sklearn.decomposition` | Accounts unrepresentable in the principal subspace |
| 📊 | **Z-Score Baseline** | `numpy` | Extreme-feature statistical thresholding |

### 🟠 Supervised Detectors — Ground Truth Mode (4 Models)

| | Model | Library | Specialization |
|:---:|:---|:---|:---|
| 🌳 | **Random Forest Classifier** | `sklearn.ensemble` | Non-linear ensemble tree voting on account features |
| ⚡ | **XGBoost** | `xgboost` | Gradient-boosted trees optimized for sparse financial data |
| 💡 | **LightGBM** | `lightgbm` | Histogram-based gradient boosting, high speed |
| 🐱 | **CatBoost** | `catboost` | Handles categorical telecom identifiers natively |

### 🤖 Generative AI Copilot

| | Model | Provider | Capability |
|:---:|:---|:---|:---|
| 🧠 | **Nemotron (Grounded RAG)** | `OpenRouter` | Translates natural language (EN/HI/GJ) → SQL/Graph queries with zero hallucination |


---

## 👮 Real-Life Investigation Workflow

From the investigator's perspective, the workflow is streamlined:

1. **01 — Collect Evidence**: Gather Bank, CDR, IPDR, and related records from providers.
2. **02 — Ingest**: Drop files into the platform. The system automatically detects the schema (Jio, Airtel, SBI, HDFC).
3. **03 — Normalize**: Standardizes identifiers (phones, IPs, accounts) and timestamps.
4. **04 — Fuse**: Connects related records across domains via shared attributes (e.g., UPI IDs linked to phones).
5. **05 — Analyze**: Applies the 11-model ensemble and deterministic rules.
6. **06 — Investigate**: Utilize Fused Transactions, Anomalies, Timeline, Entity Search, Network Graphs, and the AI Copilot.
7. **07 — Report**: Generate final forensic dossiers and automated Suspicious Transaction Reports (STR).

---

## 📸 Platform Walkthrough

### Investigation Command Center
<img src="docs/screenshots/03-overview.png" width="100%" alt="Overview">
<em>Command Center displaying node ingestion metrics, high-risk flags, and live model confidence.</em>

### Cross-Domain Evidence Ingestion
<img src="docs/screenshots/04-ingestion.png" width="100%" alt="Data Ingestion">
<em>Multi-format drag-and-drop ingestion interface supporting heterogeneous logs.</em>

### Cross-Dataset Fusion & Timeline
<img src="docs/screenshots/05-fused-transactions.png" width="100%" alt="Fused Transactions">
<em>Fused Transactions showing unified activity across previously isolated datasets.</em>

<img src="docs/screenshots/11-timeline.png" width="100%" alt="Unified Timeline">
<em>Unified Timeline overlaying call events, IP sessions, and financial transactions simultaneously.</em>

### Network & Syndicate Intelligence
<img src="docs/screenshots/06-money-flow.png" width="100%" alt="Money Flow">
<em>Money Flow topology tracking laundering hops and intermediary mule accounts.</em>

<img src="docs/screenshots/07-call-network.png" width="100%" alt="Communication Network">
<em>Communication Network mapping interactions between suspect phone numbers.</em>

### Anomaly Feed & AI Profiling
<img src="docs/screenshots/08-anomalies.png" width="100%" alt="Anomaly Feed">
<em>Anomaly Feed detailing multi-stage risk orchestration alerts generated by the ML ensemble.</em>

<img src="docs/screenshots/09-anomaly-detail.png" width="100%" alt="Transaction Intelligence Card">
<em>Transaction Intelligence Card providing deep-dive context into a specific high-risk flag.</em>

### Autonomous Investigative Copilot
<img src="docs/screenshots/12-copilot-response.png" width="100%" alt="Copilot Response">
<em>Natural language RAG queries grounded in case data returning evidence-backed answers.</em>

### 3D LLM Semantic Graph (USP)
<img src="docs/screenshots/13-copilot-graph.png" width="100%" alt="3D LLM Tree with Nodes">
<em>Interactive 3D Semantic Tree visualizing anomalous entities, branches, and master nodes generated dynamically by the LLM.</em>

### STR Generation & Forensic Reporting
<img src="docs/screenshots/14-reports-overview.png" width="100%" alt="Reports">
<em>One-click court-ready case dossier and Suspicious Transaction Report (STR) generator.</em>

---

## 🏛️ Pipeline Architecture

```mermaid
graph TD
    subgraph 1. Ingestion Layer
        Detect[Detection & Fingerprinting]
        Provider[Provider-Specific Parsers]
    end

    subgraph 2. Unification Layer
        Norm[Canonical Normalization]
        Link[Entity Linking]
        Fuse[Cross-Dataset Fusion]
    end

    subgraph 3. Intelligence Engine
        Rules[Deterministic Rules]
        ML[11-Model ML Ensemble]
        Time[Temporal Analysis]
        GraphInt[NetworkX Graph Intelligence]
    end

    subgraph 4. Interface & Reporting
        FastAPI[FastAPI Backend]
        UI[Next.js Dashboard]
        Copilot[OpenRouter RAG Copilot]
    end

    Detect --> Provider
    Provider --> Norm
    
    Norm --> Link
    Link --> Fuse
    
    Fuse --> Rules
    Fuse --> ML
    Fuse --> Time
    Fuse --> GraphInt
    
    Rules & ML & Time & GraphInt --> FastAPI
    
    FastAPI --> UI
    FastAPI --> Copilot
```

---

## 📖 Deep-Dive Documentation

For an in-depth understanding of the platform's inner workings, refer to the documentation:

* [Architecture Overview](docs/architecture.md)
* [API Reference](docs/api.md)
* [Data & Entity Model](docs/data-model.md)
* [Parsers Ecosystem](docs/parsers.md)
* [Canonical Normalization](docs/normalization.md)
* [Cross-Dataset Fusion](docs/fusion.md)
* [Risk Engine (Rules + ML)](docs/risk-engine.md)
* [AI Copilot Architecture](docs/copilot.md)
* [Database & Storage](docs/database.md)
* [Deployment Guide](docs/deployment.md)
* [Attribution & Third-Party Libraries](docs/attribution.md)
* [Requirements Traceability Matrix](docs/requirements-matrix.md)
* [Troubleshooting](docs/troubleshooting.md)

---

## 🚀 Quick Start & Evaluator Walkthrough

### Prerequisites
* **Python**: 3.11+
* **Node.js**: 18.x+ (Next.js 16)

### 1. Start the Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 10000
```

### 2. Start the Frontend
```bash
cd frontend
npm install
npm run dev
```

### Quick Evaluation Walkthrough
1. **Launch**: Open `http://localhost:3000`.
2. **Login**: Authenticate (Default: admin/admin).
3. **Upload Evidence**: Drag and drop Bank + CDR + IPDR files from the `data/` directory.
4. **Inspect Pipeline**: Watch the status as the files are parsed, normalized, and fused.
5. **Explore Network Graph**: Visualize money flows and communication.
6. **Open Anomalies**: Review the flagged transactions based on the ML ensemble.
7. **Ask Copilot**: Query the data in natural language (e.g. "Who did suspect X call before the transaction?").
8. **View STR**: Inspect the Suspicious Transaction Report.

For detailed Docker or production setup, see [docs/deployment.md](docs/deployment.md).

---

## 📄 License & Attribution

Distributed under the MIT License. See [docs/attribution.md](docs/attribution.md) for details on third-party libraries, external APIs (OpenRouter), UI libraries, and custom code distinction.
