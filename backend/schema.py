"""Canonical v3 internal schemas shared by every parser and the rest of the pipeline.

Every ingested file — regardless of provider or layout — is normalised onto one
of the canonical record shapes below (BankTransaction, CDREvent, IPDREvent,
SubscriberRecord, ComplaintRecord). Timestamps are stored as ISO strings plus
integer epoch seconds so fusion can do pure numeric comparisons.

Entity schemas (Customer, Phone, Account, IMEI, Device, IP, UPI, Beneficiary,
Location, Tower, Case, Investigation, TimelineEvent, RiskScore) define what the
entity registry and the Neo4j-ready graph layer operate on. Raw provider
columns never escape the parser layer.

Inputs:  nothing (constant catalog).
Outputs: record-column catalogs, entity-type catalog, format registry, and the
         `blank_record(dataset)` / `blank_entity(kind)` helpers.
Workflow: import schema constants wherever canonical records are produced or
          consumed; use the format registry to enumerate supported formats.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical BANK transaction record
# ---------------------------------------------------------------------------
BANK_COLUMNS = [
    "txn_id",            # stable id: source file + index
    "bank",              # bank name as printed on the statement
    "account_no",        # account number of the statement holder
    "account_name",      # account holder name
    "ifsc",              # branch IFSC
    "branch",            # branch name
    "date",              # ISO YYYY-MM-DD (transaction date)
    "time",              # HH:MM:SS or "" when the statement has no clock time
    "ts",                # epoch seconds (None when time is unknown -> date at 00:00)
    "value_date",        # ISO YYYY-MM-DD or ""
    "mode",              # UPI / IMPS / NEFT / RTGS / ATM / POS / CHEQUE / CASH / MBB / ...
    "narration",         # full raw narration text (multi-line joined)
    "debit",             # float or None
    "credit",            # float or None
    "balance",           # float or None (post-transaction)
    "txn_type",          # D / C
    "chq_ref_no",        # cheque number / reference printed by the bank
    # Entities recovered from the narration / statement ("" when unknown)
    "sender_phone",      # 12-digit '91' + 10 canonical
    "receiver_phone",
    "counterparty_name", # name decoded from narration (UPI/IMPS/NEFT beneficiary)
    "counterparty_bank", # bank of the counterparty decoded from narration
    "upi_id",            # vpa@bankpsp
    "upi_ref",           # UPI reference number when present
    "receiver_account",  # account number when recoverable from narration
    "source_file",       # absolute path of the ingested file
    "source_format",     # e.g. axis_pdf, hdfc_pdf, centralbank_xlsx

    # --- New Forensic Semantic Intelligence Fields ---
    "merchant_name",     # unified merchant entity
    "merchant_category", # e.g. Food, Travel, Salary, Unknown
    "payment_gateway",   # e.g. NPCI, Razorpay, BillDesk
    "purpose",           # inferred purpose of transfer
    "geo_location",      # inferred lat/lon if any
    "risk_tags",         # comma separated behavioral tags
    "confidence_score",  # 0-100 score of parsing confidence
    "salary_flag",       # 1 if likely salary, else 0
    "recurring_flag",    # 1 if recurring payment
    "loan_flag",         # 1 if loan/EMI
    "suspicious_flag",   # 1 if tagged by LLM/Semantic rules
    "cash_burst_flag",   # 1 if rapid ATM/Cash withdrawal
    
    # --- Engineered Features ---
    "feat_rolling_mean",
    "feat_rolling_std",
    "feat_rolling_max",
    "feat_historical_mean",
    "feat_historical_median",
    "feat_max_withdrawal",
    "feat_max_deposit",
    "feat_balance_volatility",
    "feat_hour_of_day",
    "feat_day_of_week",
    "feat_is_weekend",
    "feat_is_night",
    "feat_merchant_diversity",
    "feat_round_amount",
    "feat_repeated_amount",
    "feat_daily_txns",
    "feat_daily_spend",
    "feat_burst_indicator",
    "feat_rapid_cash_out",
    "feat_days_since_last_txn",
    "feat_dormant_activation",
    "feat_coarse_anomaly_risk",
]

# ---------------------------------------------------------------------------
# Canonical CDR event record
# ---------------------------------------------------------------------------
CDR_COLUMNS = [
    "cdr_id",
    "operator",          # Jio / Vi / Airtel / ...
    "query_type",        # MSISDN / IMEI / IMSI / CELL_ID
    "query_value",       # raw value the ticket was raised for
    "a_number",          # caller / target (canonical 91XXXXXXXXXX)
    "b_number",          # called party (canonical, "" for SMS-service codes)
    "call_type",         # IN / OUT / SMS / IN_SMS / OUT_SMS / VOICE / SMT/SMO/DSM mapped
    "service_type",      # Voice / SMS / data as printed
    "date",              # ISO
    "time",              # HH:MM:SS
    "ts",                # epoch seconds
    "duration_sec",      # int
    "imei",              # device id of the target line
    "imsi",              # subscriber id of the target line
    "cell_id_first",     # tower the call started on
    "cell_id_last",
    "bts_location_first",
    "bts_location_last",
    "roaming_circle",    # e.g. GJ, UP-W, Guj-Vodafone - India
    "msc_id",
    "lrn_b_party",
    "lrn_translation",
    "lat_first",         # v3: first-cell latitude when the export carries it
    "lon_first",
    "lat_last",
    "lon_last",
    "source_file",
    "source_format",
]

# ---------------------------------------------------------------------------
# Canonical IPDR record
# ---------------------------------------------------------------------------
IPDR_COLUMNS = [
    "ipdr_id",
    "operator",          # Jio / Vi / ...
    "msisdn",            # subscriber phone (canonical)
    "imsi",
    "imei",
    "user_id",           # auth user id when present
    "mac",               # source MAC / device id
    "source_ip",         # address assigned to the subscriber
    "public_ip",
    "dest_ip",
    "dest_port",
    "apn",
    "cell_id",
    "date",              # ISO start date
    "start_time",        # HH:MM:SS
    "end_time",
    "start_ts",          # epoch seconds
    "end_ts",
    "duration_sec",
    "volume_up",         # bytes
    "volume_down",       # bytes
    "roaming_circle",
    "is_static",
    "source_file",
    "source_format",
]

# ---------------------------------------------------------------------------
# Subscriber record (SDR / CAF / subscriber-detail exports)  [v3]
# ---------------------------------------------------------------------------
SUBSCRIBER_COLUMNS = [
    "sub_id",
    "operator",          # Airtel / Jio / Vi / BSNL ...
    "msisdn",            # canonical phone
    "imsi",
    "imei",
    "subscriber_name",
    "father_name",
    "date_of_birth",
    "gender",
    "id_type",           # e.g. AADHAAR / VOTER / PASSPORT
    "id_number",
    "address",           # joined subscriber address lines
    "circle",
    "connection_type",   # PREPAID / POSTPAID / BROADBAND ...
    "sim_type",
    "alternate_number",
    "activation_date",
    "email",
    "query_type",        # how this record was fetched (MSISDN/IMEI ticket)
    "query_value",
    "source_file",
    "source_format",
]

# ---------------------------------------------------------------------------
# NCRP complaint record (police fraud-account ledger)  [v3]
# ---------------------------------------------------------------------------
COMPLAINT_COLUMNS = [
    "complaint_id",
    "ack_no",
    "account_no",
    "ifsc",
    "bank_name",
    "state",
    "district",
    "police_station",
    "officer_name",
    "designation",
    "mobile",
    "email",
    "source_file",
]

DATASET_TYPES = ("BANK", "CDR", "IPDR", "SUBSCRIBER", "COMPLAINT")

SUBFORMAT_BANK = "BANK"
SUBFORMAT_CDR = "CDR"
SUBFORMAT_IPDR = "IPDR"
SUBFORMAT_SUBSCRIBER = "SUBSCRIBER"
SUBFORMAT_COMPLAINT = "COMPLAINT"

# ---------------------------------------------------------------------------
# Format registry (detector + parser plugin catalogs)
# ---------------------------------------------------------------------------
FORMAT_JIO_VVM = "jio_vvm"          # CDR  F1
FORMAT_VI = "vi"                    # CDR  F2
FORMAT_JIO_NODAL = "jio_nodal"      # CDR  F3
FORMAT_AIRTEL = "airtel"            # CDR  F4
FORMAT_AIRTEL_SDR = "airtel_sdr"    # CDR  F5 (subscriber detail)
FORMAT_JIO_IPV6 = "jio_ipv6"        # IPDR
FORMAT_IPDR_XLSX = "ipdr_xlsx"      # IPDR generic xlsx
FORMAT_IPDR_CSV = "ipdr_csv"        # IPDR generic csv [v3]
FORMAT_BANK_PDF = "bank_pdf"
FORMAT_BANK_XLSX = "bank_xlsx"
FORMAT_BANK_XLS = "bank_xls"        # legacy binary Excel [v3]
FORMAT_BANK_ODS = "bank_ods"        # OpenDocument spreadsheet [v3]
FORMAT_BANK_TXT = "bank_txt"
FORMAT_BANK_CSV = "bank_csv"
FORMAT_COMPLAINTS = "ncrp_complaints"
FORMAT_SYNTHETIC_BANK = "synthetic_bank"   # problem-statement clean/anomalous exports
FORMAT_SYNTHETIC_CDR = "synthetic_cdr"
FORMAT_SYNTHETIC_IPDR = "synthetic_ipdr"

# Which physical file extensions each format family can arrive in.
FORMAT_FILE_TYPES = {
    FORMAT_JIO_VVM: {".csv", ".txt"},
    FORMAT_VI: {".csv", ".txt"},
    FORMAT_JIO_NODAL: {".csv", ".txt"},
    FORMAT_AIRTEL: {".csv", ".txt"},
    FORMAT_AIRTEL_SDR: {".csv", ".txt"},
    FORMAT_JIO_IPV6: {".csv", ".txt"},
    FORMAT_IPDR_XLSX: {".xlsx", ".xls"},
    FORMAT_IPDR_CSV: {".csv", ".txt"},
    FORMAT_BANK_PDF: {".pdf"},
    FORMAT_BANK_XLSX: {".xlsx"},
    FORMAT_BANK_XLS: {".xls"},
    FORMAT_BANK_ODS: {".ods"},
    FORMAT_BANK_TXT: {".txt"},
    FORMAT_BANK_CSV: {".csv"},
    FORMAT_COMPLAINTS: {".csv", ".txt", ".xlsx"},
    FORMAT_SYNTHETIC_BANK: {".csv", ".txt"},
    FORMAT_SYNTHETIC_CDR: {".csv", ".txt"},
    FORMAT_SYNTHETIC_IPDR: {".csv", ".txt"},
}

BANK_FAMILIES = (
    "axis",
    "bandhan",
    "federal",
    "hdfc",
    "icici",
    "kotak",
    "pnb",
    "union",
    "utkarsh",
    "yes",
    "uco",
    "centralbank",
    "generic",
)

# ---------------------------------------------------------------------------
# Entity schemas  [v3] — keys the entity registry and graph layer use
# ---------------------------------------------------------------------------
ENTITY_PHONE = "phone"
ENTITY_ACCOUNT = "account"
ENTITY_UPI = "upi"
ENTITY_IMEI = "imei"
ENTITY_IMSI = "imsi"
ENTITY_IP = "ip"
ENTITY_NAME = "name"            # beneficiary / counterparty name
ENTITY_DEVICE = "device"        # MAC / device-id
ENTITY_LOCATION = "location"    # BTS / tower site
ENTITY_BENEFICIARY = "beneficiary"
ENTITY_CUSTOMER = "customer"
ENTITY_CASE = "case"
ENTITY_INVESTIGATION = "investigation"

ENTITY_TYPES = (
    ENTITY_PHONE, ENTITY_ACCOUNT, ENTITY_UPI, ENTITY_IMEI, ENTITY_IMSI,
    ENTITY_IP, ENTITY_NAME, ENTITY_DEVICE, ENTITY_LOCATION, ENTITY_BENEFICIARY,
    ENTITY_CUSTOMER, ENTITY_CASE, ENTITY_INVESTIGATION,
)

ENTITY_FIELDS = {
    ENTITY_PHONE: ("value", "roles", "records", "sources", "account_no", "imei", "imsi", "risk"),
    ENTITY_ACCOUNT: ("value", "bank", "ifsc", "holder", "records", "phones", "risk"),
    ENTITY_UPI: ("value", "records", "accounts", "risk"),
    ENTITY_IMEI: ("value", "phones", "records", "risk"),
    ENTITY_IMSI: ("value", "phones", "records", "risk"),
    ENTITY_IP: ("value", "msisdns", "records", "risk"),
    ENTITY_NAME: ("value", "records", "accounts", "risk"),
    ENTITY_DEVICE: ("value", "phones", "records", "risk"),
    ENTITY_LOCATION: ("value", "cell_ids", "records", "lat", "lon"),
    ENTITY_BENEFICIARY: ("value", "records", "risk"),
    ENTITY_CUSTOMER: ("value", "phones", "accounts", "records"),
    ENTITY_CASE: ("value", "title", "entities", "records"),
    ENTITY_INVESTIGATION: ("value", "case_no", "entities", "risk", "summary"),
}

# ---------------------------------------------------------------------------
# Timeline event kinds  [v3]
# ---------------------------------------------------------------------------
EVENT_BANK = "bank"
EVENT_CDR = "cdr"
EVENT_IPDR = "ipdr"
EVENT_SUBSCRIBER = "subscriber"
EVENT_COMPLAINT = "complaint"
EVENT_CORRELATION = "correlation"
EVENT_ANOMALY = "anomaly"

EVENT_KINDS = (EVENT_BANK, EVENT_CDR, EVENT_IPDR, EVENT_SUBSCRIBER,
               EVENT_COMPLAINT, EVENT_CORRELATION, EVENT_ANOMALY)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_RECORD_COLUMNS = {
    "BANK": BANK_COLUMNS,
    "CDR": CDR_COLUMNS,
    "IPDR": IPDR_COLUMNS,
    "SUBSCRIBER": SUBSCRIBER_COLUMNS,
    "COMPLAINT": COMPLAINT_COLUMNS,
}


def blank_record(dataset: str) -> dict:
    """Return an empty canonical record dict for `dataset` (all keys '')."""
    return {k: "" for k in _RECORD_COLUMNS.get(dataset, BANK_COLUMNS)}


def blank_entity(kind: str) -> dict:
    """Return an empty entity dict with the declared fields."""
    return {k: "" for k in ENTITY_FIELDS.get(kind, ("value",))}


def entity_index(name: str) -> int:
    """Stable 0-based type id (used by the Neo4j-ready graph schema)."""
    return ENTITY_TYPES.index(name) if name in ENTITY_TYPES else -1
