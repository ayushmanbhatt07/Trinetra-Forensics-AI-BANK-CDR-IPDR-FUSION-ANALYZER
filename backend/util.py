"""Shared helpers: robust CSV reading, phone/date/amount normalisation.

These helpers encode every quirk found in the real Surat Police data:
single-quote wrapping (Jio VVM), '=\"...\"' Excel formula quoting (Jio nodal),
BTS addresses containing commas (Vi), truncated years (HDFC), split date lines
(Bandhan), Indian lakh number grouping, and mixed phone formats.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta

INR_AMOUNT_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{2,3})*(?:\.\d+)?$")
BARE_AMOUNT_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
YEAR_RE = re.compile(r"\d{4}")


def read_raw_text(path: str, max_bytes: int | None = None) -> str:
    """Read a text file trying the encodings seen in the wild."""
    data = open(path, "rb").read(max_bytes) if max_bytes else open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


def parse_csv_robust(path: str) -> list[list[str]]:
    """Parse a CSV with a strict dialect. Returns rows of unquoted strings.

    Handles BOMs, the '=\"...\"' formula style and single-quote wrapping via
    `clean_field` on every cell. BTS addresses with commas are preserved because
    we use the real csv module, never naive line splitting.
    """
    text = read_raw_text(path)
    if '="' in text:
        text = text.replace('="', '"')
    if not text.strip():
        return []
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if "\t" in first_line and "," not in first_line:
        delim = "\t"
    else:
        delim = ","
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        pass
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = []
    try:
        for row in reader:
            rows.append(row)
    except csv.Error:
        pass  # malformed rows (e.g. binary content misdetected as CSV) stop here
    return rows


def clean_field(value) -> str:
    """Strip quote-wrapper artifacts from any cell value."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        s = s[1:-1]
    return s.strip()


def is_amount(value: str) -> bool:
    v = value.strip().replace(",", "").replace("₹", "").replace(" ", "")
    return bool(BARE_AMOUNT_RE.match(v))


def parse_amount(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("₹", "").replace(" ", "")
    if not s or s in ("-", "--", "N/A", "NA", ""):
        return None
    m = re.match(r"^([+-]?\d*\.?\d+)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalise_phone(raw) -> str:
    """Return canonical 12-digit '91XXXXXXXXXX' or '' when not a phone.

    Accepts +91..., 91..., 0XXXXXXXXX, bare 10-digit numbers and digits with
    spaces. Deliberately rejects obvious non-phones (bank SMS codes like
    'VD-HDFCBN', short codes, VZ-ViCARE, AD-Airtel) via a length + digit check.
    """
    if raw is None:
        return ""
    s = str(raw).strip().strip("'\"")
    if not s or s in ("-", "--", "NA", "N/A"):
        return ""
    s = re.sub(r"[^\d]", "", s)
    if not s.isdigit():
        return ""
    if len(s) == 13 and s.startswith("91"):
        s = s[2:]
    elif len(s) == 12 and s.startswith("91"):
        s = s[2:]
    elif len(s) == 11 and s.startswith("0"):
        s = s[1:]
    elif len(s) == 10:
        pass
    else:
        return ""
    if not s.startswith(("6", "7", "8", "9")):
        return ""
    return "91" + s


def normalise_imei(raw) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().strip("'\"")
    if not s or s == "-":
        return ""
    s = re.sub(r"\D", "", s)
    return s


def normalise_imsi(raw) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().strip("'\"")
    if not s or s == "-":
        return ""
    s = re.sub(r"\D", "", s)
    return s


_DATE_CACHE: dict = {}


def parse_date(value: str, formats: tuple | list | None = None,
                period: tuple | None = None) -> str:
    """Parse a date string to ISO YYYY-MM-DD (or '').

    `period` = (start_iso, end_iso) lets truncated years (HDFC '02/01/20') be
    resolved to the century closest to the statement period.
    """
    if value is None:
        return ""
    s = str(value).strip().strip("'\"")
    if not s or s in ("-", "--", "NA", "N/A", "..."):
        return ""
    s = re.sub(r"\s+", " ", s)
    if re.fullmatch(r"\d{8}", s):  # ddmmyyyy / yyyymmdd ambiguity handled below
        pass
    fmts = formats or (
        "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y", "%d/%b/%y",
        "%d %b %Y", "%d-%B-%Y", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d",
        "%Y%m%d", "%d%m%Y", "%Y-%m-%d %H:%M:%S", "%d %b %Y",
    )
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # drop the trailing day-of-week / time noise some formats carry
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # 8-digit compact date: ddmmyyyy (central bank drops zero padding, so try
    # both ddmmyyyy and yyyymmdd, preferring the one inside the period)
    if re.fullmatch(r"\d{8}", s):
        cand = []
        try:
            cand.append(datetime.strptime(s, "%d%m%Y"))
        except ValueError:
            pass
        try:
            cand.append(datetime.strptime(s, "%Y%m%d"))
        except ValueError:
            pass
        if cand:
            if period:
                p0 = datetime.strptime(period[0], "%Y-%m-%d")
                p1 = datetime.strptime(period[1], "%Y-%m-%d")
                for c in cand:
                    if p0 - timedelta(days=5) <= c <= p1 + timedelta(days=5):
                        return c.strftime("%Y-%m-%d")
            return cand[0].strftime("%Y-%m-%d")
    # resolve truncated two-digit year against period when supplied
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})$", s)
    if m and period:
        d, mo, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        base = int(period[0][:4]) // 100 * 100
        for y in (base + yy, base + yy - 100, base + yy + 100):
            try:
                dt = datetime(y, mo, d)
            except ValueError:
                continue
            p0 = datetime.strptime(period[0], "%Y-%m-%d") - timedelta(days=400)
            p1 = datetime.strptime(period[1], "%Y-%m-%d") + timedelta(days=400)
            if p0 <= dt <= p1:
                return dt.strftime("%Y-%m-%d")
    return ""


def parse_time(value: str) -> str:
    if value is None:
        return ""
    s = str(value).strip().strip("'\"")
    if not s or s in ("-", "--", "NA", "N/A"):
        return ""
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m:
        h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        if h <= 23 and mi <= 59 and se <= 59:
            return f"{h:02d}:{mi:02d}:{se:02d}"
    m = re.fullmatch(r"(\d{2})(\d{2})(\d{2})", s)  # compact hhmmss
    if m:
        h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if h <= 23 and mi <= 59 and se <= 59:
            return f"{h:02d}:{mi:02d}:{se:02d}"
    return ""


def to_epoch(iso_date: str, hhmmss: str) -> int | None:
    if not iso_date:
        return None
    base = datetime.strptime(iso_date, "%Y-%m-%d")
    if hhmmss:
        m = re.match(r"(\d{2}):(\d{2}):(\d{2})", hhmmss)
        if m:
            base = base.replace(hour=int(m.group(1)), minute=int(m.group(2)),
                                second=int(m.group(3)))
    return int(base.timestamp())


def iso_to_epoch(iso: str) -> int | None:
    if not iso:
        return None
    try:
        return int(datetime.strptime(iso, "%Y-%m-%d %H:%M:%S").timestamp())
    except ValueError:
        return to_epoch(iso, "")


def normalise_ip(raw) -> str:
    """Lowercase + strip whitespace on IP addresses; '' for junk."""
    if raw is None:
        return ""
    s = str(raw).strip().strip("'\"")
    if not s or s == "-":
        return ""
    if re.match(r"^[\da-fA-F:./]+$", s) or re.match(r"^\d{1,3}(\.\d{1,3}){3}$", s):
        return s.lower()
    return ""
