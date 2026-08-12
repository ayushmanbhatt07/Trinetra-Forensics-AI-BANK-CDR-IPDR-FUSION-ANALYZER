"""IPDR parser plugins (Jio IPv6, generic xlsx, generic csv)."""

from __future__ import annotations

import re

from .. import parsers_ipdr as _v2
from ..errors import SkipFileError
from ..util import parse_csv_robust, clean_field, to_epoch
from .base import BaseParser, ParseResult
from .registry import register


class _IpdrBase(BaseParser):
    dataset = "IPDR"


@register
class JioIpv6Parser(_IpdrBase):
    format_id = "jio_ipv6"
    description = "Jio IPv6 session export (CSV)"

    def parse(self, path, context=None):
        try:
            res = _v2.parse_jio_ipv6(path)
        except ValueError as e:
            raise SkipFileError("parse_error", str(e)[:160]) from e
        return ParseResult(res["records"], res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class IpdrXLSXParser(_IpdrBase):
    format_id = "ipdr_xlsx"
    description = "Generic IPDR spreadsheet"

    def parse(self, path, context=None):
        res = _v2.parse_ipdr_xlsx(path)
        return ParseResult(res["records"], res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class IpdrCSVParser(_IpdrBase):
    format_id = "ipdr_csv"
    description = "Generic IPDR text export"

    def parse(self, path, context=None):
        return ParseResult(*_generic_csv_records(path),
                           self.format_id, self.dataset)


def _generic_csv_records(path: str) -> tuple[list[dict], dict]:
    rows = parse_csv_robust(path)
    if not rows:
        return [], {"layout": "ipdr_csv", "row_count": 0}
    header = [clean_field(c).lower() for c in rows[0]]
    col = {h: i for i, h in enumerate(header)}
    src_ip = next((col[k] for k in ("source ip", "source ip address", "ip address",
                                    "ip", "public ip") if k in col), None)
    if src_ip is None:
        return [], {"layout": "ipdr_csv", "row_count": 0, "no_header": True}
    dst_ip = next((col[k] for k in ("destination ip", "dest ip") if k in col), None)
    date_c = next((col[k] for k in ("start date", "date", "f date", "start_date")
                   if k in col), None)
    time_c = next((col[k] for k in ("start time", "time", "f time", "start_time",
                                    "time(ist)") if k in col), None)
    recs: list[dict] = []
    for r in rows[1:]:
        if len(r) <= src_ip:
            continue
        src = clean_field(r[src_ip])
        if not src or not re.match(r"[\dA-Fa-f:.]+", src):
            continue
        d = clean_field(r[date_c]) if date_c is not None else ""
        t = clean_field(r[time_c]) if time_c is not None else ""
        recs.append({
            "txn_id": "", "msisdn": "", "source_ip": src,
            "destination_ip": clean_field(r[dst_ip]) if dst_ip is not None else "",
            "start_time": to_epoch(d, t) or 0,
            "end_time": 0, "duration": 0, "source_port": "", "destination_port": "",
            "source_file": path, "source_format": "ipdr_csv",
            "date": d, "time": t,
        })
    stem = path.rsplit("\\", 1)[-1].rsplit(".", 1)[0][:20]
    for i, rec in enumerate(recs):
        rec["txn_id"] = f"ipdr_{stem}_{i:06d}"
    return recs, {"layout": "ipdr_csv", "row_count": len(recs)}
