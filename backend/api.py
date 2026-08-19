"""FastAPI entrypoint for the financial & telecom analysis backend.

Production entrypoint:

    uvicorn backend.api:app --host 0.0.0.0 --port 8000

or inside the container (see Dockerfile):

    python -m uvicorn backend.api:app --host $APP_API_HOST --port $APP_API_PORT

Updated with Tri-Netra Investigative Co-Pilot enhancements.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import csv
import io
import os
import sys
from pathlib import Path
import tempfile
import threading
from typing import Any

# Ensure both workspace root and backend directory are in sys.path
_cur_dir = Path(__file__).resolve().parent
_root_dir = _cur_dir.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
if not __package__:
    import importlib
    _mod = importlib.import_module("backend.api")
    globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith("__")})
    app = _mod.app
else:
    from fastapi import (
        Depends, FastAPI, File, HTTPException, Query, UploadFile, status,
    )
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
    """Clean startup workflow: clears stale caches, pipeline jobs and temp data if configured."""
    _log.info("[AUTH] Storage database path resolved to: %s", store._db_path().resolve())
    try:
        if config.clear_on_startup():
            store.clear_bundle()
            with _lock:
                _state.clear()
            orchestrator.reset()
            copilot_router.reset_engine()
            risk.clear_cache()
            risk.clear_hybrid_cache()
            clear_fusion_cache()
            clear_report_cache()
            clear_graph_cache()
            
            # Clean orphan temp upload folders from temp directory
            import glob, shutil
            for tmp_folder in glob.glob(os.path.join(tempfile.gettempdir(), "backend_upload_*")):
                try:
                    shutil.rmtree(tmp_folder, ignore_errors=True)
                except Exception:
                    pass
            _log.info("[CLEANUP] Clean startup: Purged stale datasets, previous pipeline jobs, temp files, and in-memory caches.")
        else:
            bundle = store.load_bundle()
            if bundle and (bundle.get("bank") or bundle.get("cdr") or bundle.get("ipdr")):
                with _lock:
                    _state["bundle"] = bundle
                copilot_router.learn_bundle(bundle)
                orchestrator.start_pipeline(bundle)
                _log.info("Restored persisted bundle from store on startup")
    except Exception as e:
        _log.warning("Failed during startup lifecycle: %s", e)
    yield


app = FastAPI(
    title="Financial & Telecom Analysis API",
    description="Bank-statement / CDR / IPDR ingestion, fusion and risk scoring "
                "for cyber-crime investigations.",
    version="3.0.0",
    lifespan=lifespan,
)

cors_list = config.cors_origins()
if "*" in cors_list:
    allow_origins_cfg = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
else:
    allow_origins_cfg = cors_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins_cfg,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(copilot_router.router)
# Force reload for copilot and cache locks
class _AutoBundleState(dict):
    def get(self, key, default=None):
        if key == "bundle" and not super().__contains__("bundle"):
            try:
                b = store.load_bundle()
                if b and (b.get("bank") or b.get("cdr") or b.get("ipdr")):
                    super().__setitem__("bundle", b)
                    copilot_router.learn_bundle(b)
                    return b
            except Exception:
                pass
        return super().get(key, default)

    def __getitem__(self, key):
        val = self.get(key)
        if val is None and not super().__contains__(key):
            raise KeyError(key)
        return val

    def __contains__(self, key):
        if key == "bundle" and not super().__contains__("bundle"):
            try:
                b = store.load_bundle()
                if b and (b.get("bank") or b.get("cdr") or b.get("ipdr")):
                    super().__setitem__("bundle", b)
                    copilot_router.learn_bundle(b)
                    return True
            except Exception:
                pass
        return super().__contains__(key)

_state = _AutoBundleState()
if "backend.api" in sys.modules:
    sys.modules["backend.api"]._state = _state
if "api" in sys.modules:
    sys.modules["api"]._state = _state

from backend.orchestrator import orchestrator
from concurrent.futures import ThreadPoolExecutor

_lock = threading.Lock()
_persist_executor = ThreadPoolExecutor(max_workers=1)

def _persist() -> None:
    b = _state.get("bundle")
    if b:
        # Run serialization asynchronously in background so HTTP response returns instantly
        _persist_executor.submit(store.save_bundle, b)



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
        "service": "Financial & Telecom Forensic Analysis API",
        "version": "3.0.0",
        "status": "online",
        "endpoints": {
            "auth": ["/auth/login", "/auth/register", "/auth/me"],
            "ingest": ["/ingest", "/ingest/status", "/ingest/pipeline-status", "/upload/parse-multi"],
            "fusion": ["/summary", "/data/fused", "/data/fused.csv", "/scoring/alerts"],
            "copilot": ["/api/v1/copilot/query", "/api/v1/copilot/stats"],
            "docs": "/docs",
        },
    }


@app.get("/health")
def health():
    b = _state.get("bundle")
    return {
        "status": "ok",
        "loaded": bool(b),
        "last_ingested": store.last_ingested(),
        "stats": {
            "bank": len(b.get("bank", [])) if b else 0,
            "cdr": len(b.get("cdr", [])) if b else 0,
            "ipdr": len(b.get("ipdr", [])) if b else 0,
            "complaints": len(b.get("complaints", [])) if b else 0,
        },
    }


# ---------------------------------------------------------------- auth
# Bearer-token authentication for analyst logins; required on all data
# routes when auth is configured.


class LoginBody(BaseModel):
    username: str
    password: str


class RegisterBody(BaseModel):
    username: str
    password: str


@app.post("/auth/register")
def auth_register(body: RegisterBody):
    if not config.allow_signup():
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "registration is disabled on this server")
    user = auth.register(
        auth.RegisterBody(
            username=body.username,
            password=body.password,
        )
    )
    token = auth.issue_token(user["username"], user["role"])
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/auth/login")
def auth_login(body: LoginBody):
    return auth.login(
        auth.LoginBody(
            username=body.username,
            password=body.password,
        )
    )


@app.get("/auth/me")
def auth_me(user: dict = Depends(auth.require_user)):
    return {"user": user}


@app.post("/auth/logout")
def auth_logout(user: dict = Depends(auth.require_user)):
    return {"detail": "logged out"}


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
    return orchestrator.get_status()


@app.delete("/ingest")
def ingest_clear(user: dict = Depends(auth.require_user)):
    """Drop the loaded bundle (and its persisted copy)."""
    with _lock:
        if "bundle" in _state:
            _state.pop("bundle", None)
        dict.clear(_state)
    store.clear_bundle()
    orchestrator.reset()
    copilot_router.reset_engine()
    risk.clear_cache()
    risk.clear_hybrid_cache()
    clear_fusion_cache()
    clear_report_cache()
    clear_graph_cache()
    return {"cleared": True}


@app.post("/ingest")
def ingest(req: IngestRequest, user: dict = Depends(auth.require_user)) -> IngestResponse:
    import pathlib
    base_dir = config.data_dir().resolve()
    try:
        requested_path = pathlib.Path(req.folder).resolve()
    except Exception:
        raise HTTPException(400, "invalid path format")
    
    if not requested_path.is_relative_to(base_dir):
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
    clear_graph_cache()
    
    orchestrator.start_pipeline(_state["bundle"])
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
    status = orchestrator.get_status()
    
    if status.get("anomalies_ready") or status.get("ready"):
        res = risk.hybrid_analyze_fast(b)
        if not res:
            res = risk.hybrid_analyze(b)
        heat = res.get("accounts", {})
        top_accs = [
            {"account_no": a.get("account_no"), "score": a.get("risk_score", 0), "flags": a.get("flags", [])}
            for a in heat.values() if a.get("risk_score", 0) >= 50
        ]
        top_accs.sort(key=lambda x: -x["score"])
        top_accs = top_accs[:10]
    else:
        top_accs = []
        
    top_phones = []
    
    ent = b.get("entities", {})
    phones_count = len(ent.get("phones", [])) if ent.get("phones") else len({str(r.get("sender_phone") or r.get("receiver_phone") or "") for r in b.get("bank", []) if r.get("sender_phone") or r.get("receiver_phone")} | {str(r.get("caller_msisdn") or r.get("recipient_msisdn") or "") for r in b.get("cdr", []) if r.get("caller_msisdn") or r.get("recipient_msisdn")} | {str(r.get("msisdn") or "") for r in b.get("ipdr", []) if r.get("msisdn")})
    accounts_count = len(ent.get("accounts", [])) if ent.get("accounts") else len({str(r.get("account_no") or "") for r in b.get("bank", []) if r.get("account_no")})
    upi_count = len(ent.get("upi_ids", [])) if ent.get("upi_ids") else len({str(r.get("upi_id") or "") for r in b.get("bank", []) if r.get("upi_id")})
    imeis_count = len(ent.get("imeis", [])) if ent.get("imeis") else len({str(r.get("caller_imei") or r.get("imei") or "") for r in b.get("cdr", []) if r.get("caller_imei") or r.get("imei")})
    ips_count = len(ent.get("ips", [])) if ent.get("ips") else len({str(r.get("source_ip") or r.get("ip") or "") for r in b.get("ipdr", []) if r.get("source_ip") or r.get("ip")})

    return {
        "bank_records": len(b.get("bank", [])),
        "cdr_records": len(b.get("cdr", [])),
        "ipdr_records": len(b.get("ipdr", [])),
        "complaints": len(b.get("complaints", [])),
        "files": b.get("files", {"ok": [], "skipped": [], "errors": []}),
        "entities": {
            "phones": phones_count,
            "accounts": accounts_count,
            "upi_ids": upi_count,
            "imeis": imeis_count,
            "imsis": len(ent.get("imsis", [])),
            "ips": ips_count,
        },
        "top_risk_accounts": top_accs,
        "top_risk_phones": top_phones,
        "last_ingested": store.last_ingested(),
    }


@app.get("/accounts")
def accounts(min_score: float = 0, limit: int = Query(50, le=500),
             user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    heat = cached_fraud_heat(b)
    analysis = account_analysis(b)
    out = []
    for a in heat["accounts"]:
        if a["score"] < min_score:
            continue
        acc_no = a["account_no"]
        st = analysis.get(acc_no, {})
        out.append({
            "account_no": acc_no,
            "bank": a.get("bank", ""),
            "txns": st.get("txns", 0),
            "credit": st.get("credit", 0.0),
            "debit": st.get("debit", 0.0),
            "score": a["score"],
            "flags": a["flags"],
        })
        if len(out) >= limit:
            break
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
    if kind not in ("account", "phone", "upi", "imei", "imsi", "ip", "name"):
        raise HTTPException(400, f"unsupported entity kind: {kind}")
    b = _require_bundle()
    import hashlib
    safe_val = hashlib.sha256(value.encode()).hexdigest()[:16]
    path = os.path.join(tempfile.gettempdir(),
                        f"str_entity_{kind}_{safe_val}.pdf")
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


@app.get("/payouts")
def payouts(user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return rapid_payouts(b)


@app.get("/coincidence")
def coincidence(window_sec: int = Query(3600, ge=60, le=86400),
                limit: int = Query(100, le=1000),
                user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    return correlate_phones(b, window_sec=window_sec, limit=limit)


@app.get("/report")
def report(user: dict = Depends(auth.require_user)):
    b = _require_bundle()
    path = os.path.join(tempfile.gettempdir(), "str_report.pdf")
    generate_str_report(b, path)
    return FileResponse(path, media_type="application/pdf",
                        filename="STR_Report.pdf")


# ---------------------------------------------------------------- investigations
# Analyst case management: structured findings, notes and status persistence
# backed by SQLite.


class CreateInvestigationBody(BaseModel):
    title: str
    notes: str = ""


class UpdateInvestigationBody(BaseModel):
    title: str | None = None
    notes: str | None = None
    status: str | None = None


class AddFindingBody(BaseModel):
    kind: str
    title: str
    detail: str = ""
    severity: str = "medium"


@app.get("/investigations")
def investigations_list(user: dict = Depends(auth.require_user)):
    return {"investigations": store.list_investigations()}


@app.post("/investigations")
def investigations_create(body: CreateInvestigationBody,
                          user: dict = Depends(auth.require_user)):
    inv = store.create_investigation(body.title, body.notes)
    return {"investigation": inv}


@app.get("/investigations/{investigation_id}")
def investigations_get(investigation_id: int,
                       user: dict = Depends(auth.require_user)):
    inv = store.get_investigation(investigation_id)
    if not inv:
        raise HTTPException(404, "investigation not found")
    return {"investigation": inv}


@app.patch("/investigations/{investigation_id}")
def investigations_update(investigation_id: int, body: UpdateInvestigationBody,
                          user: dict = Depends(auth.require_user)):
    inv = store.update_investigation(investigation_id, title=body.title,
                                     notes=body.notes, status=body.status)
    if not inv:
        raise HTTPException(404, "investigation not found")
    return {"investigation": inv}


@app.delete("/investigations/{investigation_id}")
def investigations_delete(investigation_id: int,
                          user: dict = Depends(auth.require_user)):
    store.delete_investigation(investigation_id)
    return {"deleted": investigation_id}


@app.post("/investigations/{investigation_id}/findings")
def investigations_add_finding(investigation_id: int, body: AddFindingBody,
                               user: dict = Depends(auth.require_user)):
    finding = store.add_finding(investigation_id, body.kind, body.title,
                                detail=body.detail, severity=body.severity)
    if not finding:
        raise HTTPException(404, "investigation not found")
    return {"finding": finding}


@app.get("/investigations/{investigation_id}/findings")
def investigations_list_findings(investigation_id: int,
                                 user: dict = Depends(auth.require_user)):
    return {"findings": store.list_findings(investigation_id)}


@app.get("/investigations/{investigation_id}/tree")
def investigations_tree(investigation_id: int,
                        user: dict = Depends(auth.require_user)):
    """Investigation tree: returns the case with its findings plus any
    flagged transactions, linked phones, and evidence chains associated
    with the investigation's subject accounts."""
    inv = store.get_investigation(investigation_id)
    if not inv:
        raise HTTPException(404, "investigation not found")
    b = _require_bundle()
    scored = risk.cached_transaction_risk(b)
    # Find transactions related to findings
    finding_titles = {f["title"].lower() for f in inv.get("findings", [])}
    flagged = []
    for s in scored:
        acc = (s.get("account_no") or "").lower()
        tid = (s.get("transaction_id") or "").lower()
        if any(acc and acc in t for t in finding_titles) or any(tid and tid in t for t in finding_titles):
            flagged.append({
                "transaction_id": s.get("transaction_id"),
                "risk_score": s.get("risk_score", 0),
                "risk_band": s.get("risk_band", "LOW"),
                "rules_fired": s.get("rules_fired", []),
                "evidence": s.get("evidence", []),
                "receiver_account": s.get("receiver_account"),
            })
    return {
        "investigation": inv,
        "findings": inv.get("findings", []),
        "flagged_transactions": flagged,
    }


# ---------------------------------------------------------------- hybrid engine
# Master-prompt Section II compliance: exposes hybrid composite scoring,
# per-model component breakdown, explainability and weight inspection.


@app.get("/hybrid/analyze")
def hybrid_analyze(user: dict = Depends(auth.require_user)):
    """Full hybrid analysis payload across transactions, accounts, entities."""
    return risk.hybrid_analyze(_require_bundle())


@app.get("/hybrid/transactions")
def hybrid_transactions(min_score: float = Query(0, ge=0, le=100),
                        limit: int = Query(50, le=500),
                        user: dict = Depends(auth.require_user)):
    rows = risk.hybrid_transaction_risk(_require_bundle(), min_score=min_score)
    return {"transactions": rows[:limit], "total": len(rows)}


@app.get("/hybrid/accounts")
def hybrid_accounts(user: dict = Depends(auth.require_user)):
    rows = risk.hybrid_account_risk(_require_bundle())
    return {"accounts": rows, "total": len(rows)}


@app.get("/hybrid/entities")
def hybrid_entities(user: dict = Depends(auth.require_user)):
    rows = risk.hybrid_entity_risk(_require_bundle())
    return {"entities": rows, "total": len(rows)}


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
    import hashlib
    safe_id = hashlib.sha256(transaction_id.encode()).hexdigest()[:16]
    path = os.path.join(tempfile.gettempdir(),
                        f"str_transaction_{safe_id}.pdf")
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
    from backend.report_intelligence import report_intelligence
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


@app.get("/payouts")
def payouts_endpoint(user: dict = Depends(auth.require_user)):
    """Rapid bursts and round-trip payouts detection."""
    b = _require_bundle()
    bank = b.get("bank") or []
    rapid = []
    round_payouts = []

    for r in bank:
        amt = float(r.get("debit") or r.get("amount") or 0.0)
        if amt > 0 and amt >= 1000 and amt % 1000 == 0:
            round_payouts.append({
                "txn_id": r.get("txn_id") or "",
                "account_no": r.get("account_no") or "",
                "amount": amt,
                "date": r.get("date") or "",
                "time": r.get("time") or "",
                "mode": r.get("mode") or "",
                "narration": r.get("narration") or "",
            })

    by_acc: dict[str, list] = {}
    for r in bank:
        acc = r.get("account_no")
        if not acc:
            continue
        amt = float(r.get("debit") or 0.0)
        if amt > 0:
            ts = float(r.get("ts") or 0.0)
            by_acc.setdefault(acc, []).append((ts, r))

    for acc, txns in by_acc.items():
        if len(txns) >= 3:
            txns.sort(key=lambda x: x[0])
            for i in range(len(txns) - 2):
                w_start = txns[i][0]
                w_txns = [t for t in txns[i:] if t[0] - w_start <= 3600]
                if len(w_txns) >= 3:
                    rapid.append({
                        "account_no": acc,
                        "count": len(w_txns),
                        "window_min": 60,
                        "first": w_txns[0][1].get("time") or w_txns[0][1].get("date") or "",
                        "last": w_txns[-1][1].get("time") or w_txns[-1][1].get("date") or "",
                    })
                    break

    return {
        "rapid": rapid,
        "round": round_payouts[:100],
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
    clear_graph_cache()
    
    orchestrator.start_pipeline(_state["bundle"])
    b = _state["bundle"]
    copilot_router.learn_bundle(b)
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
        
    status = orchestrator.get_status()
    if not status.get("anomalies_ready") and status.get("status") in ("PARSING", "FUSING", "SCORING") and status.get("dataset_id"):
        raise HTTPException(425, "Anomaly detection engine is still warming up.")
        
    ncrp_accounts = {str(c.get("account_no") or "").strip()
                     for c in b.get("complaints", [])}
    ncrp_accounts.discard("")
    bank_by_id = {r.get("txn_id"): r for r in b.get("bank", [])}
    acc_to_name = {}
    for acc in b.get("accounts", []):
        a_no = str(acc.get("account_no") or "").strip()
        a_name = acc.get("holder") or acc.get("account_name") or acc.get("customer_name") or ""
        if a_no and a_name:
            acc_to_name[a_no] = a_name
    for r in b.get("bank", []):
        a_no = str(r.get("account_no") or "").strip()
        a_name = r.get("account_name") or r.get("holder") or r.get("customer_name") or ""
        if a_no and a_name and a_no not in acc_to_name:
            acc_to_name[a_no] = a_name

    res = risk.hybrid_analyze_fast(b)
    if res is None:
        if status.get("anomalies_ready") or status.get("ready"):
            res = risk.hybrid_analyze(b)
        else:
            raise HTTPException(425, "Anomaly detection engine is still warming up.")

    scored_sorted = res.get("sorted_transactions")
    if not scored_sorted:
        scored_sorted = list(res["transactions"].values())
        scored_sorted.sort(key=lambda r: (-r.get("risk_score", 0.0), r.get("risk_band", "")))
    from backend.explain import plain_reason
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
            "account_no": s.get("account_no") or "",
            "sender_customer_id": s.get("sender_phone") or s.get("sender_customer_id") or s.get("account_no") or "",
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
        }, bank_by_id, acc_to_name)
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
               date_start: str = Query(""), date_end: str = Query(""),
               min_amount: float = Query(0.0, ge=0), max_amount: float = Query(0.0, ge=0),
               risk_band: str = Query(""),
               risk_annotate: int = Query(0, ge=0, le=1),
               user: dict = Depends(auth.require_user)):
    """Fused bank x CDR x IPDR preview table (the post-ingestion fusion view).

    Pass risk_annotate=1 to attach behavioural risk scores to each row
    (expensive on large bundles — runs the full scoring engine once).
    """
    b = _require_bundle()
    scored = None
    if risk_annotate:
        res = risk.hybrid_analyze_fast(b)
        if res:
            scored = res.get("transactions")
    return fused_table(b, offset=offset, limit=limit, q=q,
                       account=account, mode=mode, scored=scored,
                       date_start=date_start, date_end=date_end,
                       min_amount=min_amount, max_amount=max_amount, risk_band=risk_band)



@app.get("/data/fused.csv")
def fused_data_csv(q: str = Query(""), account: str = Query(""), mode: str = Query(""),
                   date_start: str = Query(""), date_end: str = Query(""),
                   min_amount: float = Query(0.0, ge=0), max_amount: float = Query(0.0, ge=0),
                   risk_band: str = Query(""),
                   max_rows: int = Query(50000, ge=1, le=200000),
                   user: dict = Depends(auth.require_user)):
    """Download the fused dataset as CSV (the 'fused CSV' export)."""
    b = _require_bundle()
    # Apply scored if risk_band is specified
    scored = None
    if risk_band and risk_band.lower() != "all":
        res = risk.hybrid_analyze_fast(b)
        if res:
            scored = res.get("transactions")
            
    page = fused_table(b, offset=0, limit=max_rows, q=q, account=account, mode=mode,
                       scored=scored, date_start=date_start, date_end=date_end,
                       min_amount=min_amount, max_amount=max_amount, risk_band=risk_band)
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


def _enrich_txn_row(row: dict, bank_by_id: dict, acc_to_name: dict = None) -> dict:
    tid = row.get("transaction_id") or row.get("txn_id") or ""
    raw = bank_by_id.get(tid, {})
    acc_no = str(row.get("account_no") or raw.get("account_no") or "").strip()

    name = (
        row.get("customer_name")
        or raw.get("customer_name")
        or raw.get("account_name")
        or raw.get("holder")
        or (acc_to_name.get(acc_no) if acc_to_name else "")
        or raw.get("counterparty_name")
        or raw.get("merchant_name")
        or ""
    )
    phone = (
        row.get("customer_phone")
        or raw.get("customer_phone")
        or raw.get("sender_phone")
        or raw.get("phone")
        or row.get("sender_customer_id")
        or ""
    )
    return {
        **row,
        "date": row.get("date") or raw.get("date") or "",
        "time": row.get("time") or raw.get("time") or "",
        "mode": row.get("mode") or raw.get("mode") or "",
        "bank": row.get("bank") or raw.get("bank") or "",
        "customer_name": name,
        "account_name": name,
        "customer_phone": phone,
    }


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
    from backend.analysis import account_hour_heatmap
    b = _require_bundle()
    return account_hour_heatmap(b, account=body.account or "",
                                max_accounts=max(1, min(60, body.max_accounts)))


@app.post("/analysis/relationship")
def analysis_relationship(body: RelationshipBody,
                          user: dict = Depends(auth.require_user)):
    """Relationship model between the selected transactions: money-flow legs,
    shared accounts/phones, time proximity — with edge strength + reasons."""
    from backend.analysis import relationship_model
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
