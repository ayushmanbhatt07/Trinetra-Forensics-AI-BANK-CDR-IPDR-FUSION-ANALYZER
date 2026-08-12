"""Validation suite: ground-truth readers + bundle comparator.

    validate.run(bundle, gt_dir)      -> full report dict
    validate.synthetic_gt(gt_dir)     -> parsed GT tables
    validate.police_gt(gt_dir)        -> structural report of police xlsx GT

CLI: `python -m backend.validate --gt <dir> [--bundle <file.json>]`
"""

from __future__ import annotations

from .comparator import build_validation_report
from .ground_truth import read_anomalies_csv, read_police_gt, read_synthetic_gt

__all__ = ["build_validation_report", "read_anomalies_csv", "read_police_gt",
           "read_synthetic_gt", "run"]


def run(bundle: dict, gt_dir: str,
        risk_thresholds: tuple[int, ...] = (25, 50, 75)) -> dict:
    gt = read_synthetic_gt(gt_dir)
    return build_validation_report(bundle, gt, risk_thresholds)
