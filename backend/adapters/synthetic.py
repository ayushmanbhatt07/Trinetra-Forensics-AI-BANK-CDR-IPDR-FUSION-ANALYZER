"""Synthetic dataset adapters (problem-statement data/ layout).

Reads the synthetic CSV datasets shipped with the problem statement
(data/clean/*_final.csv, data/anomalous/*_anomaly.csv) into canonical v3
records so the full pipeline — entity extraction, fusion, risk scoring,
validation vs ground truth — can run unchanged on them.
"""

from __future__ import annotations

import calendar
import csv
import datetime as dt
import os

from ..normalise import extract_entities
from ..validate.comparator import _norm_phone

_CSV_ENCODINGS = ("utf-8-sig", "latin-1")


def _read_csv(path: str) -> list[dict]:
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
    return list(csv.DictReader(text.splitlines()))


def _ts(date: str, time: str) -> float | None:
    try:
        d = dt.datetime.strptime(
            f"{date} {time[:8]}", "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(d.timetuple())
    except (ValueError, TypeError):
        return None


def bank_csv_records(path: str) -> list[dict]:
    """Oriented to the sender (debit perspective) — the money-flow table has
    both legs, and the GT transactions resolve against sender accounts."""
    out = []
    for row in _read_csv(path):
        try:
            amount = float(row.get("Transaction_Amount") or 0)
        except ValueError:
            amount = 0.0
        ts = _ts(row.get("Date", ""), row.get("Timestamp", ""))
        out.append({
            "txn_id": row.get("Transaction_ID", ""),
            "bank": row.get("Sender_Bank_Name", ""),
            "account_no": row.get("Sender_Account_Number", ""),
            "account_name": row.get("Sender_Customer_Name", ""),
            "customer_id": row.get("Sender_Customer_ID", ""),
            "ifsc": row.get("Sender_IFSC", ""),
            "date": row.get("Date", ""),
            "time": row.get("Timestamp", ""),
            "ts": ts,
            "mode": (row.get("Transaction_Mode") or "").upper(),
            "debit": amount,
            "credit": None,
            "balance": None,
            "txn_type": "D",
            "sender_phone": _norm_phone(row.get("Sender_Phone_Number", "")),
            "receiver_phone": _norm_phone(row.get("Receiver_Phone_Number", "")),
            "counterparty_name": row.get("Receiver_Customer_Name", ""),
            "counterparty_bank": row.get("Receiver_Bank_Name", ""),
            "receiver_account": row.get("Receiver_Account_Number", ""),
            "narration": f"{row.get('Transaction_Mode', '')} "
                         f"{row.get('Receiver_Customer_Name', '')}",
            "source_file": os.path.basename(path),
            "source_format": "synthetic_csv",
        })
    return out


def cdr_csv_records(path: str) -> list[dict]:
    out = []
    for row in _read_csv(path):
        ts = _ts(row.get("Call_Date", ""), row.get("Call_Start_Time", ""))
        try:
            dur = int(row.get("Call_Duration_Seconds") or 0)
        except ValueError:
            dur = 0
        out.append({
            "cdr_id": row.get("CDR_ID", ""),
            "operator": row.get("Operator", ""),
            "query_type": "MSISDN",
            "a_number": _norm_phone(row.get("A_Party_Number", "")),
            "b_number": _norm_phone(row.get("B_Party_Number", "")),
            "call_type": row.get("Call_Type", ""),
            "date": row.get("Call_Date", ""),
            "time": row.get("Call_Start_Time", ""),
            "ts": ts,
            "duration_sec": dur,
            "imsi": row.get("IMSI", ""),
            "imei": row.get("IMEI", ""),
            "cell_id_first": row.get("First_Cell_Global_ID", ""),
            "bts_location_first": row.get("First_BTS_Location", ""),
            "roaming_circle": row.get("Roaming_Network_Circle", ""),
            "source_file": os.path.basename(path),
            "source_format": "synthetic_csv",
        })
    return out


def ipdr_csv_records(path: str) -> list[dict]:
    out = []
    for row in _read_csv(path):
        start = _ts(row.get("Session_Date", ""), row.get("Session_Start_Time", ""))
        dur = row.get("Session_Duration_Seconds") or ""
        try:
            dur_s = int(float(dur))
        except ValueError:
            dur_s = 0
        out.append({
            "ipdr_id": row.get("IPDR_ID", ""),
            "operator": row.get("Operator", ""),
            "msisdn": _norm_phone(row.get("Subscriber_MSISDN", "")),
            "imsi": row.get("Subscriber_IMSI", ""),
            "imei": row.get("Device_IMEI", ""),
            "source_ip": row.get("Source_IP_Address", ""),
            "dest_ip": row.get("Destination_IP_Address", ""),
            "dest_port": row.get("Destination_Port", ""),
            "cell_id": row.get("Cell_Global_ID", ""),
            "date": row.get("Session_Date", ""),
            "start_time": row.get("Session_Start_Time", ""),
            "start_ts": start,
            "end_ts": start + dur_s if start is not None else None,
            "duration_sec": dur_s,
            "source_file": os.path.basename(path),
            "source_format": "synthetic_csv",
        })
    return out


def build_synthetic_bundle(data_dir: str, include_clean: bool = False) -> dict:
    """Canonical bundle from the synthetic CSV datasets.

    Defaults to the `anomalous/` files only — they carry the full universe
    (clean records plus injected anomalies), which keeps GT transactions
    resolving to their injected records.
    """
    bundle: dict = {"bank": [], "cdr": [], "ipdr": [], "complaints": [],
                    "subscribers": []}
    if include_clean:
        bundle["bank"] += bank_csv_records(
            os.path.join(data_dir, "clean", "bank_final.csv"))
        bundle["cdr"] += cdr_csv_records(
            os.path.join(data_dir, "clean", "cdr_final.csv"))
        bundle["ipdr"] += ipdr_csv_records(
            os.path.join(data_dir, "clean", "ipdr_final.csv"))
    bundle["bank"] += bank_csv_records(
        os.path.join(data_dir, "anomalous", "bank_anomaly.csv"))
    bundle["cdr"] += cdr_csv_records(
        os.path.join(data_dir, "anomalous", "cdr_anomaly.csv"))
    bundle["ipdr"] += ipdr_csv_records(
        os.path.join(data_dir, "anomalous", "ipdr_anomaly.csv"))
    bundle["entities"] = extract_entities(
        bundle["bank"], bundle["cdr"], bundle["ipdr"],
        bundle.get("subscribers"), bundle.get("complaints"))
    return bundle

def full_validation(data_dir: str, gt_dir: str,
                    risk_thresholds: tuple[int, ...] = (25, 50, 75)) -> dict:
    """One-shot: ingest synthetic data, validate vs ground truth."""
    from ..validate import run
    return run(build_synthetic_bundle(data_dir), gt_dir, risk_thresholds)
