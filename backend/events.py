"""Event Intelligence Dossier Generator.

Aggregates raw event records, risk metadata, and cross-domain temporal correlations
specifically for single forensic events (BANK, CDR, IPDR, COMPLAINTS) clicked
from the unified timeline.
"""

from typing import Any, Dict
from datetime import datetime
from backend.risk import hybrid

def _parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1]
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None

def find_correlations(bundle: dict, target_ts: datetime, window_sec: int = 1800) -> list[Dict[str, Any]]:
    """Find other events happening within window_sec of the target timestamp."""
    correlations = []
    
    # Check bank
    for r in bundle.get("bank", []):
        ts = r.get("ts")
        if not ts: continue
        dt = _parse_ts(ts)
        if dt:
            diff = abs((dt - target_ts).total_seconds())
            if 0 < diff <= window_sec:
                correlations.append({
                    "type": "BANK",
                    "time_diff_sec": int(diff),
                    "description": f"Txn: {r.get('amount', 'N/A')} {r.get('txn_type', '')}",
                    "id": r.get("txn_id"),
                    "ts": ts
                })
                
    # Check cdr
    for r in bundle.get("cdr", []):
        ts = r.get("ts")
        if not ts: continue
        dt = _parse_ts(ts)
        if dt:
            diff = abs((dt - target_ts).total_seconds())
            if 0 < diff <= window_sec:
                correlations.append({
                    "type": "CDR",
                    "time_diff_sec": int(diff),
                    "description": f"Call {r.get('call_type', '')} with {r.get('b_number', '')}",
                    "id": r.get("cdr_id"),
                    "ts": ts
                })
                
    # Check ipdr
    for r in bundle.get("ipdr", []):
        ts = r.get("start_ts")
        if not ts: continue
        dt = _parse_ts(ts)
        if dt:
            diff = abs((dt - target_ts).total_seconds())
            if 0 < diff <= window_sec:
                correlations.append({
                    "type": "IPDR",
                    "time_diff_sec": int(diff),
                    "description": f"Session to {r.get('dest_ip', '')}",
                    "id": r.get("ipdr_id"),
                    "ts": ts
                })
                
    # Sort by closest time
    correlations.sort(key=lambda x: x["time_diff_sec"])
    return correlations[:25]  # limit to top 25 closest

def get_event_dossier(bundle: dict, source_type: str, event_id: str) -> Dict[str, Any]:
    """Build the rich event dossier for a timeline click."""
    
    out = {
        "event_id": event_id,
        "source_type": source_type.upper(),
        "timestamp": None,
        "primary_entity": {},
        "source_record": {},
        "risk": {},
        "identities": [],
        "correlations": [],
        "evidence": []
    }
    
    target_ts = None
    
    if source_type.lower() == "bank":
        record = next((r for r in bundle.get("bank", []) if str(r.get("txn_id")) == event_id), None)
        if not record:
            return {}
        out["source_record"] = record
        out["timestamp"] = record.get("ts")
        if out["timestamp"]:
            target_ts = _parse_ts(out["timestamp"])
            
        out["primary_entity"] = {
            "type": "ACCOUNT",
            "value": record.get("account_no", ""),
            "name": record.get("customer_name", "")
        }
        
        # Risk
        explain = hybrid.explanations_for_txn(bundle, event_id)
        if explain:
            out["risk"] = {
                "score": explain.get("risk_score", 0),
                "band": explain.get("risk_band", "SAFE")
            }
            out["evidence"] = explain.get("breakdown", [])
            
        # Identities
        out["identities"].append({"type": "ACCOUNT", "value": record.get("account_no", "")})
        if record.get("customer_phone"):
            out["identities"].append({"type": "PHONE", "value": record.get("customer_phone")})
        if record.get("receiver_account"):
            out["identities"].append({"type": "COUNTERPARTY_ACCOUNT", "value": record.get("receiver_account")})
        if record.get("receiver_name"):
            out["identities"].append({"type": "COUNTERPARTY_NAME", "value": record.get("receiver_name")})
            
    elif source_type.lower() == "cdr":
        record = next((r for r in bundle.get("cdr", []) if str(r.get("cdr_id")) == event_id), None)
        if not record:
            return {}
        out["source_record"] = record
        out["timestamp"] = record.get("ts")
        if out["timestamp"]:
            target_ts = _parse_ts(out["timestamp"])
            
        out["primary_entity"] = {
            "type": "PHONE",
            "value": record.get("a_number", "")
        }
        
        out["identities"].append({"type": "PHONE", "value": record.get("a_number", "")})
        if record.get("b_number"):
            out["identities"].append({"type": "COUNTERPARTY_PHONE", "value": record.get("b_number")})
        if record.get("imsi"):
            out["identities"].append({"type": "IMSI", "value": record.get("imsi")})
        if record.get("imei"):
            out["identities"].append({"type": "IMEI", "value": record.get("imei")})
            
    elif source_type.lower() == "ipdr":
        record = next((r for r in bundle.get("ipdr", []) if str(r.get("ipdr_id")) == event_id), None)
        if not record:
            return {}
        out["source_record"] = record
        out["timestamp"] = record.get("start_ts")
        if out["timestamp"]:
            target_ts = _parse_ts(out["timestamp"])
            
        out["primary_entity"] = {
            "type": "IP",
            "value": record.get("source_ip", "")
        }
        
        out["identities"].append({"type": "SOURCE_IP", "value": record.get("source_ip", "")})
        if record.get("dest_ip"):
            out["identities"].append({"type": "DESTINATION_IP", "value": record.get("dest_ip")})
        if record.get("subscriber_id"):
            out["identities"].append({"type": "SUBSCRIBER", "value": record.get("subscriber_id")})
            
    elif source_type.lower() == "complaint":
        record = next((r for r in bundle.get("complaints", []) if str(r.get("complaint_id")) == event_id), None)
        if not record:
            return {}
        out["source_record"] = record
        out["timestamp"] = record.get("date")
        if out["timestamp"]:
            target_ts = _parse_ts(out["timestamp"] + "T00:00:00")
            
        out["primary_entity"] = {
            "type": "COMPLAINT",
            "value": record.get("complaint_id", "")
        }
        if record.get("account_no"):
            out["identities"].append({"type": "ACCOUNT", "value": record.get("account_no")})
        if record.get("phone"):
            out["identities"].append({"type": "PHONE", "value": record.get("phone")})
            
    if target_ts:
        out["correlations"] = find_correlations(bundle, target_ts)
        
    return out
