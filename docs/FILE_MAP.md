# Tri-Netra Forensics — File Map

Every tracked source file in the repository, organized by layer.

## Backend (`backend/`)

| File | Purpose |
|---|---|
| `main.py` | FastAPI app entrypoint (lifespan, CORS, router mounting) |
| `api.py` | API routes: ingest, summary, accounts, phones, graphs, hybrid, risk, scoring/alerts (with `explain_plain`), fused data, reports, dossiers, `/evaluate` |
| `auth.py` | JWT auth + `AuthContext` for every protected route |
| `store.py` | SQLite persistence (`backend/data/backend.db`), session/lab storage |
| `config.py` | Env-based config: API keys, app dir, model names, fallback Groq keys |
| `errors.py` | Typed API exceptions + handlers |
| `log.py` | Structured logging (ingest/flag/report events) |
| `schema.py` | Canonical dataclasses: transactions, CDR, IPDR, complaints, entities |
| `pipeline.py` | Parallel ingestion pipeline: detect → parse → normalise → fuse → score |
| `normalise.py` | Entity normalisation (phones, accounts, IMEI, IMSI, IP, UPI) |
| `fusion.py` | Cross-domain fusion: unified timeline, call↔transfer correlations |
| `graphs.py` | Money-flow + phone-call networkx graphs, centrality/communities |
| `dossier.py` | Unified cross-domain dossier compilation for accounts, phones, IMEIs, IPs, names |
| `behavioural.py` | Customer behavioural scoring (velocity, hour deviation, round amounts) |
| `explain.py` | Plain-English explainability: `RULE_PLAIN` + `DETECTOR_PLAIN` maps, `plain_reason()`, `plain_explainability()` |
| `evidence.py` | Evidence-reason bundles per transaction |
| `report.py` | STR / report generation (CSV) |
| `util.py` | Shared helpers (parsing dates, amounts, currency) |
| `adapters/synthetic.py` | Synthetic-dataset reader (`bank_final.csv` etc.) |
| `detect/engine.py` | Format detection dispatcher |
| `detect/fingerprints.py` | ~20 provider-layout fingerprints (bank dialects, Jio CDR, Vi CDR, generic IPDR…) |
| `parsers/bank.py` | Bank statement parser (PDF via pdfplumber, Excel, CSV) |
| `parsers/cdr.py` | CDR parser (Jio/Airtel/Vi/BSNL layouts) |
| `parsers/ipdr.py` | IPDR session-log parser |
| `parsers/subscriber.py` | Subscriber master parser |
| `parsers/complaint.py` | NCRP complaint ledger parser |
| `parsers/synthetic.py` | Synthetic CSV parser (bank/cdr/ipdr final sets) |
| `parsers/registry.py` | Parser ↔ fingerprint registration |
| `parsers/base.py`, `parsers/common/*` | Base parser + CSV/spreadsheet helpers |
| `parsers_bank.py`, `parsers_cdr.py`, `parsers_ipdr.py` | Legacy v2 parsers (fallback) |
| `risk/engine.py` | Risk orchestration: banding, evidence, alert hooks |
| `risk/ensemble.py` | ML ensemble: IsolationForest (lead), LOF, DBSCAN, HDBSCAN, One-Class SVM, PCA error; RF/XGB/LGBM/CatBoost supervised |
| `risk/ml.py` | Feature builder + `IsolationForest` anomaly fitting |
| `risk/features.py` | Extreme-feature z-magnitude features for txn ML |
| `risk/weights.py` | Hybrid weight config (`APP_HYBRID_*`, renormalisation) |
| `risk/hybrid.py` | Weighted composite at txn/account/entity level |
| `risk/scenarios.py` | 22 rule scenarios (layering, structuring, mule, bursts…) |
| `risk/profiles.py` | Customer profile deviation rules |
| `risk/temporal.py` | Sliding-window temporal concentration |
| `risk/telecom.py` | Telecom scoring: call-before-transfer, repeated calls |
| `risk/internet.py` | IPDR bursts, device novelty |
| `risk/graph_features.py` | Graph-embedding kNN/PCA features |
| `risk/entity_risk.py` | Unified entity-risk concentration (shared phone/IMEI/IP/beneficiary) |
| `risk/moneyflow.py` | N-hop circular/layering money-flow detection |
| `risk/explain.py` | Score-band explainability helpers |
| `validate/__init__.py` | Validation harness API |
| `validate/__main__.py` | CLI: `python -m backend.validate --help` |
| `validate/ground_truth.py` | GT readers (synthetic anomalies, correlation sets, police xlsx) |
| `validate/comparator.py` | `build_validation_report()`: coverage, correlation fidelity, confusion matrices |
| `validate/measure.py` | P/R/F1/FPR/FNR helpers |

## Co-pilot (`investigative_copilot/`)

| File | Purpose |
|---|---|
| `router.py` | `/api/v1/copilot/*` routes: analyze, answer, translate, llm-tree, memory |
| `copilot_engine.py` | Main analysis: entity extraction → retrieval → SQL/graph → CoT → narrative (+ `explainability`) |
| `retrieval.py` | RAG evidence retrieval from the loaded SQLite bundle |
| `db_builder.py` | In-memory SQLite bundle (bank/cdr/ipdr tables, indexes) |
| `graph_engine.py` | 3-hop mule-chain graph traces (bank↔CDR↔IPDR) |
| `prompts.py` | Groq prompt templates (EN) with Hindi/Gujarati instructions |
| `llm_client.py` | LLM transport: Groq primary, deterministic fallback |
| `memory.py` | Per-user investigation memory for follow-up questions |

## Frontend (`frontend/`)

| File | Purpose |
|---|---|
| `app/layout.tsx` | Root layout (fonts, themes, global background, OmniWidget on landing) |
| `app/page.tsx` | Landing page (Matrix Rain sequence -> HeroSection fade-in) |
| `app/(app)/layout.tsx` | Dashboard layout (sidebar, header, OmniWidget, blur overlay) |
| `app/(app)/dashboard/page.tsx` | Dashboard shell (tabs per section, investigations route removed) |
| `components/dashboard/sections/*.tsx` | Overview, anomalies (with plain-English "why" modal), network, timeline, ingestion, reports, search, settings (investigations removed) |
| `components/dashboard/charts/*.tsx` | Pipeline-overview + activity charts |
| `components/dashboard/investigation-panel.tsx` | Redesigned multi-tab dossier panel (timeline, connections, alerts, IPDR) |
| `components/omni/omni-widget.tsx` | Floating eye co-pilot: conditional rendering on status, EN/हिं/ગુ answers, 2D/3D trees |
| `components/omni/eye-spinner.tsx` | Radar rings + rotating arc + pulsing eye spinner |
| `components/omni/omni-eye.tsx` | The OmniEye SVG logo |
| `components/omni/llm-tree-view.tsx` | 2D linking tree (React Flow): layered BFS layout, value-only filtering |
| `components/omni/three-d-tree.tsx` | 3D linking tree (three.js/React Three Fiber): orbit controls |
| `components/ui/*` | UI primitives |
| `lib/api.ts` | Typed API client (`Alert.explain_plain`, `CopilotQueryResult.explainability`…) |
| `lib/auth.tsx` | Client auth context |
| `lib/utils.ts` | Shared utilities |
| `middleware.ts` | Route protection |
| `package.json` | Project configuration and dependencies |

## Tests (`tests/`)

| File | Purpose |
|---|---|
| `conftest.py` | Shared fixtures (temp SQLite stores, memory databases) |
| `test_validate.py` | Ground-truth harness against synthetic GT |
| `test_api.py` | API routes test suite |
| `test_pipeline.py` | Ingestion pipeline checks (fingerprint -> normalisation -> fusion) |
| `test_risk.py` | Rule engine + ML ensemble scores verification |
| `test_hybrid_engine.py` | Weight composition, PCA-safe evaluations |
| `test_investigative_copilot.py` | Co-pilot deterministic logic |
| `test_copilot_llm.py` | LLM client translation / fallbacks |
| `test_auth.py` | JWT authentication logic tests |
