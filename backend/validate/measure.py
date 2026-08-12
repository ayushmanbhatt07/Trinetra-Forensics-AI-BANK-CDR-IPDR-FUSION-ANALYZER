"""Dataset validation CLI.

Usage:
    python -m backend.validate.measure <data_dir> <gt_csv>

Loads the synthetic CSVs from <data_dir> (anomalous/ or a dir with
bank_*.csv/cdr_*.csv/ipdr_*.csv), scores every transaction with the
behavioural engine and reports recall/precision at several risk
thresholds against the given ground-truth CSV.

    python -m backend.validate.measure --all

Runs the three known synthetic datasets (SCRATCH 20k, ERAKSHAK 100k,
ERAKSHAK reduced) and prints a comparison table.
"""
from __future__ import annotations

import csv
import os
import sys
import time

SCORE_THRESHOLDS = (50, 60)


def _load_bundle(data_dir: str) -> dict:
    from ..adapters.synthetic import (bank_csv_records, cdr_csv_records,
                                      ipdr_csv_records)
    from ..normalise import extract_entities
    candidates = {
        "bank": ("bank_anomaly.csv", "bank_reduced.csv", "bank_final.csv"),
        "cdr": ("cdr_anomaly.csv", "cdr_reduced.csv", "cdr_final.csv"),
        "ipdr": ("ipdr_anomaly.csv", "ipdr_reduced.csv", "ipdr_final.csv"),
    }
    pick = {}
    for kind, names in candidates.items():
        for n in names:
            p = os.path.join(data_dir, n)
            if os.path.exists(p):
                pick[kind] = p
                break
    missing = [k for k in ("bank", "cdr", "ipdr") if k not in pick]
    if missing:
        raise SystemExit(f"missing files in {data_dir}: {missing}")
    bank = bank_csv_records(pick["bank"])
    cdr = cdr_csv_records(pick["cdr"])
    ipdr = ipdr_csv_records(pick["ipdr"])
    return {
        "bank": bank, "cdr": cdr, "ipdr": ipdr,
        "complaints": [], "subscribers": [],
        "entities": extract_entities(bank, cdr, ipdr),
    }


def load_gt(path: str) -> set[str]:
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        return {row["Transaction_ID"] for row in csv.DictReader(fh)}


def measure(data_dir: str, gt_path: str) -> dict:
    from ..behavioural import score_transactions
    bundle = _load_bundle(data_dir)
    gt = load_gt(gt_path)
    t0 = time.time()
    scored = score_transactions(bundle)
    elapsed = time.time() - t0
    by_id = {s["transaction_id"]: s for s in scored}
    found = set(gt) & set(by_id)
    out = {"bank": len(bundle["bank"]), "gt": len(gt), "elapsed_s": round(elapsed, 1)}
    for thr in SCORE_THRESHOLDS:
        alerts = [s for s in scored if s["risk_score"] >= thr]
        tp = {s["transaction_id"] for s in alerts} & found
        out[thr] = {
            "alerts": len(alerts),
            "recall": round(100 * len(tp) / len(gt), 1) if gt else 0.0,
            "precision": round(100 * len(tp) / max(1, len(alerts)), 1),
        }
    out["top100"] = len({s["transaction_id"] for s in scored[:100]} & found)
    return out


def main() -> None:
    args = sys.argv[1:]
    if args == ["--all"]:
        datasets = [
            (r"F:\SCRATCH\AI-BANK-TRANSACTIONS-TELECOM-ANALYZER\data\anomalous",
             r"F:\SCRATCH\AI-BANK-TRANSACTIONS-TELECOM-ANALYZER\data\ground_truth\anomaly_ground_truth.csv",
             "scratch-20k"),
            (r"F:\ERAKSHAK\AI-Bank-Transaction-and-Telecom-Analyzer\data\anomalous",
             r"F:\ERAKSHAK\AI-Bank-Transaction-and-Telecom-Analyzer\data\ground_truth\anomaly_ground_truth.csv",
             "erakshak-100k"),
            (r"F:\ERAKSHAK\AI-Bank-Transaction-and-Telecom-Analyzer\data\new_reduced",
             r"F:\ERAKSHAK\AI-Bank-Transaction-and-Telecom-Analyzer\data\new_reduced\anomaly_ground_truth_reduced.csv",
             "erakshak-reduced"),
        ]
        for data_dir, gt_path, name in datasets:
            m = measure(data_dir, gt_path)
            print(f"{name:16s} bank={m['bank']:>6d} gt={m['gt']:>5d} "
                  f"t50={m[50]['alerts']:>6d} r50={m[50]['recall']:>5.1f}% "
                  f"p50={m[50]['precision']:>5.1f}% "
                  f"top100={m['top100']:>3d} ({m['elapsed_s']}s)")
        return
    if len(args) < 2:
        raise SystemExit("usage: python -m backend.validate.measure <data_dir> <gt_csv> | --all")
    m = measure(args[0], args[1])
    print(m)


if __name__ == "__main__":
    main()
