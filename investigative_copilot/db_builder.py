import sqlite3
import pandas as pd
from pathlib import Path
from typing import Optional, Union, List, Dict, Any, Tuple
import logging
import bisect

logger = logging.getLogger(__name__)

_BANK_COLS = (
    "transaction_id", "date", "timestamp", "txn_ref_number", "transaction_mode",
    "currency", "transaction_amount", "sender_customer_id", "sender_customer_name",
    "sender_bank_name", "sender_account_number", "sender_account_type",
    "sender_ifsc", "sender_phone_number", "receiver_customer_id",
    "receiver_customer_name", "receiver_bank_name", "receiver_account_number",
    "receiver_account_type", "receiver_ifsc", "receiver_phone_number",
)

_CDR_COLS = (
    "cdr_id", "call_date", "call_start_time", "a_party_number", "b_party_number",
    "call_type", "call_duration_seconds", "imsi", "imei", "first_bts_location",
    "first_cell_global_id", "roaming_network_circle",
)

_IPDR_COLS = (
    "ipdr_id", "session_date", "session_start_time", "subscriber_imsi",
    "subscriber_msisdn", "device_imei", "source_ip_address",
    "destination_ip_address", "destination_port", "cell_global_id",
    "session_duration_seconds",
)

_BC_LINK_COLS = ("transaction_id", "cdr_id", "relationship_type",
                 "time_difference_seconds", "is_correlated")

_CI_LINK_COLS = ("cdr_id", "ipdr_id", "relationship_type",
                 "time_difference_seconds", "is_correlated")

_ANOMALY_COLS = (
    "anomaly_id", "customer_id", "customer_name", "account_no",
    "transaction_id", "cdr_ids", "ipdr_ids", "scenario_type",
    "risk_score", "risk_band", "rules_fired", "amount",
    "difficulty", "source_scope", "is_suspicious",
)

_COMPLAINT_COLS = ("complaint_id", "acknowledgement_no", "account_no", "ifsc",
                   "state", "district", "police_station", "complainant_name",
                   "designation", "mobile", "email")

_SUBSCRIBER_COLS = ("phone", "imsi", "imei", "name", "circle", "operator")


def _norm_phone(p) -> str:
    p = str(p or "")
    digits = "".join(c for c in p if c.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    if len(digits) == 10:
        return "91" + digits
    return ""


def _cdr_party_phones(r: dict) -> set[str]:
    return {p for p in (_norm_phone(r.get("a_number")),
                        _norm_phone(r.get("b_number"))) if p}


class CopilotDBBuilder:
    """SQLite Database Builder for Tri-Netra Forensics Investigative Co-Pilot.

    Two build modes:

    * ``build_database``     — reads reduced CSV datasets from a folder
      (original standalone behaviour, defaults to ``data/new_reduced``).
    * ``build_database_from_bundle`` — builds the same schema from a
      normalized v3 bundle (``{"bank": [...], "cdr": [...], "ipdr": [...]}``),
      deriving the correlation link tables from phone / subscriber-key
      matches inside a time window.
    """

    def __init__(self, data_dir: Optional[Union[str, Path]] = None, db_path: str = ":memory:"):
        if data_dir is None:
            # Default to project_root / data / new_reduced
            project_root = Path(__file__).resolve().parent.parent
            data_dir = project_root / "data" / "new_reduced"
        self.data_dir = Path(data_dir)
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.source: str = "csv"

    def build_database(self) -> sqlite3.Connection:
        """Loads all reduced datasets and creates indexed SQLite tables."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._create_schema(conn)

        # Load datasets
        bank_csv = self.data_dir / "bank_reduced.csv"
        cdr_csv = self.data_dir / "cdr_reduced.csv"
        ipdr_csv = self.data_dir / "ipdr_reduced.csv"
        bank_cdr_gt_csv = self.data_dir / "bank_cdr_ground_truth_reduced.csv"
        cdr_ipdr_gt_csv = self.data_dir / "cdr_ipdr_ground_truth_reduced.csv"
        anomaly_gt_csv = self.data_dir / "anomaly_ground_truth_reduced.csv"

        if bank_csv.exists():
            df_bank = pd.read_csv(bank_csv)
            # Standardize column names for SQL convenience
            df_bank.columns = [c.lower() for c in df_bank.columns]
            df_bank.to_sql("bank_transactions", conn, if_exists="replace", index=False)

        if cdr_csv.exists():
            df_cdr = pd.read_csv(cdr_csv)
            df_cdr.columns = [c.lower() for c in df_cdr.columns]
            df_cdr.to_sql("cdr_records", conn, if_exists="replace", index=False)

        if ipdr_csv.exists():
            df_ipdr = pd.read_csv(ipdr_csv)
            df_ipdr.columns = [c.lower() for c in df_ipdr.columns]
            df_ipdr.to_sql("ipdr_records", conn, if_exists="replace", index=False)

        if bank_cdr_gt_csv.exists():
            df_b_cdr = pd.read_csv(bank_cdr_gt_csv)
            df_b_cdr.columns = [c.lower() for c in df_b_cdr.columns]
            df_b_cdr.to_sql("bank_cdr_links", conn, if_exists="replace", index=False)

        if cdr_ipdr_gt_csv.exists():
            df_c_ipdr = pd.read_csv(cdr_ipdr_gt_csv)
            df_c_ipdr.columns = [c.lower() for c in df_c_ipdr.columns]
            df_c_ipdr.to_sql("cdr_ipdr_links", conn, if_exists="replace", index=False)

        if anomaly_gt_csv.exists():
            df_anomaly = pd.read_csv(anomaly_gt_csv)
            df_anomaly.columns = [c.lower() for c in df_anomaly.columns]
            df_anomaly.to_sql("anomaly_records", conn, if_exists="replace", index=False)

        self._create_indices(conn)
        self.conn = conn
        self.source = "csv"
        logger.info(f"Copilot SQLite database initialized successfully at {self.db_path}")
        return conn

    def build_database_from_bundle(self, bundle: Dict[str, Any],
                                   bank_window_sec: int = 300,
                                   cdr_ipdr_window_sec: int = 900) -> sqlite3.Connection:
        """Builds the copilot SQLite schema from a normalized v3 bundle.

        Link tables are derived, not read:

        * ``bank_cdr_links``  — (txn, cdr) pairs whose bank-phone leg is a CDR
          party number and money falls inside ``bank_window_sec``.
        * ``cdr_ipdr_links``  — (cdr, ipdr) pairs sharing an IMSI/IMEI/MSISDN
          subscriber key with sessions inside ``cdr_ipdr_window_sec``.
        * ``anomaly_records`` — created empty (label table; no GT in bundles).
        """
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        bank = bundle.get("bank", [])
        cdr = bundle.get("cdr", [])
        ipdr = bundle.get("ipdr", [])

        self._create_schema(conn)
        self._insert_rows(conn, "bank_transactions", _BANK_COLS,
                          [self._bank_row(r) for r in bank])
        self._insert_rows(conn, "cdr_records", _CDR_COLS,
                          [self._cdr_row(r) for r in cdr])
        self._insert_rows(conn, "ipdr_records", _IPDR_COLS,
                          [self._ipdr_row(r) for r in ipdr])
        self._insert_rows(conn, "bank_cdr_links", _BC_LINK_COLS,
                          self._bank_cdr_rows(bank, cdr, bank_window_sec))
        self._insert_rows(conn, "cdr_ipdr_links", _CI_LINK_COLS,
                          self._cdr_ipdr_rows(cdr, ipdr, cdr_ipdr_window_sec))
        self._insert_rows(conn, "complaints", _COMPLAINT_COLS,
                          [self._complaint_row(r) for r in bundle.get("complaints", [])])
        self._insert_rows(conn, "subscribers", _SUBSCRIBER_COLS,
                          self._subscribers_from_bundle(bundle))
        self._insert_rows(conn, "anomaly_records", _ANOMALY_COLS,
                          self._anomaly_rows_from_bundle(bundle))

        self._create_indices(conn)
        self.conn = conn
        self.source = "bundle"
        logger.info("Copilot SQLite database built from bundle "
                    f"(bank={len(bank)} cdr={len(cdr)} ipdr={len(ipdr)})")
        return conn

    # ------------------------------------------------------------ mapping

    @staticmethod
    def _bank_row(r: dict) -> list:
        amt_raw = r.get("amount") or r.get("transaction_amount")
        if amt_raw is None or amt_raw == 0:
            if r.get("txn_type") == "C":
                amt_raw = r.get("credit") or r.get("amount") or 0
            else:
                amt_raw = r.get("debit") or r.get("credit") or r.get("amount") or 0
        try:
            amount = float(amt_raw or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        date = str(r.get("date") or "")
        time_ = str(r.get("time") or "")
        timestamp = f"{date} {time_}".strip()
        if not timestamp and r.get("ts") is not None:
            import datetime as _dt
            timestamp = _dt.datetime.utcfromtimestamp(float(r["ts"])).isoformat()
        return [
            str(r.get("txn_id") or r.get("transaction_id") or ""),
            date,
            timestamp,
            str(r.get("txn_ref_number") or r.get("narration") or ""),
            str(r.get("mode") or r.get("transaction_mode") or ""),
            str(r.get("currency") or "INR"),
            amount,
            str(r.get("customer_id") or r.get("sender_customer_id") or ""),
            str(r.get("sender_customer_name") or r.get("account_name") or r.get("customer_name") or ""),
            str(r.get("bank") or r.get("sender_bank_name") or ""),
            str(r.get("sender_account_number") or r.get("account_no") or r.get("sender_account") or ""),
            str(r.get("account_type") or r.get("sender_account_type") or ""),
            str(r.get("ifsc") or r.get("sender_ifsc") or ""),
            str(r.get("sender_phone_number") or r.get("sender_phone") or r.get("phone") or ""),
            str(r.get("counterparty_customer_id") or r.get("receiver_customer_id") or ""),
            str(r.get("receiver_customer_name") or r.get("counterparty_name") or r.get("beneficiary_name") or ""),
            str(r.get("counterparty_bank") or r.get("receiver_bank_name") or ""),
            str(r.get("receiver_account_number") or r.get("receiver_account") or r.get("counterparty_account") or ""),
            str(r.get("counterparty_account_type") or r.get("receiver_account_type") or ""),
            str(r.get("receiver_ifsc") or r.get("counterparty_ifsc") or ""),
            str(r.get("receiver_phone_number") or r.get("receiver_phone") or r.get("counterparty_phone") or ""),
        ]

    @staticmethod
    def _cdr_row(r: dict) -> list:
        dur = r.get("duration_sec") or 0
        try:
            dur = int(dur)
        except (TypeError, ValueError):
            dur = 0
        return [
            str(r.get("cdr_id") or ""),
            str(r.get("date") or ""),
            str(r.get("time") or ""),
            str(r.get("a_number") or ""),
            str(r.get("b_number") or ""),
            str(r.get("call_type") or ""),
            dur,
            str(r.get("imsi") or ""),
            str(r.get("imei") or ""),
            str(r.get("bts_location_first") or ""),
            str(r.get("cell_id_first") or ""),
            str(r.get("roaming_circle") or ""),
        ]

    @staticmethod
    def _ipdr_row(r: dict) -> list:
        dur = r.get("duration_sec") or 0
        try:
            dur = int(float(dur))
        except (TypeError, ValueError):
            dur = 0
        return [
            str(r.get("ipdr_id") or ""),
            str(r.get("date") or ""),
            str(r.get("start_time") or ""),
            str(r.get("imsi") or ""),
            str(r.get("msisdn") or ""),
            str(r.get("imei") or ""),
            str(r.get("source_ip") or ""),
            str(r.get("dest_ip") or ""),
            str(r.get("dest_port") or ""),
            str(r.get("cell_id") or ""),
            dur,
        ]

    @staticmethod
    def _complaint_row(r: dict) -> list:
        return [
            str(r.get("complaint_id") or r.get("acknowledgement_no") or ""),
            str(r.get("acknowledgement_no") or ""),
            str(r.get("account_no") or ""),
            str(r.get("ifsc") or ""),
            str(r.get("state") or ""),
            str(r.get("district") or ""),
            str(r.get("police_station") or ""),
            str(r.get("complainant_name") or r.get("name") or ""),
            str(r.get("designation") or ""),
            str(r.get("mobile") or r.get("phone") or ""),
            str(r.get("email") or ""),
        ]

    @staticmethod
    def _subscriber_row(r: dict) -> list:
        return [
            str(r.get("phone") or r.get("msisdn") or r.get("mobile") or ""),
            str(r.get("imsi") or ""),
            str(r.get("imei") or ""),
            str(r.get("name") or r.get("subscriber_name") or ""),
            str(r.get("circle") or r.get("roaming_circle") or ""),
            str(r.get("operator") or ""),
        ]

    @staticmethod
    def _subscribers_from_bundle(bundle: dict) -> List[list]:
        explicit = bundle.get("subscribers", [])
        if explicit:
            return [CopilotDBBuilder._subscriber_row(r) for r in explicit]

        seen_phones = set()
        subs = []
        for r in bundle.get("bank", []):
            ph = str(r.get("sender_phone") or "").strip()
            name = str(r.get("account_name") or r.get("customer_name") or "").strip()
            if ph and ph not in seen_phones:
                seen_phones.add(ph)
                subs.append([ph, "", "", name, "", ""])
            rph = str(r.get("receiver_phone") or "").strip()
            rname = str(r.get("counterparty_name") or "").strip()
            if rph and rph not in seen_phones:
                seen_phones.add(rph)
                subs.append([rph, "", "", rname, "", ""])
        for c in bundle.get("cdr", []):
            a_ph = str(c.get("a_number") or "").strip()
            circle = str(c.get("roaming_circle") or "").strip()
            imsi = str(c.get("imsi") or "").strip()
            imei = str(c.get("imei") or "").strip()
            if a_ph and a_ph not in seen_phones:
                seen_phones.add(a_ph)
                subs.append([a_ph, imsi, imei, "", circle, ""])
            b_ph = str(c.get("b_number") or "").strip()
            if b_ph and b_ph not in seen_phones:
                seen_phones.add(b_ph)
                subs.append([b_ph, "", "", "", "", ""])
        return subs

    @staticmethod
    def _anomaly_rows_from_bundle(bundle: dict) -> List[list]:
        bank = bundle.get("bank", [])
        if not bank:
            return []

        scored_dict = {}
        try:
            from backend.risk import hybrid
            res = hybrid.hybrid_analyze_fast(bundle)
            if not res:
                res = hybrid.hybrid_analyze(bundle)
            scored_dict = res.get("transactions", {})
        except Exception as e:
            logger.warning(f"Could not compute hybrid anomaly scores for copilot db: {e}")

        bank_by_id = {str(r.get("txn_id") or r.get("transaction_id") or ""): r for r in bank}
        rows = []

        if scored_dict:
            for tid, s in scored_dict.items():
                if not isinstance(s, dict):
                    continue
                risk_score = float(s.get("risk_score") or 0.0)
                if risk_score < 50.0:
                    continue
                raw = bank_by_id.get(str(tid), {})
                cust_id = str(s.get("sender_customer_id") or raw.get("customer_id") or raw.get("sender_customer_id") or "")
                cust_name = str(raw.get("account_name") or raw.get("customer_name") or raw.get("sender_customer_name") or "")
                acc_no = str(s.get("account_no") or raw.get("account_no") or "")
                scenarios = s.get("scenarios") or []
                primary_scenario = scenarios[0].get("scenario") if scenarios else (s.get("rules_fired", ["UNKNOWN"])[0] if s.get("rules_fired") else "Anomaly")
                rules_fired = s.get("rules_fired") or []
                rules_str = ",".join(rules_fired) if isinstance(rules_fired, list) else str(rules_fired)
                amount = float(s.get("amount") or raw.get("debit") or raw.get("credit") or 0.0)
                risk_band = str(s.get("risk_band") or ("CRITICAL" if risk_score >= 75 else "HIGH"))
                diff = "CRITICAL" if risk_score >= 75 else "HIGH"

                rows.append([
                    f"ANOM_{tid}",
                    cust_id,
                    cust_name,
                    acc_no,
                    str(tid),
                    "",
                    "",
                    primary_scenario,
                    risk_score,
                    risk_band,
                    rules_str,
                    amount,
                    diff,
                    "bank_cdr_ipdr_fusion",
                    1,
                ])
        else:
            for r in bank:
                tid = str(r.get("txn_id") or r.get("transaction_id") or "")
                amt = float(r.get("debit") or r.get("credit") or 0.0)
                cust_name = str(r.get("account_name") or r.get("customer_name") or "")
                cust_id = str(r.get("customer_id") or "")
                acc_no = str(r.get("account_no") or "")
                if amt >= 100000:
                    rows.append([
                        f"ANOM_{tid}",
                        cust_id,
                        cust_name,
                        acc_no,
                        tid,
                        "",
                        "",
                        "High Value Transfer",
                        75.0,
                        "HIGH",
                        "HIGH_VALUE_TRANSFER",
                        amt,
                        "HIGH",
                        "bank_transactions",
                        1,
                    ])
        return rows

    # ------------------------------------------------------------ linking

    @staticmethod
    def _bank_cdr_rows(bank: List[dict], cdr: List[dict],
                       window: int) -> List[list]:
        cdr_by_phone: dict[str, list[dict]] = {}
        for c in cdr:
            if not c.get("cdr_id") or c.get("ts") is None:
                continue
            for p in _cdr_party_phones(c):
                cdr_by_phone.setdefault(p, []).append(c)
                
        cdr_indexed: dict[str, tuple[list[float], list[dict]]] = {}
        for p, clist in cdr_by_phone.items():
            clist.sort(key=lambda x: x["ts"])
            cdr_indexed[p] = ([x["ts"] for x in clist], clist)
            
        best: dict[tuple, float] = {}
        for r in bank:
            phones = {_norm_phone(r.get("receiver_phone")),
                      _norm_phone(r.get("sender_phone"))}
            phones.discard("")
            txn_ts = r.get("ts")
            txn_id = r.get("txn_id")
            if txn_ts is None or not txn_id:
                continue
            for ph in phones:
                if ph not in cdr_indexed:
                    continue
                k_ts, c_list = cdr_indexed[ph]
                idx_start = bisect.bisect_left(k_ts, txn_ts - window)
                idx_end = bisect.bisect_right(k_ts, txn_ts + window)
                for c in c_list[idx_start:idx_end]:
                    cts = c["ts"]
                    key = (str(txn_id), str(c["cdr_id"]))
                    delta = abs(cts - txn_ts)
                    if key not in best or delta < best[key]:
                        best[key] = delta
        return [[txn_id, cdr_id, "bank_cdr_correlation", delta, 1]
                for (txn_id, cdr_id), delta in best.items()]

    @staticmethod
    def _cdr_ipdr_rows(cdr: List[dict], ipdr: List[dict],
                       window: int) -> List[list]:
        def keys(r: dict, ks: Tuple[str, ...]) -> set:
            out = set()
            for k in ks:
                v = r.get(k)
                if v:
                    out.add(str(v).strip())
            return out

        cdr_by_key: dict[str, list[dict]] = {}
        for c in cdr:
            if not c.get("cdr_id") or c.get("ts") is None:
                continue
            for k in keys(c, ("imsi", "imei")):
                cdr_by_key.setdefault(k, []).append(c)
                
        cdr_indexed: dict[str, tuple[list[float], list[dict]]] = {}
        for k, clist in cdr_by_key.items():
            clist.sort(key=lambda x: x["ts"])
            cdr_indexed[k] = ([x["ts"] for x in clist], clist)
            
        rows = []
        for i in ipdr:
            ipdr_id = i.get("ipdr_id")
            its = i.get("start_ts")
            if not ipdr_id or its is None:
                continue
                
            for k in keys(i, ("imsi", "imei", "msisdn")):
                if k not in cdr_indexed:
                    continue
                k_ts, c_list = cdr_indexed[k]
                idx_start = bisect.bisect_left(k_ts, its - window)
                idx_end = bisect.bisect_right(k_ts, its + window)
                for c in c_list[idx_start:idx_end]:
                    cts = c["ts"]
                    rows.append([
                        str(c["cdr_id"]), str(ipdr_id),
                        "cdr_ipdr_correlation", float(abs(cts - its)), 1,
                    ])
        return rows

    # ------------------------------------------------------------ schema

    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS bank_transactions (
            transaction_id TEXT PRIMARY KEY, date TEXT, timestamp TEXT,
            txn_ref_number TEXT, transaction_mode TEXT, currency TEXT,
            transaction_amount REAL, sender_customer_id TEXT,
            sender_customer_name TEXT, sender_bank_name TEXT,
            sender_account_number TEXT, sender_account_type TEXT,
            sender_ifsc TEXT, sender_phone_number TEXT,
            receiver_customer_id TEXT, receiver_customer_name TEXT,
            receiver_bank_name TEXT, receiver_account_number TEXT,
            receiver_account_type TEXT, receiver_ifsc TEXT,
            receiver_phone_number TEXT
        );
        CREATE TABLE IF NOT EXISTS cdr_records (
            cdr_id TEXT PRIMARY KEY, call_date TEXT, call_start_time TEXT,
            a_party_number TEXT, b_party_number TEXT, call_type TEXT,
            call_duration_seconds INTEGER, imsi TEXT, imei TEXT,
            first_bts_location TEXT, first_cell_global_id TEXT,
            roaming_network_circle TEXT
        );
        CREATE TABLE IF NOT EXISTS ipdr_records (
            ipdr_id TEXT PRIMARY KEY, session_date TEXT, session_start_time TEXT,
            subscriber_imsi TEXT, subscriber_msisdn TEXT, device_imei TEXT,
            source_ip_address TEXT, destination_ip_address TEXT,
            destination_port TEXT, cell_global_id TEXT,
            session_duration_seconds INTEGER
        );
        CREATE TABLE IF NOT EXISTS bank_cdr_links (
            transaction_id TEXT, cdr_id TEXT, relationship_type TEXT,
            time_difference_seconds REAL, is_correlated INTEGER
        );
        CREATE TABLE IF NOT EXISTS cdr_ipdr_links (
            cdr_id TEXT, ipdr_id TEXT, relationship_type TEXT,
            time_difference_seconds REAL, is_correlated INTEGER
        );
        CREATE TABLE IF NOT EXISTS anomaly_records (
            anomaly_id TEXT, customer_id TEXT, customer_name TEXT,
            account_no TEXT, transaction_id TEXT, cdr_ids TEXT,
            ipdr_ids TEXT, scenario_type TEXT, risk_score REAL,
            risk_band TEXT, rules_fired TEXT, amount REAL,
            difficulty TEXT, source_scope TEXT, is_suspicious INTEGER
        );
        CREATE TABLE IF NOT EXISTS complaints (
            complaint_id TEXT, acknowledgement_no TEXT, account_no TEXT,
            ifsc TEXT, state TEXT, district TEXT, police_station TEXT,
            complainant_name TEXT, designation TEXT, mobile TEXT, email TEXT
        );
        CREATE TABLE IF NOT EXISTS subscribers (
            phone TEXT, imsi TEXT, imei TEXT, name TEXT, circle TEXT,
            operator TEXT
        );
        """)

    @staticmethod
    def _insert_rows(conn: sqlite3.Connection, table: str,
                     cols: Tuple[str, ...], rows: List[list]) -> None:
        if not rows:
            return
        placeholders = ",".join("?" for _ in cols)
        # OR IGNORE: real-world bundles carry duplicate transaction/cdr ids;
        # keep the first occurrence instead of failing the whole build.
        sql = (f"INSERT OR IGNORE INTO {table} "
               f"({','.join(cols)}) VALUES ({placeholders})")
        conn.executemany(sql, rows)
        conn.commit()

    def _create_indices(self, conn: sqlite3.Connection) -> None:
        """Creates indices to ensure real-time query execution."""
        cursor = conn.cursor()
        index_queries = [
            # Bank indices
            "CREATE INDEX IF NOT EXISTS idx_bank_tx_id ON bank_transactions(transaction_id);",
            "CREATE INDEX IF NOT EXISTS idx_bank_sender_acc ON bank_transactions(sender_account_number);",
            "CREATE INDEX IF NOT EXISTS idx_bank_receiver_acc ON bank_transactions(receiver_account_number);",
            "CREATE INDEX IF NOT EXISTS idx_bank_sender_phone ON bank_transactions(sender_phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_bank_receiver_phone ON bank_transactions(receiver_phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_bank_ts ON bank_transactions(timestamp);",
            # CDR indices
            "CREATE INDEX IF NOT EXISTS idx_cdr_id ON cdr_records(cdr_id);",
            "CREATE INDEX IF NOT EXISTS idx_cdr_a_party ON cdr_records(a_party_number);",
            "CREATE INDEX IF NOT EXISTS idx_cdr_b_party ON cdr_records(b_party_number);",
            "CREATE INDEX IF NOT EXISTS idx_cdr_bts ON cdr_records(first_bts_location);",
            "CREATE INDEX IF NOT EXISTS idx_cdr_imsi ON cdr_records(imsi);",
            # IPDR indices
            "CREATE INDEX IF NOT EXISTS idx_ipdr_id ON ipdr_records(ipdr_id);",
            "CREATE INDEX IF NOT EXISTS idx_ipdr_msisdn ON ipdr_records(subscriber_msisdn);",
            "CREATE INDEX IF NOT EXISTS idx_ipdr_imsi ON ipdr_records(subscriber_imsi);",
            # Link indices
            "CREATE INDEX IF NOT EXISTS idx_b_cdr_tx ON bank_cdr_links(transaction_id);",
            "CREATE INDEX IF NOT EXISTS idx_b_cdr_cdr ON bank_cdr_links(cdr_id);",
            "CREATE INDEX IF NOT EXISTS idx_c_ipdr_cdr ON cdr_ipdr_links(cdr_id);",
            "CREATE INDEX IF NOT EXISTS idx_c_ipdr_ipdr ON cdr_ipdr_links(ipdr_id);",
            # Anomaly indices
            "CREATE INDEX IF NOT EXISTS idx_anomaly_tx ON anomaly_records(transaction_id);",
            "CREATE INDEX IF NOT EXISTS idx_anomaly_cust ON anomaly_records(customer_id);",
            "CREATE INDEX IF NOT EXISTS idx_anomaly_name ON anomaly_records(customer_name);",
            "CREATE INDEX IF NOT EXISTS idx_anomaly_acc ON anomaly_records(account_no);",
            "CREATE INDEX IF NOT EXISTS idx_anomaly_risk ON anomaly_records(risk_score);",
            # Complaint / subscriber indices
            "CREATE INDEX IF NOT EXISTS idx_complaint_acc ON complaints(account_no);",
            "CREATE INDEX IF NOT EXISTS idx_complaints_mobile ON complaints(mobile);",
            "CREATE INDEX IF NOT EXISTS idx_subscriber_phone ON subscribers(phone);",
            "CREATE INDEX IF NOT EXISTS idx_sub_imsi ON subscribers(imsi);",
        ]
        for query in index_queries:
            try:
                cursor.execute(query)
            except sqlite3.OperationalError:
                pass
        conn.commit()


_global_db_conn: Optional[sqlite3.Connection] = None
_global_db_source: str = "csv"

def get_copilot_db(bundle: Optional[Dict[str, Any]] = None,
                   data_dir: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """Returns a singleton SQLite connection for the Copilot module.

    Pass a v3 bundle to build the forensic schema from the in-memory dataset;
    without one the original CSV-folder builder is used.
    """
    global _global_db_conn, _global_db_source
    if _global_db_conn is not None:
        return _global_db_conn
    if bundle is not None:
        builder = CopilotDBBuilder()
        _global_db_conn = builder.build_database_from_bundle(bundle)
    else:
        builder = CopilotDBBuilder(data_dir=data_dir)
        _global_db_conn = builder.build_database()
    _global_db_source = builder.source
    return _global_db_conn


def copilot_db_source() -> str:
    """'bundle' when the copilot DB was built from an in-memory v3 bundle,
    'csv' when it was built from reduced CSV files."""
    return _global_db_source


def reset_copilot_db() -> None:
    """Drops the singleton connection so the next get_copilot_db() rebuilds."""
    global _global_db_conn
    _global_db_conn = None
