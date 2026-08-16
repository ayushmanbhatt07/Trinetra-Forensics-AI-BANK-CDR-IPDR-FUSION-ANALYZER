"""End-to-end ingestion engine: classify -> parse -> canonical normalise.

Also parses NCRP account-complaint files (account -> police-station ledger)
which seed the risk analysis with known fraud-beneficiary accounts.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout

from . import detect, parsers
from .errors import SkipFileError
from .normalise import (
    extract_entities, normalise_bank, normalise_cdr, normalise_complaints,
    normalise_ipdr, normalise_subscriber,
)
from .util import clean_field, normalise_phone, parse_csv_robust

_OCR_ERROR = "scanned or image-only PDF"
_SKIP_ERRORS = ("scanned or image-only", "password-protected PDF",
                "unreadable PDF", "pdf: skipped", "OCR required")
_FILE_TIMEOUT = 120


def _parse_one(path: str) -> dict:
    cls, res = parse_file(path)
    if res.get("meta", {}).get("kind") == "ncrp_complaints":
        parsed = parsers.parse("ncrp_complaints", path)
        return {"kind": "ncrp", "complaints": parsed.records}
    norm = _normalise_result(cls, res, path)
    return {"kind": "data", "norm": norm, "name": os.path.basename(path)}


def parse_ncrp_complaints(path: str) -> list[dict]:
    """Parse the all_account_complain.csv ledger.

    Each row: acknowledgement no, account no, IFSC, state, district, police
    station, officer name, designation, mobile, email.
    """
    rows = parse_csv_robust(path)
    header = None
    out = []
    for i, r in enumerate(rows):
        if not r:
            continue
        cells = [clean_field(c) for c in r]
        if header is None:
            low = " ".join(c.lower() for c in cells)
            if "account" in low and "ifsc" in low:
                header = cells
                continue
            continue
        if len(cells) < 4:
            continue
        d = dict(zip(header, cells))
        acct = ""
        for k in d:
            if "account" in k.lower() and d[k]:
                acct = d[k]
                break
        ifsc = ""
        for k in d:
            if "ifsc" in k.lower() and d[k]:
                ifsc = d[k].upper()
                break
        if not acct:
            continue
        def get(*keys):
            for k in keys:
                if k in d:
                    return d[k]
            for k, v in d.items():
                if any(s in k.lower() for s in keys):
                    return v
            return ""
        out.append({
            "ack_no": get("Acknowledgement", "ack"),
            "account_no": re.sub(r"\D", "", acct),
            "ifsc": ifsc,
            "state": get("State", "state"),
            "district": get("District", "district"),
            "police_station": get("police Station", "police station", "ps"),
            "officer": get("Name of Complain", "officer", "name"),
            "designation": get("Designation", "designation"),
            "mobile": normalise_phone(get("Mobile", "mobile")),
            "email": get("Email", "email"),
            "source_file": path,
        })
    return out


def parse_file(path: str) -> tuple[dict, dict]:
    """Classify + parse a single file. Returns (cls, parser_result)."""
    cls = detect.classify(path)
    name = os.path.basename(path).lower()
    if "complain" in name or "ncrp" in name:
        return cls, {"records": [], "meta": {"kind": "ncrp_complaints"}}
    fmt = cls["format"]
    if fmt == "bank_pdf" and os.path.splitext(path)[1].lower() != ".pdf":
        fmt = "bank_txt"  # line-layout text detected as pdf-family
    parser = parsers.get_parser(fmt)
    if parser is not None:
        res = parser.parse(path)
        return cls, {"records": res.records, "meta": res.meta}
    # Fallback: never detected but extension is a supported bank layout.
    ext = os.path.splitext(path)[1].lower()
    fmt_by_ext = {".pdf": "bank_pdf", ".txt": "bank_txt", ".csv": "bank_csv",
                  ".xlsx": "bank_xlsx", ".xls": "bank_xls", ".ods": "bank_ods"}
    fallback = fmt_by_ext.get(ext)
    if fallback:
        res = parsers.require_parser(fallback).parse(path)
        cls = {"dataset": "BANK", "format": fallback, "ext": ext}
        return cls, {"records": res.records, "meta": res.meta}
    return cls, {"records": [], "meta": {"kind": "unparsed"}}


def _normalise_result(cls: dict, res: dict, path: str) -> dict | None:
    if res.get("meta", {}).get("canonical"):
        return {"dataset": cls["dataset"], "format": cls["format"],
                "records": res["records"], "meta": res.get("meta", {})}
    dataset = cls["dataset"]
    if dataset == "BANK":
        records = normalise_bank(res["records"], res.get("meta", {}), path)
        return {"dataset": "BANK", "format": cls["format"], "records": records,
                "meta": res.get("meta", {})}
    if dataset == "CDR":
        records = normalise_cdr(res["records"], res.get("meta", {}), path)
        return {"dataset": "CDR", "format": cls["format"], "records": records,
                "meta": res.get("meta", {})}
    if dataset == "IPDR":
        records = normalise_ipdr(res["records"], res.get("meta", {}), path)
        return {"dataset": "IPDR", "format": cls["format"], "records": records,
                "meta": res.get("meta", {})}
    if dataset == "SUBSCRIBER":
        records = normalise_subscriber(res["records"], res.get("meta", {}), path)
        return {"dataset": "SUBSCRIBER", "format": cls["format"],
                "records": records, "meta": res.get("meta", {})}
    return None


def _usable_bank(records: list[dict]) -> tuple[list[dict], int]:
    """Drop bank rows that carry no identity, no timestamp and no amount
    (misaligned column exports / empty template lines).  Legitimate
    opening-balance rows keep their txn id and pass through."""
    kept: list[dict] = []
    dropped = 0
    for r in records:
        amt = float(r.get("debit") or 0.0) + float(r.get("credit") or 0.0)
        if not (r.get("txn_id") or "") and not r.get("ts") and amt <= 0 \
                and not (r.get("account_no") or ""):
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


def ingest_folder(folder: str, patterns: tuple[str, ...] | None = None,
                  max_files: int = 0) -> dict:
    """Ingest every supported file under `folder` (recursive).

    Returns a single bundle: canonical records, NCRP complaints, the entity
    registry and per-file status.
    """
    bank: list[dict] = []
    cdr: list[dict] = []
    ipdr: list[dict] = []
    subscribers: list[dict] = []
    complaints: list[dict] = []
    files_ok: list[str] = []
    files_skipped: list[str] = []
    errors: list[str] = []

    from concurrent.futures import as_completed
    paths_to_parse = []
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in sorted(names):
            if fname.startswith("~$"):
                files_skipped.append(fname)
                continue
            path = os.path.join(root, fname)
            if patterns and not any(p in fname.lower() for p in patterns):
                continue
            if "ground_truth" in fname.lower():
                continue
            if os.path.splitext(path)[1].lower() not in (
                    ".pdf", ".xlsx", ".csv", ".txt"):
                files_skipped.append(fname)
                continue
            paths_to_parse.append((fname, path))

    from . import config
    futures = {}
    workers = config.parser_threads()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fname, path in paths_to_parse:
            futures[ex.submit(_parse_one, path)] = (fname, path)
            
        for future in as_completed(futures):
            fname, path = futures[future]
            try:
                parsed = future.result(timeout=_FILE_TIMEOUT)
            except FTimeout:
                files_skipped.append(f"{fname} (timeout)")
                continue
            except SkipFileError as e:
                files_skipped.append(f"{fname} ({e.reason})")
                continue
            except ValueError as e:
                if any(m in str(e) for m in _SKIP_ERRORS):
                    files_skipped.append(fname)
                else:
                    errors.append(f"{fname}: {str(e)[:200]}")
                continue
            except Exception as e:
                errors.append(f"{fname}: {str(e)[:200]}")
                continue
                
            if parsed["kind"] == "ncrp":
                complaints.extend(parsed["complaints"])
                files_ok.append(fname)
                continue
            norm = parsed["norm"]
            if norm is None:
                files_skipped.append(fname)
                continue
            if norm["dataset"] == "BANK":
                rows, dropped = _usable_bank(norm["records"])
                if dropped:
                    errors.append(f"{fname}: dropped {dropped} unparseable rows")
                bank.extend(rows)
            elif norm["dataset"] == "CDR":
                cdr.extend(norm["records"])
            elif norm["dataset"] == "IPDR":
                ipdr.extend(norm["records"])
            else:
                subscribers.extend(norm["records"])
            files_ok.append(fname)

    entities = extract_entities(bank, cdr, ipdr, subscribers, complaints)
    return {
        "bank": bank, "cdr": cdr, "ipdr": ipdr, "subscribers": subscribers,
        "complaints": complaints, "entities": entities,
        "files": {"ok": files_ok, "skipped": files_skipped, "errors": errors},
    }
