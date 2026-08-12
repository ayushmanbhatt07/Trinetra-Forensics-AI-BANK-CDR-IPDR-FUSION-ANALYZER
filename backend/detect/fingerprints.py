"""Fingerprint catalog for the confidence-scored format detector.

Each entry maps a format family to the signals that identify it:
    keywords   substrings that must appear in the preview text
    headers    header-row cells (first non-empty row of a table/CSV/XLSX)
    regex      compiled patterns searched over the preview
    magic      file magic bytes (extensionless files)

Signals carry weights; the engine sums matched weights into a 0..1 confidence.
The catalog is configuration-driven: add a new operator/bank layout by adding
one entry here (or subclassing in a plugin module).

Inputs:  nothing (catalog).
Outputs: FORMATS list of FormatFingerprint objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FormatFingerprint:
    format_id: str            # stable id, matches schema.FORMAT_*
    dataset: str              # BANK | CDR | IPDR | SUBSCRIBER | COMPLAINT
    file_types: frozenset     # physical extensions the family arrives in
    keywords: tuple[str, ...] = ()
    headers: tuple[str, ...] = ()     # cell prefixes (case-insensitive, stripped)
    regex: tuple[str, ...] = ()
    magic: tuple[bytes, ...] = ()
    weight: float = 1.0
    note: str = ""

    def __post_init__(self):
        object.__setattr__(self, "regex",
                           tuple(re.compile(p, re.I | re.S) for p in self.regex))


def _ft(*exts: str) -> frozenset:
    return frozenset(exts)


# ---------------------------------------------------------------------------
# CDR — telecom operators
# ---------------------------------------------------------------------------
CDR_VVM = FormatFingerprint(
    format_id="jio_vvm", dataset="CDR", file_types=_ft(".csv", ".txt"),
    keywords=("calling party telephone number", "input value (msisdn",
              "called party telephone number"),
    headers=("Calling Party Telephone Number", "Input Value (MSISDN"),
    regex=(r"call\s+date[\s,]", r"call\s+duration[\s,]"),
    weight=1.0, note="Jio VVM ticket export")

CDR_VI = FormatFingerprint(
    format_id="vi", dataset="CDR", file_types=_ft(".csv", ".txt"),
    keywords=("target /a party number", "b party number",
              "vodafone idea call data records", "allindia report",
              "main cdr report", "call initiation time"),
    headers=("Target /A PARTY NUMBER", "Target /A PARTY"),
    regex=(r"call\s+date[\s,]", r"first\s+cell\s+global\s+id"),
    weight=1.0, note="Vodafone Idea CDR")

CDR_JIO_NODAL = FormatFingerprint(
    format_id="jio_nodal", dataset="CDR", file_types=_ft(".csv", ".txt"),
    keywords=("nodaloffice", "search criteria :", "enquirer name :",
              "other_party_no", "call_initiation_time"),
    headers=("SL_NO", "Mobile_No"),
    regex=(r"sl_no[\s,]+\s*mobile_no", r"call_initiation_time\s*\(cit\)"),
    weight=1.0, note="Jio nodal-office export")

CDR_AIRTEL = FormatFingerprint(
    format_id="airtel", dataset="CDR", file_types=_ft(".csv", ".txt"),
    keywords=("bharti airtel limited", "call details of", "pan india",
              "target no", "b party no", "first cgi"),
    headers=("Target No", "B Party No"),
    regex=(r"dur\s*\(\s*s\s*\)",),
    weight=1.0, note="Bharti Airtel CDR")

CDR_AIRTEL_SDR = FormatFingerprint(
    format_id="airtel_sdr", dataset="SUBSCRIBER", file_types=_ft(".csv", ".txt"),
    keywords=("subscriber address1", "dealer retailer code", "sim type",
              "father name"),
    headers=("MSISDN", "Subscriber Address1"),
    regex=(r"subscriber\s+address\d", r"dealer\s+retailer\s+code"),
    weight=1.0, note="Airtel subscriber detail (SDR/CAF)")

# ---------------------------------------------------------------------------
# IPDR
# ---------------------------------------------------------------------------
IPDR_JIO_IPV6 = FormatFingerprint(
    format_id="jio_ipv6", dataset="IPDR", file_types=_ft(".csv", ".txt"),
    keywords=("landline/msisdn", "ip address assigned/translated",
              "source mac-id", "data volume up link"),
    headers=("Landline/MSISDN", "Source IP Address"),
    regex=(r"start\s+date\s+of\s+public\s+ip", r"session\s+duration"),
    weight=1.0, note="Jio IPv6 session export")

IPDR_XLSX = FormatFingerprint(
    format_id="ipdr_xlsx", dataset="IPDR", file_types=_ft(".xlsx", ".xls"),
    keywords=("source ip address", "session duration", "time(ist)",
              "f date", "f time", "t date", "f time"),
    headers=("No.", "IP Address", "IP", "F DATE", "T DATE"),
    regex=(r"source\s+ip\s+address", r"\bf\s*date[\s,]+\s*f\s*time",
           r"ip\s+address[\s,]+.*date"),
    weight=1.0, note="Generic IPDR spreadsheet")

IPDR_CSV = FormatFingerprint(
    format_id="ipdr_csv", dataset="IPDR", file_types=_ft(".csv", ".txt"),
    keywords=("source ip", "destination port", "start time", "end time",
              "time(ist)"),
    headers=("IP Address", "IP", "Source IP"),
    regex=(r"(source\s+)?ip\s+address.*(time|date|port)",),
    weight=0.8, note="Generic IPDR text export")

# ---------------------------------------------------------------------------
# BANK — statements (PDF/TXT/CSV/XLSX/XLS/ODS)
# ---------------------------------------------------------------------------
BANK_LINE = FormatFingerprint(
    format_id="bank_pdf", dataset="BANK", file_types=_ft(".pdf"),
    keywords=("statement of account", "statement of axis", "bank statement",
              "transaction particulars", "closing balance", "opening balance",
              "account no", "ifsc", "narration", "withdrawals", "deposits",
              "debits", "credits", "balance", "tran date", "value date",
              "debit amount", "credit amount"),
    headers=(),
    regex=(r"statement\s+of\s+(account|axis)", r"transaction\s+particulars",
           r"account\s+no", r"opening\s+balance"),
    weight=0.9, note="Bank statement (line layout)")

BANK_TABULAR = FormatFingerprint(
    format_id="bank_xlsx", dataset="BANK",
    file_types=_ft(".xlsx", ".xls", ".ods", ".csv", ".txt"),
    keywords=("transaction particulars", "debit", "credit", "balance",
              "narration", "withdrawals", "deposits", "closing balance",
              "account no", "ifsc", "value date", "tran date", "txn date",
              "tran_amount", "txn_desc", "naration", "txn_branch"),
    headers=("DATE", "TXN DATE", "TRAN DATE", "NARRATION", "PARTICULARS",
             "DEBIT", "CREDIT", "BALANCE", "ACCOUNT", "TRAN_AMOUNT"),
    regex=(r"debit[\s/]+credit", r"withdrawals?[\s/]+deposits?",
           r"tran\s+amount"),
    weight=0.8, note="Bank statement (tabular layout)")

# ---------------------------------------------------------------------------
# Synthetic problem-statement exports (data/clean, data/anomalous)
# ---------------------------------------------------------------------------
SYN_BANK = FormatFingerprint(
    format_id="synthetic_bank", dataset="BANK", file_types=_ft(".csv", ".txt"),
    keywords=("sender_phone_number", "receiver_phone_number",
              "sender_account_number", "transaction_amount"),
    headers=("Transaction_ID", "Sender_Account_Number", "Transaction_Amount",
             "Receiver_Phone_Number"),
    weight=1.3, note="Synthetic problem-statement bank export")

SYN_CDR = FormatFingerprint(
    format_id="synthetic_cdr", dataset="CDR", file_types=_ft(".csv", ".txt"),
    keywords=("a_party_number", "b_party_number", "call_duration_seconds",
              "first_cell_global_id", "roaming_network_circle"),
    headers=("CDR_ID", "A_Party_Number", "Call_Duration_Seconds"),
    weight=1.3, note="Synthetic problem-statement CDR export")

SYN_IPDR = FormatFingerprint(
    format_id="synthetic_ipdr", dataset="IPDR", file_types=_ft(".csv", ".txt"),
    keywords=("subscriber_msisdn", "session_duration_seconds",
              "destination_ip_address"),
    headers=("IPDR_ID", "Subscriber_MSISDN", "Source_IP_Address"),
    weight=1.3, note="Synthetic problem-statement IPDR export")

# ---------------------------------------------------------------------------
# NCRP complaints ledger
# ---------------------------------------------------------------------------
COMPLAINTS = FormatFingerprint(
    format_id="ncrp_complaints", dataset="COMPLAINT", file_types=_ft(".csv", ".txt", ".xlsx"),
    keywords=("acknowledgement", "police station", "complain"),
    headers=("Acknowledgement no", "Account No", "IFSC Code"),
    regex=(r"acknowledgement\s*no", r"police\s*station"),
    weight=1.0, note="NCRP fraud-account complaint ledger")

# ---------------------------------------------------------------------------
# Non-data documents found in the wild (email covers, CAF forms)
# ---------------------------------------------------------------------------
EMAIL_COVER = FormatFingerprint(
    format_id="email_cover", dataset="UNKNOWN",
    file_types=_ft(".pdf", ".txt"),
    keywords=("fw:", "fw re", "this mail is from external domain",
              "crime branch surat", "ccps fir", "importance:",
              "part1/1", "crimebranch2nd2024@gmail.com"),
    headers=(),
    regex=(r"^(from|sent|to|subject|importance|attachments)[\s:]+",
           r"\d+\s+attachments?\s*\(", r"mail\s*-\s*\w+@"),
    weight=1.3, note="E-mail thread / cover letter (data in attachments)")

CAF_FORM = FormatFingerprint(
    format_id="caf_form", dataset="SUBSCRIBER",
    file_types=_ft(".pdf", ".txt"),
    keywords=("customer application form", "caf no", "prepaid customer application",
              "reliance jio infocomm", "service center", "postpaid customer application",
              "registered office", "circle office"),
    headers=(),
    regex=(r"customer\s+application\s+form", r"caf\s*no\.?", r"subscriber\s*id"),
    weight=1.2, note="Customer Application Form (subscriber document)")

SUBSCRIBER_DETAIL = FormatFingerprint(
    format_id="subs_detail", dataset="SUBSCRIBER",
    file_types=_ft(".pdf", ".txt"),
    keywords=("subscriber details report", "deactivation_da", "subscriber_typ",
              "ported_date", "mnp_status", "current operator", "prev operator"),
    headers=(),
    regex=(r"subscriber\s+details\s+report", r"mobile\s+number\s*:"),
    weight=1.2, note="Operator subscriber-detail report (MSISDN/IMEI/CAF)")

FORMATS: list[FormatFingerprint] = [
    CDR_VVM, CDR_VI, CDR_JIO_NODAL, CDR_AIRTEL, CDR_AIRTEL_SDR,
    IPDR_JIO_IPV6, IPDR_XLSX, IPDR_CSV,
    BANK_LINE, BANK_TABULAR, COMPLAINTS,
    SYN_BANK, SYN_CDR, SYN_IPDR,
    EMAIL_COVER, CAF_FORM, SUBSCRIBER_DETAIL,
]

FORMAT_BY_ID = {f.format_id: f for f in FORMATS}
