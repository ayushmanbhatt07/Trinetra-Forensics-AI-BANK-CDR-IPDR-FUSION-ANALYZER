# Attribution & License

In accordance with the Stage-3 Prototype Submission Instructions, this document explicitly outlines the third-party libraries, APIs, datasets, and open-source components utilized in Tri-Netra Forensics, distinguishing them from the team's original code.

## 1. Custom Code (Our Intellectual Property)
All proprietary logic related to the forensic analysis is custom-built by the team. This includes, but is not limited to:
* **The Parser Ecosystem**: All heuristics and extraction logic for SBI, HDFC, Jio, Airtel, Vi, and BSNL schemas.
* **The Fusion Engine**: The temporal correlation windowing and entity linking algorithms.
* **The Risk Engine**: The 22 deterministic laundering scenarios and the specific implementation of the ML ensemble orchestration.
* **The Copilot Router**: The intent extraction and dynamic context injection logic that feeds the LLM.
* **The Frontend Application**: The entire React/Next.js dashboard, visualizations, and user experience.

## 2. Third-Party Libraries (Open Source)

### Backend (Python)
* **`FastAPI` & `Uvicorn`**: Used for the REST API routing and server implementation.
* **`scikit-learn`**: Provides the base implementations for `IsolationForest` and `LocalOutlierFactor` used in our Risk Engine.
* **`NetworkX`**: Used as the underlying graph data structure for calculating centralities and detecting circular money flows.
* **`pdfplumber`**: Utilized by the parser ecosystem to extract text and table geometry from raw Bank PDF statements.
* **`pandas`**: Used for intermediate data manipulation during CSV/Excel ingestion.

### Frontend (Node / React)
* **`Next.js` (16) & `React`**: The core frontend framework.
* **`TailwindCSS`**: Used for utility-first styling and glassmorphism effects.
* **`Three.js` / `React Flow`**: Utilized for rendering the 2D and 3D force-directed network graphs.
* **`D3.js`**: Powers the unified timeline visualizations.

## 3. Third-Party Services & APIs
* **OpenRouter API**: The Investigative Copilot relies on the OpenRouter inference engine for high-speed, natural language processing using open-weight models (e.g., NVIDIA Nemotron). OpenRouter provides the raw text generation; the grounding context and prompt engineering are handled entirely by our backend.

## 4. Datasets
The datasets included in the `data/` directory (if any) are strictly synthetic or heavily anonymized open-source samples used purely for demonstration and evaluator testing. **No real Personally Identifiable Information (PII) or sensitive financial data is included in this repository.**

## 5. License
Tri-Netra Forensics is provided under the MIT License. See the `LICENSE` file in the root directory for full text.
