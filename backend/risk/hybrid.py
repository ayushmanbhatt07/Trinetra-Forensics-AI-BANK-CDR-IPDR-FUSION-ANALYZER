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

import bisect
import logging
import threading

from ..behavioural import score_transactions
from ..fusion import fraud_heat
from .ensemble import ensemble_scores
from .features import txn_ml_scores
from .graph_features import graph_features, graph_score as _batch_graph_score
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

    # ---- Group 1: Fully independent engines run in parallel ----------------
    # These engines only need `bundle` as input. They have no data dependencies
    # on each other and can safely run concurrently.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from backend import config

    g1_results: dict = {
        "behavioural": [], "heat": {"accounts": []}, "ens": {"accounts": [], "detectors": []},
        "tml": {}, "prof_txn": {}, "prof_acc": {}, "temporal_txn": {}, "acc_temporal": {},
        "telecom": {"txn": {}, "phone": {}}, "internet": {"txn": {}, "ip": {}}
    }

    def _run_behavioural():
        try: return ("behavioural", score_transactions(bundle))
        except Exception as e:
            logger.warning("[HYBRID] score_transactions failed: %s", e)
            return ("behavioural", [])

    def _run_heat():
        try: return ("heat", fraud_heat(bundle))
        except Exception as e:
            logger.warning("[HYBRID] fraud_heat failed: %s", e)
            return ("heat", {"accounts": []})

    def _run_ensemble():
        try: return ("ens", ensemble_scores(bundle))
        except Exception as e:
            logger.warning("[HYBRID] ensemble_scores failed: %s", e)
            return ("ens", {"accounts": [], "detectors": []})

    def _run_txn_ml():
        try: return ("tml", txn_ml_scores(bundle))
        except Exception as e:
            logger.warning("[HYBRID] txn_ml_scores failed: %s", e)
            return ("tml", {})

    def _run_prof_txn():
        try: return ("prof_txn", profile_deviation(bundle))
        except Exception as e:
            logger.warning("[HYBRID] profile_deviation failed: %s", e)
            return ("prof_txn", {})

    def _run_prof_acc():
        try: return ("prof_acc", account_profile_deviation(bundle))
        except Exception as e:
            logger.warning("[HYBRID] account_profile_deviation failed: %s", e)
            return ("prof_acc", {})

    def _run_temporal_txn():
        try: return ("temporal_txn", txn_temporal_scores(bundle))
        except Exception as e:
            logger.warning("[HYBRID] txn_temporal_scores failed: %s", e)
            return ("temporal_txn", {})

    def _run_temporal_acc():
        try: return ("acc_temporal", account_temporal_scores(bundle))
        except Exception as e:
            logger.warning("[HYBRID] account_temporal_scores failed: %s", e)
            return ("acc_temporal", {})

    def _run_telecom():
        try: return ("telecom", telecom_scores(bundle))
        except Exception as e:
            logger.warning("[HYBRID] telecom_scores failed: %s", e)
            return ("telecom", {"txn": {}, "phone": {}})

    def _run_internet():
        try: return ("internet", internet_scores(bundle))
        except Exception as e:
            logger.warning("[HYBRID] internet_scores failed: %s", e)
            return ("internet", {"txn": {}, "ip": {}})

    with ThreadPoolExecutor(max_workers=config.max_workers()) as executor:
        futs = [
            executor.submit(_run_behavioural),
            executor.submit(_run_heat),
            executor.submit(_run_ensemble),
            executor.submit(_run_txn_ml),
            executor.submit(_run_prof_txn),
            executor.submit(_run_prof_acc),
            executor.submit(_run_temporal_txn),
            executor.submit(_run_temporal_acc),
            executor.submit(_run_telecom),
            executor.submit(_run_internet),
        ]
        for f in as_completed(futs):
            try:
                key, val = f.result()
                g1_results[key] = val
            except Exception as e:
                logger.warning("[HYBRID] G1 worker raised unhandled: %s", e)

    behavioural = g1_results["behavioural"]
    heat = g1_results["heat"]
    ens = g1_results["ens"]
    tml = g1_results["tml"]
    prof_txn = g1_results["prof_txn"]
    prof_acc = g1_results["prof_acc"]
    temporal_txn = g1_results["temporal_txn"]
    acc_temporal = g1_results["acc_temporal"]
    telecom = g1_results["telecom"]
    internet = g1_results["internet"]

    heat_by_acc = {a["account_no"]: a for a in heat.get("accounts", [])}
    ens_by_acc = {a["account_no"]: a for a in ens.get("accounts", [])}

    # ---- Group 2: Engines that depend on group 1 results -------------------
    def _run_moneyflow():
        try: return ("moneyflow", money_flow_analysis(bundle))
        except Exception as e:
            logger.warning("[HYBRID] money_flow_analysis failed: %s", e)
            return ("moneyflow", {"accounts": {}, "transactions": {}})

    def _run_entity():
        try: return ("entity", entity_risk(bundle))
        except Exception as e:
            logger.warning("[HYBRID] entity_risk failed: %s", e)
            return ("entity", {"account_exposure": {}, "entities": {}})

    def _run_graph():
        try: return ("gfeats", graph_features(bundle))
        except Exception as e:
            logger.warning("[HYBRID] graph_features failed: %s", e)
            return ("gfeats", ({}, {}))

    g2_results: dict = {
        "moneyflow": {"accounts": {}, "transactions": {}},
        "entity": {"account_exposure": {}, "entities": {}},
        "gfeats": ({}, {})
    }
    with ThreadPoolExecutor(max_workers=config.max_workers()) as executor:
        futs2 = [
            executor.submit(_run_moneyflow),
            executor.submit(_run_entity),
            executor.submit(_run_graph),
        ]
        for f in as_completed(futs2):
            try:
                key, val = f.result()
                g2_results[key] = val
            except Exception as e:
                logger.warning("[HYBRID] G2 worker raised unhandled: %s", e)

    moneyflow = g2_results["moneyflow"]
    entity = g2_results["entity"]
    gfeats, gmeta = g2_results["gfeats"]

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

    # Pre-compute graph scores for ALL accounts in one batch (avoids
    # re-normalising per account which was the old per-account bottleneck).
    all_graph_scores = _batch_graph_score(gfeats) if gfeats else {}

    hw = hybrid_weights()
    w_trules, w_tml, w_tbeh = hw.get("txn_rules", 0.30), hw.get("txn_ml", 0.20), hw.get("txn_behaviour", 0.25)
    w_ttemp, w_ttel, w_tnet = hw.get("txn_temporal", 0.10), hw.get("txn_telecom", 0.10), hw.get("txn_internet", 0.05)
    w_ttotal = w_trules + w_tml + w_tbeh + w_ttemp + w_ttel + w_tnet
    inv_ttotal = (1.0 / w_ttotal) if w_ttotal > 0 else 0.0

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
        beh_val = float(prof.get("score", 0.0))
        temp_val = float(temp.get("temporal_score", 0.0))
        tel_val = float(tel.get("call_assist_score", 0.0))
        net_val = float(net.get("internet_score", 0.0))

        raw_sum = (w_trules * rules_score + w_tml * ml_score + w_tbeh * beh_val
                   + w_ttemp * temp_val + w_ttel * tel_val + w_tnet * net_val)
        hybrid = round(min(100.0, max(0.0, raw_sum * inv_ttotal)), 2)

        rec = dict(b)
        rec.update({
            "risk_score": hybrid,
            "risk_band": risk_band(hybrid),
            "hybrid_components": {
                "rules": round(rules_score, 2),
                "ml": round(ml_score, 2),
                "behaviour": round(beh_val, 2),
                "temporal": round(temp_val, 2),
                "telecom": round(tel_val, 2),
                "internet": round(net_val, 2),
            },
            "models_fired": _models_fired(rules_score, ml_score, beh_val, temp_val, tel_val, net_val),
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
            "acc_graph": float(all_graph_scores.get(acc, 0.0)),
            "acc_entity": float(ent.get("entity_risk", 0.0)),
            "acc_moneyflow": float(flow.get("flow_score", 0.0)),
        }, weights=hw)
        accounts[acc] = {
            "account_no": acc,
            "risk_score": hybrid,
            "risk_band": risk_band(hybrid),
            "components": {
                "rules": round(rule, 2),
                "ml_ensemble": round(ml, 2),
                "behaviour": round(float(beh.get("behaviour_score", 0.0)), 2),
                "temporal": round(float(temp.get("temporal_score", 0.0)), 2),
                "graph": round(float(all_graph_scores.get(acc, 0.0)), 2),
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
            }, weights=hw)
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
    scored_sorted = list(transactions.values())
    scored_sorted.sort(key=lambda r: (-r.get("risk_score", 0.0), r.get("risk_band", "")))

    return {
        "transactions": transactions,
        "sorted_transactions": scored_sorted,
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
    from backend.events import _get_ts_indexes
    idx = _get_ts_indexes(bundle)
    
    cts, cr = idx["cdr_ts"], idx["cdr_r"]
    i0 = bisect.bisect_left(cts, ts - w)
    i1 = bisect.bisect_right(cts, ts + w)
    for i in range(i0, min(i1, i0 + 30)):
        r = cr[i]
        a, b = r.get("a_number") or "", r.get("b_number") or ""
        if phone and phone not in (a, b):
            continue
        events.append({"kind": "call", "ts": cts[i],
                       "detail": f"{a} -> {b} ({r.get('duration_sec')}s)"})
        if len(events) >= 12:
            break

    its, ir = idx["ipdr_ts"], idx["ipdr_r"]
    i0 = bisect.bisect_left(its, ts - w)
    i1 = bisect.bisect_right(its, ts + w)
    for i in range(i0, min(i1, i0 + 30)):
        r = ir[i]
        if phone and r.get("msisdn") != phone:
            continue
        events.append({"kind": "session", "ts": its[i],
                       "detail": f"{r.get('msisdn')} @ {r.get('ip') or '?'}"})
        if len(events) >= 20:
            break

    events.sort(key=lambda e: e["ts"])
    return events[:12]


def _neighbours(bundle: dict, txn: dict) -> list[dict]:
    """Other transactions from the same customer nearby in time."""
    cust = txn.get("sender_customer_id") or txn.get("account_no") or ""
    ts = float(txn.get("ts") or 0.0)
    if not ts:
        return []
    out = []
    from backend.events import _get_ts_indexes
    idx = _get_ts_indexes(bundle)
    bts, br = idx["bank_ts"], idx["bank_r"]
    i0 = bisect.bisect_left(bts, ts - 3600)
    i1 = bisect.bisect_right(bts, ts + 3600)
    for i in range(i0, min(i1, i0 + 50)):
        r = br[i]
        if r.get("customer_id") != cust and r.get("account_no") != cust:
            continue
        if r.get("txn_id") != txn.get("txn_id"):
            out.append({"transaction_id": r.get("txn_id"),
                        "amount": r.get("debit") or r.get("credit") or 0,
                        "ts": bts[i]})
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
