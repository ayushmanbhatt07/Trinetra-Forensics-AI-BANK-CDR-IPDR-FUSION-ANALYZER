"""Parsers for the synthetic problem-statement CSV datasets.

`data/clean/*_final.csv` and `data/anomalous/*_anomaly.csv` are already
canonical v3 exports: the synthetic adapter emits final records, so these
parsers mark the result `canonical` and the pipeline skips re-normalisation.
"""

from __future__ import annotations

from ..adapters.synthetic import bank_csv_records, cdr_csv_records, ipdr_csv_records
from .base import BaseParser, ParseResult
from .registry import register


@register
class SyntheticBankParser(BaseParser):
    format_id = "synthetic_bank"
    dataset = "BANK"
    description = "Synthetic problem-statement bank export (CSV)"

    def parse(self, path: str, context: dict | None = None) -> ParseResult:
        records = bank_csv_records(path)
        return ParseResult(records=records,
                           meta={"canonical": True, "rows": len(records)},
                           format_id=self.format_id, dataset=self.dataset)


@register
class SyntheticCdrParser(BaseParser):
    format_id = "synthetic_cdr"
    dataset = "CDR"
    description = "Synthetic problem-statement CDR export (CSV)"

    def parse(self, path: str, context: dict | None = None) -> ParseResult:
        records = cdr_csv_records(path)
        return ParseResult(records=records,
                           meta={"canonical": True, "rows": len(records)},
                           format_id=self.format_id, dataset=self.dataset)


@register
class SyntheticIpdrParser(BaseParser):
    format_id = "synthetic_ipdr"
    dataset = "IPDR"
    description = "Synthetic problem-statement IPDR export (CSV)"

    def parse(self, path: str, context: dict | None = None) -> ParseResult:
        records = ipdr_csv_records(path)
        return ParseResult(records=records,
                           meta={"canonical": True, "rows": len(records)},
                           format_id=self.format_id, dataset=self.dataset)
