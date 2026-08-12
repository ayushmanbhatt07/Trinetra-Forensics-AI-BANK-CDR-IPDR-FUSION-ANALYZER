"""CLI for the validation suite: python -m backend.validate [options]."""

from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv: list[str] | None = None) -> int:
    from ..pipeline import ingest_folder
    from ..validate import run, read_synthetic_gt

    ap = argparse.ArgumentParser(
        prog="python -m backend.validate",
        description="Validate an ingested bundle against synthetic ground truth.")
    ap.add_argument("--gt", required=True, help="ground truth dir "
                                                "(data/ground_truth)")
    ap.add_argument("--bundle", help="bundle JSON (default: ingest --gt dir)")
    ap.add_argument("--out", help="write report JSON here")
    ap.add_argument("--risk-thresholds", type=int, nargs="+",
                    default=[25, 50, 75], help="risk-score thresholds")
    ap.add_argument("--engine", choices=["hybrid", "behavioural"],
                    default="hybrid", help="scorer for anomaly detection")
    args = ap.parse_args(argv)

    if args.bundle:
        with open(args.bundle, encoding="utf-8") as fh:
            bundle = json.load(fh)
    else:
        bundle = ingest_folder(args.gt)

    from .comparator import compare_anomalies
    report = run(bundle, args.gt, tuple(args.risk_thresholds))
    if args.engine == "behavioural":
        report["anomalies"] = compare_anomalies(
            bundle, read_synthetic_gt(args.gt),
            tuple(args.risk_thresholds), engine="behavioural")
    else:
        report["anomalies"]["engine"] = args.engine
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"validation report written to {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    raise SystemExit(main())
