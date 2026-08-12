"""Canonical normalisation and entity extraction.

Turns parser output (family-specific dicts) into the canonical BANK / CDR /
IPDR record shapes from `schema.py`, extracts recoverable entities from bank
narrations (UPI ids, phones, counterparty names, banks, references) and builds
a fused entity registry so later steps can correlate bank money with telecom
activity.
"""

from __future__ import annotations

import re
from collections import Counter
import logging

logger = logging.getLogger(__name__)

from .schema import (
    BANK_COLUMNS, CDR_COLUMNS, COMPLAINT_COLUMNS, IPDR_COLUMNS,
    SUBSCRIBER_COLUMNS,
)
from .util import (
    iso_to_epoch, normalise_imei, normalise_imsi, normalise_ip,
    normalise_phone, to_epoch,
)

_BANK_NAMES = {
    "axis bank", "hdfc bank", "icici bank", "kotak mahindra", "kotak bank",
    "yes bank", "bandhan bank", "federal bank", "punjab national bank",
    "pnb", "union bank", "uco bank", "bank of baroda", "state bank of india",
    "sbi", "canara bank", "central bank of india", "indian bank",
    "bank of india", "idbi", "idbi bank", "utkarsh", "city union",
    "rbl bank", "au bank", "bank of maharashtra", "baroda", "indusind",
    "dbs bank", "idfc first", "equitas", "sbm bank",
}

_UPI_RE = re.compile(r"upi[/\\]p2[am][/\\]([^/\\]+)[/\\]([^/\\]+)[/\\]([^/\\]+)", re.I)
_UPI_REF_RE = re.compile(r"upi[/\\]p2[am][/\\]([^/\\]+)", re.I)
_VPA_RE = re.compile(r"[\w.\-]+@[\w.\-]+")
_PHONE10_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)")
_RRN_RE = re.compile(r"rrn:?\s*(\d{10,14})", re.I)
_UTRN_RE = re.compile(r"utr:?\s*([A-Za-z0-9]{12,22})", re.I)
_NEFT_ACCT_RE = re.compile(r"neft[/\\]?\s*([A-Za-z0-9*Xx]{9,18})", re.I)
_IMPS_ACCT_RE = re.compile(r"imps[/\\]?\s*([A-Za-z0-9*Xx]{9,18})", re.I)


def _detect_mode(narration: str) -> str:
    low = narration.lower()
    if "upi" in low:
        return "UPI"
    if "imps" in low:
        return "IMPS"
    if "neft" in low:
        return "NEFT"
    if "rtgs" in low:
        return "RTGS"
    if "nach" in low:
        return "NACH"
    if "ecs" in low:
        return "ECS"
    if "atmcash" in low or " at atm" in low or low.startswith("atm"):
        return "ATM"
    if "pos" in low or "swipe" in low:
        return "POS"
    if "cheque" in low or "chq" in low:
        return "CHEQUE"
    if "cash" in low:
        return "CASH"
    if "mbb" in low or "mobile banking" in low:
        return "MBB"
    return ""


def _find_counterparty_bank(narration: str) -> str:
    low = narration.lower()
    for name in _BANK_NAMES:
        if name in low:
            if name == "pnb":
                return "Punjab National Bank"
            if name == "sbi":
                return "State Bank of India"
            if name == "baroda":
                return "Bank of Baroda"
            return name.title()
    return ""


def _extract_upi(narration: str) -> tuple[str, str, str, str]:
    """Return (upi_id, upi_ref, name, phone) recoverable from a narration."""
    m = _UPI_RE.search(narration)
    if not m:
        m = _UPI_REF_RE.search(narration)
    ref, name, vpa = "", "", ""
    if m:
        parts = m.groups()
        if len(parts) >= 1:
            ref = parts[0]
        if len(parts) >= 2:
            name = parts[1]
        if len(parts) >= 3:
            vpa = parts[2]
        if len(parts) == 1:
            vpa = ""
    if not vpa:
        for v in _VPA_RE.finditer(narration):
            candidate = v.group(0).lower()
            if "@" in candidate and not re.match(r"^[\w.]+@(\d+|\w+)$", candidate) is False:
                if candidate.split("@")[0].isdigit():
                    continue
                vpa = candidate
                break
    phone = ""
    pm = _PHONE10_RE.search(narration)
    if pm:
        phone = "91" + pm.group(1)
    return vpa, ref, name, phone


def normalise_bank(records: list[dict], meta: dict, path: str) -> list[dict]:
    out = []
    bank = meta.get("bank") or ""
    account_no = meta.get("account_no") or ""
    for r in records:
        n = {k: "" for k in BANK_COLUMNS}
        n["txn_id"] = r.get("txn_id") or ""
        n["bank"] = bank or r.get("bank") or ""
        n["account_no"] = account_no or r.get("account_no") or ""
        n["account_name"] = meta.get("account_name") or ""
        n["ifsc"] = meta.get("ifsc") or ""
        n["branch"] = meta.get("branch") or ""
        n["date"] = r.get("date") or ""
        n["time"] = r.get("time") or ""
        n["value_date"] = r.get("value_date") or ""
        n["mode"] = r.get("mode") or ""
        n["narration"] = r.get("narration") or ""
        n["debit"] = r.get("debit")
        n["credit"] = r.get("credit")
        n["balance"] = r.get("balance")
        debit = r.get("debit") or 0.0
        credit = r.get("credit") or 0.0
        n["txn_type"] = "D" if debit > 0 else ("C" if credit > 0 else "")
        n["chq_ref_no"] = r.get("chq_ref_no") or r.get("ref") or ""
        n["source_file"] = path
        n["source_format"] = r.get("source_format") or ""
        if not n["mode"]:
            n["mode"] = _detect_mode(n["narration"])
        upi_id, upi_ref, cp_name, cp_phone = _extract_upi(n["narration"])
        n["upi_id"] = upi_id
        n["upi_ref"] = upi_ref or _find_ref(n["narration"])
        if not n["chq_ref_no"] and n["upi_ref"]:
            n["chq_ref_no"] = n["upi_ref"]
        n["counterparty_name"] = cp_name
        n["counterparty_bank"] = _find_counterparty_bank(n["narration"])
        if cp_phone:
            if n["txn_type"] == "D":
                n["receiver_phone"] = cp_phone
            else:
                n["sender_phone"] = cp_phone
        acct = _find_account_in_narration(n["narration"])
        if acct:
            n["receiver_account"] = acct
        n["ts"] = to_epoch(n["date"], n["time"])
        out.append(n)
        
    # Phase 1: Universal Semantic Narration Enrichment
    try:
        from .semantic_parser import enrich_bank_transactions
        out = enrich_bank_transactions(out)
    except Exception as e:
        logger.error(f"Semantic enrichment failed: {e}")
        
    # Phase 2: Feature Engineering & Behavioural Profiling
    try:
        from .feature_engineering import generate_features
        out = generate_features(out)
    except Exception as e:
        logger.error(f"Feature engineering failed: {e}")
        
    return out


def _find_ref(narration: str) -> str:
    m = _RRN_RE.search(narration) or _UTRN_RE.search(narration)
    return m.group(1) if m else ""


def _find_account_in_narration(narration: str) -> str:
    for rx in (_NEFT_ACCT_RE, _IMPS_ACCT_RE):
        m = rx.search(narration)
        if m:
            return m.group(1)
    return ""


def normalise_cdr(records: list[dict], meta: dict, path: str) -> list[dict]:
    out = []
    for i, r in enumerate(records):
        n = {k: "" for k in CDR_COLUMNS}
        n["cdr_id"] = r.get("cdr_id") or f"cdr_{i:08d}"
        n["operator"] = meta.get("operator") or r.get("operator") or ""
        n["query_type"] = meta.get("query_type") or ""
        n["query_value"] = meta.get("query_value") or ""
        n["a_number"] = normalise_phone(r.get("a_number"))
        n["b_number"] = normalise_phone(r.get("b_number"))
        n["call_type"] = r.get("call_type") or ""
        n["service_type"] = r.get("service_type") or ""
        n["date"] = r.get("date") or ""
        n["time"] = r.get("time") or ""
        n["duration_sec"] = r.get("duration_sec") or 0
        n["imei"] = normalise_imei(r.get("imei"))
        n["imsi"] = normalise_imsi(r.get("imsi"))
        n["cell_id_first"] = r.get("cell_id_first") or ""
        n["cell_id_last"] = r.get("cell_id_last") or ""
        n["bts_location_first"] = r.get("bts_location_first") or ""
        n["bts_location_last"] = r.get("bts_location_last") or ""
        n["roaming_circle"] = r.get("roaming_circle") or ""
        n["msc_id"] = r.get("msc_id") or ""
        n["lrn_b_party"] = r.get("lrn_b_party") or ""
        n["lrn_translation"] = r.get("lrn_translation") or ""
        n["lat_first"] = r.get("lat_first") or ""
        n["lon_first"] = r.get("lon_first") or ""
        n["lat_last"] = r.get("lat_last") or ""
        n["lon_last"] = r.get("lon_last") or ""
        n["source_file"] = path
        n["source_format"] = r.get("source_format") or ""
        n["ts"] = r.get("ts") or to_epoch(n["date"], n["time"])
        out.append(n)
    return out


def normalise_subscriber(records: list[dict], meta: dict, path: str) -> list[dict]:
    out = []
    for i, r in enumerate(records):
        n = {k: "" for k in SUBSCRIBER_COLUMNS}
        n["sub_id"] = r.get("sub_id") or f"sub_{i:08d}"
        n["operator"] = meta.get("operator") or r.get("operator") or ""
        n["msisdn"] = normalise_phone(r.get("msisdn"))
        n["imsi"] = normalise_imsi(r.get("imsi"))
        n["imei"] = normalise_imei(r.get("imei"))
        n["subscriber_name"] = r.get("name") or r.get("subscriber_name") or ""
        n["father_name"] = r.get("father_name") or ""
        n["date_of_birth"] = r.get("date_of_birth") or ""
        n["gender"] = r.get("gender") or ""
        n["id_type"] = r.get("id_type") or ""
        n["id_number"] = r.get("id_number") or ""
        n["address"] = r.get("address") or ""
        n["circle"] = meta.get("circle") or r.get("circle") or ""
        n["connection_type"] = meta.get("connection_type") or r.get("connection_type") or ""
        n["sim_type"] = r.get("sim_type") or ""
        n["alternate_number"] = r.get("alternate_number") or ""
        n["activation_date"] = r.get("activation_date") or ""
        n["email"] = r.get("email") or ""
        n["query_type"] = meta.get("query_type") or ""
        n["query_value"] = meta.get("query_value") or ""
        n["source_file"] = path
        n["source_format"] = r.get("source_format") or ""
        out.append(n)
    return out


def normalise_complaints(records: list[dict], meta: dict, path: str) -> list[dict]:
    out = []
    for i, r in enumerate(records):
        n = {k: "" for k in COMPLAINT_COLUMNS}
        n["complaint_id"] = r.get("complaint_id") or f"cmp_{i:08d}"
        n["ack_no"] = r.get("ack_no") or ""
        n["account_no"] = re.sub(r"\D", "", r.get("account_no") or "")
        n["ifsc"] = (r.get("ifsc") or "").upper()
        n["bank_name"] = r.get("bank_name") or ""
        n["state"] = r.get("state") or ""
        n["district"] = r.get("district") or ""
        n["police_station"] = r.get("police_station") or ""
        n["officer_name"] = r.get("officer") or ""
        n["designation"] = r.get("designation") or ""
        n["mobile"] = normalise_phone(r.get("mobile"))
        n["email"] = r.get("email") or ""
        n["source_file"] = path
        out.append(n)
    return out


def normalise_ipdr(records: list[dict], meta: dict, path: str) -> list[dict]:
    out = []
    for i, r in enumerate(records):
        n = {k: "" for k in IPDR_COLUMNS}
        n["ipdr_id"] = r.get("ipdr_id") or f"ipdr_{i:08d}"
        n["operator"] = meta.get("operator") or r.get("operator") or ""
        n["msisdn"] = normalise_phone(r.get("msisdn"))
        n["imsi"] = normalise_imsi(r.get("imsi"))
        n["imei"] = normalise_imei(r.get("imei"))
        n["user_id"] = r.get("user_id") or ""
        n["mac"] = r.get("mac") or ""
        n["source_ip"] = normalise_ip(r.get("source_ip"))
        n["public_ip"] = normalise_ip(r.get("public_ip"))
        n["dest_ip"] = normalise_ip(r.get("dest_ip"))
        n["dest_port"] = r.get("dest_port") or ""
        n["apn"] = r.get("apn") or ""
        n["cell_id"] = r.get("cell_id") or ""
        n["date"] = r.get("date") or ""
        n["start_time"] = r.get("start_time") or ""
        n["end_time"] = r.get("end_time") or ""
        n["start_ts"] = r.get("start_ts") or to_epoch(n["date"], n["start_time"])
        n["end_ts"] = r.get("end_ts") or to_epoch(n["date"], n["end_time"])
        n["duration_sec"] = r.get("duration_sec") or 0
        n["volume_up"] = r.get("volume_up") or 0
        n["volume_down"] = r.get("volume_down") or 0
        n["roaming_circle"] = r.get("roaming_circle") or ""
        n["is_static"] = r.get("is_static") or ""
        n["source_file"] = path
        n["source_format"] = r.get("source_format") or ""
        out.append(n)
    return out


# ---------------------------------------------------------------------------
# Entity registry
# ---------------------------------------------------------------------------
def extract_entities(bank: list[dict], cdr: list[dict], ipdr: list[dict],
                     subscribers: list[dict] | None = None,
                     complaints: list[dict] | None = None) -> dict:
    subscribers = subscribers or []
    complaints = complaints or []
    phones: dict[str, dict] = {}
    accounts: dict[str, dict] = {}
    upi_ids: dict[str, int] = Counter()
    imeis: dict[str, dict] = {}
    imsis: dict[str, dict] = {}
    ips: dict[str, int] = Counter()
    names: dict[str, dict] = {}

    def bump_phone(p, role, src, ref=""):
        if not p:
            return
        e = phones.setdefault(p, {"count": 0, "roles": Counter(), "sources": set(), "records": []})
        e["count"] += 1
        e["roles"][role] += 1
        e["sources"].add(src)
        if ref:
            e["records"].append(ref)

    for r in bank:
        acc = r.get("account_no") or ""
        if acc:
            a = accounts.setdefault(acc, {"bank": r.get("bank"), "count": 0, "txns": []})
            a["count"] += 1
            a["txns"].append(r.get("txn_id"))
        for p, role in ((r.get("sender_phone"), "bank_sender"),
                        (r.get("receiver_phone"), "bank_receiver")):
            bump_phone(p, role, "bank", r.get("txn_id"))
        if r.get("upi_id"):
            upi_ids[r["upi_id"]] += 1
        nm = (r.get("counterparty_name") or "").strip()
        if nm and len(nm) < 60:
            e = names.setdefault(nm.lower(), {"name": nm, "count": 0})
            e["count"] += 1
        acct = r.get("receiver_account")
    for r in cdr:
        a, b = r.get("a_number"), r.get("b_number")
        bump_phone(a, "cdr_a", "cdr", r.get("cdr_id"))
        bump_phone(b, "cdr_b", "cdr", r.get("cdr_id"))
        imei, imsi = r.get("imei"), r.get("imsi")
        if imei and imei not in _JUNK_IDS:
            e = imeis.setdefault(imei, {"count": 0, "phones": set(), "records": []})
            e["count"] += 1
            if a:
                e["phones"].add(a)
            e["records"].append(r.get("cdr_id"))
        if imsi and imsi not in _JUNK_IDS:
            e = imsis.setdefault(imsi, {"count": 0, "phones": set()})
            e["count"] += 1
            if a:
                e["phones"].add(a)
    for r in ipdr:
        msisdn = r.get("msisdn")
        bump_phone(msisdn, "ipdr", "ipdr", r.get("ipdr_id"))
        ip = r.get("source_ip") or r.get("public_ip")
        if ip:
            ips[ip] += 1
    for r in subscribers:
        msisdn = r.get("msisdn")
        bump_phone(msisdn, "subscriber", "subscriber", r.get("sub_id"))
        if r.get("subscriber_name"):
            nm = r["subscriber_name"].strip()
            if len(nm) < 60:
                e = names.setdefault(nm.lower(), {"name": nm, "count": 0})
                e["count"] += 1
        imei, imsi = r.get("imei"), r.get("imsi")
        if imei and imei not in _JUNK_IDS:
            e = imeis.setdefault(imei, {"count": 0, "phones": set(), "records": []})
            e["count"] += 1
            if msisdn:
                e["phones"].add(msisdn)
        if imsi and imsi not in _JUNK_IDS:
            e = imsis.setdefault(imsi, {"count": 0, "phones": set()})
            e["count"] += 1
            if msisdn:
                e["phones"].add(msisdn)
    for r in complaints:
        acct = r.get("account_no") or ""
        if acct:
            a = accounts.setdefault(acct, {"bank": "", "count": 0, "txns": []})
            a.setdefault("complaints", []).append(
                r.get("ack_no") or r.get("complaint_id"))
        mob = r.get("mobile")
        bump_phone(mob, "complaint_mobile", "complaint", r.get("complaint_id"))
        if r.get("police_station"):
            nm = r["police_station"].strip()
            if len(nm) < 60:
                e = names.setdefault(nm.lower(), {"name": nm, "count": 0})
                e["count"] += 1

    return {
        "phones": dict(phones),
        "accounts": dict(accounts),
        "upi_ids": dict(upi_ids),
        "imeis": dict(imeis),
        "imsis": dict(imsis),
        "ips": dict(ips),
        "names": dict(names),
    }


_JUNK_IDS = {"", "-", "0"}

_MODE_ORDER = ("UPI", "IMPS", "NEFT", "RTGS", "ATM", "POS", "CHEQUE", "CASH",
               "MBB", "NACH", "ECS")


def bank_mode_stats(bank: list[dict]) -> dict:
    c = Counter(r["mode"] or "OTHER" for r in bank)
    return {m: c[m] for m in _MODE_ORDER if c[m]} | {"OTHER": c["OTHER"]}
