"""Spreadsheet row iteration for tabular parsers (xlsx, xls, ods).

Returns (headers, row) pairs for every data row after the first non-empty
header row, for the first `MAX_SHEETS` sheets.  Best-effort: raises only
SkipFileError for genuinely unreadable binaries.
"""

from __future__ import annotations

from ...errors import SkipFileError

MAX_SHEETS = 20


def iter_spreadsheet_rows(path: str):
    """Yield (headers, values_row) tuples, headers = first non-empty row."""
    ext = path.rsplit(".", 1)[-1].lower()
    if ext == "xlsx":
        yield from _xlsx_rows(path)
    elif ext == "xls":
        yield from _xls_rows(path)
    elif ext == "ods":
        yield from _ods_rows(path)
    else:
        raise SkipFileError("unsupported_type", f"not a spreadsheet: {path}")


def _xlsx_rows(path):
    import openpyxl
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise SkipFileError("unreadable_xlsx", str(e)[:120]) from e
    try:
        for ws in wb.worksheets[:MAX_SHEETS]:
            headers = None
            for row in ws.iter_rows(values_only=True):
                if headers is None:
                    headers = list(row)
                    if not any(v is not None and str(v).strip() for v in headers):
                        headers = None
                    continue
                yield list(headers), list(row)
    finally:
        wb.close()


def _xls_rows(path):
    import xlrd
    try:
        book = xlrd.open_workbook(path)
    except Exception as e:
        raise SkipFileError("unreadable_xls", str(e)[:120]) from e
    for sh in book.sheets()[:MAX_SHEETS]:
        headers = None
        for r in range(sh.nrows):
            row = sh.row_values(r)
            if headers is None:
                if any(str(v).strip() for v in row):
                    headers = row
                continue
            yield list(headers), row


def _ods_rows(path):
    from odf.opendocument import load as odf_load
    from odf.table import Table, TableRow, TableCell
    from odf.text import P
    try:
        doc = odf_load(path)
    except Exception as e:
        raise SkipFileError("unreadable_ods", str(e)[:120]) from e
    for tbl in doc.spreadsheet.getElementsByType(Table)[:MAX_SHEETS]:
        headers = None
        for r in tbl.getElementsByType(TableRow):
            vals = []
            for c in r.getElementsByType(TableCell):
                txt = "".join(str(n) for n in c.getElementsByType(P))
                txt = txt or (str(c) if c.getAttribute("value") else "")
                vals.append(txt)
            if headers is None:
                if any(str(v).strip() for v in vals):
                    headers = vals
                continue
            yield list(headers), vals
