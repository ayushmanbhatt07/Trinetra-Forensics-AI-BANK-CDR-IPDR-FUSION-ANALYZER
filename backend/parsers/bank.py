"""Bank statement parsers (plugin classes over the proven v2 engines).

v3 addition: .xls / .ods spreadsheets route through a shared tabular
reader so every tabular statement layout is handled by one code path.
"""

from __future__ import annotations

from .. import parsers_bank as _v2
from ..errors import SkipFileError
from ..util import parse_amount, parse_date, parse_time, clean_field
from .base import BaseParser, ParseResult
from .common.spreadsheet import iter_spreadsheet_rows
from .registry import register

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d/%b/%Y")


class _BankBase(BaseParser):
    dataset = "BANK"


@register
class BankPDFParser(_BankBase):
    format_id = "bank_pdf"
    description = "Bank statement PDF (line layout)"

    def parse(self, path, context=None):
        try:
            res = _v2.parse_bank_pdf(path)
        except ValueError as e:
            raise SkipFileError("scanned_or_image_pdf", str(e)) from e
        return ParseResult(res["records"], res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class BankTXTParser(_BankBase):
    format_id = "bank_txt"
    description = "Bank statement TXT (line layout)"

    def parse(self, path, context=None):
        res = _v2.parse_bank_txt(path)
        return ParseResult(res["records"], res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class BankCSVParser(_BankBase):
    format_id = "bank_csv"
    description = "Bank statement CSV (tabular)"

    def parse(self, path, context=None):
        res = _v2.parse_bank_csv(path)
        return ParseResult(res["records"], res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class BankXLSXParser(_BankBase):
    format_id = "bank_xlsx"
    description = "Bank statement XLSX (tabular)"

    def parse(self, path, context=None):
        res = _v2.parse_bank_xlsx(path)
        return ParseResult(res["records"], res.get("meta", {}),
                           self.format_id, self.dataset)


@register
class BankXLSParser(_BankBase):
    format_id = "bank_xls"
    description = "Bank statement XLS (legacy binary)"

    def parse(self, path, context=None):
        return ParseResult(*_tabular_records(path, self.format_id),
                           self.format_id, self.dataset)


@register
class BankODSParser(_BankBase):
    format_id = "bank_ods"
    description = "Bank statement ODS (OpenDocument)"

    def parse(self, path, context=None):
        return ParseResult(*_tabular_records(path, self.format_id),
                           self.format_id, self.dataset)


def _tabular_records(path: str, fmt: str) -> tuple[list[dict], dict]:
    """Generic tabular bank rows for .xls/.ods (mirrors _generic_xlsx_row)."""
    records: list[dict] = []
    meta: dict = {"layout": fmt, "family": fmt, "account_no": "",
                  "account_name": "", "ifsc": "", "bank": ""}
    for headers, row in iter_spreadsheet_rows(path):
        d = {clean_field(h).upper(): clean_field(v)
             for h, v in zip(headers, row) if h is not None}
        if not any(d.values()):
            continue
        date = (parse_date(d.get("DATE") or d.get("TXN_DATE") or d.get("TRAN DATE"),
                           _DATE_FORMATS) or
                parse_date(d.get("VALUE DATE"), _DATE_FORMATS))
        if not date:
            continue
        debit = parse_amount(d.get("DEBIT") or d.get("WITHDRAWALS") or d.get("WITHDRAWAL"))
        credit = parse_amount(d.get("CREDIT") or d.get("DEPOSITS") or d.get("DEPOSIT"))
        if debit is None and credit is None and d.get("TRAN_AMOUNT"):
            amt = parse_amount(d.get("TRAN_AMOUNT"))
            if amt is not None:
                if amt > 0:
                    credit = amt
                else:
                    debit = abs(amt)
        if debit is None and credit is None:
            continue
        if not meta["account_no"] and d.get("ACCOUNT"):
            meta["account_no"] = d["ACCOUNT"]
        records.append({
            "txn_id": "", "bank": "", "account_no": d.get("ACCOUNT", ""),
            "account_name": "", "ifsc": "", "branch": "",
            "date": date, "time": parse_time(d.get("TIME", "")),
            "ts": None, "value_date": "",
            "mode": "", "narration": d.get("NARRATION") or d.get("PARTICULARS")
                         or d.get("DESCRIPTION") or "",
            "debit": debit, "credit": credit,
            "balance": parse_amount(d.get("BALANCE")),
            "txn_type": "D" if (debit or 0) > 0 else "C",
            "chq_ref_no": d.get("INSTRUMENT_NO", "") or d.get("CHEQUE NO", ""),
            "sender_phone": "", "receiver_phone": "", "counterparty_name": "",
            "counterparty_bank": "", "upi_id": "", "upi_ref": "",
            "receiver_account": "", "source_file": path, "source_format": fmt,
        })
    stem = path.rsplit("\\", 1)[-1].rsplit(".", 1)[0][:20]
    for i, r in enumerate(records):
        r["txn_id"] = f"{fmt}_{stem}_{i:06d}"
    meta["row_count"] = len(records)
    return records, meta
