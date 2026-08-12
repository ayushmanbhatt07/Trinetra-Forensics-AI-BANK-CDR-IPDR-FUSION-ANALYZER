# Parsers Ecosystem

The parsing layer is responsible for translating messy, heterogeneous raw files into structured dictionaries. It lives primarily in the `backend/parsers/` directory.

## 1. Auto-Detection (Fingerprinting)
The system does not rely on user input or filenames to determine the file type. Instead, `backend/detect/fingerprints.py` inspects the file contents:
- **For PDFs**: It extracts text from the first page and runs regex heuristics to find operator or bank names.
- **For CSV/Excel**: It reads the header row and matches it against known schema templates.

## 2. Bank Parsers (`parsers_bank.py`)
### Supported Formats
* **SBI (PDF / Excel)**: Handles multi-page table continuation and specific date formats.
* **HDFC (PDF / Excel)**: Manages complex merged cells often found in HDFC exports.
* **Generic CSV**: A fallback parser for standard tabular transaction data.

### Extraction Logic
The bank parser uses `pdfplumber` to extract tables from PDFs. It applies heuristic cleaning to remove headers/footers and reconstructs broken rows before mapping columns to `Date`, `Description`, `Debit`, `Credit`, and `Balance`.

## 3. Telecom Parsers (`parsers_cdr.py`, `parsers_ipdr.py`)
### Supported Operators
* **Jio, Airtel, Vi, BSNL**

### CDR Extraction
Extracts `Calling Number`, `Called Number`, `Date`, `Time`, `Duration`, `IMEI`, `IMSI`, `First Cell ID`, and `Last Cell ID`. It normalizes variations in operator headers (e.g., "A Party" vs "Calling No").

### IPDR Extraction
Extracts `Source IP`, `Source Port`, `Dest IP`, `Dest Port`, `Start Time`, `End Time`, and `Data Volume`.

## 4. Failure Handling
If a file is corrupted, password-protected, or matches no known fingerprint, the parser raises a graceful error. The file is moved to a `skipped` bin, and the frontend is notified via the pipeline status API. The ingestion pipeline does not crash.
