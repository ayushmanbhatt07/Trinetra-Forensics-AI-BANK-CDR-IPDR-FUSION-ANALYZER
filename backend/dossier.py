"""Investigation Dossier Generator.

Aggregates all datasets, AI analysis, and evidence links to generate a massive
forensic dossier for any entity or transaction.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend import evidence, fusion, store
from backend.risk import hybrid
from investigative_copilot import router as copilot

_log = logging.getLogger(__name__)


def generate_dossier(bundle: dict, kind: str, value: str) -> Dict[str, Any]:
    """Build the complete 360-degree forensic dossier."""
    
    primary: Dict[str, Any] = {}
    sender: Dict[str, Any] = {}
    receivers: list[Dict[str, Any]] = []
    ai: Dict[str, Any] = {
        "money_flow_summary": "",
        "flow_stats": {},
        "investigation_summary": [],
        "recommendations": []
    }
    journey: list[Dict[str, Any]] = []
    rules: list[Dict[str, Any]] = []
    connections: Dict[str, list[str]] = {}
    network: Dict[str, Any] = {}
    history: Dict[str, Any] = {}
    correlations: list[Dict[str, Any]] = []
    
    # -------------------------------------------------------------
    # TRANSACTION DOSSIER
    # -------------------------------------------------------------
    if kind == "transaction":
        txns = bundle.get("bank", [])
        txn = next((t for t in txns if t.get("txn_id") == value), None)
        if not txn:
            return {}
            
        account_no = txn.get("account_no", "")
        # Primary info
        primary = {
            "timestamp": f"{txn.get('date', '')} {txn.get('time', '')}".strip(),
            "amount": txn.get("amount", 0.0),
            "type": txn.get("mode", ""),
            "channel": txn.get("mode", ""),
            "bank": txn.get("bank", ""),
            "status": "COMPLETED",
            "reference": txn.get("description", "")
        }
        
        # We get the txn explanations to build the risk & rules
        explain = hybrid.explanations_for_txn(bundle, value)
        if explain:
            primary["risk_score"] = explain.get("risk_score", 0)
            primary["risk_band"] = explain.get("risk_band", "SAFE")
            primary["confidence"] = explain.get("confidence", 0.0)
            primary["fraud_probability"] = explain.get("confidence", 0.0) * 100
            
            for b in explain.get("breakdown", []):
                rules.append({
                    "rule": b.get("rule", ""),
                    "points": b.get("points", 0),
                    "meaning": b.get("reason", ""),
                    "evidence": b.get("reason", "")
                })
                
        # Sender Profile (using account intelligence)
        sender_intel = evidence.entity_intelligence(bundle, "account", account_no)
        if sender_intel:
            sender = {
                "name": txn.get("customer_name", ""),
                "account_no": account_no,
                "bank": txn.get("bank", ""),
                "phone": txn.get("customer_phone", ""),
                "balance": txn.get("balance", 0.0),
                "str_count": len(sender_intel.get("ncrp", [])),
                "linked_devices": sender_intel.get("links", {}).get("imeis", []),
                "linked_ips": sender_intel.get("links", {}).get("ips", []),
                "linked_sims": sender_intel.get("links", {}).get("phones", []),
            }
            # Add to history
            history = {
                "avg_daily_txns": sender_intel.get("counts", {}).get("transactions", 0),
                "avg_amount": sender_intel.get("volumes", {}).get("avg_amount", 0.0),
                "max_amount": sender_intel.get("volumes", {}).get("max_amount", 0.0),
                "normal_hours": "Unknown",
                "frequent_beneficiaries": sender_intel.get("links", {}).get("receiver_accounts", [])[:5]
            }
            connections = sender_intel.get("links", {})
            
            # Use timeline for Journey
            events = fusion.cached_build_timeline(bundle, "account", account_no)
            for e in events:
                journey.append({
                    "timestamp": f"{e.get('date', '')} {e.get('ts', '')}",
                    "event": f"[{e.get('kind', '')}] {e.get('detail', '')}"
                })
                
        # Receiver Intelligence
        # Look for payout
        rcv_account = txn.get("counterparty_account")
        rcv_name = txn.get("counterparty_name")
        if rcv_account:
            receivers.append({
                "name": rcv_name,
                "account_no": rcv_account,
                "bank": txn.get("counterparty_bank", ""),
                "total_received": txn.get("amount", 0.0),
            })
            
    # -------------------------------------------------------------
    # ENTITY DOSSIER
    # -------------------------------------------------------------
    else:
        intel = evidence.entity_intelligence(bundle, kind, value)
        if not intel:
            return {}
            
        primary = {
            "risk_score": intel.get("risk_score", 0),
            "risk_band": intel.get("risk_band", "SAFE"),
            "confidence": intel.get("confidence", 0.0),
        }
        for b in intel.get("breakdown", []):
            rules.append({
                "rule": b.get("rule", ""),
                "points": b.get("points", 0),
                "meaning": b.get("reason", ""),
                "evidence": b.get("reason", "")
            })
            
        if kind == "account":
            sender = {
                "account_no": value,
                "str_count": len(intel.get("ncrp", [])),
                "linked_devices": intel.get("links", {}).get("imeis", []),
                "linked_ips": intel.get("links", {}).get("ips", []),
                "linked_sims": intel.get("links", {}).get("phones", []),
            }
        else:
            sender = {
                "name": value,
                "linked_devices": intel.get("links", {}).get("imeis", []),
                "linked_ips": intel.get("links", {}).get("ips", []),
                "linked_sims": intel.get("links", {}).get("phones", []),
            }
            
        history = {
            "avg_daily_txns": intel.get("counts", {}).get("transactions", 0),
            "avg_amount": intel.get("volumes", {}).get("avg_amount", 0.0),
            "max_amount": intel.get("volumes", {}).get("max_amount", 0.0),
            "frequent_beneficiaries": intel.get("links", {}).get("receiver_accounts", [])[:5]
        }
        connections = intel.get("links", {})
        
        # Use timeline for Journey
        all_events = fusion.cached_build_timeline(bundle)
        events = [e for e in all_events if value.lower() in str(e.get("entity", "")).lower()]
        for e in events[:50]:
            journey.append({
                "timestamp": f"{e.get('date', '')} {e.get('ts', '')}",
                "event": f"[{e.get('kind', '')}] {e.get('detail', '')}"
            })

    # AI Generation
    # We call the copilot engine to build the flow and summary
    # To keep this fast, we run a tailored synchronous prompt.
    prompt = (
        f"Analyze this financial/telecom investigation for {kind} '{value}'. "
        f"Primary Risk Score: {primary.get('risk_score')}. "
        f"Sender Details: {sender}. "
        f"Receivers: {receivers}. "
        f"Connections: {connections}. "
        "Generate a structured JSON output with ONLY these keys: "
        "'money_flow_summary' (a brief chronological text of how money moved), "
        "'investigation_summary' (a list of 5-10 numbered string points highlighting key suspicious behaviours), "
        "'recommendations' (a list of 5 actionable next steps for investigators)."
    )
    
    # Fire LLM (we'll just use the default LlmClient logic via copilot)
    try:
        from investigative_copilot.llm_client import LlmClient
        llm = LlmClient()
        if llm.has_provider():
            ok, parsed, _ = llm.generate_json(
                system_prompt="You are an expert financial forensic analyst.",
                user_content=prompt,
                temperature=0.2
            )
            if ok and parsed:
                ai["money_flow_summary"] = parsed.get("money_flow_summary", "")
                ai["investigation_summary"] = parsed.get("investigation_summary", [])
                ai["recommendations"] = parsed.get("recommendations", [])
    except Exception as e:
        _log.error("Failed to generate AI dossier summary: %s", e)

    return {
        "kind": kind,
        "value": value,
        "primary": primary,
        "sender": sender,
        "receivers": receivers,
        "ai": ai,
        "journey": journey[:100],  # cap at 100 events
        "rules": rules,
        "connections": connections,
        "network": network,
        "history": history,
        "correlations": correlations
    }
