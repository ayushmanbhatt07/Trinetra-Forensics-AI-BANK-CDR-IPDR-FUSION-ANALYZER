"""Format detection package.

Public API (v2-compatible):
    detect.classify(path)            -> {"dataset", "format", "ext"}
    detect.classify_file(path)       -> DetectionResult (confidence, hints, …)
    detect.score_candidates(path)    -> sorted candidate list
    detect.is_supported(path)        -> bool
    detect.scanned_pdf(path)         -> bool (image-only PDF)

Inputs:  file path (PDF/CSV/TXT/XLSX/XLS/ODS, extensionless content).
Outputs: DetectionResult dataclass (see engine.py).
Workflow: preview -> fingerprint scoring -> best candidate; low confidence is
          surfaced via ask_user so the API layer can ask the investigator.
"""

from .engine import (
    DetectionResult, Preview, classify, classify_file, classify_xlsx,
    is_supported, scanned_pdf, score_candidates,
)

__all__ = [
    "DetectionResult", "Preview", "classify", "classify_file", "classify_xlsx",
    "is_supported", "scanned_pdf", "score_candidates",
]
