"""CDR parsers for the four real operator formats found in the police dataset.

F1 jio_vvm     Jio ticket exports ("VVM") with 2-column metadata header
F2 vi          Vodafone Idea ALLINDIA / Main CDR report
F3 jio_nodal   Jio nodal-office exports with '=\"...\"' quoting everywhere
F4 airtel      Bharti Airtel PAN India exports (MSISDN or IMEI tickets)
F5 airtel_sdr  Airtel subscriber-detail files (metadata only)

Every parser returns {"records": [canonical CDR dicts], "meta": {...}}.
"""

from __future__ import annotations

import re

from .util import (
    clean_field, normalise_imei, normalise_imsi, normalise_phone, parse_csv_robust,
    parse_date, parse_time, to_epoch, read_raw_text,
)

META_KEYS = ("operator", "query_type", "query_value", "from_date", "to_date",
             "subscriber_name", "subscriber_address", "circle", "connection_type",
             "report_index", "report_date", "total_records", "raw_meta")

_EMPTY = {"-", "--", "", "NA", "N/A", "---", "null", "NULL"}


def _blank(v):
    v = clean_field(v)
    return "" if v in _EMPTY else v


def _canon(row: dict, operator: str, query_type: str, query_value: str,
           source_file: str, source_format: str) -> dict:
    rec = {k: "" for k in (
        "cdr_id", "operator", "query_type", "query_value", "a_number", "b_number",
        "call_type", "service_type", "date", "time", "ts", "duration_sec",
        "imei", "imsi", "cell_id_first", "cell_id_last", "bts_location_first",
        "bts_location_last", "roaming_circle", "msc_id", "lrn_b_party",
        "lrn_translation", "lat_first", "lon_first", "lat_last", "lon_last",
        "source_file", "source_format")}
    rec.update(row)
    rec["operator"] = operator
    rec["query_type"] = query_type
    rec["query_value"] = query_value
    rec["source_file"] = source_file
    rec["source_format"] = source_format
    if rec.get("date") and rec.get("time"):
        rec["ts"] = to_epoch(rec["date"], rec["time"])
    return rec


def _orient(row: dict, target: str) -> None:
    """Orient a row against the queried number: a_number = target side."""
    tgt = normalise_phone(target)
    a, b = normalise_phone(row.get("a_number")), normalise_phone(row.get("b_number"))
    if tgt and a != tgt and b == tgt:
        row["a_number"], row["b_number"] = b, a
        ct = row.get("call_type", "")
        if ct == "IN":
            row["call_type"] = "OUT"
        elif ct == "OUT":
            row["call_type"] = "IN"


# ---------------------------------------------------------------------------
# F1 — Jio VVM
# ---------------------------------------------------------------------------
def parse_jio_vvm(path: str) -> dict:
    rows = parse_csv_robust(path)
    meta = {k: "" for k in META_KEYS}
    meta["operator"] = "Jio"
    header_idx = None
    for i, r in enumerate(rows):
        if r and clean_field(r[0]) == "Calling Party Telephone Number":
            header_idx = i
            break
    if header_idx is None:
        for i, r in enumerate(rows):
            if r and "calling party" in clean_field(r[0]).lower():
                header_idx = i
                break
    if header_idx is None:
        raise ValueError("Jio VVM: table header not found")
    for r in rows[:header_idx]:
        if not r or len(r) < 2:
            continue
        k = clean_field(r[0]).lower().rstrip(" :")
        v = clean_field(r[1])
        if k.startswith("input value"):
            meta["query_type"] = re.sub(r"\(.*", "", v or "").strip() or "MSISDN"
            meta["query_value"] = v
        elif k == "date range":
            m = re.search(r"(\d{4}-\d{2}-\d{2})", v)
            if m:
                meta["from_date"] = m.group(1)
            m = re.search(r"to\s+(\d{4}-\d{2}-\d{2})", v)
            if m:
                meta["to_date"] = m.group(1)
        elif k == "total records":
            meta["total_records"] = v
        elif k.startswith("msisdn/imsi"):
            meta["raw_meta"] += f"IMSI={v} "
        elif k.startswith("subscriber name"):
            meta["subscriber_name"] = v
        elif k.startswith("local address"):
            meta["subscriber_address"] = v
        elif k == "circle":
            meta["circle"] = v
        elif k == "connection type":
            meta["connection_type"] = v
    header = [clean_field(c) for c in rows[header_idx]]
    records = []
    for r in rows[header_idx + 1:]:
        if not r or not any(clean_field(c) for c in r):
            continue
        m = {h: (clean_field(v) if h else "") for h, v in zip(header, r)}
        date = parse_date(m.get("Call Date"))
        if not date:
            continue
        ct = m.get("Call Type", "").lower()
        is_sms = "sms" in ct or ct.startswith("a2p") or ct.startswith("p2p")
        direction = "OUT" if "out" in ct else ("IN" if "in" in ct else "")
        rec = _canon({
            "a_number": m.get("Calling Party Telephone Number"),
            "b_number": m.get("Called Party Telephone Number"),
            "call_type": ("SMS" if is_sms else direction),
            "service_type": "SMS" if is_sms else "Voice",
            "date": date,
            "time": parse_time(m.get("Call Time")),
            "duration_sec": int(float(clean_field(m.get("Call Duration")) or 0) or 0)
                            if clean_field(m.get("Call Duration")) not in _EMPTY else 0,
            "cell_id_first": m.get("First Cell ID"),
            "cell_id_last": m.get("Last Cell ID"),
            "imei": m.get("IMEI"),
            "imsi": m.get("IMSI"),
            "roaming_circle": m.get("Roaming Circle Name"),
            "lrn_b_party": m.get("LRN Called No"),
        }, "Jio", meta["query_type"], meta["query_value"], path, "jio_vvm")
        _orient(rec, meta["query_value"])
        records.append(rec)
    return {"records": records, "meta": meta}


# ---------------------------------------------------------------------------
# F2 — Vi (Vodafone Idea)
# ---------------------------------------------------------------------------
def parse_vi(path: str) -> dict:
    rows = parse_csv_robust(path)
    meta = {k: "" for k in META_KEYS}
    meta["operator"] = "Vi"
    header_idx = None
    for i, r in enumerate(rows):
        if r and clean_field(r[0]).startswith("Target /A PARTY NUMBER"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Vi: table header not found")
    for r in rows[:header_idx]:
        if not r or not r[0]:
            continue
        line = clean_field(r[0])
        low = line.lower()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), clean_field(v).strip().lstrip("-").strip()
        if "msisdn" in k or "imei" in k:
            meta["query_type"] = k.upper()
            meta["query_value"] = v
        elif "report type" in k:
            meta["raw_meta"] += f"ReportType={v} "
        elif "from date" in k:
            meta["from_date"] = v[:10]
        elif "till date" in k or "to date" in k:
            meta["to_date"] = v[:10]
        elif "report index" in k:
            meta["report_index"] = v
    header = [clean_field(c) for c in rows[header_idx]]
    records = []
    for r in rows[header_idx + 1:]:
        if not r or not any(clean_field(c) for c in r):
            continue
        if clean_field(r[0]).startswith("Target /A PARTY") or set(r) <= {"", "-"}:
            continue
        m = {h: clean_field(v) for h, v in zip(header, r)}
        date = parse_date(m.get("Call date"), ("%d-%m-%Y", "%d/%m/%Y"))
        if not date:
            continue
        ct = m.get("CALL_TYPE", "").lower()
        is_sms = "sms" in ct
        direction = "OUT" if "out" in ct else ("IN" if "in" in ct else "")
        rec = _canon({
            "a_number": m.get("Target /A PARTY NUMBER"),
            "b_number": m.get("B PARTY NUMBER"),
            "call_type": ("SMS" if is_sms else direction),
            "service_type": m.get("Service Type") or ("SMS" if is_sms else "Voice"),
            "date": date,
            "time": parse_time(m.get("Call Initiation Time")),
            "duration_sec": int(float(m.get("Call Duration") or 0) or 0),
            "cell_id_first": m.get("First Cell Global Id"),
            "cell_id_last": m.get("Last Cell Global Id"),
            "bts_location_first": m.get("First BTS Location"),
            "bts_location_last": m.get("Last BTS Location"),
            "imei": m.get("IMEI"),
            "imsi": m.get("IMSI"),
            "roaming_circle": m.get("Roaming Network/Circle"),
            "msc_id": m.get("MSC ID"),
            "lrn_b_party": m.get("LRN- B Party Number"),
            "lrn_translation": m.get("Translation of LRN"),
        }, "Vi", meta["query_type"], meta["query_value"], path, "vi")
        _orient(rec, meta["query_value"])
        records.append(rec)
    return {"records": records, "meta": meta}


# ---------------------------------------------------------------------------
# F3 — Jio nodal office
# ---------------------------------------------------------------------------
def parse_jio_nodal(path: str) -> dict:
    rows = parse_csv_robust(path)
    meta = {k: "" for k in META_KEYS}
    meta["operator"] = "Jio"
    header_idx = None
    for i, r in enumerate(rows):
        if r and clean_field(r[0]).lower().startswith("sl_no"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Jio nodal: table header not found")
    for r in rows[:header_idx]:
        if not r or not r[0]:
            continue
        line = clean_field(r[0])
        low = line.lower()
        if low.startswith("search value"):
            meta["query_value"] = line.split(":", 1)[1].strip()
        elif low.startswith("search criteria"):
            meta["query_type"] = line.split(":", 1)[1].strip().upper()
        elif low.startswith("start date"):
            meta["from_date"] = line.split(":", 1)[1].strip()[:10]
        elif low.startswith("end date"):
            meta["to_date"] = line.split(":", 1)[1].strip()[:10]
        elif low.startswith("name:"):
            meta["subscriber_name"] = line.split(",", 1)[0][5:].strip()
    header = [clean_field(c).strip() for c in rows[header_idx]]
    records = []
    for r in rows[header_idx + 1:]:
        if not r or not any(clean_field(c) for c in r):
            continue
        m = {h: clean_field(v) for h, v in zip(header, r)}
        date = parse_date(m.get("Call_Date"), ("%d/%m/%Y", "%d-%m-%Y"))
        if not date:
            continue
        ct = m.get("Call_Type", "").upper()
        is_sms = "SMS" in ct
        direction = "OUT" if "OUT" in ct else ("IN" if "IN" in ct else ct)
        rec = _canon({
            "a_number": m.get("Mobile_No"),
            "b_number": m.get("Other_Party_No"),
            "call_type": ("SMS" if is_sms else direction),
            "service_type": m.get("Service_Type"),
            "date": date,
            "time": parse_time(m.get("Call_Initiation_Time(CIT)") or m.get("Call_Initiation_Time")),
            "duration_sec": int(float(m.get("Call_Duration") or 0) or 0),
            "cell_id_first": m.get("First_Cell_id"),
            "cell_id_last": m.get("Last_Cell_ID"),
            "bts_location_first": m.get("First_Cell_Desc"),
            "bts_location_last": m.get("Last_Cell_Desc"),
            "imei": m.get("IMEI"),
            "imsi": m.get("IMSI"),
            "roaming_circle": m.get("Roaming Circle") or m.get("Roaming_Circle"),
            "msc_id": m.get("MSC_ID"),
            "lrn_b_party": m.get("LRN_B_Party_No"),
            "lrn_translation": m.get("LRN_DESCRIPTION"),
            "lat_first": m.get("First_LAT"),
            "lon_first": m.get("First_Long"),
        }, "Jio", meta["query_type"], meta["query_value"], path, "jio_nodal")
        _orient(rec, meta["query_value"])
        records.append(rec)
    return {"records": records, "meta": meta}


# ---------------------------------------------------------------------------
# F4 — Airtel
# ---------------------------------------------------------------------------
def parse_airtel(path: str) -> dict:
    rows = parse_csv_robust(path)
    meta = {k: "" for k in META_KEYS}
    meta["operator"] = "Airtel"
    header_idx = None
    for i, r in enumerate(rows):
        if r and clean_field(r[0]) == "Target No":
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Airtel: table header not found")
    text = read_raw_text(path, 16 * 1024)
    m = re.search(r"Call Details of (Mobile|IMEI) No '([^']+)'", text)
    if m:
        meta["query_type"] = "MSISDN" if m.group(1) == "Mobile" else "IMEI"
        meta["query_value"] = m.group(2)
    header = [clean_field(c) for c in rows[header_idx]]
    records = []
    for r in rows[header_idx + 1:]:
        if not r or not any(clean_field(c) for c in r):
            continue
        if clean_field(r[0]) in ("Target No",) or clean_field(r[0]).lower() in ("no data found",):
            continue
        m = {h: clean_field(v) for h, v in zip(header, r)}
        date = parse_date(m.get("Date"), ("%d/%m/%Y", "%d-%m-%Y"))
        if not date:
            continue
        ct = m.get("Call Type", "").upper()
        is_sms = ct in ("SMT", "SMO", "DSM", "SMS")
        direction = "OUT" if ct == "OUT" or ct == "SMO" else ("IN" if ct in ("IN", "SMT", "DSM") else "")
        dur = clean_field(m.get("Dur(s)"))
        rec = _canon({
            "a_number": m.get("Target No"),
            "b_number": m.get("B Party No"),
            "call_type": ("SMS" if is_sms else direction),
            "service_type": m.get("Service Type"),
            "date": date,
            "time": parse_time(m.get("Time")),
            "duration_sec": int(float(dur) or 0) if dur not in _EMPTY else 0,
            "cell_id_first": m.get("First CGI"),
            "cell_id_last": m.get("Last CGI"),
            "imei": m.get("IMEI"),
            "imsi": m.get("IMSI"),
            "roaming_circle": m.get("Roam Nw"),
            "msc_id": m.get("SW & MSC ID"),
            "lrn_b_party": m.get("LRN No"),
            "lrn_translation": m.get("LRN TSP-LSA"),
        }, "Airtel", meta["query_type"], meta["query_value"], path, "airtel")
        _orient(rec, meta["query_value"])
        records.append(rec)
    return {"records": records, "meta": meta}


# ---------------------------------------------------------------------------
# F5 — Airtel SDR subscriber detail (metadata only)
# ---------------------------------------------------------------------------
def parse_airtel_sdr(path: str) -> dict:
    rows = parse_csv_robust(path)
    meta = {k: "" for k in META_KEYS}
    meta["operator"] = "Airtel"
    if len(rows) < 2:
        return {"records": [], "meta": meta}
    header = [clean_field(c).lower() for c in rows[0]]
    vals = [clean_field(c) for c in rows[1]]
    d = dict(zip(header, vals))
    meta["query_type"] = "MSISDN"
    meta["query_value"] = d.get("msisdn", "")
    meta["subscriber_name"] = " ".join(
        x for x in (d.get("first name"), d.get("last name")) if x)
    addr = " ".join(
        str(d.get(k, "") or "") for k in (
            "subscriber address1", "subscriber address2", "subscriber address3",
            "subscriber address4"))
    meta["subscriber_address"] = addr.strip()
    meta["circle"] = d.get("circle id", "")
    meta["connection_type"] = d.get("service type", "")
    meta["raw_meta"] = "; ".join(
        f"{k}={v}" for k, v in d.items() if v and k in (
            "father name", "date of birth", "identification type",
            "identification number", "gender", "alternate number",
            "activation date", "sim type", "mobile imsi"))
    return {"records": [], "meta": meta}


PARSERS = {
    "jio_vvm": parse_jio_vvm,
    "vi": parse_vi,
    "jio_nodal": parse_jio_nodal,
    "airtel": parse_airtel,
    "airtel_sdr": parse_airtel_sdr,
}
