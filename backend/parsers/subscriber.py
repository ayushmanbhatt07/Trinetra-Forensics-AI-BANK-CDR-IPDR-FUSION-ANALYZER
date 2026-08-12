"""Subscriber parsers: Airtel SDR CSV, operator subs-detail PDF, CAF forms."""

from __future__ import annotations

import os
import re

from .. import parsers_cdr as _v2
from ..errors import SkipFileError
from ..util import clean_field, normalise_phone
from .base import BaseParser, ParseResult
from .registry import register

_PHONE_RE = re.compile(r"\b(\d{10})\b")
_CAF_RE = re.compile(r"caf\s*no[.:\s]*([A-Za-z0-9/-]+)", re.IGNORECASE)
_SUBS_DETAIL_RE = re.compile(r"mobile\s+number\s*[:.-]?\s*(\d{10})", re.IGNORECASE)
_SUBS_NAME_RE = re.compile(r"custname\s*([A-Za-z .'-]+)", re.IGNORECASE)
_ADDR_RE = re.compile(r"address\s*([A-Za-z0-9 ,#/.'-]{6,})", re.IGNORECASE)
_ACTIVATION_RE = re.compile(r"activation_date\s*(\d{1,2}-[A-Za-z]{3}-\d{2,4})",
                            re.IGNORECASE)


class _SubBase(BaseParser):
    dataset = "SUBSCRIBER"

    @staticmethod
    def _mk(msisdn: str, name: str = "", address: str = "", caf_no: str = "",
            operator: str = "", activation_date: str = "", path: str = "",
            source_format: str = "") -> dict:
        return {
            "msisdn": normalise_phone(msisdn) or msisdn,
            "name": name, "address": address, "caf_no": caf_no,
            "operator": operator, "activation_date": activation_date,
            "activation_status": "", "imei": "", "imsi": "",
            "subscriber_type": "", "source_file": path,
            "source_format": source_format,
        }


@register
class AirtelSDRParser(_SubBase):
    format_id = "airtel_sdr"
    description = "Airtel subscriber detail (SDR CSV)"

    def parse(self, path, context=None):
        try:
            res = _v2.parse_airtel_sdr(path)
        except ValueError as e:
            raise SkipFileError("parse_error", str(e)[:160]) from e
        recs = list(res["records"])
        m = res.get("meta", {})
        if not recs and m.get("query_value"):
            recs.append(self._mk(
                msisdn=m["query_value"],
                name=m.get("subscriber_name", ""),
                address=m.get("subscriber_address", ""),
                operator="Airtel",
                activation_date=m.get("raw_meta", "").split("activation date=")[-1]
                               .split(";")[0].strip()
                               if "activation date=" in m.get("raw_meta", "") else "",
                path=path, source_format="airtel_sdr"))
        return ParseResult(recs, res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class SubsDetailParser(_SubBase):
    format_id = "subs_detail"
    description = "Operator subscriber-detail report (PDF)"

    def parse(self, path, context=None):
        import pdfplumber
        try:
            with pdfplumber.open(path) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception as e:
            raise SkipFileError("unreadable_pdf", str(e)[:120]) from e
        if not text.strip():
            raise SkipFileError("scanned_or_image_pdf",
                                "subscriber detail PDF has no text layer")
        m = _SUBS_DETAIL_RE.search(text) or _PHONE_RE.search(
            os.path.basename(path))
        msisdn = m.group(1) if m else ""
        rec = self._mk(
            msisdn=msisdn,
            name=(m.group(1).strip() if (m := _SUBS_NAME_RE.search(text)) else ""),
            address=(m.group(1).strip() if (m := _ADDR_RE.search(text)) else ""),
            operator="", path=path, source_format="subs_detail")
        if m := _ACTIVATION_RE.search(text):
            rec["activation_date"] = m.group(1)
        return ParseResult([rec], {"row_count": 1, "layout": "subs_detail"},
                           self.format_id, self.dataset)


@register
class CAFParser(_SubBase):
    format_id = "caf_form"
    description = "Customer Application Form (PDF)"

    def parse(self, path, context=None):
        import pdfplumber
        try:
            with pdfplumber.open(path) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception as e:
            raise SkipFileError("unreadable_pdf", str(e)[:120]) from e
        if not text.strip():
            raise SkipFileError("scanned_or_image_pdf",
                                "CAF PDF has no text layer")
        caf_no = ""
        if m := _CAF_RE.search(text):
            caf_no = m.group(1).strip()
        m = _PHONE_RE.search(os.path.basename(path)) or _PHONE_RE.search(text)
        msisdn = m.group(1) if m else ""
        rec = self._mk(msisdn=msisdn, caf_no=caf_no, operator="", path=path,
                       source_format="caf_form")
        return ParseResult([rec], {"row_count": 1, "layout": "caf_form"},
                           self.format_id, self.dataset)
