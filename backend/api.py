"""FastAPI backend.

Production entrypoint:

    uvicorn backend.api:app --host 0.0.0.0 --port 8000

or inside the container (see Dockerfile):

    python -m uvicorn backend.api:app --host $APP_API_HOST --port $APP_API_PORT
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import (Depends, FastAPI, File, HTTPException, Query,
                     UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from . import auth, config, evidence, ml, risk, store, dossier, events
from .behavioural import score_transactions
from .fusion import (account_analysis, build_timeline, circular_flows,
                     correlate_phones, fraud_heat, fused_table,
                     rapid_in_out, rapid_payouts, search_bundle,
                     cached_fraud_heat, cached_build_timeline, clear_fusion_cache)
from .graphs import (account_phone_graph, central_phones, ego_network,
                     money_graph, phone_call_graph, cached_money_graph,
                     cached_account_phone_graph, cached_phone_call_graph,
                     clear_graph_cache)
from .pipeline import ingest_folder
from .report import (generate_entity_str_report,
                     generate_str_report,
                     generate_transaction_str_report)
from .report_intelligence import clear_report_cache
from investigative_copilot import router as copilot_router

_log = config.log


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start with a fresh state on every restart."""
    yield


app = FastAPI(
    title="Financial & Telecom Analysis API",
    description="Bank-statement / CDR / IPDR ingestion, fusion and risk scoring "
                "for cyber-crime investigations.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(copilot_router.router)
# Force reload for copilot and cache locks
_state: dict = {}
_pipeline: dict = {"status": "IDLE", "progress": 0, "ready": False, "dataset_id": None}
_lock = threading.Lock()


def _persist() -> None:
    pass


class IngestRequest(BaseModel):
    folder: str


class IngestResponse(BaseModel):
    files_ok: int
    files_skipped: int
    errors: list[str]
    bank: int
    cdr: int
    ipdr: int
    complaints: int


@app.get("/")
def root():
    return {
        "name": "Financial & Telecom Analysis API",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
        "status": "/ingest/status",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "loaded": bool(_state),
        "last_ingested": store.last_ingested(),
    }


# ---------------------------------------------------------------- auth


@app.post("/auth/register")
def auth_register(body: auth.RegisterBody):
    """Create an account (first registered user becomes admin).
    Wipes all loaded data so the new user starts with a clean slate."""
    user = auth.register(body)
    wipe_all_data(reason=f"register:{body.username}")
    return {"detail": "user created", "user": user}


@app.post("/auth/login")
def auth_login(body: auth.LoginBody):
    """Exchange credentials for a Bearer token."""
    return auth.login(body)


@app.get("/auth/me")
def auth_me(user: dict = Depends(auth.require_user)):
    return {"user": user}


def wipe_all_data(reason: str = "manual") -> None:
    """Full data wipe: in-memory bundle, copilot DB, risk caches, and
    persisted store on disk. Called on register and logout."""
    with _lock:
        _state.pop("bundle", None)
        _state.pop("hybrid_warm", None)
        _pipeline.update({"status": "IDLE", "progress": 0, "ready": False, "dataset_id": None})
    copilot_router.reset_engine()
    risk.clear_cache()
    risk.clear_hybrid_cache()
    clear_fusion_cache()
    clear_report_cache()
    clear_graph_cache()
    store.clear_bundle()
    _log.info("full data wipe (%s)", reason)


@app.post("/auth/logout")
def auth_logout(user: dict = Depends(auth.require_user)):
    """End the session and wipe ALL loaded data (memory + disk) so the
    next login starts completely fresh."""
    wipe_all_data(reason=f"logout:{user.get('username')}")
    return {"detail": "signed out; all loaded data wiped"}


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


@app.post("/auth/change-password")
def auth_change_password(body: ChangePasswordBody,
                         user: dict = Depends(auth.require_user)):
    """Verify the current password and replace it (account settings tabs)."""
    return auth.change_password(user["username"], body.current_password,
                                body.new_password)


@app.get("/ingest/status")
def ingest_status(user: dict = Depends(auth.require_user)):
    b = _state.get("bundle")
    return {
        "loaded": bool(b),
        "last_ingested": store.last_ingested(),
        "bank": len(b["bank"]) if b else 0,
        "cdr": len(b["cdr"]) if b else 0,
        "ipdr": len(b["ipdr"]) if b else 0,
        "subscribers": len(b["subscribers"]) if b else 0,
        "complaints": len(b["complaints"]) if b else 0,
        "files_ok": len(b["files"]["ok"]) if b else 0,
        "files_skipped": len(b["files"]["skipped"]) if b else 0,
        "errors": b["files"]["errors"] if b else [],
    }


@app.get("/ingest/pipeline-status")
def get_pipeline_status(user: dict = Depends(auth.require_user)):
    return _pipeline


@app.delete("/ingest")
def ingest_clear(user: dict = Depends(auth.require_user)):
    """Drop the loaded bundle (and its persisted copy)."""
    with _lock:
        _state.pop("bundle", None)
        _pipeline.update({"status": "IDLE", "progress": 0, "ready": False, "dataset_id": None})
    copilot_router.reset_engine()
    risk.clear_cache()
    risk.clear_hybrid_cache()
    clear_fusion_cache()
    clear_report_cache()
    clear_graph_cache()
    store.clear_bundle()
    return {"cleared": True}


@app.post("/ingest")
def ingest(req: IngestRequest, user: dict = Depends(auth.require_user)) -> IngestResponse:
    import pathlib
    base_dir = config.data_dir().resolve()
    try:
        requested_path = pathlib.Path(req.folder).resolve()
    except Exception:
        raise HTTPException(400, "invalid path format")
    
    if not str(requested_path).startswith(str(base_dir)):
        raise HTTPException(403, "path traversal blocked: folder must be inside data directory")
        
    if not requested_path.is_dir():
        raise HTTPException(400, f"folder not found: {requested_path}")
    
    folder_str = str(requested_path)
    _log.info("ingesting folder %s", folder_str)
    with _lock:
        _state["bundle"] = ingest_folder(folder_str)
        _persist()
    copilot_router.reset_engine()
    risk.clear_cache()
    risk.clear_hybrid_cache()
    clear_fusion_cache()
    clear_report_cache()
    
    import uuid
    _pipeline["dataset_id"] = str(uuid.uuid4())
    _pipeline["status"] = "PARSING"
    _pipeline["progress"] = 10
    _pipeline["ready"] = False
    
    _run_pipeline_background(_state["bundle"])
    b = _state["bundle"]
    copilot_router.learn_bundle(b)
    _log.info("ingest done: %d files ok, %d skipped, %d errors | bank=%d cdr=%d ipdr=%d",
              len(b["files"]["ok"]), len(b["files"]["skipped"]),
              len(b["files"]["errors"]), len(b["bank"]), len(b["cdr"]),
              len(b["ipdr"]))
    return IngestResponse(
        files_ok=len(b["files"]["ok"]),
        files_skipped=len(b["files"]["skipped"]),
        errors=b["files"]["errors"],
        bank=len(b["bank"]), cdr=len(b["cdr"]),
        ipdr=len(b["ipdr"]), complaints=len(b["complaints"]),
    )


def _require_bundle() -> dict:
    if "bundle" not in _state:
        raise HTTPException(409, "no data loaded; POST /ingest first")
    return _state["bundle"]


@app.get("/summary")
def summary(user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    heat = cached_fraud_heat(b)
    return {
        "files": b["files"],
        "bank_records": len(b["bank"]),
        "cdr_records": len(b["cdr"]),
        "ipdr_records": len(b["ipdr"]),
        "complaints": len(b["complaints"]),
        "entities": {
            "phones": len(b["entities"]["phones"]),
            "accounts": len(b["entities"]["accounts"]),
            "upi_ids": len(b["entities"]["upi_ids"]),
            "imeis": len(b["entities"]["imeis"]),
            "imsis": len(b["entities"]["imsis"]),
            "ips": len(b["entities"]["ips"]),
        },
        "top_risk_accounts": [
            {"account_no": a["account_no"], "score": a["score"], "flags": a["flags"]}
            for a in heat["accounts"][:10]],
        "top_risk_phones": [
            {"phone": p["phone"], "score": p["score"], "flags": p["flags"]}
            for p in heat["phones"][:10]],
        "last_ingested": store.last_ingested(),
    }


@app.get("/accounts")
def accounts(min_score: float = 0, limit: int = Query(50, le=500),
             user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    heat = cached_fraud_heat(b)
    out = [a for a in heat["accounts"] if a["score"] >= min_score][:limit]
    return {"accounts": out}


@app.get("/phones")
def phones(min_score: float = 0, limit: int = Query(50, le=500),
           user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    heat = cached_fraud_heat(b)
    out = [p for p in heat["phones"] if p["score"] >= min_score][:limit]
    return {"phones": out}


@app.get("/phone/{phone}/egonet")
def phone_egonet(phone: str, depth: int = Query(1, ge=1, le=3), min_weight: int = 0,
                 mode: str = Query("evidence", pattern="^(evidence|full)$"),
                 user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    if mode == "evidence":
        return evidence.evidence_egonet(b, phone, depth=depth)
    g = phone_call_graph(b["cdr"])
    return ego_network(g, phone, depth=depth, min_weight=min_weight)


@app.get("/entity/{kind}/{value}")
def entity_evidence(kind: str, value: str,
                    user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    if kind not in ("account", "phone", "upi", "imei", "imsi", "ip", "name"):
        raise HTTPException(400, f"unsupported entity kind: {kind}")
    info = evidence.entity_intelligence(b, kind, value)
    if info is None:
        raise HTTPException(404, f"no evidence found for {kind} {value}")
    return info

@app.get("/dossier/{kind}/{value}")
def get_dossier(kind: str, value: str,
                user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    if kind not in ("transaction", "account", "phone", "upi", "imei", "imsi", "ip", "name"):
        raise HTTPException(400, f"unsupported dossier kind: {kind}")
    return dossier.generate_dossier(b, kind, value)


@app.get("/relationship/{a}/{b}")
def relationship_evidence(a: str, b: str,
                          user: dict = Depends(auth.require_user)):
    return evidence.relationship_intelligence(_require_bundle(), a, b)


@app.get("/graph/device")
def graph_device(phone: str, user: dict = Depends(auth.require_user)):
    return evidence.device_graph(_require_bundle(), phone)


@app.get("/graph/ip")
def graph_ip(phone: str, user: dict = Depends(auth.require_user)):
    return evidence.ip_graph(_require_bundle(), phone)


@app.get("/report/entity/{kind}/{value}")
def entity_report(kind: str, value: str,
                  user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    path = os.path.join(tempfile.gettempdir(),
                        f"str_entity_{kind}_{abs(hash(value)) % 100000}.pdf")
    try:
        generate_entity_str_report(b, kind, value, path)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return FileResponse(path, media_type="application/pdf",
                        filename=f"STR_{kind}_{value[:32]}.pdf")


@app.get("/timeline")
def timeline(kind: str | None = None, since: int | None = None,
             until: int | None = None, limit: int = Query(2000, le=20000),
             user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    events = cached_build_timeline(b)
    if kind:
        events = [e for e in events if e["kind"] == kind]
    if since is not None:
        events = [e for e in events if e["ts"] >= since]
    if until is not None:
        events = [e for e in events if e["ts"] <= until]
    return {"count": len(events), "events": events[:limit]}

@app.get("/timeline/event/{source_type}/{event_id}")
def timeline_event(source_type: str, event_id: str, user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    if source_type.lower() not in ("bank", "cdr", "ipdr", "complaint"):
        raise HTTPException(400, f"unsupported source type: {source_type}")
    out = events.get_event_dossier(b, source_type, event_id)
    if not out:
        raise HTTPException(404, f"event not found: {event_id}")
    return out


@app.get("/coincidence")
def coincidence(window_sec: int = Query(3600, ge=60, le=86400),
                limit: int = Query(100, le=1000),
                user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    res = correlate_phones(b, window_sec=window_sec)
    return {"window_sec": window_sec, "hits": res["hits"][:limit],
            "total": len(res["hits"])}


@app.get("/payouts")
def payouts(threshold: int = Query(5, ge=1, le=100), window_min: int = Query(60, ge=1),
            user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return {"rapid": rapid_payouts(b, threshold, window_min),
            "round": cached_fraud_heat(b)["round_payouts"]}


@app.get("/account/{account_no}")
def account_detail(account_no: str, user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    accts = account_analysis(b["bank"], b["complaints"])
    if account_no not in accts:
        raise HTTPException(404, "account not found")
    txns = [r for r in b["bank"] if r.get("account_no") == account_no]
    return {"profile": accts[account_no],
            "txns": sorted(txns, key=lambda r: r.get("ts") or 0,
                           reverse=True)[:200]}


_STR_PATH = os.path.join(tempfile.gettempdir(), "str_report.pdf")


def _str_is_fresh() -> bool:
    if not os.path.exists(_STR_PATH):
        return False
    age_h = (datetime.now(timezone.utc).timestamp()
             - os.path.getmtime(_STR_PATH)) / 3600
    return age_h <= config.str_file_ttl_hours()


@app.get("/report")
def report(user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    if not _str_is_fresh():
        generate_str_report(b, _STR_PATH)
    return FileResponse(_STR_PATH, media_type="application/pdf",
                        filename="STR_Report.pdf")


@app.get("/entities")
def entities(user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return b["entities"]


# ---------------------------------------------------------------- hybrid engine
# Hybrid Multi-Stage Fraud Detection Engine (ERH26_PS_03): rules + ML
# ensemble + behavioural profiling + temporal windows + telecom/internet
# correlation + money-flow N-hop + entity risk + named scenario detection,
# fused through configurable weights with full explainability.
# The engine runs once per bundle and caches; ingest/restore trigger a
# background warm-up so the first UI request is fast.


def _run_pipeline_background(bundle: dict) -> None:
    def _run() -> None:
        try:
            from backend.fusion import cached_fused_base, cached_build_timeline
            from backend.graphs import cached_money_graph, cached_account_phone_graph, cached_phone_call_graph
            import backend.risk.hybrid as hybrid
            
            _pipeline["status"] = "FUSING"
            _pipeline["progress"] = 25
            cached_fused_base(bundle)
            cached_build_timeline(bundle)
            
            # Fused data is ready — page can now render without waiting for ML
            _pipeline["status"] = "FUSED_READY"
            _pipeline["progress"] = 40
            
            _pipeline["status"] = "SCORING"
            _pipeline["progress"] = 50
            hybrid.hybrid_analyze(bundle)
            
            _pipeline["status"] = "GRAPHS"
            _pipeline["progress"] = 85
            cached_money_graph(bundle)
            cached_account_phone_graph(bundle)
            cached_phone_call_graph(bundle)
            
            _pipeline["status"] = "READY"
            _pipeline["progress"] = 100
            _pipeline["ready"] = True
            
            _state["hybrid_warm"] = True
            _log.info("hybrid engine warmed (%d txns)", len(bundle.get("bank", [])))
        except Exception:
            _state["hybrid_warm"] = False
            _pipeline["status"] = "ERROR"
            _log.exception("hybrid engine warm-up failed")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return


def _enrich_txn_row(row: dict, bank_by_id: dict) -> dict:
    """Attach customer name + phone to a hybrid transaction row."""
    rec = bank_by_id.get(row.get("transaction_id") or "", {})
    row = dict(row)
    row["customer_name"] = rec.get("account_name") or rec.get("customer_name") or ""
    row["customer_phone"] = rec.get("sender_phone") or rec.get("customer_phone") or ""
    return row


@app.get("/hybrid/transactions")
def hybrid_transactions(min_score: float = Query(0, ge=0, le=100),
                        limit: int = Query(50, le=1000),
                        band: str = Query("", pattern="^(SAFE|LOW|MEDIUM|HIGH|CRITICAL)?$"),
                        user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    scored = risk.hybrid_transaction_risk(b)
    bank_by_id = {r.get("txn_id"): r for r in b.get("bank", [])}
    results = []
    for s in scored:
        if s["risk_score"] < min_score:
            continue
        if band and s["risk_band"] != band:
            continue
        results.append(_enrich_txn_row({
            "transaction_id": s.get("transaction_id"),
            "account_no": s.get("account_no"),
            "amount": s.get("amount"),
            "mode": s.get("mode"),
            "customer_id": s.get("sender_customer_id"),
            "risk_score": s["risk_score"],
            "risk_band": s["risk_band"],
            "rules_fired": s.get("rules_fired", []),
            "breakdown": s.get("breakdown", []),
            "evidence": s.get("evidence", []),
            "hybrid_components": s.get("hybrid_components", {}),
            "models_fired": s.get("models_fired", []),
            "scenarios": s.get("scenarios", []),
            "confidence": s.get("confidence"),
        }, bank_by_id))
        if len(results) >= limit:
            break
    return {"results": results, "total": len(results)}


@app.get("/hybrid/accounts")
def hybrid_accounts(min_score: float = Query(0, ge=0, le=100),
                    limit: int = Query(50, le=500),
                    user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    accounts = [a for a in risk.hybrid_account_risk(b)
                if a["risk_score"] >= min_score][:limit]
    return {"accounts": accounts, "total": len(accounts)}


@app.get("/hybrid/entities")
def hybrid_entities(min_score: float = Query(0, ge=0, le=100),
                    limit: int = Query(50, le=500),
                    user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    entities = [e for e in risk.hybrid_entity_risk(b)
                if e["risk_score"] >= min_score][:limit]
    return {"entities": entities, "total": len(entities)}


@app.get("/hybrid/scenarios")
def hybrid_scenarios(limit: int = Query(20, le=100),
                     user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    res = risk.hybrid_analyze(b)
    scen = res["scenarios"]
    return {"stats": scen["stats"],
            "moneyflow": scen["moneyflow"]["stats"],
            "entity": {k: v for k, v in res["entity_risk"]["stats"].items()},
            "top": scen["stats"]["top_scenarios"][:limit]}


@app.get("/hybrid/stats")
def hybrid_stats(user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    res = risk.hybrid_analyze(b)
    return {"stats": res["stats"],
            "scenarios": res["scenarios"]["stats"],
            "weights": risk.hybrid_weights()}


@app.get("/hybrid/explain/transaction/{transaction_id}")
def hybrid_explain_transaction(transaction_id: str,
                               user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    out = risk.explanations_for_txn(b, transaction_id)
    if not out:
        raise HTTPException(404, "transaction not found")
    return {"explanation": out}


@app.get("/hybrid/explain/account/{account_no}")
def hybrid_explain_account(account_no: str,
                           user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    out = risk.explanations_for_account(b, account_no)
    if not out:
        raise HTTPException(404, "account not found")
    return {"explanation": out}


@app.get("/hybrid/explain/entity/{kind}/{entity}")
def hybrid_explain_entity(kind: str, entity: str,
                          user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    out = risk.explanations_for_entity(b, kind, entity)
    if not out:
        raise HTTPException(404, "entity not found")
    return {"explanation": out}


@app.get("/hybrid/weights")
def hybrid_weights(user: dict = Depends(auth.require_user)):
    return {"weights": risk.hybrid_weights()}


# ---------------------------------------------------------------- risk engine
# Phase-1 hybrid scoring: rule/ML/graph composite per account and the
# max() fusion per transaction, exposed for the investigation UI.


@app.get("/risk/accounts")
def risk_accounts(min_score: float = Query(0, ge=0, le=100),
                  limit: int = Query(50, le=500),
                  user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    res = risk.cached_account_risk(b)
    accounts = [a for a in res["accounts"] if a["risk_score"] >= min_score][:limit]
    return {"accounts": accounts, "total": len(accounts),
            "detectors": res["detectors"], "graph": res["graph"],
            "ensemble_fitted": res["ensemble_fitted"]}


@app.get("/risk/transactions")
def risk_transactions(min_score: float = Query(0, ge=0, le=100),
                      limit: int = Query(50, le=1000),
                      band: str = Query("", pattern="^(SAFE|LOW|MEDIUM|HIGH|CRITICAL)?$"),
                      user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    scored = risk.cached_transaction_risk(b)
    results = []
    for s in scored:
        if s["risk_score"] < min_score:
            continue
        if band and s["risk_band"] != band:
            continue
        results.append({
            "transaction_id": s["transaction_id"],
            "account_no": s.get("account_no"),
            "amount": s.get("amount"),
            "mode": s.get("mode"),
            "risk_score": s["risk_score"],
            "risk_band": s["risk_band"],
            "rules_fired": s["rules_fired"],
            "breakdown": s["breakdown"],
            "evidence": s["evidence"],
            "risk_components": s["risk_components"],
        })
        if len(results) >= limit:
            break
    return {"results": results, "total": len(results)}


@app.get("/anomalies/top-50")
def anomalies_top(limit: int = Query(50, le=500),
                  user: dict = Depends(auth.require_user)):
    """The 50 highest-risk transactions — the analyst alert feed."""
    return risk_transactions(min_score=0, limit=limit, band="", user=user)


@app.get("/transactions/{transaction_id}")
def transaction_detail(transaction_id: str,
                       user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    scored = risk.cached_transaction_risk(b)
    s = next((x for x in scored if x["transaction_id"] == transaction_id),
             None)
    if s is None:
        raise HTTPException(404, "transaction not found")
    return {"transaction": s}


@app.get("/loading/status")
def loading_status(user: dict = Depends(auth.require_user)):
    b = _state.get("bundle")
    if not b:
        return {"loaded": False, "detail": "no bundle ingested yet"}
    return {
        "loaded": True,
        "bank": len(b.get("bank", [])),
        "cdr": len(b.get("cdr", [])),
        "ipdr": len(b.get("ipdr", [])),
        "complaints": len(b.get("complaints", [])),
        "entities": len(b.get("entities", [])),
        "last_ingested": store.last_ingested(),
        "cache_warm": bool(_state.get("hybrid_warm", False)),
    }


@app.get("/report/transaction/{transaction_id}")
def transaction_report(transaction_id: str,
                       user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    path = os.path.join(tempfile.gettempdir(),
                        f"str_transaction_{transaction_id}.pdf")
    try:
        generate_transaction_str_report(b, transaction_id, path)
    except ValueError:
        raise HTTPException(404, "transaction not found")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"STR_{transaction_id}.pdf")


@app.get("/reports/intelligence")
def reports_intelligence(user: dict = Depends(auth.require_user)):
    """Aggregated forensic intelligence for the Reports centre.

    One cached bundle-wide payload covering the executive summary, risk
    heatmaps, network / temporal / ML / circular-flow / fusion intelligence,
    statistical analytics and investigation recommendations. Every metric is
    computed from the loaded bundle by the fusion, graph, ML, timeline and
    rule engines — nothing is fabricated.
    """
    from .report_intelligence import report_intelligence
    return report_intelligence(_require_bundle())


# ---------------------------------------------------------------- analytics
# Problem-statement coverage: money-flow network (IV-a), circular flows and
# layering (III-a), ML anomaly layer (III-a), cross-entity search (IV-b).


@app.get("/graph/money")
def graph_money(min_amount: float = Query(0, ge=0),
                limit: int = Query(300, le=1000),
                user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    g = cached_money_graph(b)
    nodes, edges = [], []
    for n in g.nodes:
        nodes.append({"id": n, "kind": "account"
                      if g.nodes[n].get("kind") == "account" else "counterparty"})
    for u, v, d in g.edges(data=True):
        if d.get("amount", 0) < min_amount:
            continue
        edges.append({"source": u, "target": v, "weight": d.get("weight", 0),
                      "amount": round(d.get("amount", 0), 2)})
        if len(edges) >= limit:
            break
    return {"nodes": nodes, "edges": edges,
            "stats": {"nodes": len(nodes), "edges": g.number_of_edges()}}


@app.get("/graph/account-phone")
def graph_account_phone(limit: int = Query(200, le=500),
                        user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    g = cached_account_phone_graph(b)
    nodes = [{"id": n, "kind": g.nodes[n].get("kind", "")} for n in list(g.nodes)[:limit]]
    edges = [{"source": u, "target": v, "kind": d.get("kind", "")}
             for u, v, d in list(g.edges(data=True))[:limit * 4]]
    return {"nodes": nodes, "edges": edges}


@app.get("/graph/central-phones")
def graph_central_phones(top: int = Query(15, ge=1, le=100),
                         user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return {"phones": central_phones(cached_phone_call_graph(b), top)}


@app.get("/flows/patterns")
def flows_patterns(min_amount: float = Query(10000, ge=0),
                   window_min: int = Query(15, ge=1),
                   user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return {
        "circular": circular_flows(b, min_amount=min_amount),
        "rapid_in_out": rapid_in_out(b, window_min=window_min),
    }


@app.get("/ml/outliers")
def ml_outliers_endpoint(contamination: float = Query(0.05, gt=0, le=0.5),
                         min_txns: int = Query(5, ge=1),
                         user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return ml.ml_outliers(b, contamination=contamination, min_txns=min_txns)


@app.get("/search")
def search(q: str = Query("", max_length=128),
           limit: int = Query(50, le=200),
           user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return search_bundle(b, q, limit=limit)


# ---------------------------------------------------------------- frontend
# Legacy endpoints the Next.js frontend (localhost:3000) calls; kept in the
# old shape so the UI works unchanged against this engine.


@app.post("/upload/parse-multi")
async def upload_parse_multi(files: list[UploadFile] = File(...),
                             user: dict = Depends(auth.require_user)):
    if not files:
        raise HTTPException(400, "no files uploaded")
    tmp = tempfile.mkdtemp(prefix="backend_upload_")
    names: list[str] = []
    for f in files:
        name = os.path.basename(f.filename or "upload")
        with open(os.path.join(tmp, name), "wb") as fh:
            fh.write(await f.read())
        names.append(name)
    _log.info("uploading %d files -> %s", len(names), tmp)
    def _do_ingest():
        with _lock:
            _state["bundle"] = ingest_folder(tmp)
            _persist()
            
    from fastapi.concurrency import run_in_threadpool
    await run_in_threadpool(_do_ingest)
    copilot_router.reset_engine()
    risk.clear_cache()
    risk.clear_hybrid_cache()
    clear_fusion_cache()
    clear_report_cache()
    
    import uuid
    _pipeline["dataset_id"] = str(uuid.uuid4())
    _pipeline["status"] = "PARSING"
    _pipeline["progress"] = 10
    _pipeline["ready"] = False
    
    _run_pipeline_background(_state["bundle"])
    b = _state["bundle"]
    return {
        "detail": "fusion complete",
        "files": [{"name": n} for n in b["files"]["ok"]]
                 or [{"name": n} for n in names],
        "skipped": b["files"]["skipped"],
        "errors": b["files"]["errors"],
        "bank": len(b["bank"]), "cdr": len(b["cdr"]), "ipdr": len(b["ipdr"]),
        "complaints": len(b["complaints"]),
    }


@app.get("/scoring/alerts")
def scoring_alerts(min_risk: float = Query(50, ge=0, le=100),
                   limit: int = Query(100, le=1000),
                   user: dict = Depends(auth.require_user)):
    """Highest-risk *transactions* flagged by the behavioural engine.

    Accounts listed in the NCRP fraud complaint ledger receive a hard
    +60 boost (rule NCRP_FRAUD_ACCOUNT), so complaints never disappear
    from the alert feed regardless of transaction behaviour.
    """
    b = _require_bundle()
    if not b.get("bank"):
        return {"results": [], "total": 0}
    ncrp_accounts = {str(c.get("account_no") or "").strip()
                     for c in b.get("complaints", [])}
    ncrp_accounts.discard("")
    bank_by_id = {r.get("txn_id"): r for r in b.get("bank", [])}
    res = risk.hybrid_analyze_fast(b)
    if res is None:
        raise HTTPException(425, "Anomaly detection engine is still warming up.")
    scored_sorted = res["transactions_sorted"]
    results = []
    for orig_s in scored_sorted:
        is_ncrp = orig_s.get("account_no") in ncrp_accounts
        if not is_ncrp and orig_s.get("risk_score", 0) < min_risk:
            continue
            
        s = dict(orig_s)  # defensive copy only for candidate rows
        if "transaction_id" not in s:
            s["transaction_id"] = s.get("txn_id") or ""
        if is_ncrp and "NCRP_FRAUD_ACCOUNT" not in s.get("rules_fired", []):
            s["risk_score"] = min(s.get("risk_score", 0) + 60, 100)
            s["risk_band"] = ("CRITICAL" if s["risk_score"] >= 75 else "HIGH"
                              if s["risk_score"] >= 50 else "MEDIUM")
            if "rules_fired" not in s:
                s["rules_fired"] = []
            s["rules_fired"].append("NCRP_FRAUD_ACCOUNT")
            s["breakdown"] = [*s.get("breakdown", []), {
                "rule": "NCRP_FRAUD_ACCOUNT", "points": 60,
                "reason": "Account is listed in the NCRP fraud complaint "
                          "ledger"}]
        if s.get("risk_score", 0) < min_risk:
            continue
        row = _enrich_txn_row({
            "transaction_id": s.get("txn_id") or s.get("transaction_id") or "",
            "sender_customer_id": s.get("sender_phone") or s.get("sender_customer_id") or "",
            "amount_usd": s.get("debit") or s.get("credit") or s.get("amount") or 0.0,
            "date": s.get("date", ""),
            "time": s.get("time", ""),
            "risk_score": s.get("risk_score", 0),
            "risk_band": s.get("risk_band", "SAFE"),
            "rules_fired": str(s.get("rules_fired") or s.get("models_fired") or []),
            "rules": s.get("rules_fired") or s.get("models_fired") or [],
            "breakdown": s.get("breakdown") or s.get("scenarios") or [],
            "evidence": s.get("evidence") or "Hybrid model detection",
            "confidence": s.get("confidence") or (s.get("risk_score", 0) / 100.0),
            "mode": s.get("mode", ""),
            "bank": s.get("bank", ""),
            "ncrp_states": [],
        }, bank_by_id)
        from .explain import plain_reason
        row["explain_plain"] = plain_reason(
            s.get("rules_fired") or s.get("models_fired") or [],
            s.get("breakdown") or s.get("scenarios"),
            amount=s.get("debit") or s.get("credit") or s.get("amount") or 0,
            transaction_id=s.get("txn_id") or s.get("transaction_id") or "",
            confidence=s.get("confidence") or (s.get("risk_score", 0) / 100.0)
        )
        results.append(row)
        if len(results) >= limit:
            break
    return {"results": results, "total": len(results)}


_FUSED_CSV_COLUMNS = (
    "transaction_id", "date", "time", "mode", "amount", "direction",
    "account_no", "account_name", "bank", "counterparty_name",
    "counterparty_bank", "receiver_account", "sender_phone",
    "receiver_phone", "call_count", "ipdr_count", "ncrp",
    "risk_score", "risk_band",
)

_score_cache: dict = {}
_score_cache_lock = threading.Lock()



@app.get("/data/fused")
def fused_data(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
               q: str = Query(""), account: str = Query(""), mode: str = Query(""),
               risk_annotate: int = Query(0, ge=0, le=1),
               user: dict = Depends(auth.require_user)):
    """Fused bank x CDR x IPDR preview table (the post-ingestion fusion view).

    Pass risk_annotate=1 to attach behavioural risk scores to each row
    (expensive on large bundles — runs the full scoring engine once).
    """
    b = _require_bundle()
    if _pipeline.get("status") in ("PARSING", "FUSING") and _pipeline.get("dataset_id"):
        raise HTTPException(425, "Fusion dataset is being prepared.")
    scored = None
    if risk_annotate:
        res = risk.hybrid_analyze_fast(b)
        if res:
            scored = res["transactions"]
    return fused_table(b, offset=offset, limit=limit, q=q,
                       account=account, mode=mode, scored=scored)


@app.get("/data/fused.csv")
def fused_data_csv(q: str = Query(""), account: str = Query(""), mode: str = Query(""),
                   max_rows: int = Query(50000, ge=1, le=200000),
                   user: dict = Depends(auth.require_user)):
    """Download the fused dataset as CSV (the 'fused CSV' export)."""
    b = _require_bundle()
    page = fused_table(b, offset=0, limit=max_rows, q=q, account=account, mode=mode)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FUSED_CSV_COLUMNS,
                            extrasaction="ignore")
    writer.writeheader()
    for row in page["rows"]:
        writer.writerow({k: row.get(k) for k in _FUSED_CSV_COLUMNS})
    data = "\ufeff" + buf.getvalue()
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="fused_data.csv"'},
    )


# ---------------------------------------------------------------- analysis
# Anomalies workbench: account×hour heatmap + relationship model between
# user-selected transactions (multi-select in the fused-records table).


class HeatmapBody(BaseModel):
    account: str | None = None
    max_accounts: int = 30


class RelationshipBody(BaseModel):
    transaction_ids: list[str]
    window_min: int = 30


@app.post("/analysis/heatmap")
def analysis_heatmap(body: HeatmapBody,
                     user: dict = Depends(auth.require_user)):
    """Account × hour-of-day activity heatmap over the fused bank corpus."""
    from .analysis import account_hour_heatmap
    b = _require_bundle()
    return account_hour_heatmap(b, account=body.account or "",
                                max_accounts=max(1, min(60, body.max_accounts)))


@app.post("/analysis/relationship")
def analysis_relationship(body: RelationshipBody,
                          user: dict = Depends(auth.require_user)):
    """Relationship model between the selected transactions: money-flow legs,
    shared accounts/phones, time proximity — with edge strength + reasons."""
    from .analysis import relationship_model
    b = _require_bundle()
    ids = [str(t) for t in body.transaction_ids if t][:500]
    if not ids:
        raise HTTPException(400, "select at least one transaction")
    return relationship_model(b, ids, window_min=max(1, min(1440, body.window_min)))


class EvaluateBody(BaseModel):
    ground_truth_dir: str | None = None
    anomalies_csv: str | None = None
    risk_thresholds: list[int] = [25, 50, 75]
    engine: str = "hybrid"


@app.post("/evaluate")
def evaluate(bundle_eval: EvaluateBody,
             user: dict = Depends(auth.require_user)):
    """Run the ground-truth evaluation harness against the loaded bundle.

    Accepts either a full synthetic GT directory (anomaly + bank_cdr +
    cdr_ipdr CSVs) or a single anomalies CSV (e.g. the reduced police GT).
    Reports coverage, correlation fidelity and anomaly-detection confusion
    matrices (TP/FP/FN/TN, precision, recall, F1, FPR, FNR) at each risk
    threshold, broken down by source scope and scenario type.
    """
    from backend.validate.comparator import build_validation_report
    from backend.validate.ground_truth import read_anomalies_csv
    b = _require_bundle()
    if bundle_eval.anomalies_csv:
        gt = read_anomalies_csv(bundle_eval.anomalies_csv)
    elif bundle_eval.ground_truth_dir:
        from backend.validate import read_synthetic_gt
        gt = read_synthetic_gt(bundle_eval.ground_truth_dir)
    else:
        raise HTTPException(400, "provide ground_truth_dir or anomalies_csv")
    thresholds = tuple(min(max(int(t), 0), 100)
                       for t in (bundle_eval.risk_thresholds or [25, 50, 75]))
    if not thresholds:
        raise HTTPException(400, "risk_thresholds must not be empty")
    report = build_validation_report(b, gt, thresholds)
    report["engine"] = bundle_eval.engine
    return report
