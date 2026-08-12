"""Ground-truth readers.

Two sources:
  * synthetic CSV ground truth (data/ground_truth/*.csv) — used for CI and
    the problem-statement validation harness;
  * police XLSX ground truth (Validation_Ground_Truth/*.xlsx: Add Summary,
    Common A&B, Common IMEI, Common First-Cell-ID) — reader implemented and
    tested structurally; the folder is restored by the police team later.
"""

from __future__ import annotations

import csv
import os
import re

from ..errors import ValidationError

_CSV_ENCODINGS = ("utf-8-sig", "latin-1")


def _read_csv(path: str) -> tuple[list[str], list[dict]]:
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in _CSV_ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise ValidationError(f"ground truth CSV is empty: {path}")
    return list(rows[0].keys()), rows


def read_synthetic_gt(gt_dir: str) -> dict:
    """Load the three synthetic ground-truth files into keyed dicts."""
    anomalies, bank_cdr, cdr_ipdr = None, None, None
    if not os.path.isdir(gt_dir):
        raise ValidationError(f"ground truth dir not found: {gt_dir}")
    for name in os.listdir(gt_dir):
        low = name.lower()
        p = os.path.join(gt_dir, name)
        if low.endswith(".csv"):
            if low.startswith("anomaly"):
                _, rows = _read_csv(p)
                anomalies = {r.get("Anomaly_ID", ""): r for r in rows}
            elif low.startswith("bank_cdr"):
                _, rows = _read_csv(p)
                bank_cdr = {r.get("Transaction_ID", ""): r for r in rows}
            elif low.startswith("cdr_ipdr"):
                _, rows = _read_csv(p)
                cdr_ipdr = {r.get("CDR_ID", ""): r for r in rows}
    if not (anomalies and bank_cdr and cdr_ipdr):
        raise ValidationError(
            "synthetic ground truth incomplete; expected anomaly_ground_truth.csv, "
            "bank_cdr_ground_truth.csv, cdr_ipdr_ground_truth.csv in "
            + gt_dir)
    return {"anomalies": anomalies, "bank_cdr": bank_cdr,
            "cdr_ipdr": cdr_ipdr, "source": "synthetic"}


def read_anomalies_csv(path: str) -> dict:
    """Load a single anomalies CSV (e.g. anomaly_ground_truth_reduced.csv).

    Keys the table by Transaction_ID (falling back to Anomaly_ID) so the
    comparator can match against scored txns without the full synthetic set.
    """
    if not os.path.isfile(path):
        raise ValidationError(f"anomalies ground truth file not found: {path}")
    keys, rows = _read_csv(path)
    has_suspicious = "Is_Suspicious" in keys
    anomalies = {}
    for r in rows:
        tid = r.get("Transaction_ID") or r.get("Anomaly_ID") or ""
        if tid:
            if not has_suspicious:
                r["Is_Suspicious"] = "1"  # reduced police GT lists only anomalies
            anomalies[str(tid).strip()] = r
    return {"anomalies": anomalies, "bank_cdr": {}, "cdr_ipdr": {},
            "source": "police-reduced"}


def read_police_gt(gt_dir: str) -> dict:
    """Best-effort reader for the police Validation_Ground_Truth xlsx set.

    Expected layouts (folder restored later by the police team):
      Add Summary.xlsx          — per-account summary rows
      Common A&B.xlsx           — phone pairs active in both CDR & bank
      Common IMEI.xlsx          — IMEI ↔ phone mappings
      Common First-Cell-ID.xlsx — cell-id ↔ phone mappings

    Returns a structural report: {files: [...], sheets: {file: [sheet]},
    rows: {file: count}}. No records are synthesised from unknown layouts.
    """
    if not os.path.isdir(gt_dir):
        raise ValidationError(f"police ground truth dir not found: {gt_dir}")
    out = {"files": [], "sheets": {}, "rows": {}}
    for name in sorted(os.listdir(gt_dir)):
        if not name.lower().endswith(".xlsx"):
            continue
        p = os.path.join(gt_dir, name)
        out["files"].append(name)
        try:
            import openpyxl
            wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
            total = 0
            out["sheets"][name] = []
            for ws in wb.worksheets:
                out["sheets"][name].append(ws.title)
                n = 0
                for _ in ws.iter_rows(values_only=True):
                    n += 1
                total += n
            out["rows"][name] = total
            wb.close()
        except Exception as e:  # noqa: BLE001 — structural best-effort
            out["rows"][name] = f"unreadable: {str(e)[:80]}"
    return out
