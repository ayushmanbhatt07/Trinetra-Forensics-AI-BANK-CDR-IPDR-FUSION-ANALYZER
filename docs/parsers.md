# Parsers Ecosystem

The parsing layer is responsible for translating messy, heterogeneous raw files into structured dictionaries. It lives in `backend/parsers/`, `backend/parsers_bank.py`, `backend/parsers_cdr.py`, and `backend/parsers_ipdr.py`.

---

## 1. Auto-Detection & Fingerprinting (`backend/detect/`)
The system does not rely on manual user tagging or filenames to determine the file type. Instead, `backend/detect/engine.py` and `fingerprints.py` inspect the raw file content:
- **PDF Layout Inspection**: Extracts text geometries from early pages, identifies IFSC patterns, and matches layout tokens.
- **CSV/Excel Heuristics**: Reads header rows and matches column signatures against known banking and telecom schema dictionaries.
- **Scanned PDF Identification**: Flags image-only/scanned PDFs gracefully to notify the investigator.

---

## 2. Bank Parsers (`backend/parsers_bank.py`, `backend/parsers/bank.py`)

### Supported Bank Layouts (14 Dialects)
1. **Axis Bank** (7-column and 8-column variations)
2. **HDFC Bank** (Complex multi-line narration and transaction tables)
3. **ICICI Bank** (Cheque and reference extraction)
4. **State Bank of India (SBI)** (Passbook and corporate net-banking exports)
5. **Punjab National Bank (PNB)** (Acct-range / GL-level parsing)
6. **Kotak Mahindra Bank** (Withdrawal Dr/Cr split parsing)
7. **Bandhan Bank** (Two-line split-year date splicing)
8. **Federal Bank** (Withdrawal/Deposit formats)
9. **Union Bank of India** (Particulars and balance layout)
10. **Utkarsh Small Finance Bank** (Value date and account parsing)
11. **Yes Bank** (Reference and description columns)
12. **Associate Co-operative Bank** (Multi-column cooperative layouts)
13. **City Union Bank** (Chq no and balance layout)
14. **Central Bank of India / RBL Bank** (Excel and CSV standard exports)

### PDF Geometric Extraction Logic
The bank PDF parser uses `pdfplumber` for geometric table extraction. It features:
- **Split Date Joining**: Automatically splices dates split across line wraps (e.g. `01-JAN-` wrapped to `2025`).
- **Directional Amount Inference**: In balance-only or single-amount rows, computes the delta from previous balance ($Balance_t - Balance_{t-1}$) or inspects `DR`/`CR` suffixes to accurately determine Credit vs. Debit.
- **Narration Entity Extraction**: Extracts UPI VPAs (`name@bank`), UTR/RRN numbers, IMPS/NEFT account numbers, and phone numbers directly from unstructured narration text.

---

## 3. Telecom Parsers (`backend/parsers_cdr.py`, `backend/parsers_ipdr.py`)

### Supported Carriers & Layouts
- **Bharti Airtel** (Standard CDR, SDR, GPRS/IPDR)
- **Reliance Jio** (Nodal and VVM voice/SMS dumps, IPv6 IPDR logs)
- **Vodafone Idea (Vi)** (CDR voice, SMS, and cell-site exports)
- **BSNL / MTNL** (Legacy fixed-width and comma-delimited logs)

### CDR Extraction Schema
Extracts `A-Party (Calling Number)`, `B-Party (Called Number)`, `Call Date`, `Call Time`, `Duration (sec)`, `Call Type (Voice/SMS/Incoming/Outgoing)`, `IMEI`, `IMSI`, `First Cell ID`, and `Last Cell ID`. Standardizes carrier differences (e.g. `CALLING_NO` vs `A_NUM` vs `ORIGINATING_MSISDN`).

### IPDR Session Extraction Schema
Extracts `MSISDN`, `Source IP`, `Source Port`, `Destination IP`, `Destination Port`, `Session Start TS`, `Session End TS`, `Byte Volume`, `APN`, `IMEI`, and `IMSI`.

---

## 4. Cybercrime Complaints Ingestion (`backend/pipeline.py`)
- Automatically detects and parses National Cyber Crime Reporting Portal (**NCRP**) complaint ledgers (`all_account_complain.csv`).
- Extracts Acknowledgement Number, Beneficiary Account, IFSC, Complainant State, District, Police Station, and Investigating Officer details.
- Feeds known fraudulent beneficiary accounts directly into the entity risk scoring matrix.

---

## 5. Graceful Failure & Fault Tolerance
- **Corrupted / Empty Files**: Validated with zero crash guarantees; returns informative skip messages in the pipeline status.
- **Wrong Column Mappings**: Filtered through heuristic threshold checks to avoid contaminating the canonical database.
