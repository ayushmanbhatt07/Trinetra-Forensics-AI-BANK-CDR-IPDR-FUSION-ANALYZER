"""FastAPI router for Tri-Netra Forensics Investigative Co-Pilot."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import logging

from backend import auth

from .copilot_engine import InvestigativeCoPilotEngine
from .db_builder import get_copilot_db, reset_copilot_db
from .prompts import SAMPLE_QUERIES_PROMPT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/copilot", tags=["Investigative Co-Pilot"])

# Lazy engine initialization, rebuilt whenever the loaded bundle changes.
_engine: Optional[InvestigativeCoPilotEngine] = None
_engine_bundle: Optional[Dict[str, Any]] = None
_last_call_meta: Dict[str, Any] = {}


def _current_bundle() -> Optional[Dict[str, Any]]:
    import sys
    for mod_name in ("api", "backend.api"):
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "_state"):
                b = getattr(mod, "_state", {}).get("bundle")
                if b and (b.get("bank") or b.get("cdr") or b.get("ipdr")):
                    return b
    try:
        from backend import store
        return store.load_bundle()
    except Exception:
        return None


def reset_engine() -> None:
    """Drops the cached engine + copilot DB; next request rebuilds from the
    currently loaded bundle. Called by the API on ingest / clear / restore."""
    global _engine, _engine_bundle
    _engine = None
    _engine_bundle = None
    reset_copilot_db()


def learn_bundle(bundle: Dict[str, Any]) -> None:
    """Continuous-learning hook: refresh the memory digest whenever a dataset
    is ingested or restored, so the LLM always reasons on the latest corpus
    (entity census, top accounts, phone overlap, digest fingerprint)."""
    try:
        from .memory import MemoryStore
        ms = MemoryStore(bundle)
        ms.refresh(bundle)
        logger.info("copilot memory refreshed (fingerprint=%s, digest=%d bytes)",
                    ms.fingerprint, len(ms.digest()))
    except Exception as e:  # learning must never break ingestion
        logger.error("copilot memory refresh failed: %s", e)


def get_engine() -> InvestigativeCoPilotEngine:
    global _engine, _engine_bundle
    bundle = _current_bundle()
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no data loaded; POST /ingest first"
        )
    if _engine is None or _engine_bundle is not bundle:
        _engine = InvestigativeCoPilotEngine(conn=get_copilot_db(bundle),
                                             bundle=bundle)
        _engine_bundle = bundle
    return _engine


class QueryRequest(BaseModel):
    query: str = Field(..., json_schema_extra={"example": "Show me all accounts that received money within 5 minutes of a call originating from West Bengal tower locations."})


class ClusterSummaryRequest(BaseModel):
    entity_ids: List[str] = Field(..., json_schema_extra={"example": ["ACC_1001", "ACC_1002"]})


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000,
                      description="Co-pilot answer or report text to translate.")
    lang: str = Field("hi", pattern="^(hi|gu)$",
                      description="Target language: 'hi' (Hindi) or 'gu' (Gujarati).")


@router.post("/translate")
def translate_co_pilot_answer(payload: TranslateRequest,
                              user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Translates a co-pilot answer / report snippet into Hindi or Gujarati
    via the live LLM so investigators can read findings in local languages.
    Returns translated=null when no provider is configured."""
    try:
        from .llm_client import LlmClient
        from .prompts import TRANSLATE_PROMPT
        client = LlmClient()
        if not client.has_provider():
            return {"translated": None, "lang": payload.lang,
                    "provider": None, "note": "no_llm_provider"}
        lang_name = {"hi": "Hindi", "gu": "Gujarati"}[payload.lang]
        ok, parsed, meta = client.generate_json(
            TRANSLATE_PROMPT.format(lang=lang_name), payload.text)
        if not ok or not parsed:
            return {"translated": None, "lang": payload.lang,
                    "provider": meta.get("provider", ""), "note": "llm_failed"}
        translated = str(parsed.get("translated") or "").strip()
        if not translated:
            translated = payload.text
        return {"translated": translated, "lang": payload.lang,
                "provider": meta.get("provider", ""),
                "model": meta.get("model", "")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error translating co-pilot answer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to translate: {str(e)}")


@router.post("/query")
def process_investigative_query(payload: QueryRequest,
                                user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Processes a natural language investigative query and returns Evidentiary Chain-of-Thought, SQL, and graph trace."""
    try:
        engine = get_engine()
        result = engine.analyze_query(payload.query)
        _last_call_meta.update({
            "provider": result.get("llm_provider", ""),
            "model": result.get("llm_model", ""),
            "latency_ms": result.get("llm_latency_ms", 0),
            "mode": result.get("mode", ""),
            "row_count": result.get("row_count", 0),
            "at": __import__("datetime").datetime.now().isoformat(
                timespec="seconds"),
        })
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing copilot query: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )


@router.get("/health")
def copilot_health(user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Cheap ops endpoint: provider availability, memory state and the last
    served call. Deliberately does NOT build the engine, so it stays fast on
    large bundles."""
    try:
        from backend import api as _api
        from backend import config
        from .llm_client import LlmClient
        from .memory import MemoryStore

        bundle = _api._state.get("bundle")
        ms = MemoryStore(bundle)
        client = LlmClient()
        return {
            "loaded": bundle is not None,
            "corpus": {
                "bank": len((bundle or {}).get("bank", [])),
                "cdr": len((bundle or {}).get("cdr", [])),
                "ipdr": len((bundle or {}).get("ipdr", [])),
            },
            "providers": {
                "groq_keys": len(config.groq_api_keys()),
                "groq_model": client.groq_model,
            },
            "memory": {
                "file": str(ms.path),
                "fingerprint": ms.fingerprint,
                "turns": len(ms.recent_chat()),
            },
            "last_call": dict(_last_call_meta),
        }
    except Exception as e:
        logger.error(f"Error in copilot health: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build health report: {str(e)}"
        )


@router.post("/summarize-cluster")
def summarize_entity_cluster(payload: ClusterSummaryRequest,
                             user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Generates an executive lead summary paragraph for a cluster of clicked nodes/transactions."""
    try:
        engine = get_engine()
        result = engine.summarize_cluster(payload.entity_ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating cluster summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary: {str(e)}"
        )


@router.get("/schema")
def get_database_schema(user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Returns database schema definition and sample questions for UI prompt assistance."""
    return {
        "tables": [
            "bank_transactions",
            "cdr_records",
            "ipdr_records",
            "bank_cdr_links",
            "cdr_ipdr_links",
            "anomaly_records",
            "complaints",
            "subscribers"
        ],
        "sample_queries": [
            "Show me all accounts that received money within 5 minutes of a call originating from West Bengal tower locations.",
            "Trace the 3-hop money flow from mule account ACC_1001.",
            "Find all UPI transactions greater than ₹50,000 where the sender was in active CDR call.",
            "List top receiver accounts that rapidly layered funds via IMPS."
        ],
        "prompt_help": SAMPLE_QUERIES_PROMPT
    }


@router.get("/stats")
def get_copilot_stats(user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Returns database statistics for the Co-Pilot module."""
    try:
        engine = get_engine()
        conn = engine.conn
        cursor = conn.cursor()
        
        counts = {}
        tables = ["bank_transactions", "cdr_records", "ipdr_records",
                  "bank_cdr_links", "cdr_ipdr_links", "anomaly_records",
                  "complaints", "subscribers"]
        for t in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) as c FROM {t}")
                counts[t] = cursor.fetchone()["c"]
            except Exception:
                counts[t] = 0

        return {
            "dataset_source": engine.dataset_source,
            "tables": counts,
            "graph_nodes": engine.graph_engine.graph.number_of_nodes(),
            "graph_edges": engine.graph_engine.graph.number_of_edges(),
            "max_graph_hops": 3
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/{entity_id}")
def get_entity_graph(entity_id: str, max_hops: int = 3,
                     user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Returns the 3-hop NetworkX graph structure (nodes, edges, layers) for an entity or transaction."""
    try:
        engine = get_engine()
        result = engine.graph_engine.trace_mule_chain(entity_id, max_hops=max_hops)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching entity graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tree/{entity_id}")
def get_entity_linking_tree(entity_id: str, max_hops: int = 3,
                            user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Returns the complete linking tree for an entity/transaction: accounts,
    phones and their transactions/calls grouped by hop layer."""
    try:
        engine = get_engine()
        result = engine.graph_engine.linking_tree(entity_id, max_hops=max_hops)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching linking tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph-html/{entity_id}")
def get_entity_graph_html(entity_id: str, max_hops: int = 3,
                          user: dict = Depends(auth.require_user)):
    """Returns an interactive standalone HTML Network Diagram for viewing in browser."""
    from fastapi.responses import HTMLResponse
    try:
        engine = get_engine()
        res = engine.graph_engine.trace_mule_chain(entity_id, max_hops=max_hops)
        
        nodes = res.get("nodes", [])[:500]
        edges = res.get("edges", [])[:5000]
        
        vis_nodes = []
        for n in nodes:
            nid = str(n["node_id"])
            ntype = n.get("type", "account")
            color = "#1E88E5" if ntype == "account" else ("#8E24AA" if ntype == "phone" else "#FB8C00")
            label = f"{n.get('name', nid)}\n({nid})" if n.get("name") and n.get("name") != "Unknown Entity" else nid
            vis_nodes.append({"id": nid, "label": label, "color": color, "shape": "dot", "size": 18 - (n.get("hop_distance", 0) * 3)})

        vis_edges = []
        for e in edges:
            etype = e.get("edge_type", "link")
            label = f"₹{e['amount']:,.0f}" if "amount" in e else (f"{e['duration']}s" if "duration" in e else etype)
            color = "#43A047" if etype == "bank_transfer" else "#3949AB"
            vis_edges.append({"from": str(e["source"]), "to": str(e["target"]), "label": label, "color": color, "arrows": "to"})

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Tri-Netra Forensics 3-Hop Network Graph: {entity_id}</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{ font-family: sans-serif; margin: 0; background: #0F172A; color: #F8FAFC; }}
        #header {{ padding: 15px 20px; background: #1E293B; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }}
        #network {{ width: 100vw; height: calc(100vh - 70px); }}
        .badge {{ background: #3B82F6; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-left: 5px; }}
    </style>
</head>
<body>
    <div id="header">
        <h2>Tri-Netra Forensics Forensic Graph — Entity: <span style="color:#60A5FA">{entity_id}</span></h2>
        <div>
            <span class="badge">Max Hops: {max_hops}</span>
            <span class="badge" style="background:#10B981">Nodes: {len(nodes)}</span>
            <span class="badge" style="background:#8B5CF6">Edges: {len(edges)}</span>
        </div>
    </div>
    <div id="network"></div>
    <script type="text/javascript">
        var container = document.getElementById('network');
        var data = {{
            nodes: new vis.DataSet({vis_nodes}),
            edges: new vis.DataSet({vis_edges})
        }};
        var options = {{
            nodes: {{ font: {{ color: '#F8FAFC', size: 12 }} }},
            edges: {{ font: {{ color: '#94A3B8', size: 10, align: 'middle' }} }},
            physics: {{ barnesHut: {{ gravitationalConstant: -3000, springLength: 120 }} }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
</body>
</html>"""
        return HTMLResponse(content=html_content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rendering graph HTML: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class LlmTreeRequest(BaseModel):
    entity_id: str = Field(..., min_length=1,
                           description="Any entity id: txn, phone, account, IMEI, IP, UPI…")
    max_hops: int = Field(3, ge=1, le=4)


@router.post("/llm-tree")
def build_llm_investigation_tree(payload: LlmTreeRequest,
                                 user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Flagship 3D-tree feature: builds the forensic linking tree around ANY
    entity, then lets the LLM annotate each node (role, suspicion label) and
    edge (why the link matters), plus a natural-language investigation
    narrative. Falls back to the deterministic graph when no LLM provider is
    reachable, so the tree is ALWAYS returned."""
    try:
        engine = get_engine()
        tree = engine.graph_engine.linking_tree(payload.entity_id,
                                                max_hops=payload.max_hops)
        if not tree.get("found", False):
            resolved = engine._resolve_entity_in_db(payload.entity_id)
            if not resolved:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"entity not found: {payload.entity_id}")
            tree = engine.graph_engine.linking_tree(resolved,
                                                    max_hops=payload.max_hops)
            if not tree.get("found", False):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"entity not found: {payload.entity_id}")

        raw_nodes = graph.get("nodes", [])[:120]
        
        node_ids = {str(n.get("node_id")) for n in raw_nodes}
        filtered_edges = [e for e in graph.get("edges", []) if str(e.get("source")) in node_ids and str(e.get("target")) in node_ids]
        raw_edges = filtered_edges[:240]

        nodes, edges = raw_nodes, raw_edges

        # Deterministic labels first (always present).
        label_by_type = {
            "account": "Account", "phone": "Phone", "txn": "Transaction",
            "imei": "IMEI", "imsi": "IMSI", "ip": "IP",
            "upi": "UPI", "unknown": "Entity",
        }
        out_nodes = []
        for n in nodes:
            nid = str(n.get("node_id"))
            ntype = str(n.get("type") or "unknown")
            attrs = {k: v for k, v in n.items()
                     if k not in ("node_id", "type", "name") and v is not None}
            out_nodes.append({
                "id": nid,
                "kind": ntype,
                "label": str(n.get("name") or label_by_type.get(ntype, nid)),
                "hop_distance": int(n.get("hop_distance") or 0),
                "attrs": attrs,
                "risk": float(n.get("risk", 0) or 0),
            })
        out_edges = []
        for e in edges:
            out_edges.append({
                "source": str(e.get("source")),
                "target": str(e.get("target")),
                "kind": str(e.get("edge_type") or "link"),
                "amount": float(e.get("amount") or 0),
                "duration": float(e.get("duration") or 0),
            })

        # LLM annotation pass (best-effort; fallback keeps deterministic labels).
        narrative = None
        llm_provider = None
        try:
            from .llm_client import LlmClient
            from .prompts import LLM_TREE_PROMPT
            from backend import config as _config
            client = LlmClient()
            if client.has_provider():
                compact = {
                    "root": tree.get("entity_id"),
                    "nodes": [{"id": n["id"], "kind": n["kind"], "label": n["label"]}
                              for n in out_nodes[:60]],
                    "edges": [{"source": e["source"], "target": e["target"],
                               "kind": e["kind"],
                               "amount": round(e["amount"])}
                              for e in out_edges[:120]],
                }
                ok, raw, meta = client.generate_json(LLM_TREE_PROMPT,
                                                     json.dumps(compact))
                if ok and raw:
                    ann = raw.get("annotations") or {}
                    for n in out_nodes:
                        a = ann.get(n["id"]) or {}
                        if isinstance(a, dict) and a.get("role"):
                            n["role"] = a["role"]
                        if isinstance(a, dict) and a.get("suspicion"):
                            n["suspicion"] = a["suspicion"]
                    for e in out_edges:
                        a = ann.get(f"{e['source']}->{e['target']}") or {}
                        if isinstance(a, dict) and a.get("reason"):
                            e["reason"] = a["reason"]
                    narrative = raw.get("narrative")
                    llm_provider = meta.get("provider")
        except Exception as le:
            logger.warning("LLM tree annotation skipped: %s", le)

        return {
            "root": tree.get("entity_id"),
            "max_hops": payload.max_hops,
            "nodes": out_nodes,
            "edges": out_edges,
            "narrative": narrative,
            "llm_provider": llm_provider,
            "annotated": llm_provider is not None,
            "graph": {
                "nodes": len(out_nodes),
                "edges": len(out_edges),
                "found": tree.get("found", False),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building LLM tree: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class GraphBuildRequest(BaseModel):
    entity_id: str = Field(..., min_length=1,
                           description="Entity id: account, txn, phone, IMEI, IP…")
    max_hops: int = Field(3, ge=1, le=4)


class InsightsRequest(BaseModel):
    root_entity: str = Field("", description="Root entity id for the graph")
    nodes: list = Field(default_factory=list)
    edges: list = Field(default_factory=list)


@router.post("/graph/build")
def build_investigation_graph(payload: GraphBuildRequest,
                              user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Builds a full investigation graph for the 3D tree visualisation.
    Returns nodes + edges shaped for the frontend force-graph renderer,
    with LLM annotations when available."""
    try:
        engine = get_engine()

        # 1. Get the raw graph traversal
        graph = engine.graph_engine.trace_mule_chain(
            payload.entity_id, max_hops=payload.max_hops)

        if not graph.get("found", False):
            # Try resolving the entity via DB before giving up
            resolved = engine._resolve_entity_in_db(payload.entity_id)
            if resolved and resolved != payload.entity_id:
                graph = engine.graph_engine.trace_mule_chain(
                    resolved, max_hops=payload.max_hops)
            if not graph.get("found", False):
                return {"found": False, "nodes": [], "edges": [],
                        "entity_id": payload.entity_id}

        raw_nodes = graph.get("nodes", [])[:120]
        
        node_ids = {str(n.get("node_id")) for n in raw_nodes}
        filtered_edges = [e for e in graph.get("edges", []) if str(e.get("source")) in node_ids and str(e.get("target")) in node_ids]
        raw_edges = filtered_edges[:240]

        # 2. Shape nodes for the 3D frontend
        label_by_type = {
            "account": "Account", "phone": "Phone", "txn": "Transaction",
            "imei": "IMEI", "imsi": "IMSI", "ip": "IP",
            "upi": "UPI", "unknown": "Entity",
        }
        out_nodes = []
        for n in raw_nodes:
            nid = str(n.get("node_id", ""))
            ntype = str(n.get("type") or "unknown")
            out_nodes.append({
                "id": nid,
                "kind": ntype,
                "label": str(n.get("name") or label_by_type.get(ntype, nid)),
                "hop_distance": int(n.get("hop_distance") or 0),
                "risk": float(n.get("risk", 0) or 0),
                "centrality": 0.0,
                "role": "",
                "suspicion": "",
            })

        # Compute basic centrality: degree centrality from edges
        degree: Dict[str, int] = {}
        for e in raw_edges:
            s, t = str(e.get("source", "")), str(e.get("target", ""))
            degree[s] = degree.get(s, 0) + 1
            degree[t] = degree.get(t, 0) + 1
        max_deg = max(degree.values()) if degree else 1
        for n in out_nodes:
            n["centrality"] = round(degree.get(n["id"], 0) / max_deg, 2)

        # 3. Shape edges for the 3D frontend
        out_edges = []
        for e in raw_edges:
            etype = str(e.get("edge_type") or "link")
            kind = "TRANSFERRED_TO" if etype == "bank_transfer" else (
                "CALLED" if etype == "cdr_call" else "LINKED")
            out_edges.append({
                "source": str(e.get("source", "")),
                "target": str(e.get("target", "")),
                "kind": kind,
                "amount": float(e.get("amount") or 0),
                "duration": float(e.get("duration") or 0),
                "reason": "",
                "tx_id": str(e.get("tx_id", "")),
                "cdr_id": str(e.get("cdr_id", "")),
            })

        # 4. LLM annotation pass (best-effort)
        try:
            from .llm_client import LlmClient
            from .prompts import LLM_TREE_PROMPT
            client = LlmClient()
            if client.has_provider():
                compact = {
                    "root": payload.entity_id,
                    "nodes": [{"id": n["id"], "kind": n["kind"],
                               "label": n["label"]}
                              for n in out_nodes[:60]],
                    "edges": [{"source": e["source"], "target": e["target"],
                               "kind": e["kind"],
                               "amount": round(e["amount"])}
                              for e in out_edges[:120]],
                }
                ok, raw, meta = client.generate_json(
                    LLM_TREE_PROMPT, json.dumps(compact))
                if ok and raw:
                    ann = raw.get("annotations") or {}
                    for n in out_nodes:
                        a = ann.get(n["id"]) or {}
                        if isinstance(a, dict):
                            if a.get("role"):
                                n["role"] = a["role"]
                            if a.get("suspicion"):
                                n["suspicion"] = a["suspicion"]
                    for e in out_edges:
                        a = ann.get(
                            f"{e['source']}->{e['target']}") or {}
                        if isinstance(a, dict) and a.get("reason"):
                            e["reason"] = a["reason"]
        except Exception as le:
            logger.warning("LLM graph annotation skipped: %s", le)

        return {
            "found": True,
            "entity_id": graph.get("start_node", payload.entity_id),
            "max_hops": payload.max_hops,
            "nodes": out_nodes,
            "edges": out_edges,
            "layers": graph.get("layers", {}),
            "total_nodes": len(out_nodes),
            "total_edges": len(out_edges),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/insights/generate")
def generate_graph_insights(payload: InsightsRequest,
                            user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Generates structured forensic insights from a graph's nodes and edges.
    Returns executive_summary, primary_findings, and recommended_actions
    for the investigation report panel."""
    try:
        nodes = payload.nodes or []
        edges = payload.edges or []

        # Deterministic analysis
        account_nodes = [n for n in nodes if n.get("kind") == "account"
                         or n.get("kind") == "Account"]
        phone_nodes = [n for n in nodes if n.get("kind") == "phone"
                       or n.get("kind") == "Phone"]
        money_edges = [e for e in edges
                       if e.get("kind") in ("TRANSFERRED_TO", "bank_transfer")
                       and (e.get("amount") or 0) > 0]
        call_edges = [e for e in edges
                      if e.get("kind") in ("CALLED", "cdr_call")]

        total_flow = sum(float(e.get("amount") or 0) for e in money_edges)
        max_amount = max((float(e.get("amount") or 0) for e in money_edges),
                         default=0)

        # Degree centrality
        degree: Dict[str, int] = {}
        for e in edges:
            s = str(e.get("source", ""))
            t = str(e.get("target", ""))
            degree[s] = degree.get(s, 0) + 1
            degree[t] = degree.get(t, 0) + 1
        hub_nodes = sorted(degree.items(), key=lambda x: -x[1])[:3]

        # Build findings
        findings: list = []
        if total_flow > 0:
            findings.append(
                f"Total money flow in the network: ₹{total_flow:,.0f} across "
                f"{len(money_edges)} transaction edges.")
        if max_amount > 50000:
            findings.append(
                f"Largest single transfer: ₹{max_amount:,.0f} — exceeds the "
                f"high-value threshold for enhanced scrutiny.")
        if len(account_nodes) > 3:
            findings.append(
                f"{len(account_nodes)} distinct accounts detected in the "
                f"network — potential layering structure.")
        if call_edges:
            findings.append(
                f"{len(call_edges)} CDR call edges link phone activity to "
                f"financial transactions, indicating call-assisted transfers.")
        if hub_nodes:
            top_hub = hub_nodes[0]
            findings.append(
                f"Hub node '{top_hub[0]}' has {top_hub[1]} connections — "
                f"highest centrality, likely a coordination point.")
        for n in nodes:
            if n.get("suspicion"):
                findings.append(f"{n.get('id')}: {n['suspicion']}")
                break

        # Build recommendations
        actions: list = []
        if total_flow > 100000:
            actions.append(
                "File STR with FIU-IND for the entire network cluster.")
        if hub_nodes:
            actions.append(
                f"Freeze account '{hub_nodes[0][0]}' — highest centrality "
                f"hub in the mule network.")
        if call_edges:
            actions.append(
                "Subpoena CDR tower records for all linked phone numbers.")
        if len(account_nodes) > 4:
            actions.append(
                "Investigate Layer-2 and Layer-3 offramp accounts for "
                "cash-out activity.")
        if not actions:
            actions.append("Continue monitoring — no immediate enforcement "
                           "threshold breached.")

        summary = (
            f"Investigation graph for entity '{payload.root_entity}' reveals "
            f"a {len(nodes)}-node, {len(edges)}-edge network. "
            f"{'₹' + f'{total_flow:,.0f}' + ' in tracked flow. ' if total_flow else ''}"
            f"{len(account_nodes)} accounts and {len(phone_nodes)} phones "
            f"are interconnected. "
            f"{'High-centrality hub detected. ' if hub_nodes else ''}"
            f"{'CDR call correlation confirms telephonic coordination.' if call_edges else ''}"
        )

        return {
            "executive_summary": summary,
            "primary_findings": findings[:6],
            "recommended_actions": actions[:4],
            "metrics": {
                "nodes": len(nodes),
                "edges": len(edges),
                "accounts": len(account_nodes),
                "phones": len(phone_nodes),
                "total_flow": total_flow,
                "max_transfer": max_amount,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
def _generate_deterministic_audit_report(entity_id: str, txns: list, calls: list, ips: list) -> str:
    total_val = sum(float(t.get("amount") or 0) for t in txns)
    debits = sum(float(t.get("amount") or 0) for t in txns if str(t.get("type") or "").upper() in ("DEBIT", "D", "DR"))
    credits = sum(float(t.get("amount") or 0) for t in txns if str(t.get("type") or "").upper() in ("CREDIT", "C", "CR"))
    counterparties = {str(t.get("counterparty")) for t in txns if t.get("counterparty")}
    
    bullets = [
        f"**Target Entity Identity**: Forensic records linked to identifier `{entity_id}`.",
        f"**Financial Audit**: Analyzed {len(txns)} transactions totaling ₹{total_val:,.2f} (Credits: ₹{credits:,.2f}, Debits: ₹{debits:,.2f}).",
        f"**Network Dispersion**: Discovered financial links with {len(counterparties)} unique counterparty entities.",
    ]
    if calls:
        bullets.append(f"**Telecom Coincidence**: Cross-referenced {len(calls)} voice call sessions in proximity to monetary flow.")
    if ips:
        bullets.append(f"**Cyber/IP Footprint**: Captured {len(ips)} IPDR network sessions linked to device hardware.")
        
    if debits > 0 and credits > 0 and abs(debits - credits) / max(debits, credits) < 0.15:
        bullets.append("**Critical Forensic Indicator**: Rapid pass-through liquidity pattern detected (near 1:1 inflow to outflow ratio), indicative of mule layering.")
    elif len(txns) >= 5 and total_val > 100000:
        bullets.append("**High-Risk Flag**: Significant cumulative transfer velocity above baseline thresholds.")
    else:
        bullets.append("**Behavioral Baseline**: Direct financial activity recorded. Cross-domain correlation active.")
        
    return "\n\n".join([f"• {b}" for b in bullets])


@router.get("/entity/{entity_id}/details")
def get_entity_full_details(entity_id: str,
                            user: dict = Depends(auth.require_user)) -> Dict[str, Any]:
    """Retrieves full profile, all direct transactions, calls, IP sessions, and an LLM-generated audit report for an entity."""
    try:
        from .db_builder import get_copilot_db
        bundle = _current_bundle()
        if not bundle:
            raise HTTPException(status_code=409, detail="No dataset loaded")
            
        conn = get_copilot_db(bundle)
        cursor = conn.cursor()
        
        # Normalize targets to search for (e.g. 10-digit, 12-digit phone, raw id)
        targets = {entity_id.lower()}
        digits = "".join(c for c in entity_id if c.isdigit())
        if len(digits) == 10:
            targets.add("91" + digits)
            targets.add(digits)
        elif len(digits) == 12 and digits.startswith("91"):
            targets.add(digits[2:])
            targets.add(digits)
            
        # Collect transactions
        txns = []
        for t in bundle.get("bank", []):
            snd = str(t.get("account_no", "")).lower()
            rcv = str(t.get("receiver_account", "")).lower()
            snd_p = str(t.get("sender_phone", "")).lower()
            rcv_p = str(t.get("receiver_phone", "")).lower()
            tx_id = str(t.get("transaction_id", "")).lower()
            
            if any(tgt in snd or tgt in rcv or tgt in snd_p or tgt in rcv_p or tgt == tx_id for tgt in targets):
                txns.append({
                    "date": t.get("date"),
                    "txn_id": t.get("transaction_id"),
                    "amount": t.get("amount"),
                    "type": "Debit" if any(tgt in snd or tgt in snd_p for tgt in targets) else "Credit",
                    "counterparty": t.get("receiver_account") if any(tgt in snd or tgt in snd_p for tgt in targets) else t.get("account_no"),
                    "bank": t.get("bank")
                })
                
        # Collect calls
        calls = []
        for c in bundle.get("cdr", []):
            if any(t in str(c.get("caller_msisdn", "")).lower() or t in str(c.get("receiver_msisdn", "")).lower() for t in targets):
                calls.append({
                    "date": c.get("call_date"),
                    "time": c.get("call_time"),
                    "duration": c.get("duration"),
                    "type": "Voice",
                    "counterparty": c.get("receiver_msisdn") if any(t in str(c.get("caller_msisdn", "")).lower() for t in targets) else c.get("caller_msisdn")
                })
                
        # Collect IP sessions
        ips = []
        for p in bundle.get("ipdr", []):
            if any(t in str(p.get("msisdn", "")).lower() for t in targets):
                ips.append({
                    "ip": p.get("private_ipv4"),
                    "destination": p.get("destination_ipv4"),
                    "date": p.get("start_date") or p.get("date"),
                    "duration": p.get("duration")
                })
                
        # Generate LLM Summary with robust deterministic fallback
        from .llm_client import LlmClient
        client = LlmClient()
        audit_report = ""
        if client.has_provider():
            prompt = (
                f"You are a financial forensic investigator. The user clicked on entity '{entity_id}' in the graph. "
                f"Analyze the following data for this entity and write a short audit report (use markdown bullet points). "
                f"Explain why this entity's activity might be suspicious, providing a bulleted summary of key flags.\n"
                f"Transactions: {len(txns)} found. Calls: {len(calls)} found. IP Sessions: {len(ips)} found.\n"
                f"Sample txns: {txns[:20]}\n"
                f"Sample calls: {calls[:20]}\n"
                "Return JSON with a single key 'audit_report' containing the markdown text of your findings."
            )
            ok, raw, meta = client.generate_json(prompt, "{}")
            if ok and raw and "audit_report" in raw:
                audit_report = str(raw["audit_report"]).strip()

        if not audit_report or "failed" in audit_report.lower() or "no llm" in audit_report.lower():
            audit_report = _generate_deterministic_audit_report(entity_id, txns, calls, ips)
                
        return {
            "entity_id": entity_id,
            "transactions": txns,
            "calls": calls,
            "ips": ips,
            "audit_report": audit_report
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching entity details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

