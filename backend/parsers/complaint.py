"""NCRP complaint-ledger parser (fraud-beneficiary accounts)."""

from __future__ import annotations

import csv
import io
import os
import re

from ..util import normalise_phone
from .base import BaseParser, ParseResult
from .common.spreadsheet import iter_spreadsheet_rows
from .registry import register

_COMPLAINTS_KEYS = (
    "ack_no", "account_no", "ifsc", "state", "district", "police_station",
    "officer", "designation", "mobile", "email", "source_file",
)


def _rows_from(path: str):
    """Yield header + row tuples from CSV/TXT or spreadsheet content."""
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xls", "ods"):
        for headers, values in iter_spreadsheet_rows(path):
            yield headers, values
        return
    with open(path, "rb") as fh:
        raw = fh.read(4096)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        yield None, row


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s


@register
class NCRPComplaintsParser(BaseParser):
    format_id = "ncrp_complaints"
    dataset = "COMPLAINT"
    description = "NCRP fraud-account complaint ledger"

    def parse(self, path, context=None):
        recs: list[dict] = []
        header: list[str] | None = None
        for _, row in _rows_from(path):
            if not row:
                continue
            cells = [_clean(c) for c in row]
            low = " ".join(c.lower() for c in cells)
            if header is None:
                if "account" in low and ("ifsc" in low or "police" in low):
                    header = cells
                continue
            if len(cells) < 4:
                continue
            d = dict(zip(header, cells))
            acct = ""
            for k in d:
                if "account" in k.lower() and d[k]:
                    acct = d[k]
                    break
            if not acct:
                continue

            def get(*keys: str) -> str:
                for k in keys:
                    if k in d:
                        return d[k]
                for k, v in d.items():
                    if any(s in k.lower() for s in keys):
                        return v
                return ""

            recs.append({
                "ack_no": get("acknowledgement", "ack"),
                "account_no": re.sub(r"\D", "", acct),
                "ifsc": get("ifsc", "ifsc code").upper(),
                "state": get("state", "state"),
                "district": get("district", "district"),
                "police_station": get("police station", "police Station", "ps"),
                "officer": get("name of complain", "officer", "name"),
                "designation": get("designation", "designation"),
                "mobile": normalise_phone(get("mobile", "mobile")),
                "email": get("email", "email"),
                "source_file": path,
            })
        return ParseResult(recs, {"row_count": len(recs), "kind": "ncrp_complaints"},
                           self.format_id, self.dataset)
