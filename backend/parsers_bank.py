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
    r"^(?:\d{1,3}(?:,\d{2,3})+(?:\.\d{2,3})?|(?:[\d,]{1,12}\.\d{2,3}|\.\d{2,3}))"
    r"(?:\(?[CcDd][Rr]\)?)?$")
PARTIAL_DATE_RE = re.compile(r"(\d{2}-[A-Za-z]{3}-$|\d{1,2}/\d{1,2}/\d{1,2}$)")
SKIP_LINE_RE = re.compile(
    r"^(page\s*\d+|disclaimer|this is system|registered office|grand total|"
    r"opening balance|closing balance|b/f|brought forward|balance forward|"
    r"swipe limit|available balance|elapsed|[-_=]{4,}|summary\s*:|total debits|"
    r"total credits|linked\s|no records found|other digital|facility\s|disclaimer|"
    r"si\s+scheme\s|scheme\s+type|sanctioned\s+limit|locker\s+type|"
    r"linked or not|further it does not|generated date)", re.IGNORECASE)
DENSIFY_RE = re.compile(r"\(cid:\d+\)")
# Date token at start of a line (possibly after a serial number):
DATE_TOKEN_RE = re.compile(
    r"^\d{1,2}[/-](?:\d{1,2}|[A-Za-z]{3})[/-]\d{2,4}$")
# Line starts with serial_number + date:
SERIAL_DATE_RE = re.compile(
    r"^\s*(\d{1,4})\s+(\d{1,2}[/-](?:\d{1,2}|[A-Za-z]{3})[/-]\d{2,4})\b")
# Page footer pattern (e.g., '1 of 2', 'Page 1'):
PAGE_FOOTER_RE = re.compile(
    r"^\s*(?:\d+\s+of\s+\d+|page\s*\d+)\s*$", re.IGNORECASE)
# Section headers that indicate the transaction table has ended:
END_OF_TABLE_RE = re.compile(
    r"^(?:summary\s*:?|linked\s+(?:casa|deposits?|loans?|lockers?|accounts?)|"
    r"other\s+digital\s+products|facility\s+sms|summary\s+of\s+accounts|"
    r"account\s+summary|end\s+of\s+statement|\*{3,}\s*end|"
    r"total\s+debits?|total\s+credits?|grand\s+total|cheque\s+book\s+details|"
    r"sanctioned\s+limit|si\s+scheme\s+type|closure\s+details|"
    r"disclaimer\s*:|this\s+is\s+a\s+computer\s+generated)", re.IGNORECASE)


def _sanitize(text: str) -> str:
    return DENSIFY_RE.sub("", text)


def _is_amount(tok: str) -> bool:
    return bool(AMOUNT_RE.match(tok))


def extract_pdf_lines(path: str) -> list[str]:
    lines: list[str] = []
    # Fast path 1: pypdf (pure-python stream decoder, 50x faster than visual layout engines)
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            txt = page.extract_text() or ""
            if txt:
                lines.extend(_sanitize(txt).splitlines())
        clean = [ln.strip() for ln in lines if ln.strip()]
        if clean and sum(len(l) for l in clean) >= 50:
            return clean
    except Exception:
        pass

    # Fast path 2: pdfminer high_level
    try:
        from pdfminer.high_level import extract_text as _pm_extract_text
        raw = _pm_extract_text(path)
        if raw and len(raw.strip()) >= 50:
            clean = [ln.strip() for ln in _sanitize(raw).splitlines() if ln.strip()]
            if clean and sum(len(l) for l in clean) >= 50:
                return clean
    except Exception:
        pass

    # Reliable fallback: pdfplumber page-by-page extraction
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text(layout=False) or page.extract_text() or ""
                lines.extend(_sanitize(txt).splitlines())
    except ValueError as e:
        if "password" in str(e).lower():
            raise ValueError("password-protected PDF: skipped") from e
        raise
    except Exception as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            raise ValueError("password-protected PDF: skipped") from e
        raise ValueError(f"unreadable PDF: {str(e)[:80]}") from e
    return [ln.strip() for ln in lines if ln.strip()]


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


def _join_multiline_rows(lines: list[str], date_fmts: tuple = None) -> list[str]:
    """Merge multi-line transaction rows into single logical lines.

    Many Indian bank PDFs (Union Bank, BOI, etc.) split each transaction
    across 2-3 physical lines:
        Line A:  SI  DATE  narration_start …
        Line B:  narration_continuation …
        Line C:  amount1  amount2  [Cr|Dr]

    This pass reassembles them so the main parser sees one line per
    transaction with date + narration + amounts together.
    """
    if date_fmts is None:
        date_fmts = DATE_FORMATS_DEFAULT
    out: list[str] = []
    buf: list[str] = []          # accumulates fragments of current txn

    def _flush():
        if buf:
            out.append(" ".join(buf))
            buf.clear()

    def _line_starts_txn(ln: str) -> bool:
        """Does this line look like the start of a new transaction row?"""
        s = ln.strip()
        if not s:
            return False
        toks = s.split()
        if not toks:
            return False
        # Pattern 1: serial_number + date  (e.g. '1 02-08-2026 …')
        if (len(toks) >= 2 and toks[0].isdigit() and len(toks[0]) <= 4
                and DATE_TOKEN_RE.match(toks[1])):
            return True
        # Pattern 2: bare date at start  (e.g. '02-08-2026 …')
        if DATE_TOKEN_RE.match(toks[0]):
            return True
        return False

    def _is_amount_only_line(ln: str) -> bool:
        """Line contains ONLY amount tokens (+ optional Cr/Dr suffix)."""
        toks = ln.strip().split()
        if not toks:
            return False
        meaningful = [t for t in toks
                      if not re.fullmatch(r"(?:[CcDd][Rr]|\(?[CcDd][Rr]\)?)", t)]
        return bool(meaningful) and all(_is_amount(t) for t in meaningful)

    def _is_page_break(ln: str) -> bool:
        """Detect page footers/headers that interrupt transaction flow."""
        s = ln.strip()
        return bool(PAGE_FOOTER_RE.match(s))

    i = 0
    in_table = False
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()

        # Skip blank lines
        if not s:
            i += 1
            continue

        # Once we see the first transaction, we're in the table
        if _line_starts_txn(ln):
            in_table = True

        if not in_table:
            out.append(ln)
            i += 1
            continue

        # Skip page footers/headers that appear mid-table
        if _is_page_break(ln):
            i += 1
            continue

        # Skip repeated table headers on subsequent pages
        low = s.lower()
        if ('date' in low and ('particulars' in low or 'narration' in low)
                and ('balance' in low or 'withdrawal' in low or 'deposit' in low
                     or 'debit' in low or 'credit' in low)):
            i += 1
            continue

        # Stop table ingestion if a terminal section (summary, linked accounts, etc.) starts
        if END_OF_TABLE_RE.match(s):
            _flush()
            in_table = False
            out.append(ln)
            i += 1
            continue

        if SKIP_LINE_RE.match(s):
            _flush()
            out.append(ln)
            i += 1
            continue

        if _line_starts_txn(ln):
            _flush()  # emit previous transaction
            buf.append(s)
            i += 1
            continue

        # Continuation line (narration fragment or amount-only line)
        if buf:
            buf.append(s)
        else:
            # Stray line before first transaction — pass through
            out.append(ln)
        i += 1

    _flush()
    return out


# ---------------------------------------------------------------------------
# Layout registry
# ---------------------------------------------------------------------------
FAMILY_LAYOUTS: dict = {
    # family: (header hints that must all appear within a 3-line window, kind)
    "casa":    (["post date", "debit", "credit", "balance"], "amt_bal"),
    "axis8":   (["transaction particulars", "dr/cr"], "amt_bal"),
    "axis7":   (["tran date", "particulars", "debit", "credit"], "amt_bal"),
    "federal": (["withdrawals", "deposits", "dr/cr"], "gen"),
    "hdfc":    (["narration", "withdrawalamt"], "gen"),
    "kotak":   (["narration", "withdrawal (dr)"], "gen"),
    "bandhan": (["trans value", "description", "debits"], "gen"),
    "pnb":     (["gl.", "debit amount", "credit amount"], "gen"),
    "union":   (["particulars", "withdrawal", "deposit", "balance"], "gen"),
    "icici":   (["transaction details", "cheque no", "debit"], "gen"),
    "utkarsh": (["value date", "transaction", "debit", "credit"], "gen"),
    "yes":     (["description", "reference", "debits", "credits"], "gen"),
    "associate": (["narra", "chequeno", "debit", "credit", "balance"], "gen"),
    "cityunion": (["particulars", "chq no", "debit", "credit", "balance"], "gen"),
    "rbl":     (["tran particular", "debit amount", "credit amount"], "gen"),
    "sbi":     (["txn date", "description", "debit", "credit", "balance"], "gen"),
    "bob":     (["transaction date", "debit", "credit", "balance"], "gen"),
    "boi":     (["date", "particulars", "debit", "credit", "balance"], "gen"),
    "idbi":    (["txn posted date", "cheque/ref no", "debit", "credit"], "gen"),
    "indian":  (["date", "description", "debit", "credit", "balance"], "gen"),
    "generic": (["balance"], "gen"),
}

FAMILY_ORDER = ("casa", "axis8", "axis7", "federal", "hdfc", "kotak", "bandhan", "pnb",
                "union", "icici", "utkarsh", "yes", "rbl", "cityunion",
                "associate", "sbi", "bob", "boi", "idbi", "indian", "generic")

BANK_NAMES = {
    "casa": "Canara / Gramin Bank",
    "axis8": "Axis Bank", "axis7": "Axis Bank", "federal": "Federal Bank",
    "hdfc": "HDFC Bank", "kotak": "Kotak Mahindra Bank",
    "bandhan": "Bandhan Bank", "pnb": "Punjab National Bank",
    "union": "Union Bank of India", "utkarsh": "Utkarsh Small Finance Bank",
    "yes": "Yes Bank", "associate": "Associate Co-operative Bank",
    "cityunion": "City Union Bank", "rbl": "RBL Bank",
    "icici": "ICICI Bank", "sbi": "State Bank of India",
    "bob": "Bank of Baroda", "boi": "Bank of India",
    "idbi": "IDBI Bank", "indian": "Indian Bank", "generic": "",
}

IFSC_OVERRIDES = {
    "UTIB": "axis8", "BDBL": "bandhan", "FDRL": "federal", "HDFC": "hdfc",
    "ICIC": "icici", "KKBK": "kotak", "PUNB": "pnb", "UBIN": "union",
    "UTKS": "utkarsh", "YESB": "yes", "UCBA": "pnb", "CIUB": "cityunion",
    "GSCB": "associate", "RATN": "rbl",
    "SBIN": "sbi", "BARB": "bob", "BKID": "boi", "IBKL": "idbi",
    "IDIB": "indian", "CNRB": "casa", "CBIN": "casa",
}

IFSC_PREFIX_TO_BANK: dict[str, str] = {
    "UTIB": "Axis Bank", "UBIN": "Union Bank of India",
    "SBIN": "State Bank of India", "PUNB": "Punjab National Bank",
    "HDFC": "HDFC Bank", "ICIC": "ICICI Bank",
    "KKBK": "Kotak Mahindra Bank", "BARB": "Bank of Baroda",
    "BKID": "Bank of India", "IBKL": "IDBI Bank",
    "IDIB": "Indian Bank", "CNRB": "Canara Bank",
    "CBIN": "Central Bank of India", "FDRL": "Federal Bank",
    "BDBL": "Bandhan Bank", "YESB": "Yes Bank",
    "CIUB": "City Union Bank", "RATN": "RBL Bank",
    "IOBA": "Indian Overseas Bank", "UCBA": "UCO Bank",
    "PSIB": "Punjab & Sind Bank", "CORP": "Union Bank of India",
    "ANDB": "Union Bank of India", "ALLA": "Indian Bank",
    "SYNB": "Canara Bank", "ORBC": "Punjab National Bank",
    "VIJB": "Bank of Baroda", "MAHB": "Bank of Maharashtra",
    "IDFB": "IDFC First Bank", "INDB": "IndusInd Bank",
    "AUBL": "AU Small Finance Bank", "ESFB": "Equitas Small Finance Bank",
    "UTKS": "Utkarsh Small Finance Bank", "GSCB": "Gujarat State Co-operative Bank",
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
    "union": r"(?:a/c\s*no:?\s*(\d{10,})|account\s*number\s*:?\s*([\dX]{10,}))",
    "utkarsh": r"(?:account\s*number|account\s*no\.?)[\d\s]{0,30}?(\d{12,})",
    "yes": r"a/c\s*number:?\s*(\d{10,})",
    "associate": r"a/c\s*no:?\s*(\d{10,})",
    "cityunion": r"account\s*no\s*:?\s*(\d{10,})",
    "rbl": r"account\s*no:?\s*(\d{9,})",
    "icici": r"account\s*no\s*:?\s*(\d{10,})",
    "sbi": r"account\s*(?:no|number)\s*:?\s*([\dX]{10,})",
    "bob": r"account\s*(?:no|number)\s*:?\s*([\dX]{10,})",
    "boi": r"account\s*(?:no|number)\s*:?\s*([\dX]{10,})",
    "idbi": r"account\s*(?:no|number)\s*:?\s*([\dX]{10,})",
    "indian": r"account\s*(?:no|number)\s*:?\s*([\dX]{10,})",
    "generic": r"account\s*(?:no|number)?\s*:?\s*([\dX]{10,})",
}
IFSC_RE = re.compile(r"ifsc\s*(?:code)?\s*:?\s*([A-Za-z]{4}\d{7})", re.IGNORECASE)
NAME_BAD = (
    "bank", "bldg", "road", "street", "society", "apartment", "opp.",
    "phone", "email", "cust", "branch", "ltd", "limited", "smt", "shri",
    "details", "statement", "account", "address", "nomination", "transaction",
    "summary", "saving", "current", "balance", "registered", "customer",
    "generated", "facility", "scheme", "locker", "page", "period", "currency",
    "joint", "holder", "kyc", "ckyc", "micr", "ifsc", "pan", "description"
)


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
        if "period" in low or "statement" in low or "from" in low:
            pm = re.search(r"(?:from\s*:?|period\s*:?)\s*([A-Za-z0-9/-]{8,12})\s+(?:to\s*:?|-)\s*([A-Za-z0-9/-]{8,12})", ln, re.I)
            if pm:
                meta["period_start"] = pm.group(1).strip()
                meta["period_end"] = pm.group(2).strip()
                break

    # Look for name labeled explicitly (on the same line or immediate next line)
    for i, ln in enumerate(lines[:30]):
        s = ln.strip()
        if re.match(r"^(?:name\s*(?:&|\+)?\s*address|account\s*name|customer\s*name|holder\s*name)\s*:\s*$", s, re.I):
            if i + 1 < len(lines):
                cand = lines[i + 1].strip()
                if cand and not any(b in cand.lower() for b in NAME_BAD) and not re.search(r"\d", cand):
                    meta["account_name"] = cand
                    break
        m = re.match(r"^(?:name\s*(?:&|\+)?\s*address|account\s*name|customer\s*name|holder\s*name|account\s*title)\s*:\s*([-A-Za-z ./\']{2,60})$", s, re.I)
        if m:
            cand = m.group(1).strip()
            if cand and not any(b in cand.lower() for b in NAME_BAD):
                meta["account_name"] = cand
                break

    # Standalone name search in header lines (common in Indian PDFs like Axis, Canara)
    if not meta["account_name"]:
        for ln in lines[:25]:
            s = ln.strip().rstrip(".")
            if not s or re.search(r"\d", s) or len(s) < 3:
                continue
            if any(b in s.lower() for b in NAME_BAD):
                continue
            if re.match(r"^[A-Z][-A-Z ./\']{2,60}$", s):
                meta["account_name"] = s
                break
    if not meta["account_name"]:
        m = re.search(r"(?:name\s*:?\s*|account\s*title\s*:?\s*)"
                      r"([-A-Za-z ./\']{3,60})", text, re.I)
        if m:
            meta["account_name"] = m.group(1).strip()
    if not meta["account_name"]:
        m = re.search(r"INR\s+([A-Z][-A-Z .]{3,50})$", text, re.M)
        if m:
            meta["account_name"] = m.group(1).strip()

    # Deduce bank name from IFSC prefix or statement text if not already populated
    if not meta["bank"] and meta["ifsc"]:
        prefix = meta["ifsc"][:4].upper()
        meta["bank"] = IFSC_PREFIX_TO_BANK.get(prefix, "")
    if not meta["bank"]:
        for pfx, bname in IFSC_PREFIX_TO_BANK.items():
            if bname.lower() in text.lower():
                meta["bank"] = bname
                break
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
        else:
            # Check if token immediately following the last amount token is Cr/Dr
            try:
                last_amt_str = amts[-1]
                last_idx = len(tokens) - 1 - tokens[::-1].index(last_amt_str)
                if last_idx + 1 < len(tokens):
                    nxt = tokens[last_idx + 1].strip().upper()
                    sm = re.match(r"^\(?([CD]R)\)?$", nxt)
                    if sm:
                        suffix = sm.group(1)
            except (ValueError, IndexError):
                pass
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
    # Strip leading serial number (1-4 digit SI column)
    if (tokens[0].isdigit() and len(tokens[0]) <= 4 and len(tokens) > 1
            and parse_date(clean_field(tokens[1]), date_fmts, period)):
        tokens = tokens[1:]
    elif tokens[0].isdigit() and len(tokens) > 1 and parse_date(clean_field(tokens[1]), date_fmts, period):
        tokens = tokens[1:]
    elif tokens[0].isdigit() and len(tokens[0]) >= 8:  # stray account/ref column
        tokens = tokens[1:]
    date = parse_date(clean_field(tokens[0]), date_fmts, period)
    if not date:
        return None
    idx = 1
    value_date = ""
    txn_time = ""
    if len(tokens) > 1 and re.match(r"^\d{2}:\d{2}(:\d{2})?$", tokens[1]):
        txn_time = tokens[1]
        idx = 2
    if len(tokens) > idx:
        vd = parse_date(clean_field(tokens[idx]), date_fmts, period)
        if vd and vd != date:
            value_date = vd
            idx += 1
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
        # first line that begins with a date (possibly prefixed by SI no).
        for i, ln in enumerate(joined):
            if re.match(r"^\s*\d{1,2}[/-][A-Za-z0-9]", ln):
                header_idx = max(i - 1, 0)
                break
            # serial number + date  (e.g. '1 02-08-2026 …')
            if SERIAL_DATE_RE.match(ln):
                header_idx = max(i - 1, 0)
                break
    if header_idx < 0 or header_idx >= len(joined):
        header_idx = 0
        family = "generic"
    # ---- Multi-line join pass: merge fragmented transaction rows ----
    joined = _join_multiline_rows(joined)
    # Re-find header in the merged list since line numbers shifted
    header_idx = _find_header(joined, family)
    if header_idx < 0:
        # fallback: find first transaction line
        for i, ln in enumerate(joined):
            if SERIAL_DATE_RE.match(ln.strip()):
                header_idx = max(i - 1, 0)
                break
            if re.match(r"^\s*\d{1,2}[/-][A-Za-z0-9]", ln):
                header_idx = max(i - 1, 0)
                break
    if header_idx < 0:
        header_idx = 0
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
    # Try to extract numeric opening balance from statement text
    ob_match = re.search(
        r"opening\s+balance\s*:?\s*([\d,]+(?:\.\d{1,2})?)\s*(?:\(?[CcDd][Rr]\)?)?",
        text, re.IGNORECASE)
    if ob_match:
        opening_balance = parse_amount(ob_match.group(1))
        if opening_balance is not None:
            prev_balance = opening_balance
    # Fallback: seed at 0 so the first amount row can be oriented
    if opening_balance is None and "opening balance" in text.lower():
        opening_balance = 0.0
        prev_balance = 0.0
    for ln in joined[header_idx + 1:]:
        s = ln.strip()
        if not s or SKIP_LINE_RE.match(s):
            continue
        if END_OF_TABLE_RE.match(s):
            break
        tokens = s.split()
        if tokens[0].isdigit() and len(tokens) > 1 and parse_date(clean_field(tokens[1]), date_fmts, period):
            date = parse_date(clean_field(tokens[1]), date_fmts, period)
        else:
            date = parse_date(clean_field(tokens[0]), date_fmts, period)
        if not date:
            if last_row is not None and len(last_row["narration"]) < 250:
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
        if not r.get("bank"):
            r["bank"] = meta.get("bank", "")
        if not r.get("account_no"):
            r["account_no"] = meta.get("account_no", "")
        if not r.get("account_name"):
            r["account_name"] = meta.get("account_name", "")
        if not r.get("ifsc"):
            r["ifsc"] = meta.get("ifsc", "")
    if rows and (not meta.get("period_start") or not meta.get("period_end")):
        valid_dates = sorted([r["date"] for r in rows if r.get("date")])
        if valid_dates:
            if not meta.get("period_start"):
                meta["period_start"] = valid_dates[0]
            if not meta.get("period_end"):
                meta["period_end"] = valid_dates[-1]
    meta["family"] = family
    meta["layout"] = family
    meta["opening_balance"] = opening_balance
    meta["row_count"] = len(rows)
    return {"records": rows, "meta": meta}


def _parse_pdf_tables(path: str) -> dict | None:
    """Fallback parser for PDFs with grid/tabular layout when line parsing finds 0 records."""
    try:
        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(path) as pdf:
            all_tables = []
            for page in pdf.pages:
                tables = page.extract_tables() or []
                all_tables.extend(tables)
            if not all_tables:
                return None

            records = []
            header_map = None
            for tbl in all_tables:
                for row in tbl:
                    if not row or not any(row):
                        continue
                    clean_row = [clean_field(c or "") for c in row]
                    low_row = [c.lower() for c in clean_row]
                    row_text = " ".join(low_row)
                    if ("date" in row_text and
                            any(w in row_text for w in ("particular", "narration", "description", "details")) and
                            any(w in row_text for w in ("balance", "withdrawal", "deposit", "debit", "credit"))):
                        header_map = {}
                        for idx, col in enumerate(low_row):
                            if "date" in col and "val" not in col and "value" not in col and "date" not in header_map:
                                header_map["date"] = idx
                            elif "val" in col and "date" in col:
                                header_map["value_date"] = idx
                            elif any(w in col for w in ("particular", "narration", "description", "details")):
                                header_map["narration"] = idx
                            elif any(w in col for w in ("debit", "withdrawal", "dr")):
                                header_map["debit"] = idx
                            elif any(w in col for w in ("credit", "deposit", "cr")):
                                header_map["credit"] = idx
                            elif "balance" in col:
                                header_map["balance"] = idx
                        continue

                    if not header_map or "date" not in header_map:
                        continue

                    date_val = parse_date(clean_row[header_map["date"]], DATE_FORMATS_DEFAULT)
                    if not date_val:
                        continue

                    narration = clean_row[header_map["narration"]] if "narration" in header_map and header_map["narration"] < len(clean_row) else ""
                    narration = re.sub(r"\s+", " ", narration).strip()

                    debit = parse_amount(clean_row[header_map["debit"]]) if "debit" in header_map and header_map["debit"] < len(clean_row) else None
                    credit = parse_amount(clean_row[header_map["credit"]]) if "credit" in header_map and header_map["credit"] < len(clean_row) else None
                    balance = parse_amount(clean_row[header_map["balance"]]) if "balance" in header_map and header_map["balance"] < len(clean_row) else None

                    if debit is None and credit is None:
                        continue
                    debit = debit or 0.0
                    credit = credit or 0.0

                    records.append({
                        "date": date_val,
                        "value_date": clean_row[header_map["value_date"]] if "value_date" in header_map and header_map["value_date"] < len(clean_row) else "",
                        "narration": narration,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance,
                        "txn_type": "D" if debit > 0 else "C",
                    })
            if records:
                meta = {"layout": "pdf_table", "family": "table", "row_count": len(records)}
                stem = os.path.splitext(os.path.basename(path))[0]
                for i, r in enumerate(records):
                    r["txn_id"] = f"{stem[:24]}_{i:06d}"
                    r["source_file"] = path
                    r["source_format"] = "table_pdf"
                return {"records": records, "meta": meta}
    except Exception:
        pass
    return None


def parse_bank_pdf(path: str) -> dict:
    lines = extract_pdf_lines(path)
    if not lines or sum(len(l) for l in lines) < 50:
        tbl_res = _parse_pdf_tables(path)
        if tbl_res and tbl_res.get("records"):
            return tbl_res
        raise ValueError("scanned or image-only PDF: OCR required, skipped")
    res = _parse_lines(path, lines, "pdf")
    if not res.get("records"):
        tbl_res = _parse_pdf_tables(path)
        if tbl_res and tbl_res.get("records"):
            tbl_res["meta"].update({k: v for k, v in res.get("meta", {}).items() if v})
            for r in tbl_res["records"]:
                if not r.get("bank"):
                    r["bank"] = tbl_res["meta"].get("bank", "")
                if not r.get("account_no"):
                    r["account_no"] = tbl_res["meta"].get("account_no", "")
                if not r.get("account_name"):
                    r["account_name"] = tbl_res["meta"].get("account_name", "")
                if not r.get("ifsc"):
                    r["ifsc"] = tbl_res["meta"].get("ifsc", "")
            return tbl_res
    return res


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
            elif amt is not None:
                if amt >= 0:
                    credit = amt
                else:
                    debit = abs(amt)
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
