"""Confidence-scored format detection engine.

Flow:
    preview(path)                    extract a small text/header/magic snapshot
    score_candidates(preview)        run every fingerprint, produce scored list
    classify_file(path)              -> DetectionResult (best candidate + hints)
    classify(path)                   v2-compat dict API

Low-confidence behaviour: `classify_file` returns the best candidate anyway
but sets `ask_user=True` when confidence < APP_DETECT_MIN_CONFIDENCE;
the pipeline can then surface an AskUser issue. Extensionless files are
sniffed by magic bytes + content. Scanned / image-only PDFs are flagged with
`skip_reason="scanned"` so the pipeline skips them gracefully (no OCR).

Inputs:  file path.
Outputs: DetectionResult(dataset, format, confidence, parser_hint, hints,
         candidates, skip_reason).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import config
from ..errors import DetectError
from .fingerprints import FORMATS, FormatFingerprint

_PREVIEW_BYTES = 64 * 1024
_PDF_PREVIEW_PAGES = 3
_MAGIC_SCANNED = 0.85


@dataclass
class Preview:
    text: str = ""                 # lowercased preview text (CSV/TXT/PDF/ODS/XLSX)
    headers: list[str] = field(default_factory=list)  # lowercased cell headers
    magic: bytes = b""
    is_pdf: bool = False
    pdf_has_text: bool = True
    ext: str = ""
    binary: bool = False           # decoded text looks like binary content


@dataclass
class DetectionResult:
    dataset: str
    format: str
    confidence: float
    candidates: list[dict] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    skip_reason: str = ""
    ask_user: bool = False
    ext: str = ""

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset, "format": self.format,
            "confidence": round(self.confidence, 3),
            "hints": self.hints, "skip_reason": self.skip_reason,
            "ask_user": self.ask_user, "ext": self.ext,
        }


def _read_preview_bytes(path: str, limit: int = _PREVIEW_BYTES) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(limit)


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _is_binary(text: str) -> bool:
    """Heuristic: control chars dominate => not human-readable text."""
    if not text:
        return False
    sample = text[:4096]
    control = sum(1 for ch in sample if ord(ch) < 9 or 13 < ord(ch) < 32
                  or ord(ch) == 127)
    return control / max(len(sample), 1) > 0.30


def _pdf_preview(path: str) -> tuple[str, bool]:
    """Return (preview_text_lower, has_text). Raises DetectError on failure."""
    try:
        import pdfplumber
    except ImportError as e:  # pragma: no cover
        raise DetectError("pdfplumber unavailable") from e
    try:
        with pdfplumber.open(path) as pdf:
            parts = []
            for page in pdf.pages[:_PDF_PREVIEW_PAGES]:
                txt = page.extract_text() or ""
                if txt.strip():
                    parts.append(txt)
            has_text = any(len(p.strip()) > 20 for p in parts)
            return "\n".join(parts).lower(), has_text
    except ValueError as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            raise DetectError("password-protected PDF") from e
        raise DetectError(f"unreadable PDF: {str(e)[:80]}") from e
    except Exception as e:
        raise DetectError(f"unreadable PDF: {str(e)[:80]}") from e


def _spreadsheet_preview(path: str) -> tuple[str, list[str]]:
    """Extract a preview + header cells from xlsx/xls/ods. Graceful on failure."""
    ext = os.path.splitext(path)[1].lower()
    text_parts: list[str] = []
    headers: list[str] = []
    try:
        if ext == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            for ws in wb.worksheets[:3]:
                first = True
                for row in ws.iter_rows(max_row=3, values_only=True):
                    cells = [str(c).strip() for c in row if c is not None]
                    line = " ".join(cells).lower()
                    if first and cells:
                        headers = [c.lower() for c in cells[:12]]
                        first = False
                    text_parts.append(line)
            wb.close()
        elif ext == ".ods":
            from odf.opendocument import load as odf_load
            from odf.table import Table, TableRow, TableCell
            doc = odf_load(path)
            for tbl in doc.spreadsheet.getElementsByType(Table)[:3]:
                for r in tbl.getElementsByType(TableRow)[:3]:
                    cells = [str(c) for c in
                             r.getElementsByType(TableCell)
                             if str(c).strip()]
                    line = " ".join(cells).lower()
                    text_parts.append(line)
            doc.close()
        else:  # .xls legacy
            import pandas as pd
            for sh in pd.ExcelFile(path).sheet_names[:3]:
                df = pd.read_excel(path, sheet_name=sh, header=None, nrows=3)
                for _, row in df.iterrows():
                    cells = [str(c).strip() for c in row if str(c).strip().lower() != "nan"]
                    if cells:
                        text_parts.append(" ".join(cells).lower())
                try:
                    h = df.iloc[0].astype(str).tolist()
                    headers = [c.lower().strip() for c in h
                               if c.lower().strip() not in ("nan", "")]
                except Exception:
                    pass
    except Exception:
        pass  # preview best-effort; scoring falls back to extension
    return "\n".join(text_parts), headers


def _csv_preview(path: str) -> tuple[str, list[str]]:
    data = _read_preview_bytes(path)
    text = _decode_text(data)
    if '="' in text:
        text = text.replace('="', '"')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    preview = "\n".join(lines[:40]).lower()
    headers: list[str] = []
    for ln in lines[:8]:
        parts = [p.strip('"\' ').lower() for p in re.split(r"[,;\t|]", ln)]
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            headers = parts
            break
    return preview, headers


def preview(path: str) -> Preview:
    """Extract a detection preview from `path` (best-effort, never raises)."""
    ext = os.path.splitext(path)[1].lower()
    pv = Preview(ext=ext)
    try:
        pv.magic = _read_preview_bytes(path, 16)
    except OSError:
        return pv
    if not ext:
        if pv.magic[:4] == b"%PDF":
            ext = ".pdf"
        elif pv.magic[:2] == b"PK":
            return pv  # zip/xlsx — content preview skipped
        elif pv.magic[:8] == b"\x89PNG\r\n\x1a\n" or pv.magic[:2] == b"\xff\xd8":
            return pv  # image — unsupported
        else:
            ext = ".txt"
    pv.ext = ext
    try:
        if ext == ".pdf":
            pv.is_pdf = True
            text, has_text = _pdf_preview(path)
            pv.text, pv.pdf_has_text = text, has_text
            if not has_text:
                return pv
            head = text.splitlines()[:8]
            pv.headers = [ln[:60] for ln in head][:12]
        elif ext in (".csv", ".txt"):
            pv.text, pv.headers = _csv_preview(path)
            pv.binary = _is_binary(pv.text)
        elif ext in (".xlsx", ".xls", ".ods"):
            pv.text, pv.headers = _spreadsheet_preview(path)
    except Exception:
        pass
    return pv


def _magic_hint(pv: Preview) -> str:
    if pv.magic[:2] == b"PK":
        return "zip container (xlsx/docx/archive)"
    if pv.magic[:4] == b"7z\xbc\xaf":
        return "7z archive"
    if pv.magic[:8] == b"\x89PNG\r\n\x1a\n":
        return "png image"
    if pv.magic[:2] == b"\xff\xd8":
        return "jpeg image"
    if pv.magic[:4] == b"\xd0\xcf\x11\xe0":
        return "ole container (legacy xls/doc)"
    return ""


_KNOWN_EXTS = frozenset({".pdf", ".csv", ".txt", ".xlsx", ".xls", ".ods"})


def _score(pv: Preview, fp: FormatFingerprint) -> tuple[float, list[str]]:
    """Score one fingerprint against the preview. Returns (score, hints)."""
    score, hints = 0.0, []
    # Strict extension gating: a fingerprint may only match files whose
    # physical extension it declares. This stops a tabular-layout PDF from
    # being detected as bank_xlsx (openpyxl cannot read PDFs).
    if (pv.ext in _KNOWN_EXTS and fp.file_types and pv.ext not in fp.file_types):
        return 0.0, []
    text = pv.text
    kw_hits = sum(1 for k in fp.keywords if k in text)
    if kw_hits:
        score += min(0.55, 0.12 * kw_hits)
        hints.append(f"keywords:{kw_hits}")
    headers_low = [h.lower() for h in pv.headers]
    hd_hits = sum(1 for h in fp.headers if h.lower() in headers_low)
    if hd_hits:
        score += min(0.4, 0.2 * hd_hits)
        hints.append(f"headers:{hd_hits}")
    rg_hits = sum(1 for rx in fp.regex if rx.search(text))
    if rg_hits:
        score += min(0.5, 0.18 * rg_hits)
        hints.append(f"regex:{rg_hits}")
    if fp.magic and pv.magic[:4] in fp.magic:
        score += 0.3
        hints.append("magic")
    # Extension bonus only as a tie-breaker on real content signals —
    # otherwise every CSV/XLSX would tie at 0.1 for empty files.
    if score > 0.0 and fp.file_types and pv.ext in fp.file_types:
        score += 0.1
    return min(score, 1.0), hints


def score_candidates(path: str) -> list[dict]:
    """Return sorted candidate list: [{dataset, format, confidence, hints}]."""
    pv = preview(path)
    out = []
    for fp in FORMATS:
        s, hints = _score(pv, fp)
        if s > 0.0:
            out.append({
                "dataset": fp.dataset, "format": fp.format_id,
                "confidence": round(min(s, 1.0), 3), "hints": hints,
            })
    out.sort(key=lambda c: -c["confidence"])
    return out


def classify_file(path: str, min_confidence: float | None = None) -> DetectionResult:
    """Classify a file; returns the best DetectionResult (never raises for
    ordinary unreadable content — those become skip_reason entries)."""
    min_conf = min_confidence if min_confidence is not None else config.detect_min_confidence()
    pv = preview(path)
    if pv.ext == ".pdf":
        if not pv.pdf_has_text or len(pv.text.strip()) < 40:
            return DetectionResult("BANK", "bank_pdf", 0.0, hints=["scanned"],
                                   skip_reason="scanned_or_image_pdf", ext=pv.ext)
    if pv.ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"):
        return DetectionResult("UNKNOWN", "image", 0.0,
                               skip_reason="unsupported_image", ext=pv.ext)
    if pv.ext in (".zip", ".7z", ".rar"):
        return DetectionResult("UNKNOWN", "archive", 0.0,
                               skip_reason="archive", ext=pv.ext)
    if pv.binary:
        return DetectionResult("UNKNOWN", "binary", 0.0,
                               skip_reason="binary_content",
                               hints=["newgen/image-scan"], ext=pv.ext)
    if pv.ext not in (".pdf", ".csv", ".txt", ".xlsx", ".xls", ".ods"):
        return DetectionResult("UNKNOWN", "unknown", 0.0,
                               skip_reason="unsupported_type", ext=pv.ext)

    cands = score_candidates(path)
    if not cands:
        return DetectionResult("UNKNOWN", "unknown", 0.0,
                               skip_reason="no_match", ext=pv.ext)
    best = cands[0]
    # Non-data documents: skip, but record the reason so the pipeline can
    # distinguish "not parseable" from "parseable".
    if best["format"] == "email_cover":
        return DetectionResult("UNKNOWN", "email_cover", best["confidence"],
                               candidates=cands, hints=best.get("hints", []),
                               skip_reason="email_cover_no_data", ext=pv.ext)
    if best["format"] == "caf_form":
        return DetectionResult("SUBSCRIBER", "caf_form", best["confidence"],
                               candidates=cands, hints=best.get("hints", []),
                               skip_reason="caf_form_no_data", ext=pv.ext)
    result = DetectionResult(
        dataset=best["dataset"], format=best["format"],
        confidence=best["confidence"], candidates=cands,
        hints=best.get("hints", []), ext=pv.ext,
    )
    # Canonical bank ids are extension-specific (bank_csv/bank_xls/bank_ods/…)
    if result.dataset == "BANK" and result.format == "bank_xlsx":
        _by_ext = {".xlsx": "bank_xlsx", ".xls": "bank_xls", ".ods": "bank_ods",
                   ".csv": "bank_csv", ".txt": "bank_txt"}
        result.format = _by_ext.get(pv.ext, "bank_xlsx")
    # PDFs default to bank-line when nothing else matched (statement evidence)
    if result.dataset == "UNKNOWN" and pv.ext == ".pdf":
        result = DetectionResult("BANK", "bank_pdf", 0.3, candidates=cands,
                                 hints=["pdf_default"], ext=pv.ext)
    if result.confidence < min_conf:
        result.ask_user = True
    return result


def classify(path: str) -> dict:
    """v2-compat API: {'dataset', 'format', 'ext'} (best guess, no raise).

    Unrecognised *parseable* files default to the BANK family by extension,
    matching v2 behaviour (a bank parser is the least-damage fallback and the
    extension-based row/table parsers handle them gracefully).
    """
    r = classify_file(path)
    if r.dataset == "UNKNOWN" and r.skip_reason in ("", "no_match") and not r.ask_user:
        ext = r.ext or os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            return {"dataset": "BANK", "format": "bank_pdf", "ext": ext}
        if ext in (".xlsx", ".xls", ".ods"):
            return {"dataset": "BANK", "format": "bank_xlsx", "ext": ext}
        return {"dataset": "BANK", "format": "bank_csv", "ext": ext}
    return {"dataset": r.dataset, "format": r.format, "ext": r.ext}


def classify_xlsx(path: str) -> dict:
    """v2-compat API: classification for spreadsheet inputs."""
    r = classify_file(path)
    ext = ".xlsx"
    if r.dataset == "UNKNOWN" and r.skip_reason == "":
        return {"dataset": "BANK", "format": "bank_xlsx", "ext": ext}
    return {"dataset": r.dataset, "format": r.format, "ext": ext}


def is_supported(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".pdf", ".csv", ".txt", ".xlsx", ".xls", ".ods"):
        return True
    r = classify_file(path)
    return r.skip_reason == "" and r.dataset != "UNKNOWN"


def scanned_pdf(path: str) -> bool:
    """True when the PDF has no extractable text (image-only)."""
    pv = preview(path)
    return pv.is_pdf and not pv.pdf_has_text
