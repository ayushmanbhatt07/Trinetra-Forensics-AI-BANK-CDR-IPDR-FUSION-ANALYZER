"""Hybrid Multi-Stage Fraud Detection Engine — orchestrator.

Runs every intelligence engine once over the bundle and fuses the
normalised 0-100 scores into hybrid composites:

  per transaction:
      w_txn_rules     * behavioural rule score
    + w_txn_ml        * txn-level ML score
    + w_txn_behaviour * profile deviation
    + w_txn_temporal  * sliding-window temporal correlation
    + w_txn_telecom   * call-assist context
    + w_txn_internet  * IPDR/device context

  per account:
      w_acc_rules     * fraud_heat
    + w_acc_ml        * ML ensemble (IF, LOF, DBSCAN, HDBSCAN, OCSVM, PCA)
    + w_acc_behaviour * profile deviation aggregate
    + w_acc_temporal  * temporal concentration
    + w_acc_graph     * money-flow graph analytics
    + w_acc_entity    * entity exposure
    + w_acc_moneyflow * N-hop flow scenarios

Every composite carries a per-source `components` breakdown, `confidence`,
named `scenarios` and a full `explanation` so the STR report and the
anomaly UI can cite exactly why a record is risky.

`hybrid_analyze` caches its result keyed on the bundle identity; call
`clear_cache` after ingest.
"""

from __future__ import annotations

import logging
import threading

from ..behavioural import score_transactions
from ..fusion import fraud_heat
from .ensemble import ensemble_scores
from .features import txn_ml_scores
from .graph_features import graph_features
from .internet import internet_scores
from .moneyflow import money_flow_analysis
from .profiles import account_profile_deviation, profile_deviation
from .scenarios import scenario_engine
from .telecom import telecom_scores
from .temporal import account_temporal_scores, txn_temporal_scores
from .weights import renormalise, weight  # noqa: F401
from .weights import hybrid_weights  # noqa: F401  (re-exported for the API)
from .entity_risk import entity_risk
from .explain import explain_account, explain_entity, explain_transaction
from .engine import risk_band

logger = logging.getLogger(__name__)

_cache: dict = {}
_CACHE_KEY = "hybrid"
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# api-layer convenience alias (clear_hybrid_cache is the documented name)
clear_hybrid_cache = clear_cache


def _fingerprint(bundle: dict) -> tuple:
    bank = bundle.get("bank", [])
    return (len(bank), len(bundle.get("cdr", [])),
            len(bundle.get("ipdr", [])),
            len(bundle.get("complaints", [])),
            tuple((r.get("txn_id") or "")[:8] for r in bank[:5]))


def _fetch(bundle: dict) -> dict:
    key = _CACHE_KEY + ":" + repr(_fingerprint(bundle))
    # Fast path: check cache without lock
    hit = _cache.get(key)
    if hit is not None:
        return hit
    
    # Cache miss: acquire lock and compute
    with _cache_lock:
        # Check again in case another thread already computed it
        hit = _cache.get(key)
        if hit is not None:
            return hit
            
        result = _compute(bundle)
        _cache[key] = result
        return result


def _compute(bundle: dict) -> dict:
    bank = bundle.get("bank", [])
    if not bank:
        return {"transactions": {}, "accounts": {}, "entities": {},
                "scenarios": {"stats": {}},
                "stats": {"transactions": 0, "total_txns": 0,
                          "unscored_txns": 0, "accounts": 0, "entities": 0,
                          "graph": {"nodes": 0, "edges": 0, "communities": 0},
                          "ensemble_detectors": [], "ensemble_fitted": False}}

    # ---- engine outputs ------------------------------------------------
    behavioural = score_transactions(bundle)
    heat = fraud_heat(bundle)
    heat_by_acc = {a["account_no"]: a for a in heat["accounts"]}
    ens = ensemble_scores(bundle)
    ens_by_acc = {a["account_no"]: a for a in ens["accounts"]}
    tml = txn_ml_scores(bundle)
    prof_txn = profile_deviation(bundle)
    prof_acc = account_profile_deviation(bundle)
    temporal_txn = txn_temporal_scores(bundle)
    acc_temporal = account_temporal_scores(bundle)
    telecom = telecom_scores(bundle)
    internet = internet_scores(bundle)
    moneyflow = money_flow_analysis(bundle)
    entity = entity_risk(bundle)
    gfeats, gmeta = graph_features(bundle)

    beh_by_id = {b["transaction_id"]: b for b in behavioural}

    scenarios = scenario_engine(bundle, {
        "breakdown": {b["transaction_id"]: b["breakdown"]
                      for b in behavioural},
        "profile": prof_txn,
        "temporal": temporal_txn,
        "telecom": telecom["txn"],
        "internet": internet["txn"],
        "acc_profile": prof_acc,
        "graph": gfeats,
    }, moneyflow=moneyflow, entity=entity)
    txn_scen = scenarios["txn"]
    acc_scen = scenarios["account"]
    flow_by_acc = moneyflow["accounts"]
    ent_by_acc = entity["account_exposure"]

    # ---- per-transaction hybrid ----------------------------------------
    transactions: dict[str, dict] = {}
    skipped = 0
    for b in behavioural:
        tid = b["transaction_id"]
        if not tid:
            skipped += 1
            continue
        acc = b.get("account_no") or ""
        rules_score = float(b["risk_score"])
        ml_score = float(tml.get(tid, 0.0))
        prof = prof_txn.get(tid, {})
        temp = temporal_txn.get(tid, {})
        tel = telecom["txn"].get(tid, {})
        net = internet["txn"].get(tid, {})
        hybrid = renormalise({
            "txn_rules": rules_score,
            "txn_ml": ml_score,
            "txn_behaviour": float(prof.get("score", 0.0)),
            "txn_temporal": float(temp.get("temporal_score", 0.0)),
            "txn_telecom": float(tel.get("call_assist_score", 0.0)),
            "txn_internet": float(net.get("internet_score", 0.0)),
        })
        rec = dict(b)
        rec.update({
            "risk_score": hybrid,
            "risk_band": risk_band(hybrid),
            "hybrid_components": {
                "rules": round(rules_score, 2),
                "ml": round(ml_score, 2),
                "behaviour": round(float(prof.get("score", 0.0)), 2),
                "temporal": round(float(temp.get("temporal_score", 0.0)), 2),
                "telecom": round(float(tel.get("call_assist_score", 0.0)), 2),
                "internet": round(float(net.get("internet_score", 0.0)), 2),
            },
            "models_fired": _models_fired(rules_score, ml_score,
                                          float(prof.get("score", 0.0)),
                                          float(temp.get("temporal_score", 0.0)),
                                          float(tel.get("call_assist_score", 0.0)),
                                          float(net.get("internet_score", 0.0))),
            "scenarios": txn_scen.get(tid, []),
        })
        transactions[tid] = rec

    # ---- per-account hybrid ---------------------------------------------
    accounts: dict[str, dict] = {}
    all_accs = (set(heat_by_acc) | set(ens_by_acc) | set(prof_acc)
                | set(gfeats) | set(ent_by_acc) | set(flow_by_acc))
    for acc in all_accs:
        rule = float(heat_by_acc.get(acc, {}).get("score", 0.0))
        ml = float(ens_by_acc.get(acc, {}).get("ensemble_score", 0.0))
        beh = prof_acc.get(acc, {})
        temp = acc_temporal.get(acc, {})
        graph = gfeats.get(acc, {})
        ent = ent_by_acc.get(acc, {})
        flow = flow_by_acc.get(acc, {})
        hybrid = renormalise({
            "acc_rules": rule,
            "acc_ml": ml,
            "acc_behaviour": float(beh.get("behaviour_score", 0.0)),
            "acc_temporal": float(temp.get("temporal_score", 0.0)),
            "acc_graph": float(_graph_score(graph)),
            "acc_entity": float(ent.get("entity_risk", 0.0)),
            "acc_moneyflow": float(flow.get("flow_score", 0.0)),
        })
        accounts[acc] = {
            "account_no": acc,
            "risk_score": hybrid,
            "risk_band": risk_band(hybrid),
            "components": {
                "rules": round(rule, 2),
                "ml_ensemble": round(ml, 2),
                "behaviour": round(float(beh.get("behaviour_score", 0.0)), 2),
                "temporal": round(float(temp.get("temporal_score", 0.0)), 2),
                "graph": round(float(_graph_score(graph)), 2),
                "entity": round(float(ent.get("entity_risk", 0.0)), 2),
                "moneyflow": round(float(flow.get("flow_score", 0.0)), 2),
            },
            "ml_detectors": list(ens_by_acc.get(acc, {}).get("per_detector", {})),
            "flags": heat_by_acc.get(acc, {}).get("flags", []),
            "scenarios": acc_scen.get(acc, []),
            "moneyflow": flow,
            "entity_exposure": ent,
            "graph_metrics": {
                "degree": graph.get("degree", 0),
                "pagerank": graph.get("pagerank", 0),
                "betweenness": graph.get("betweenness", 0),
                "community_size": graph.get("community_size", 1),
            },
        }

    # ---- entity hybrid ---------------------------------------------------
    entities: dict[str, dict] = {}
    for kind, lst in entity["entities"].items():
        for ent in lst:
            entity_id = ent["entity"]
            conc = float(ent["entity_risk"])
            hybrid = renormalise({
                "ent_ml": conc,
                "ent_graph": 0.0,
                "ent_temporal": 0.0,
                "ent_telecom": _phone_telecom(telecom, kind, entity_id),
                "ent_internet": _phone_internet(internet, kind, entity_id),
            })
            entities[f"{kind}:{entity_id}"] = {
                "entity": entity_id,
                "kind": kind,
                "risk_score": hybrid,
                "risk_band": risk_band(hybrid),
                "components": {
                    "concentration": round(conc, 2),
                    "telecom": round(_phone_telecom(telecom, kind, entity_id), 2),
                    "internet": round(_phone_internet(internet, kind, entity_id), 2),
                },
                "accounts": ent["accounts"],
                "account_count": ent["account_count"],
                "ncrp": ent["ncrp"],
                "reasons": ent["reasons"],
            }

    return {
        "transactions": transactions,
        "accounts": accounts,
        "entities": entities,
        "scenarios": scenarios,
        "entity_risk": entity,
        "stats": {
            "transactions": len(transactions),
            "total_txns": len(bank),
            "unscored_txns": skipped,
            "accounts": len(accounts),
            "entities": len(entities),
            "graph": gmeta,
            "ensemble_detectors": ens.get("detectors", []),
            "ensemble_fitted": ens.get("fitted", False),
        },
    }


def _models_fired(*scores: float) -> list[str]:
    names = ["rules", "ml", "behaviour", "temporal", "telecom", "internet"]
    return [n for n, s in zip(names, scores) if s >= 25]


def _graph_score(feats: dict) -> float:
    """0-100 graph anomaly score for one account's feature row."""
    if not feats:
        return 0.0
    from .graph_features import graph_score
    return graph_score({feats["account_no"]: feats}).get(feats["account_no"], 0.0)


def _phone_telecom(telecom: dict, kind: str, entity_id: str) -> float:
    if kind != "phone":
        return 0.0
    net = telecom.get("phone", {}).get(entity_id, {})
    if not net:
        return 0.0
    score = min(100.0, float(net.get("degree", 0)) * 3
                + float(net.get("pagerank", 0)) * 800)
    return round(score, 2)


def _phone_internet(internet: dict, kind: str, entity_id: str) -> float:
    if kind != "ip":
        return 0.0
    hit = internet.get("shared_ips", {}).get(entity_id)
    if not hit:
        return 0.0
    return float(hit.get("shared_ip_score", 0.0))


def hybrid_analyze(bundle: dict) -> dict:
    """Top-level entry point (cached)."""
    return _fetch(bundle)


def hybrid_analyze_fast(bundle: dict) -> dict | None:
    """Top-level entry point (non-blocking). Returns None if not cached."""
    key = _CACHE_KEY + ":" + repr(_fingerprint(bundle))
    return _cache.get(key)


def hybrid_transaction_risk(bundle: dict, min_score: float = 0.0) -> list[dict]:
    """Hybrid per-transaction risk, sorted descending (cache-aware)."""
    res = _fetch(bundle)
    rows = list(res["transactions"].values())
    rows.sort(key=lambda r: (-r["risk_score"], r.get("risk_band", "")))
    if min_score > 0:
        rows = [r for r in rows if r["risk_score"] >= min_score]
    return rows


def hybrid_account_risk(bundle: dict) -> list[dict]:
    res = _fetch(bundle)
    rows = list(res["accounts"].values())
    rows.sort(key=lambda r: -r["risk_score"])
    return rows


def hybrid_entity_risk(bundle: dict) -> list[dict]:
    res = _fetch(bundle)
    rows = list(res["entities"].values())
    rows.sort(key=lambda r: -r["risk_score"])
    return rows


def explanations_for_txn(bundle: dict, txn_id: str) -> dict:
    """Full explainability payload for one transaction."""
    res = _fetch(bundle)
    txn = res["transactions"].get(txn_id)
    if txn is None:
        return {}
    info = {
        "rules": txn.get("rules_fired", []),
        "breakdown": txn.get("breakdown", []),
        "scenarios": txn.get("scenarios", []),
        "models": txn.get("models_fired", []),
        "evidence": txn.get("evidence", []),
        "profile": txn.get("hybrid_components", {}),
        "temporal": _txn_temporal(bundle, txn_id),
        "telecom": _txn_telecom(bundle, txn_id),
        "internet": _txn_internet(bundle, txn_id),
        "neighbours": _neighbours(bundle, txn),
        "timeline": _txn_timeline(bundle, txn),
        "recommendations": _recommendations(txn),
    }
    return explain_transaction(txn_id, txn, info)


def explanations_for_account(bundle: dict, account_no: str) -> dict:
    res = _fetch(bundle)
    acc = res["accounts"].get(account_no)
    if acc is None:
        return {}
    info = {
        "scenarios": acc.get("scenarios", []),
        "moneyflow": acc.get("moneyflow", {}),
        "entity": acc.get("entity_exposure", {}),
        "graph": acc.get("graph_metrics", {}),
        "profile": {"dormant_activated":
                    bool(res["scenarios"].get("account", {}).get(account_no))},
        "recommendations": _acc_recommendations(acc),
    }
    return explain_account(account_no, info)


def explanations_for_entity(bundle: dict, kind: str, entity: str) -> dict:
    res = _fetch(bundle)
    ent = res["entities"].get(f"{kind}:{entity}")
    if ent is None:
        return {}
    return explain_entity(entity, kind, ent)


def _txn_temporal(bundle: dict, txn_id: str) -> dict:
    return txn_temporal_scores(bundle).get(txn_id, {})


def _txn_telecom(bundle: dict, txn_id: str) -> dict:
    return telecom_scores(bundle)["txn"].get(txn_id, {})


def _txn_internet(bundle: dict, txn_id: str) -> dict:
    return internet_scores(bundle)["txn"].get(txn_id, {})


def _txn_timeline(bundle: dict, txn: dict) -> list[dict]:
    """Nearby calls/sessions around the transaction (evidence timeline)."""
    ts = float(txn.get("ts") or 0.0)
    if not ts:
        return []
    events = []
    phone = txn.get("sender_phone") or ""
    w = 3600
    for r in bundle.get("cdr", []):
        rts = float(r.get("ts") or 0.0)
        if rts and abs(rts - ts) <= w:
            a, b = r.get("a_number") or "", r.get("b_number") or ""
            if phone and phone not in (a, b):
                continue
            events.append({"kind": "call", "ts": rts,
                           "detail": f"{a} -> {b} "
                                     f"({r.get('duration_sec')}s)"})
    for r in bundle.get("ipdr", []):
        rts = float(r.get("start_ts") or 0.0)
        if rts and abs(rts - ts) <= w:
            if phone and r.get("msisdn") != phone:
                continue
            events.append({"kind": "session", "ts": rts,
                           "detail": f"{r.get('msisdn')} "
                                     f"@ {r.get('ip') or '?'}"})
    events.sort(key=lambda e: e["ts"])
    return events[:12]


def _neighbours(bundle: dict, txn: dict) -> list[dict]:
    """Other transactions from the same customer nearby in time."""
    cust = txn.get("sender_customer_id") or txn.get("account_no") or ""
    ts = float(txn.get("ts") or 0.0)
    out = []
    for r in bundle.get("bank", []):
        if r.get("customer_id") != cust and r.get("account_no") != cust:
            continue
        rts = float(r.get("ts") or 0.0)
        if rts and abs(rts - ts) <= 3600 and r.get("txn_id") != txn.get("txn_id"):
            out.append({"transaction_id": r.get("txn_id"),
                        "amount": r.get("debit") or r.get("credit") or 0,
                        "ts": rts})
        if len(out) >= 6:
            break
    return out


def _recommendations(txn: dict) -> list[str]:
    recs = []
    band = txn.get("risk_band", "LOW")
    if band in ("HIGH", "CRITICAL", "SEVERE"):
        recs.append("File an STR (Suspicious Transaction Report) for this "
                    "transaction.")
    if txn.get("scenarios"):
        recs.append(f"Open an investigation for scenario "
                    f"'{txn['scenarios'][0]['scenario']}'.")
    if any("call" in str(r).lower() for r in txn.get("rules_fired", [])):
        recs.append("Request call-data records (CDR) for the linked phones.")
    if any("device" in str(r).lower() or "IMEI" in str(r).upper()
           for r in txn.get("rules_fired", [])):
        recs.append("Flag the device (IMEI) and check it across other "
                    "accounts.")
    return recs[:4]


def _acc_recommendations(acc: dict) -> list[str]:
    recs = []
    band = acc.get("risk_band", "LOW")
    if band in ("HIGH", "CRITICAL", "SEVERE"):
        recs.append("Freeze/verify the account and notify the bank's AML "
                    "officer.")
    mf = acc.get("moneyflow", {})
    if mf.get("circular"):
        recs.append("Trace the full circular ring for related accounts.")
    if mf.get("layering_depth", 0) >= 3:
        recs.append("Follow the layering chain to the final cash-out "
                    "accounts.")
    if acc.get("entity_exposure", {}).get("shared_entities", 0) >= 4:
        recs.append("Investigate the shared identifiers across all linked "
                    "accounts.")
    return recs[:4]
