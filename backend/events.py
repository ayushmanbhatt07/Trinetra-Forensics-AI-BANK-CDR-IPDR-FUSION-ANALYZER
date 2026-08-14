import bisect
from typing import Any, Dict
from datetime import datetime
from backend.risk import hybrid

_TS_INDEX_CACHE: dict[int, dict] = {}

def _parse_ts(ts_val: Any) -> datetime | None:
    if not ts_val:
        return None
    if isinstance(ts_val, (int, float)):
        try:
            return datetime.fromtimestamp(ts_val)
        except Exception:
            return None
    try:
        ts_str = str(ts_val)
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1]
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None

def _get_ts_indexes(bundle: dict) -> dict:
    bundle_id = id(bundle)
    if bundle_id in _TS_INDEX_CACHE:
        return _TS_INDEX_CACHE[bundle_id]
    
    bank_list = []
    for r in bundle.get("bank", []):
        ts_val = r.get("ts")
        if ts_val:
            try:
                t_f = float(ts_val) if isinstance(ts_val, (int, float)) else _parse_ts(ts_val).timestamp()
                bank_list.append((t_f, r))
            except Exception:
                pass
    bank_list.sort(key=lambda x: x[0])
    
    cdr_list = []
    for r in bundle.get("cdr", []):
        ts_val = r.get("ts")
        if ts_val:
            try:
                t_f = float(ts_val) if isinstance(ts_val, (int, float)) else _parse_ts(ts_val).timestamp()
                cdr_list.append((t_f, r))
            except Exception:
                pass
    cdr_list.sort(key=lambda x: x[0])
    
    ipdr_list = []
    for r in bundle.get("ipdr", []):
        ts_val = r.get("start_ts") or r.get("ts")
        if ts_val:
            try:
                t_f = float(ts_val) if isinstance(ts_val, (int, float)) else _parse_ts(ts_val).timestamp()
                ipdr_list.append((t_f, r))
            except Exception:
                pass
    ipdr_list.sort(key=lambda x: x[0])
    
    idx = {
        "bank_ts": [x[0] for x in bank_list],
        "bank_r": [x[1] for x in bank_list],
        "cdr_ts": [x[0] for x in cdr_list],
        "cdr_r": [x[1] for x in cdr_list],
        "ipdr_ts": [x[0] for x in ipdr_list],
        "ipdr_r": [x[1] for x in ipdr_list],
    }
    _TS_INDEX_CACHE[bundle_id] = idx
    return idx

def find_correlations(bundle: dict, target_ts: datetime, window_sec: int = 1800) -> list[Dict[str, Any]]:
    """Find other events happening within window_sec of the target timestamp using fast bisect."""
    correlations = []
    target_ts_float = target_ts.timestamp()
    indexes = _get_ts_indexes(bundle)
    
    t_min = target_ts_float - window_sec
    t_max = target_ts_float + window_sec
    
    # Fast bisect on bank
    bts, br = indexes["bank_ts"], indexes["bank_r"]
    i0 = bisect.bisect_left(bts, t_min)
    i1 = bisect.bisect_right(bts, t_max)
    for idx in range(i0, min(i1, i0 + 20)):
        diff = abs(bts[idx] - target_ts_float)
        if diff > 0:
            r = br[idx]
            correlations.append({
                "type": "BANK",
                "time_diff_sec": int(diff),
                "description": f"Txn: {r.get('amount', 'N/A')} {r.get('txn_type', '')}",
                "id": r.get("txn_id"),
                "ts": r.get("ts")
            })
            
    # Fast bisect on cdr
    cts, cr = indexes["cdr_ts"], indexes["cdr_r"]
    i0 = bisect.bisect_left(cts, t_min)
    i1 = bisect.bisect_right(cts, t_max)
    for idx in range(i0, min(i1, i0 + 20)):
        diff = abs(cts[idx] - target_ts_float)
        if diff > 0:
            r = cr[idx]
            correlations.append({
                "type": "CDR",
                "time_diff_sec": int(diff),
                "description": f"Call {r.get('call_type', '')} with {r.get('b_number', '')}",
                "id": r.get("cdr_id"),
                "ts": r.get("ts")
            })
            
    # Fast bisect on ipdr
    its, ir = indexes["ipdr_ts"], indexes["ipdr_r"]
    i0 = bisect.bisect_left(its, t_min)
    i1 = bisect.bisect_right(its, t_max)
    for idx in range(i0, min(i1, i0 + 20)):
        diff = abs(its[idx] - target_ts_float)
        if diff > 0:
            r = ir[idx]
            correlations.append({
                "type": "IPDR",
                "time_diff_sec": int(diff),
                "description": f"Session to {r.get('dest_ip', '')}",
                "id": r.get("ipdr_id"),
                "ts": r.get("start_ts") or r.get("ts")
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
