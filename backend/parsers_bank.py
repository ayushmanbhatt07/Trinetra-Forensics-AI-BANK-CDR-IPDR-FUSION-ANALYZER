"""Bank statement parsers: PDF (line-based), xlsx, txt and csv.

Design: one generic line parser + a per-family layout config. Every layout
seen in the real police dataset reduces to the same row shape:

    [account_no?] [date] [value_date?] narration... amount_tokens...

Amount tokens are the last decimal-pointed tokens on the row (the `0` in a
cheque-number column has no decimal and is ignored):

    3 amounts -> [debit, credit, balance]
    2 amounts -> [amount, balance]  (direction from balance delta or Cr/Dr suffix)
    1 amount  -> [balance]          (direction from balance delta or suffix)

Known quirks handled here:
    Bandhan / associate-bank dates split across two lines (20-APR- / 2024)
    HDFC truncated years (02/01/20) resolved against the statement period
    balance suffixes: 2,000.00Cr | 50,000.00CR | 150,000.00(Cr) | 1.00Cr
    PNB/UCO two-line table headers and REP31 control blocks
    RBL rows that start with the account number
    central-bank xlsx compact dates (3052021 = 03-05-2021) and signed amounts
"""

from __future__ import annotations

import os
import re

from .util import (
    clean_field, parse_amount, parse_date, parse_time, read_raw_text,
)

# amount token: decimal point required OR comma-grouped integer (20,000);
# optional Cr/Dr/(Cr) suffix. Ref/cheque numbers are never comma-grouped.
AMOUNT_RE = re.compile(
    r"^(?:\d{1,3}(?:,\d{3})+(?:\.\d{2,3})?|(?:[\d,]{1,12}\.\d{2,3}|\.\d{2,3}))"
    r"(?:\(?[CcDd][Rr]\)?)?$")
PARTIAL_DATE_RE = re.compile(r"(\d{2}-[A-Za-z]{3}-$|\d{1,2}/\d{1,2}/\d{1,2}$)")
SKIP_LINE_RE = re.compile(
    r"^(page\s*\d+|disclaimer|this is system|registered office|grand total|"
    r"opening balance|closing balance|b/f|brought forward|balance forward|"
    r"swipe limit|available balance|elapsed|[-_=]{4,})", re.IGNORECASE)
DENSIFY_RE = re.compile(r"\(cid:\d+\)")


def _sanitize(text: str) -> str:
    return DENSIFY_RE.sub("", text)


def _is_amount(tok: str) -> bool:
    return bool(AMOUNT_RE.match(tok))


def extract_pdf_lines(path: str) -> list[str]:
    import pdfplumber
    lines: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                lines.extend(_sanitize(txt).splitlines())
    except ValueError as e:
        if "password" in str(e).lower():
            raise ValueError("password-protected PDF: skipped") from e
        raise
    except Exception as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            raise ValueError("password-protected PDF: skipped") from e
        raise ValueError(f"unreadable PDF: {str(e)[:80]}") from e
    return lines


def _join_split_dates(lines: list[str]) -> list[str]:
    """Join date fragments split across physical lines.

    Bandhan: '20-APR-' + '2024' (year on the *next* line, two columns);
    associate bank: '31/08/20' + '24'.
    """
    out: list[str] = []
    for ln in lines:
        stripped = ln.rstrip()
        if out and PARTIAL_DATE_RE.search(out[-1]) and stripped[:2].isdigit():
            out[-1] = out[-1].rstrip() + " " + stripped.strip()
            continue
        out.append(ln)
    return out


def _splice_bandhan_years(lines: list[str]) -> list[str]:
    """Bandhan prints dates as '22-APR- 20-APR-' with the years on the next
    line ('2024 2024'). Splice the years into the date tokens."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        toks = ln.split()
        if (toks and re.fullmatch(r"\d{2}-[A-Za-z]{3}-", toks[0])
                and i + 1 < len(lines)):
            nxt = lines[i + 1].split()
            years = [t for t in nxt[:2] if re.fullmatch(r"\d{4}", t)]
            if len(years) == 2:
                rest = " ".join(toks[2:]) if len(toks) > 2 else ""
                tail = " ".join(nxt[2:]) if len(nxt) > 2 else ""
                new = f"{toks[0]}{years[0]} {toks[1]}{years[1]}"
                if rest:
                    new += " " + rest
                if tail:
                    new += " " + tail
                out.append(new)
                i += 2
                continue
        out.append(ln)
        i += 1
    return out


# ---------------------------------------------------------------------------
# Layout registry
# ---------------------------------------------------------------------------
FAMILY_LAYOUTS: dict = {
    # family: (header hints that must all appear within a 3-line window, kind)
    "axis8":   (["transaction particulars", "dr/cr"], "amt_bal"),
    "axis7":   (["tran date", "particulars", "debit", "credit"], "amt_bal"),
    "federal": (["withdrawals", "deposits", "dr/cr"], "gen"),
    "hdfc":    (["narration", "withdrawalamt"], "gen"),
    "kotak":   (["narration", "withdrawal (dr)"], "gen"),
    "bandhan": (["trans value", "description", "debits"], "gen"),
    "pnb":     (["gl.", "debit amount", "credit amount"], "gen"),
    "union":   (["particulars", "withdrawals", "deposits", "balance"], "gen"),
    "icici":   (["transaction details", "cheque no", "debit"], "gen"),
    "utkarsh": (["value date", "transaction", "debit", "credit"], "gen"),
    "yes":     (["description", "reference", "debits", "credits"], "gen"),
    "associate": (["narra", "chequeno", "debit", "credit", "balance"], "gen"),
    "cityunion": (["particulars", "chq no", "debit", "credit", "balance"], "gen"),
    "rbl":     (["tran particular", "debit amount", "credit amount"], "gen"),
    "generic": (["balance"], "gen"),
}

FAMILY_ORDER = ("axis8", "axis7", "federal", "hdfc", "kotak", "bandhan", "pnb",
                "union", "icici", "utkarsh", "yes", "rbl", "cityunion",
                "associate", "generic")

BANK_NAMES = {
    "axis8": "Axis Bank", "axis7": "Axis Bank", "federal": "Federal Bank",
    "hdfc": "HDFC Bank", "kotak": "Kotak Mahindra Bank",
    "bandhan": "Bandhan Bank", "pnb": "Punjab National Bank",
    "union": "Union Bank of India", "utkarsh": "Utkarsh Small Finance Bank",
    "yes": "Yes Bank", "associate": "Associate Co-operative Bank",
    "cityunion": "City Union Bank", "rbl": "RBL Bank",
    "icici": "ICICI Bank", "generic": "",
}

IFSC_OVERRIDES = {
    "UTIB": "axis8", "BDBL": "bandhan", "FDRL": "federal", "HDFC": "hdfc",
    "ICIC": "icici", "KKBK": "kotak", "PUNB": "pnb", "UBIN": "union",
    "UTKS": "utkarsh", "YESB": "yes", "UCBA": "pnb", "CIUB": "cityunion",
    "GSCB": "associate", "RATN": "rbl",
}
TEXT_OVERRIDES: list[tuple[str, str]] = []

DATE_FORMATS_DEFAULT = ("%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d-%b-%y",
                        "%d/%b/%Y", "%d/%b/%y", "%d-%B-%Y", "%d/%m/%y",
                        "%d-%m-%y", "%Y-%m-%d")
DATE_FORMATS_HDFC = ("%d/%m/%y", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y")
DATE_FORMATS_BANDHAN = ("%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%d-%m-%Y")


def detect_family(lines: list[str], ifsc: str = "") -> str:
    if ifsc and ifsc[:4].upper() in IFSC_OVERRIDES:
        return IFSC_OVERRIDES[ifsc[:4].upper()]
    for fam in FAMILY_ORDER:
        if fam == "generic":
            continue
        if _match_hints_window(lines, FAMILY_LAYOUTS[fam][0]) >= 0:
            return fam
    return "generic"


def _match_hints_window(lines: list[str], hints: list[str], window: int = 3) -> int:
    low = [ln.lower() for ln in lines]
    for i in range(len(low)):
        text = " ".join(low[i:i + window])
        if all(h in text for h in hints):
            return i
    return -1


def _find_header(lines: list[str], family: str) -> int:
    hints, _ = FAMILY_LAYOUTS.get(family, FAMILY_LAYOUTS["generic"])
    return _match_hints_window(lines, hints)


# ---------------------------------------------------------------------------
# Header metadata (account no, IFSC, holder name, period)
# ---------------------------------------------------------------------------
ACCOUNT_RE = {
    "axis8": r"account\s*(?:no)?\s*[:.]?\s*(\d{10,})",
    "axis7": r"account\s*(?:no)?\s*[:.]?\s*(\d{10,})",
    "bandhan": r"account\s*no:?\s*(\d{10,})",
    "federal": r"account\s*number\s*:?\s*(\d{10,})",
    "hdfc": r"accountno\s*:?\s*(\d{10,})",
    "kotak": r"account\s*no\s*:?\s*(\d{10,})",
    "pnb": r"(?:acct\s*range\s*:?\s*(\d{6,})\s*to|account\s*no\s*:?\s*(\d{6,}))",
    "union": r"a/c\s*no:?\s*(\d{10,})",
    "utkarsh": r"(?:account\s*number|account\s*no\.?)[\d\s]{0,30}?(\d{12,})",
    "yes": r"a/c\s*number:?\s*(\d{10,})",
    "associate": r"a/c\s*no:?\s*(\d{10,})",
    "cityunion": r"account\s*no\s*:?\s*(\d{10,})",
    "rbl": r"account\s*no:?\s*(\d{9,})",
    "icici": r"account\s*no\s*:?\s*(\d{10,})",
    "generic": r"account\s*(?:no|number)?\s*:?\s*(\d{10,})",
}
IFSC_RE = re.compile(r"ifsc\s*(?:code)?\s*:?\s*([A-Za-z]{4}\d{7})", re.IGNORECASE)
NAME_BAD = ("bank", "bldg", "road", "street", "society", "apartment", "opp.",
            "phone", "email", "cust", "branch", "ltd", "limited", "smt", "shri")


def _meta_from_header(lines: list[str], family: str) -> dict:
    meta = {"account_no": "", "account_name": "", "ifsc": "", "branch": "",
            "period_start": "", "period_end": "", "bank": BANK_NAMES.get(family, "")}
    text = "\n".join(lines[:60])
    m = re.search(IFSC_RE, text)
    if m:
        meta["ifsc"] = m.group(1).upper()
    m = re.search(ACCOUNT_RE.get(family, ACCOUNT_RE["generic"]), text, re.I)
    if m:
        meta["account_no"] = next((g for g in m.groups() if g), "")
    for ln in lines[:60]:
        low = ln.lower()
        pm = re.search(r"from\s+([\dA-Za-z-]+?)\s+to\s+([\dA-Za-z-]+)", ln, re.I)
        if pm and ("period" in low or "statement" in low):
            meta["period_start"] = pm.group(1).strip()
            meta["period_end"] = pm.group(2).strip()
            break
    for ln in lines[:25]:
        s = ln.strip().rstrip(".")
        if not s or re.search(r"\d", s):
            continue
        if any(b in s.lower() for b in NAME_BAD):
            continue
        if re.match(r"^[A-Z][A-Z ./'-]{3,60}$", s):
            meta["account_name"] = s
            break
    if not meta["account_name"]:
        m = re.search(r"(?:name\s*:?\s*|account\s*title\s*:?\s*)"
                      r"([A-Za-z][A-Za-z ./'-]{3,60})", text, re.I)
        if m:
            meta["account_name"] = m.group(1).strip()
    if not meta["account_name"]:
        m = re.search(r"INR\s+([A-Z][A-Z .]{3,50})$", text, re.M)
        if m:
            meta["account_name"] = m.group(1).strip()
    return meta


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------
def _amounts(tokens: list[str]) -> tuple[list[str], str]:
    """Return (amount tokens in order, balance suffix)."""
    amts = [t for t in tokens if _is_amount(t)]
    suffix = ""
    if amts:
        m = re.match(r"^.*?\(?([CcDd][Rr])\)?$", amts[-1])
        if m:
            suffix = m.group(1).upper()
    return amts, suffix


def _normalise_row(tokens: list[str], family: str, prev_balance: float | None,
                   period: tuple | None) -> dict | None:
    if family == "rbl" and len(tokens) > 1 and tokens[0].isdigit() and len(tokens[0]) >= 9:
        tokens = tokens[1:]
    date_fmts = DATE_FORMATS_DEFAULT
    if family == "hdfc":
        date_fmts = DATE_FORMATS_HDFC
    elif family == "bandhan":
        date_fmts = DATE_FORMATS_BANDHAN
    if tokens[0].isdigit() and len(tokens[0]) >= 8:  # stray account/ref column
        tokens = tokens[1:]
    date = parse_date(clean_field(tokens[0]), date_fmts, period)
    if not date:
        return None
    idx = 1
    value_date = ""
    if len(tokens) > 1:
        vd = parse_date(clean_field(tokens[1]), date_fmts, period)
        if vd and vd != date:
            value_date = vd
            idx = 2
    amts, suffix = _amounts(tokens)
    if not amts:
        return None
    balance = parse_amount(amts[-1])
    if balance is None:
        return None
    prefix = amts[:-1]
    debit = credit = None
    if len(prefix) >= 2:
        debit, credit = parse_amount(prefix[-2]), parse_amount(prefix[-1])
    elif len(prefix) == 1:
        a = parse_amount(prefix[0])
        if a is None:
            return None
        delta = None
        if prev_balance is not None:
            delta = balance - prev_balance
        if delta is not None and abs(delta) > 1e-9:
            if delta > 0:
                credit = a
            else:
                debit = a
        elif suffix == "DR":
            debit = a
        elif suffix == "CR":
            credit = a
        else:
            credit = a
    else:
        # balance-only row: direction from balance movement
        if prev_balance is not None and abs(balance - prev_balance) > 1e-9:
            delta = balance - prev_balance
            if delta > 0:
                credit = delta
            else:
                debit = -delta
        elif suffix == "CR":
            credit = balance
        elif suffix == "DR":
            debit = balance
        else:
            return None
    if debit is None and credit is not None:
        debit = 0.0
    if credit is None and debit is not None:
        credit = 0.0
    if debit == 0.0 and credit == 0.0:
        return None
    amt_positions = [i for i, t in enumerate(tokens) if _is_amount(t)]
    if amt_positions:
        narr_end = amt_positions[0]
    else:
        narr_end = len(tokens)
    narration = " ".join(t for t in tokens[idx:narr_end])
    return {
        "date": date, "value_date": value_date,
        "debit": debit, "credit": credit, "balance": balance,
        "txn_type": "D" if debit > 0 else "C",
        "narration": re.sub(r"\s+", " ", narration).strip(),
    }


def _parse_lines(path: str, lines: list[str], source_format: str) -> dict:
    joined = _join_split_dates(lines)
    if any(re.match(r"\d{2}-[A-Za-z]{3}-\s", ln) for ln in joined):
        joined = _splice_bandhan_years(joined)
    text = "\n".join(joined)
    ifsc_hint = ""
    m = re.search(IFSC_RE, text)
    if m:
        ifsc_hint = m.group(1).upper()
    family = detect_family(joined, ifsc_hint)
    meta = _meta_from_header(lines, family)
    header_idx = _find_header(joined, family)
    if header_idx < 0:
        family = "generic"
        meta = _meta_from_header(lines, family)
        header_idx = _find_header(joined, family)
    if family == "generic" and header_idx < len(joined):
        # No reliable table header in line-layout exports: start from the
        # first line that begins with a date.
        for i, ln in enumerate(joined):
            if re.match(r"^\s*\d{1,2}[/-][A-Za-z0-9]", ln):
                header_idx = max(i - 1, 0)
                break
    if header_idx < 0 or header_idx >= len(joined):
        header_idx = 0
        family = "generic"
    date_fmts = DATE_FORMATS_DEFAULT
    if family == "hdfc":
        date_fmts = DATE_FORMATS_HDFC
    elif family == "bandhan":
        date_fmts = DATE_FORMATS_BANDHAN
    period = None
    p0 = parse_date(meta["period_start"], date_fmts)
    p1 = parse_date(meta["period_end"], date_fmts)
    if p0 and p1:
        period = (p0, p1)
    rows: list[dict] = []
    prev_balance: float | None = None
    opening_balance: float | None = None
    last_row: dict | None = None
    # Full-period statements print an opening balance; when the summary line
    # is not machine-parseable, seed the direction heuristic at 0.00 so the
    # first amount row can be oriented by balance movement.
    if opening_balance is None and "opening balance" in text.lower():
        opening_balance = 0.0
        prev_balance = 0.0
    for ln in joined[header_idx + 1:]:
        s = ln.strip()
        if not s or SKIP_LINE_RE.match(s):
            continue
        tokens = s.split()
        date = parse_date(clean_field(tokens[0]), date_fmts, period)
        if not date:
            if last_row is not None:
                last_row["narration"] += " " + s
            continue
        row = _normalise_row(list(tokens), family, prev_balance, period)
        if row is None:
            continue
        low = row["narration"].lower()
        if low.startswith(("opening balance", "b/f", "brought forward",
                           "balance forward", "grand total", "closing balance")):
            if low.startswith(("opening balance", "b/f")) and row["balance"] is not None:
                opening_balance = row["balance"]
                prev_balance = row["balance"]
            continue
        rows.append(row)
        last_row = row
        if row["balance"] is not None:
            prev_balance = row["balance"]
    base = os.path.basename(path)
    stem = os.path.splitext(base)[0]
    for i, r in enumerate(rows):
        r["txn_id"] = f"{stem[:24]}_{i:06d}"
        r["source_file"] = path
        r["source_format"] = f"{family}_{source_format}"
    meta["family"] = family
    meta["layout"] = family
    meta["opening_balance"] = opening_balance
    meta["row_count"] = len(rows)
    return {"records": rows, "meta": meta}


def parse_bank_pdf(path: str) -> dict:
    lines = extract_pdf_lines(path)
    if not lines or sum(len(l) for l in lines) < 50:
        raise ValueError("scanned or image-only PDF: OCR required, skipped")
    return _parse_lines(path, lines, "pdf")


def parse_bank_txt(path: str) -> dict:
    text = read_raw_text(path)
    lines = _sanitize(text).splitlines()
    return _parse_lines(path, lines, "txt")


def parse_bank_csv(path: str) -> dict:
    from .util import parse_csv_robust
    rows = parse_csv_robust(path)
    if not rows:
        return {"records": [], "meta": {"layout": "csv"}}
    header = [clean_field(c).lower() for c in rows[0]]
    records = []
    for r in rows[1:]:
        if not any(clean_field(c) for c in r):
            continue
        d = dict(zip(header, [clean_field(c) for c in r]))
        debit = parse_amount(d.get("debit", ""))
        credit = parse_amount(d.get("credit", ""))
        if d.get("amount") and debit is None and credit is None:
            amt = parse_amount(d.get("amount", ""))
            typ = d.get("type", "").upper()
            if typ in ("DR", "D", "DEBIT"):
                debit = amt
            elif typ in ("CR", "C", "CREDIT"):
                credit = amt
        if debit is None and credit is None:
            continue
        rec = {
            "txn_id": "", "bank": d.get("bank", ""),
            "account_no": d.get("account_no", "") or d.get("account number", ""),
            "account_name": d.get("account_name", "") or d.get("name", ""),
            "ifsc": d.get("ifsc", ""), "branch": "",
            "date": parse_date(d.get("date", ""), DATE_FORMATS_DEFAULT),
            "time": parse_time(d.get("time", "") or d.get("timestamp", "")),
            "ts": None, "value_date": "",
            "mode": d.get("mode", "") or d.get("transaction_mode", ""),
            "narration": d.get("narration", "") or d.get("particulars", "")
                         or d.get("description", ""),
            "debit": debit, "credit": credit,
            "balance": parse_amount(d.get("balance", "")),
            "txn_type": "D" if (debit or 0) > 0 else "C",
            "chq_ref_no": d.get("chq_ref_no", "") or d.get("ref", ""),
            "sender_phone": "", "receiver_phone": "", "counterparty_name": "",
            "counterparty_bank": "", "upi_id": "", "upi_ref": "",
            "receiver_account": "", "source_file": path,
            "source_format": "csv",
        }
        records.append(rec)
    stem = os.path.splitext(os.path.basename(path))[0]
    for i, r in enumerate(records):
        r["txn_id"] = f"csv_{stem[:20]}_{i:06d}"
    return {"records": records, "meta": {"layout": "csv", "family": "csv"}}


def parse_bank_xlsx(path: str, family: str = "") -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    all_rows: list[dict] = []
    meta: dict = {"account_no": "", "account_name": "", "ifsc": "",
                  "layout": "xlsx", "family": "xlsx", "bank": ""}
    seen = 0
    for ws in wb.worksheets:
        header = None
        for row in ws.iter_rows(values_only=True):
            if header is None:
                header = [clean_field(c).upper() for c in row]
                if not any(header):
                    header = None
                continue
            if not any(c is not None and clean_field(c) for c in row):
                continue
            d = {h: clean_field(c) for h, c in zip(header, row)}
            r = None
            if "ACCOUNT" in d and "TRAN_AMOUNT" in d and "BALANCE" in d:
                r = _centralbank_row(d, path, meta)
            elif any(k in d for k in ("DATE", "TXN_DATE", "TRAN DATE")):
                r = _generic_xlsx_row(d, path)
            if r:
                all_rows.append(r)
                seen += 1
    wb.close()
    if not all_rows:
        meta["layout"] = "xlsx_empty"
    return {"records": all_rows, "meta": meta}


def _centralbank_row(d: dict, path: str, meta: dict) -> dict | None:
    acct = clean_field(d.get("ACCOUNT", ""))
    if acct and not acct.isdigit():
        return None
    if acct:
        meta["account_no"] = acct
    date = _compact_date(d.get("TXN_DATE"))
    if not date:
        return None
    amount = parse_amount(d.get("TRAN_AMOUNT"))
    narration = d.get("NARATION") or d.get("TXN_DESC") or ""
    if "elapsed" in narration.lower() or amount is None:
        return None
    typ = d.get("TYPE", "").upper()
    if typ == "CR" or amount > 0:
        debit, credit = 0.0, abs(amount)
    else:
        debit, credit = abs(amount), 0.0
    time = ""
    raw_time = d.get("POST TIME HH:MM:SSSS") or d.get("POST_TIME") or ""
    m = re.search(r"(\d{2})(\d{2})(\d{2})", raw_time)
    if m and int(m.group(1)) <= 23 and int(m.group(2)) <= 59 and int(m.group(3)) <= 59:
        time = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
    return {
        "txn_id": f"cbi_{len(meta.get('_n', [])):06d}", "bank": "Central Bank of India",
        "account_no": meta["account_no"], "account_name": "", "ifsc": "",
        "branch": d.get("TXN_BRANCH", ""), "date": date, "time": time, "ts": None,
        "value_date": "", "mode": "", "narration": narration,
        "debit": debit, "credit": credit, "balance": parse_amount(d.get("BALANCE")),
        "txn_type": "D" if debit > 0 else "C", "chq_ref_no": d.get("INSTRUMENT_NO", ""),
        "sender_phone": "", "receiver_phone": "", "counterparty_name": "",
        "counterparty_bank": "", "upi_id": "", "upi_ref": "",
        "receiver_account": "", "source_file": path, "source_format": "centralbank_xlsx",
    }


def _compact_date(v) -> str:
    s = clean_field(v)
    if not s:
        return ""
    if s.isdigit() and len(s) == 8:
        try:
            return parse_date(s, ("%d%m%Y",))
        except (ValueError, TypeError):
            pass
    return parse_date(s, ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"))


def _generic_xlsx_row(d: dict, path: str) -> dict | None:
    date = parse_date(d.get("DATE") or d.get("TXN_DATE") or d.get("TRAN DATE"),
                      DATE_FORMATS_DEFAULT)
    if not date:
        return None
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
        return None
    return {
        "txn_id": "", "bank": "", "account_no": d.get("ACCOUNT", ""),
        "account_name": "", "ifsc": "", "branch": "",
        "date": date, "time": parse_time(d.get("TIME", "") or d.get("POST TIME", "")),
        "ts": None, "value_date": "",
        "mode": "", "narration": d.get("NARRATION") or d.get("PARTICULARS") or "",
        "debit": debit, "credit": credit,
        "balance": parse_amount(d.get("BALANCE") or d.get("CLOSINGBALANCE") or d.get("CLOSING BALANCE")),
        "txn_type": "D" if (debit or 0) > 0 else "C",
        "chq_ref_no": d.get("INSTRUMENT_NO", ""), "sender_phone": "",
        "receiver_phone": "", "counterparty_name": "", "counterparty_bank": "",
        "upi_id": "", "upi_ref": "", "receiver_account": "",
        "source_file": path, "source_format": "generic_xlsx",
    }
