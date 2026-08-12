"""Compare an ingested bundle against ground truth.

Metrics (per problem-statement requirement IV-b "validation against ground
truth"):

  * ID coverage — how many GT transactions / CDR records / IPDR sessions the
    ingestion recovered verbatim (ids are preserved through the pipeline),
  * correlation fidelity — precision/recall of detected bank<->CDR and
    CDR<->IPDR pairs vs the GT correlation tables,
  * anomaly detection — confusion matrix + P/R/F1 of flagged-suspicious
    accounts against the GT suspicious-transaction accounts, broken down by
    scenario type and source scope.  Default scorer is the hybrid risk engine
    (`risk.engine.transaction_risk`); `engine="behavioural"` selects the
    legacy behavioural-only scorer.
"""

from __future__ import annotations

from collections import Counter


def _ids(records: list[dict], key: str) -> set[str]:
    return {r.get(key) for r in records if r.get(key)}


def _gt_correlated_pairs(table: dict, key: str, pair_key: str) -> set[tuple]:
    out = set()
    for rid, row in table.items():
        if str(row.get("Is_Correlated", "0")) not in ("1", "true", "True"):
            continue
        peer = row.get(pair_key)
        if rid and peer:
            out.add((rid, peer))
    return out


def compare_coverage(bundle: dict, gt: dict) -> dict:
    bank_gt = set(gt["bank_cdr"].keys())
    cdr_gt = set(gt["cdr_ipdr"].keys())
    ipdr_gt = set()
    for row in gt["cdr_ipdr"].values():
        if row.get("IPDR_ID"):
            ipdr_gt.add(row["IPDR_ID"])
    for row in gt["anomalies"].values():
        if row.get("IPDR_IDs"):
            ipdr_gt.update(v for v in str(row["IPDR_IDs"]).split(";") if v)

    bank_have = _ids(bundle.get("bank", []), "txn_id")
    cdr_have = _ids(bundle.get("cdr", []), "cdr_id")
    ipdr_have = _ids(bundle.get("ipdr", []), "ipdr_id")

    def cov(have, want):
        if not want:
            return {"recall": 1.0, "matched": 0, "total": 0}
        matched = len(have & want)
        return {"recall": round(matched / len(want), 4), "matched": matched,
                "total": len(want)}

    return {
        "bank": cov(bank_have, bank_gt),
        "cdr": cov(cdr_have, cdr_gt),
        "ipdr": cov(ipdr_have, ipdr_gt),
    }


def _norm_phone(p) -> str:
    p = str(p or "")
    digits = "".join(c for c in p if c.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    if len(digits) == 10:
        return "91" + digits
    return ""


def _cdr_party_phones(r: dict) -> set[str]:
    return {p for p in (_norm_phone(r.get("a_number")),
                        _norm_phone(r.get("b_number"))) if p}


def _bank_cdr_pairs(bundle: dict, window: int) -> set[tuple]:
    """(txn_id, cdr_id) pairs the pipeline would link: a phone recovered from
    the txn (receiver or sender leg) is a CDR party and the money falls
    inside the window."""
    cdr_by_phone: dict[str, list[dict]] = {}
    for c in bundle.get("cdr", []):
        if not c.get("cdr_id"):
            continue
        for p in _cdr_party_phones(c):
            cdr_by_phone.setdefault(p, []).append(c)
    pairs = set()
    for r in bundle.get("bank", []):
        phones = {_norm_phone(r.get("receiver_phone")),
                  _norm_phone(r.get("sender_phone"))}
        phones.discard("")
        if not phones:
            continue
        txn_ts = r.get("ts")
        txn_id = r.get("txn_id")
        if txn_ts is None or not txn_id:
            continue
        for ph in phones:
            for c in cdr_by_phone.get(ph, ()):
                if abs(txn_ts - (c.get("ts") or 0)) <= window:
                    pairs.add((txn_id, c.get("cdr_id")))
    return pairs


def _subscriber_keys(r: dict, keys: tuple) -> set[str]:
    out = set()
    for k in keys:
        v = r.get(k)
        if v:
            out.add(str(v).strip())
    return out


def _cdr_ipdr_pairs(bundle: dict, window: int) -> set[tuple]:
    """(cdr_id, ipdr_id) pairs sharing a subscriber key (IMSI/IMEI/MSISDN)
    with sessions close in time."""
    cdr_by_key: dict[str, list[dict]] = {}
    cdr_by_id: dict[str, dict] = {}
    for c in bundle.get("cdr", []):
        if not c.get("cdr_id"):
            continue
        cdr_by_id[c["cdr_id"]] = c
        for k in _subscriber_keys(c, ("imsi", "imei")):
            cdr_by_key.setdefault(k, []).append(c)
    pairs = set()
    for i in bundle.get("ipdr", []):
        ipdr_id = i.get("ipdr_id")
        if not ipdr_id:
            continue
        keys = _subscriber_keys(i, ("imsi", "imei", "msisdn"))
        matched: set[str] = set()
        for k in keys:
            matched.update(c.get("cdr_id")
                           for c in cdr_by_key.get(k, ()))
        its = i.get("start_ts")
        for cdr_id in matched:
            c = cdr_by_id.get(cdr_id)
            if c is None:
                continue
            cts = c.get("ts") or 0
            if its is None or abs(cts - its) <= window:
                pairs.add((cdr_id, ipdr_id))
    return pairs


def compare_correlation(bundle: dict, gt: dict) -> dict:
    """Two tolerances:
      * `engine`  — our standard fusion window (300 s),
      * `gt`      — the GT's own maximum injected time difference (900 s),
    so a miss can be attributed to windowing vs the pipeline itself.
    """
    want_bc = _gt_correlated_pairs(gt["bank_cdr"], "Transaction_ID", "CDR_ID")
    want_ci = _gt_correlated_pairs(gt["cdr_ipdr"], "CDR_ID", "IPDR_ID")

    gt_max_bc = max((abs(int(r.get("Time_Difference_Seconds") or 0))
                     for r in gt["bank_cdr"].values()
                     if str(r.get("Is_Correlated", "0")) == "1"), default=300)
    gt_max_ci = max((abs(int(r.get("Time_Difference_Seconds") or 0))
                     for r in gt["cdr_ipdr"].values()
                     if str(r.get("Is_Correlated", "0")) == "1"), default=300)

    from ..config import correlation_window_sec
    engine_window = correlation_window_sec()

    def conf(want, have):
        tp = len(want & have)
        fp = len(have - want)
        fn = len(want - have)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return {"tp": tp, "fp": fp, "fn": fn,
                "precision": round(prec, 4), "recall": round(rec, 4),
                "f1": round(f1, 4), "total_gt": len(want)}

    return {
        "bank_cdr": {
            "engine_window": conf(want_bc, _bank_cdr_pairs(bundle, engine_window)),
            "gt_window": conf(want_bc, _bank_cdr_pairs(bundle, gt_max_bc)),
        },
        "cdr_ipdr": {
            "engine_window": conf(want_ci, _cdr_ipdr_pairs(bundle, engine_window)),
            "gt_window": conf(want_ci, _cdr_ipdr_pairs(bundle, gt_max_ci)),
        },
    }


def compare_anomalies(bundle: dict, gt: dict,
                      risk_thresholds: tuple[int, ...] = (25, 50, 75),
                      engine: str = "hybrid") -> dict:
    """Flagged-suspicious transactions vs GT suspicious transactions.

    Uses the hybrid risk engine (`transaction_risk` composite score) by
    default, with the behavioural-only scorer or account-level `fraud_heat`
    as fallbacks when the engine is unavailable or the bundle has no txn ids.
    """
    try:
        if engine == "behavioural":
            from ..behavioural import score_transactions
            scored = score_transactions(bundle)
            scores = {s["transaction_id"]: s["risk_score"]
                      for s in scored if s.get("transaction_id")}
        else:
            from ..risk.engine import transaction_risk
            scored = transaction_risk(bundle)
            scores = {s["transaction_id"]: s["risk_score"]
                      for s in scored if s.get("transaction_id")}
    except Exception:  # noqa: BLE001 — fall back to behavioural/heat
        try:
            from ..behavioural import score_transactions
            scored = score_transactions(bundle)
            scores = {s["transaction_id"]: s["risk_score"]
                      for s in scored if s.get("transaction_id")}
        except Exception:  # noqa: BLE001 — fall back to account heat
            from ..fusion import fraud_heat

            heat = fraud_heat(bundle)
            scores = {a["account_no"]: a["score"]
                      for a in heat["accounts"] if a.get("account_no")}

    by_scope: dict[str, set[str]] = {}
    suspicious: set[str] = set()
    per_type: Counter = Counter()
    for row in gt["anomalies"].values():
        if str(row.get("Is_Suspicious", "0")) != "1":
            continue
        tid = row.get("Transaction_ID") or ""
        if not tid:
            continue
        suspicious.add(tid)
        scope = (row.get("Source_Scope") or "UNKNOWN").upper()
        by_scope.setdefault(scope, set()).add(tid)
        per_type[(row.get("Scenario_Type") or "UNKNOWN").upper()] += 1

    population = len(scores)  # every scored txn is a potential TN

    def conf(want, threshold):
        predicted = {tid for tid, sc in scores.items() if sc >= threshold}
        tp = len(want & predicted)
        fn = len(want - predicted)
        fp = len(predicted - want)
        tn = max(population - len(predicted) - len(want) + tp, 0)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        fpr = fp / (fp + tn) if fp + tn else 0.0
        fnr = fn / (fn + tp) if fn + tp else 0.0
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "precision": round(prec, 4), "recall": round(rec, 4),
                "f1": round(f1, 4), "fpr": round(fpr, 4), "fnr": round(fnr, 4),
                "gt_suspicious": len(want), "predicted": len(predicted),
                "population": population, "threshold": threshold}

    def scenario_conf(want, threshold):
        """Scenario-detection accuracy: how many GT txns of a scenario type
        the engine flags at the threshold."""
        predicted = {tid for tid, sc in scores.items() if sc >= threshold}
        caught = want & predicted
        return {"tp": len(caught), "fn": len(want - caught),
                "recall": round(len(caught) / len(want), 4) if want else 0.0,
                "gt_total": len(want)}

    by_scenario: dict[str, dict] = {}
    for row in gt["anomalies"].values():
        if str(row.get("Is_Suspicious", "0")) != "1":
            continue
        tid = row.get("Transaction_ID") or ""
        if not tid:
            continue
        sc = (row.get("Scenario_Type") or "UNKNOWN").upper()
        by_scenario.setdefault(sc, {"tids": set()})["tids"].add(tid)
    by_scenario = {
        sc: {str(t): scenario_conf(d["tids"], t) for t in risk_thresholds}
        for sc, d in sorted(by_scenario.items())}

    return {
        "overall": {str(t): conf(suspicious, t) for t in risk_thresholds},
        "by_scope": {k: {str(t): conf(v, t) for t in risk_thresholds}
                     for k, v in sorted(by_scope.items())},
        "by_scenario": by_scenario,
        "scenario_types": dict(per_type),
        "risk_thresholds": list(risk_thresholds),
    }


def build_validation_report(bundle: dict, gt: dict,
                            risk_thresholds: tuple[int, ...] = (25, 50, 75)) -> dict:
    """Assemble the full validation report (coverage + correlation + anomaly)."""
    return {
        "source": gt.get("source", "synthetic"),
        "coverage": compare_coverage(bundle, gt),
        "correlation": compare_correlation(bundle, gt),
        "anomalies": compare_anomalies(bundle, gt, risk_thresholds),
    }
