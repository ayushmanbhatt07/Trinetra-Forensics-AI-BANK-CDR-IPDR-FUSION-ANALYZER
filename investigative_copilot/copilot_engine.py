import os
import re
import json
import sqlite3
from typing import Any, Dict, List, Optional
import logging


from backend import config
from .db_builder import copilot_db_source, get_copilot_db
from .graph_engine import CopilotGraphEngine
from .llm_client import LlmClient
from .memory import MemoryStore
from .prompts import SYSTEM_PROMPT, INTERPRETATION_PROMPT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entity resolution + investigation intelligence layer.
# Turns raw result rows into investigator-grade evidence: entity typing,
# per-record risk scoring, aggregate metrics, pattern insights, next-action
# suggestions and an evidence explanation — all deterministic (offline).
# ---------------------------------------------------------------------------

_TXN_ID_RE = re.compile(r'(?i)\b(TXN\w{3,}|T\d{8,})\b')
_IP_RE = re.compile(r'(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)')
_IMEI_RE = re.compile(r'(?<!\d)(?:35|86|99)\d{13}(?!\d)')
_ACCOUNT_RE = re.compile(r'\b\d{4,16}\b')

_RISK_BANDS = [
    (86, 100, "SEVERE"),
    (71, 85, "CRITICAL"),
    (51, 70, "HIGH"),
    (26, 50, "MEDIUM"),
    (0, 25, "LOW"),
]


def _band(score: int) -> str:
    for lo, hi, name in _RISK_BANDS:
        if lo <= score <= hi:
            return name
    return "LOW"


def _amount_key(r: Dict[str, Any]) -> str:
    for k in ("transaction_amount", "amount", "total_amount", "max_leg"):
        if r.get(k) is not None:
            return k
    return ""


def _ts_key(r: Dict[str, Any]) -> str:
    for k in ("timestamp", "call_start_time", "session_start_time", "created", "tx_time"):
        if r.get(k):
            return k
    return ""


def _mode_key(r: Dict[str, Any]) -> str:
    for k in ("transaction_mode", "mode"):
        if r.get(k):
            return k
    return ""


def _phone_value(r: Dict[str, Any]) -> str:
    for k in ("sender_phone_number", "receiver_phone_number", "a_party_number",
              "mobile", "phone", "subscriber_msisdn"):
        v = r.get(k)
        if v:
            return str(v)
    return ""


def _account_value(r: Dict[str, Any]) -> str:
    for k in ("sender_account_number", "receiver_account_number", "account_no"):
        v = r.get(k)
        if v:
            return str(v)
    return ""


def _receiver_value(r: Dict[str, Any]) -> str:
    for k in ("receiver_account_number", "receiver_customer_name", "receiver_account", "beneficiary"):
        v = r.get(k)
        if v and str(v) not in ("", "None", "nan"):
            return str(v)
    return ""


def _ip_value(r: Dict[str, Any]) -> str:
    for k in ("source_ip_address", "ip_address", "ip"):
        v = r.get(k)
        if v:
            return str(v)
    return ""


def _resolve_entity_type(value: str) -> str:
    """Pure regex classification of any identifier the investigator typed.
    DB-sensitive types (complaint ack vs account vs IFSC) are refined by
    `InvestigativeCoPilotEngine._resolve_entity_in_db`."""
    v = (value or "").strip()
    if not v:
        return "identifier"
    if _TXN_ID_RE.fullmatch(v):
        return "transaction"
    if _IP_RE.fullmatch(v):
        return "ip"
    if _IMEI_RE.fullmatch(v):
        return "imei"
    if re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}', v.upper()):
        return "ifsc"
    digits = re.sub(r'\D', '', v)
    if len(digits) == 10 and digits[0] in "6789":
        return "phone"
    if len(digits) == 12 and digits.startswith("91"):
        return "phone"
    if len(digits) >= 4:
        return "account"
    return "identifier"


def _normalize_cot(steps: Any) -> List[Dict[str, Any]]:
    """Normalizes chain-of-thought into the ``{step, title, content}`` shape
    the UI renders. Accepts string lists (LLM ``cot_reasoning``), object
    lists (deterministic pipeline) or a plain text block."""
    out: List[Dict[str, Any]] = []
    if isinstance(steps, list):
        for i, s in enumerate(steps, 1):
            if isinstance(s, dict):
                out.append({
                    "step": int(s.get("step") or i),
                    "title": str(s.get("title") or s.get("heading")
                                 or f"Step {i}"),
                    "content": str(s.get("content") or s.get("detail")
                                   or s.get("text") or ""),
                })
            elif s is not None and str(s).strip():
                out.append({"step": i, "title": f"Step {i}",
                            "content": str(s).strip()})
    elif isinstance(steps, str):
        for i, s in enumerate(steps.strip().splitlines(), 1):
            s = s.strip()
            if s:
                out.append({"step": i, "title": f"Step {i}", "content": s})
    return out

class InvestigativeCoPilotEngine:
    """Core LLM Investigative Co-Pilot Engine for Tri-Netra Forensics cyber-forensics.
    Provides Text-to-SQL generation, 3-hop NetworkX graph traversal, Evidentiary Chain-of-Thought,
    and executive lead auto-summarization.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None,
                 bundle: Optional[Dict[str, Any]] = None, username: str = "default"):
        if conn is not None:
            self.conn = conn
            try:
                self.conn.row_factory = sqlite3.Row
            except Exception:
                pass
        else:
            self.conn = get_copilot_db(bundle=bundle, username=username)
            try:
                self.conn.row_factory = sqlite3.Row
            except Exception:
                pass

        self.graph_engine = CopilotGraphEngine(self.conn)
        self.dataset_source = copilot_db_source()
        self.llm = LlmClient()
        self.memory = MemoryStore(bundle, username=username)
        self._last_llm_meta: Dict[str, Any] = {}

    def analyze_query(self, user_query: str) -> Dict[str, Any]:
        """Main entry point: processes natural language user query into CoT and forensic results."""
        query_clean = user_query.strip()

        # 0. RAG: pull the top evidence rows for this query from the loaded
        #    dataset so every answer is grounded in the uploaded corpus.
        try:
            from .retrieval import best_entity_hint, format_context, retrieve_context
            self._retrieved = retrieve_context(self.conn, query_clean)
            self._rag_block = format_context(self._retrieved)
            hints = __import__("investigative_copilot.retrieval", fromlist=["extract_entities"]).extract_entities(query_clean)
            self._rag_hint = best_entity_hint(hints)
        except Exception as e:
            logger.warning("RAG retrieval skipped: %s", e)
            self._retrieved = []
            self._rag_block = ""
            self._rag_hint = None

        # 1. Try the live Groq / LLM pipeline whenever an active provider is available
        llm_response = None
        if self.llm.has_provider():
            try:
                llm_response = self._call_llm_api(query_clean)
            except Exception as e:
                logger.warning(f"LLM call raised error: {e}")
                llm_response = None

        # 3. If no LLM response or offline mode, run deterministic CoT pipeline
        if not llm_response:
            try:
                llm_response = self._run_deterministic_pipeline(query_clean)
                llm_response["mode"] = "deterministic"
                llm_response["llm_provider"] = self._last_llm_meta.get("provider", "")
                llm_response["llm_model"] = self._last_llm_meta.get("model", "")
                llm_response["llm_latency_ms"] = self._last_llm_meta.get("latency_ms", 0)
                self._remember(llm_response, query_clean)
            except Exception as e:
                logger.error(f"Deterministic pipeline failed: {e}")
                llm_response = {
                    "query": query_clean,
                    "intent": query_clean,
                    "generated_sql": "",
                    "execution_success": False,
                    "row_count": 0,
                    "records": [],
                    "chain_of_thought": [],
                    "executive_summary": f"Could not process query '{query_clean}'. Please try refining your query.",
                    "answer": f"Could not process query '{query_clean}'. Please try refining your query.",
                    "mode": "fallback"
                }

        # 4. Attach the retrieved evidence to every envelope (any mode).
        llm_response.setdefault("retrieved_evidence", self._retrieved[:8])
        llm_response.setdefault("answer", llm_response.get("executive_summary") or "")
        
        # 5. Plain-English explainability companion (always deterministic).
        if not llm_response.get("explainability"):
            try:
                from backend.explain import plain_explainability
                llm_response["explainability"] = plain_explainability(
                    llm_response, query_clean)
            except Exception as e:
                logger.debug("explainability skipped: %s", e)
                llm_response["explainability"] = ""
        
        try:
            return self._make_serializable(llm_response)
        except Exception:
            return llm_response

    def _run_deterministic_pipeline(self, user_query: str) -> Dict[str, Any]:
        """Fallback deterministic pipeline when all LLM models/keys are rate-limited or offline.
        Translates natural language queries into standard SQL, queries the SQLite corpus,
        and synthesizes a rich Markdown forensic summary.
        """
        cursor = self.conn.cursor()
        query_clean = user_query.strip()
        query_lower = query_clean.lower()
        records: List[Dict[str, Any]] = []
        sql_executed = ""
        intent_desc = "Forensic Corpus Inspection"

        # Check for specific entities in query
        words = [w.strip("',\"()[]") for w in query_clean.split() if len(w.strip("',\"()[]")) >= 3]
        target_entity = ""
        for w in words:
            if re.match(r'^(TXN|ATM|ACC|CDR|IPDR|[0-9]{6,16})', w, re.IGNORECASE):
                target_entity = w
                break

        try:
            if target_entity:
                intent_desc = f"Entity Record Lookup ({target_entity})"
                sql_executed = (
                    f"SELECT transaction_id, date, timestamp, sender_customer_name, sender_account_number, "
                    f"receiver_customer_name, receiver_account_number, transaction_amount, transaction_mode "
                    f"FROM bank_transactions "
                    f"WHERE transaction_id LIKE '%{target_entity}%' "
                    f"OR sender_account_number LIKE '%{target_entity}%' "
                    f"OR receiver_account_number LIKE '%{target_entity}%' "
                    f"OR sender_customer_name LIKE '%{target_entity}%' "
                    f"OR receiver_customer_name LIKE '%{target_entity}%' "
                    f"ORDER BY transaction_amount DESC LIMIT 25"
                )
                cursor.execute(sql_executed)
                records = [dict(r) for r in cursor.fetchall()]

            elif any(w in query_lower for w in ["top", "largest", "highest", "big", "max"]):
                limit_match = re.search(r'\b(?:top|first|limit)\s*(\d+)\b', query_lower)
                lim = int(limit_match.group(1)) if limit_match else 5
                intent_desc = f"Top {lim} Highest Value Transactions"
                sql_executed = (
                    f"SELECT transaction_id, date, timestamp, sender_customer_name, sender_account_number, "
                    f"receiver_customer_name, receiver_account_number, transaction_amount, transaction_mode "
                    f"FROM bank_transactions "
                    f"ORDER BY transaction_amount DESC LIMIT {lim}"
                )
                cursor.execute(sql_executed)
                records = [dict(r) for r in cursor.fetchall()]

            elif any(w in query_lower for w in ["call", "cdr", "telecom", "phone", "tower"]):
                intent_desc = "Telecom & CDR Activity Analysis"
                sql_executed = (
                    "SELECT cdr_id, call_date, call_start_time, a_party_number, b_party_number, "
                    "call_type, call_duration_seconds, first_bts_location "
                    "FROM cdr_records ORDER BY call_duration_seconds DESC LIMIT 15"
                )
                cursor.execute(sql_executed)
                records = [dict(r) for r in cursor.fetchall()]

            elif any(w in query_lower for w in ["summary", "overview", "total", "count", "stats"]):
                intent_desc = "Corpus Volume Summary"
                sql_executed = "SELECT COUNT(*) as total_tx, SUM(transaction_amount) as total_amount, COUNT(DISTINCT sender_account_number) as sender_accounts FROM bank_transactions"
                cursor.execute(sql_executed)
                row = cursor.fetchone()
                if row:
                    tot_tx = row["total_tx"] or 0
                    tot_amt = float(row["total_amount"] or 0.0)
                    tot_acc = row["sender_accounts"] or 0
                    records = [{"transaction_id": "CORPUS_TOTAL", "total_transactions": tot_tx, "transaction_amount": tot_amt, "sender_customer_name": f"{tot_acc} Unique Accounts", "transaction_mode": "All Channels"}]

            elif any(w in query_lower for w in ["risk", "alert", "mule", "anomaly", "high risk"]):
                intent_desc = "High-Risk Account Identification"
                sql_executed = (
                    "SELECT sender_account_number, sender_customer_name, COUNT(*) as total_transactions, "
                    "SUM(transaction_amount) as transaction_amount, 'High Turnover' as transaction_mode "
                    "FROM bank_transactions GROUP BY sender_account_number ORDER BY transaction_amount DESC LIMIT 10"
                )
                cursor.execute(sql_executed)
                records = [dict(r) for r in cursor.fetchall()]

            else:
                # Default search across names / remarks / accounts
                search_term = words[0] if words else ""
                intent_desc = "Transaction & Entity Record Search"
                if search_term:
                    sql_executed = (
                        f"SELECT transaction_id, date, timestamp, sender_customer_name, sender_account_number, "
                        f"receiver_customer_name, receiver_account_number, transaction_amount, transaction_mode "
                        f"FROM bank_transactions "
                        f"WHERE sender_customer_name LIKE '%{search_term}%' "
                        f"OR receiver_customer_name LIKE '%{search_term}%' "
                        f"OR txn_ref_number LIKE '%{search_term}%' "
                        f"OR sender_account_number LIKE '%{search_term}%' "
                        f"ORDER BY transaction_amount DESC LIMIT 15"
                    )
                else:
                    sql_executed = (
                        "SELECT transaction_id, date, timestamp, sender_customer_name, sender_account_number, "
                        "receiver_customer_name, receiver_account_number, transaction_amount, transaction_mode "
                        "FROM bank_transactions ORDER BY transaction_amount DESC LIMIT 15"
                    )
                cursor.execute(sql_executed)
                records = [dict(r) for r in cursor.fetchall()]

        except Exception as e:
            logger.warning(f"Deterministic SQL fallback query error: {e}")
            sql_executed = "SELECT * FROM bank_transactions LIMIT 10"
            try:
                cursor.execute(sql_executed)
                records = [dict(r) for r in cursor.fetchall()]
            except Exception:
                records = []

        row_cnt = len(records)
        summary_text, answer_text, risk_text = self._synthesize_records_narrative(user_query, sql_executed, records)

        return {
            "query": user_query,
            "intent": intent_desc,
            "generated_sql": sql_executed,
            "execution_success": True,
            "row_count": row_cnt,
            "records": records[:10],
            "chain_of_thought": [
                "1. Multi-key Groq LLM cluster quota exhausted (HTTP 429).",
                "2. Seamlessly activated Deterministic Natural Language SQL Translation.",
                f"3. Executed SQL query: {sql_executed}",
                f"4. Retrieved {row_cnt} forensic record rows.",
                "5. Synthesized natural language Markdown investigation report."
            ],
            "executive_summary": summary_text,
            "risk_summary": risk_text,
            "answer": answer_text,
            "mode": "deterministic (LLM quota exhausted)"
        }

    def _synthesize_records_narrative(self, user_query: str, sql_q: str, records: list[dict]) -> tuple[str, str, str]:
        """Generates a deep, natural-language forensic intelligence synthesis from query records."""
        if not records:
            return (
                "No forensic records found matching the specified query criteria in the active corpus.",
                f"No transaction or telecom records matching **'{user_query}'** were identified in the current database. Recommend verifying the spelling of entity names, phone numbers, or account numbers.",
                "No suspicious patterns identified."
            )
        
        # Single record deep dossier
        if len(records) == 1:
            r = records[0]
            txn_id = r.get("transaction_id") or r.get("txn_id") or "TXN_RECORD"
            amt_v = r.get("transaction_amount") or r.get("amount") or 0.0
            try:
                amt_f = float(amt_v)
            except (ValueError, TypeError):
                amt_f = 0.0
            
            mode = r.get("transaction_mode") or r.get("mode") or "Electronic Transfer"
            date = r.get("date") or r.get("timestamp") or "N/A"
            s_name = r.get("sender_customer_name") or r.get("account_name") or "Sender Entity"
            s_acc = r.get("sender_account_number") or r.get("account_no") or "N/A"
            s_bank = r.get("sender_bank_name") or r.get("bank") or "Originating Bank"
            s_phone = r.get("sender_phone_number") or r.get("sender_phone") or "N/A"
            
            r_name = r.get("receiver_customer_name") or r.get("counterparty_name") or "Beneficiary Entity"
            r_acc = r.get("receiver_account_number") or r.get("receiver_account") or "N/A"
            r_bank = r.get("receiver_bank_name") or r.get("counterparty_bank") or "Beneficiary Bank"
            r_phone = r.get("receiver_phone_number") or r.get("receiver_phone") or "N/A"
            
            answer_text = (
                f"### 📋 Executive Forensic Intelligence Dossier\n"
                f"- **Target Transaction**: `{txn_id}`\n"
                f"- **Execution Timestamp**: `{date}`\n"
                f"- **Payment Channel / Mode**: `{mode}`\n"
                f"- **Total Amount**: **₹{amt_f:,.2f}**\n\n"
                f"### 🔄 Fund Flow & Counterparty Profiling\n"
                f"| Role | Entity / Account Holder | Account Number | Bank / Institution | Linked Phone |\n"
                f"| :--- | :--- | :--- | :--- | :--- |\n"
                f"| **Originating Sender** | {s_name} | `{s_acc}` | {s_bank} | `{s_phone}` |\n"
                f"| **Beneficiary Receiver** | {r_name} | `{r_acc}` | {r_bank} | `{r_phone}` |\n\n"
                f"### ⚠️ Forensic Suspicion & Crime Typology Analysis\n"
                f"- **Velocity / Threshold Marker**: Transfer value of ₹{amt_f:,.2f} via {mode}.\n"
                f"- **Channel Exposure**: {mode} execution between `{s_bank}` and `{r_bank}` requires source validation.\n\n"
                f"### 🛡️ Recommended Law Enforcement Next Steps\n"
                f"1. Issue Section 91 CrPC notice to `{s_bank}` and `{r_bank}` for complete KYC files.\n"
                f"2. Audit linked beneficiary account `{r_acc}` for secondary layering out-flows.\n"
                f"3. Place provisional cyber lien / debit hold if associated with active cyber complaints."
            )
            summary_text = f"Transaction {txn_id} for ₹{amt_f:,.2f} executed via {mode} from {s_name} to {r_name}."
            risk_text = f"Transaction of ₹{amt_f:,.2f} via {mode} requiring statutory KYC verification."
            return summary_text, answer_text, risk_text

        total_amt = 0.0
        modes = set()
        counterparties = set()
        accounts = set()
        dates = set()
        
        for r in records:
            amt_val = r.get("transaction_amount")
            if amt_val is None or amt_val == "":
                amt_val = r.get("amount") or 0.0
            try:
                total_amt += float(amt_val)
            except (ValueError, TypeError):
                pass
                
            m = r.get("transaction_mode") or r.get("mode") or ""
            if m: modes.add(str(m))
            cp = r.get("receiver_customer_name") or r.get("counterparty_name") or r.get("receiver_account_number") or ""
            if cp and str(cp) not in ("unknown", "None", ""): counterparties.add(str(cp))
            acc = r.get("sender_account_number") or r.get("account_no") or ""
            if acc and str(acc) not in ("unknown", "None", ""): accounts.add(str(acc))
            d = r.get("date") or ""
            if d: dates.add(str(d))
            
        date_str = f"between {min(dates)} and {max(dates)}" if len(dates) > 1 else (f"on {list(dates)[0]}" if dates else "")
        modes_str = ", ".join(sorted(modes)) if modes else "Electronic Transfers"
        
        # Format top transaction highlights
        table_rows = []
        for i, r in enumerate(records[:10], 1):
            txn = r.get("transaction_id") or r.get("txn_id") or f"Record-{i}"
            amt_v = r.get("transaction_amount")
            if amt_v is None or amt_v == "":
                amt_v = r.get("amount") or 0.0
            try:
                amt_f = float(amt_v)
            except (ValueError, TypeError):
                amt_f = 0.0
                
            mode = r.get("transaction_mode") or r.get("mode") or "Transfer"
            date = r.get("date") or "N/A"
            sender = r.get("sender_customer_name") or r.get("sender_account_number") or r.get("account_no") or "Originating Account"
            receiver = r.get("receiver_customer_name") or r.get("counterparty_name") or r.get("receiver_account_number") or "Beneficiary"
            amt_str = f"₹{amt_f:,.2f}" if amt_f > 0 else "Unspecified"
            table_rows.append(f"| `{txn}` | {date} | **{amt_str}** | `{mode}` | {sender} | {receiver} |")
            
        answer_text = (
            f"### 📋 Forensic Intelligence Summary\n"
            f"Forensic search for **'{user_query}'** retrieved **{len(records)} matching transaction record(s)** "
            f"{date_str} totaling **₹{total_amt:,.2f}** primarily executed via **{modes_str}**.\n\n"
            f"### 🔄 Key Financial Transactions\n"
            f"| Txn ID | Date | Amount | Mode | Originating Sender | Beneficiary Receiver |\n"
            f"| :--- | :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(table_rows) + "\n\n"
            f"### 🛡️ Recommended Law Enforcement Next Steps\n"
            f"1. Issue Section 91 CrPC notices to identified reporting institutions for counterparty KYC dossiers.\n"
            f"2. Freeze beneficiary accounts receiving rapid pass-through velocity.\n"
            f"3. Cross-reference CDR/IPDR telecom logs for concurrent tower transmissions."
        )
        if len(records) > 10:
            answer_text += f"\n\n*... and {len(records) - 10} additional linked transaction(s) recorded in the database.*"
            
        summary_text = (
            f"Search for '{user_query}' identified {len(records)} transaction record(s) "
            f"with total turnover of ₹{total_amt:,.2f}. Primary beneficiaries: {', '.join(list(counterparties)[:3]) or 'Multiple'}. "
            f"Immediate action: issue Section 91 CrPC notice and audit linked KYC profiles."
        )
        
        risk_text = (
            f"Observed turnover of ₹{total_amt:,.2f} across {len(records)} transaction(s) "
            f"via {modes_str} exhibits high velocity funds movement requiring counterparty verification."
        )
        
        return summary_text, answer_text, risk_text

    def _make_serializable(self, obj: Any) -> Any:
        """Deeply convert all non-native types (Decimal, datetime, numpy, NaN, sets) to JSON-safe builtins."""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(v) for v in obj]
        elif isinstance(obj, tuple):
            return tuple(self._make_serializable(v) for v in obj)
        elif isinstance(obj, set):
            return [self._make_serializable(v) for v in sorted(obj)]
        elif type(obj) in (int, float, str, bool, type(None)):
            if isinstance(obj, float):
                import math
                if math.isnan(obj) or math.isinf(obj):
                    return None
            return obj
        else:
            if hasattr(obj, "item") and callable(getattr(obj, "item")):
                try:
                    return self._make_serializable(obj.item())
                except Exception:
                    pass
            if hasattr(obj, "isoformat") and callable(getattr(obj, "isoformat")):
                return obj.isoformat()
            if isinstance(obj, bytes):
                return obj.hex()
            return str(obj)

    def summarize_cluster(self, entity_ids: List[str]) -> Dict[str, Any]:
        """Generates an executive lead summary for a cluster of entities/transactions (e.g. node click in UI)."""
        if not entity_ids:
            return {"summary": "No entities selected for cluster summary."}

        primary_entity = str(entity_ids[0]).strip()

        # Resolve Transaction ID -> Account
        target_account = primary_entity
        cursor = self.conn.cursor()
        cursor.execute("SELECT receiver_account_number, sender_account_number FROM bank_transactions WHERE transaction_id = ?", (primary_entity,))
        row_tx = cursor.fetchone()
        if row_tx:
            target_account = str(row_tx["receiver_account_number"]) or str(row_tx["sender_account_number"])

        # Perform 3-hop graph analysis
        graph_res = self.graph_engine.trace_mule_chain(primary_entity, max_hops=3)

        if not graph_res.get("found", False):
            return {
                "entity_id": primary_entity,
                "total_entities_in_cluster": len(entity_ids),
                "graph_analysis": graph_res,
                "executive_summary": f"Entity/Transaction '{primary_entity}' was not found in the observation network or has no connected bank/telecom activity."
            }

        resolved_start_node = graph_res.get("start_node", target_account)

        cursor.execute("""
            SELECT SUM(transaction_amount) as total_amount, COUNT(*) as tx_count
            FROM bank_transactions
            WHERE sender_account_number = ? OR receiver_account_number = ?
        """, (resolved_start_node, resolved_start_node))
        row = cursor.fetchone()

        tot_amt = float(row["total_amount"]) if row and row["total_amount"] is not None else 0.0
        tx_cnt = int(row["tx_count"]) if row and row["tx_count"] is not None else 0

        l1_mules = len(graph_res.get("layers", {}).get("Layer-1 Mules", []))
        l2_mules = len(graph_res.get("layers", {}).get("Layer-2 Mules", []))

        summary_text = (
            f"Target '{primary_entity}' resolves to Account '{resolved_start_node}' acting as a primary Layer-1 mule nexus. "
            f"Processed ₹{tot_amt:,.2f} across {tx_cnt} transactions within the observation window. "
            f"Graph analysis identifies {l1_mules} direct (1-hop) and {l2_mules} secondary (2-hop) downstream recipients. "
            f"Immediate cyber cell action recommended: freeze target account and subpoena associated CDR tower logs."
        )

        return self._make_serializable({
            "entity_id": primary_entity,
            "resolved_account": resolved_start_node,
            "total_entities_in_cluster": len(entity_ids),
            "total_amount_processed": tot_amt,
            "transaction_count": tx_cnt,
            "graph_analysis": graph_res,
            "executive_summary": summary_text
        })

    def _run_deterministic_pipeline(self, user_query: str) -> Dict[str, Any]:
        """Deterministic query translator and CoT generator for cyber-forensic
        scenarios. Covers tower-call correlation, mule traces, NCRP complaint
        cross-referencing, phone / account / amount / mode lookups, layering
        analytics and a high-value fallback — every response also carries a
        3-hop linking tree when a resolvable entity was mentioned."""
        q_lower = user_query.lower()
        entity_hint: Optional[str] = None

        # Recognize state/circle names dynamically
        state_patterns = {
            "west bengal": ["%WestBengal%", "%West Bengal%", "%Kolkata%"],
            "kolkata": ["%Kolkata%", "%WestBengal%", "%West Bengal%"],
            "delhi": ["%Delhi%"],
            "gujarat": ["%Gujarat%"],
            "karnataka": ["%Karnataka%"],
            "maharashtra": ["%Maharashtra%"],
            "mumbai": ["%Mumbai%"],
            "rajasthan": ["%Rajasthan%"],
            "tamil nadu": ["%TamilNadu%", "%Tamil Nadu%"],
            "uttar pradesh": ["%UttarPradesh%", "%Uttar Pradesh%"],
        }

        matched_state = "West Bengal"
        matched_patterns = ["%WestBengal%", "%West Bengal%", "%Kolkata%"]
        for st, pat_list in state_patterns.items():
            if st in q_lower:
                matched_state = st.title()
                matched_patterns = pat_list
                break

        # Scenario 0: Exact transaction / CDR / IPDR lookup
        # Intercepts simple factual lookups to prevent LLM hallucinations.
        import investigative_copilot.retrieval as ret
        hints = ret.extract_entities(user_query)
        candidate = ret.best_entity_hint(hints) or ret._extract_candidate_id(user_query)
        is_simple_lookup = bool(candidate and (
            hints.get("txn") or "txn" in q_lower or "transaction" in q_lower or
            any(w in q_lower for w in ["find", "show", "get", "details", "summarise", "summarize", "about", "check", "who is", "profile", "investigate", "trace"])
            or q_lower.startswith(str(candidate).lower())
        ))

        # Check if user specifically requested linked devices / hardware / IPs for a transaction or account candidate
        is_entity_device_lookup = bool(candidate and any(k in q_lower for k in ["device", "imei", "ip", "hardware", "endpoint", "linked", "connected", "devices"]))

        if is_entity_device_lookup:
            sql_query = f"""
            SELECT bt.transaction_id, bt.timestamp, bt.transaction_amount, bt.transaction_mode,
                   bt.sender_customer_name, bt.sender_account_number, bt.sender_phone_number, bt.sender_bank_name,
                   bt.receiver_customer_name, bt.receiver_account_number, bt.receiver_phone_number, bt.receiver_bank_name,
                   COALESCE(ip.device_imei, cr.imei, '') as device_imei,
                   COALESCE(ip.source_ip_address, '') as source_ip_address,
                   COALESCE(ip.subscriber_msisdn, bt.sender_phone_number, bt.receiver_phone_number, '') as subscriber_msisdn
            FROM bank_transactions bt
            LEFT JOIN bank_cdr_links bl ON bt.transaction_id = bl.transaction_id
            LEFT JOIN cdr_records cr ON bl.cdr_id = cr.cdr_id
            LEFT JOIN cdr_ipdr_links cl ON cr.cdr_id = cl.cdr_id
            LEFT JOIN ipdr_records ip ON cl.ipdr_id = ip.ipdr_id OR ip.subscriber_msisdn = bt.sender_phone_number OR ip.subscriber_msisdn = bt.receiver_phone_number
            WHERE bt.transaction_id = '{candidate}' COLLATE NOCASE OR bt.sender_account_number = '{candidate}' OR bt.receiver_account_number = '{candidate}'
            LIMIT 25;
            """
            intent = f"Retrieve fused bank transactions and cross-correlated device hardware IMEIs / network IPs for identifier {candidate}."
            entity_hint = candidate
        elif is_simple_lookup and hints.get("txn"):
            sql_query = f"SELECT * FROM bank_transactions WHERE transaction_id = '{candidate}' COLLATE NOCASE;"
            intent = f"Retrieve exact details for transaction {candidate}."
            entity_hint = candidate
        elif is_simple_lookup and hints.get("cdr"):
            sql_query = f"SELECT * FROM cdr_records WHERE cdr_id = '{candidate}' COLLATE NOCASE;"
            intent = f"Retrieve exact details for CDR {candidate}."
            entity_hint = candidate
        elif is_simple_lookup and hints.get("ipdr"):
            sql_query = f"SELECT * FROM ipdr_records WHERE ipdr_id = '{candidate}' COLLATE NOCASE;"
            intent = f"Retrieve exact details for IPDR {candidate}."
            entity_hint = candidate
        elif is_simple_lookup and hints.get("account"):
            sql_query = f"""SELECT * FROM bank_transactions 
WHERE sender_account_number = '{candidate}' 
   OR receiver_account_number = '{candidate}' 
   OR sender_customer_id = '{candidate}' 
   OR receiver_customer_id = '{candidate}'
ORDER BY timestamp ASC LIMIT 30;"""
            intent = f"Retrieve complete transaction profile for account or customer ID {candidate}."
            entity_hint = candidate
        elif is_simple_lookup and candidate: # Fallback for unrecognized candidate ID
            if str(candidate).isdigit():
                sql_query = f"""SELECT * FROM bank_transactions 
WHERE sender_account_number = '{candidate}' 
   OR receiver_account_number = '{candidate}' 
   OR sender_customer_id = '{candidate}' 
   OR receiver_customer_id = '{candidate}'
   OR sender_phone_number = '{candidate}'
   OR receiver_phone_number = '{candidate}'
   OR transaction_id = '{candidate}'
ORDER BY timestamp ASC LIMIT 30;"""
            else:
                sql_query = f"SELECT * FROM bank_transactions WHERE transaction_id = '{candidate}' COLLATE NOCASE;"
            intent = f"Attempt to retrieve exact details for identifier {candidate}."
            entity_hint = candidate

        # Scenario: Shared IP / IMEI devices
        elif any(k in q_lower for k in ["shared ip", "shared imei", "shared device", "imei device", "same ip", "same imei"]):
            sql_query = """
            SELECT device_imei, source_ip_address, COUNT(*) as session_count,
                   COUNT(DISTINCT subscriber_msisdn) as unique_phones,
                   GROUP_CONCAT(DISTINCT subscriber_msisdn) as associated_phones
            FROM ipdr_records
            WHERE device_imei != '' AND device_imei != 'Unknown'
            GROUP BY device_imei
            ORDER BY unique_phones DESC, session_count DESC
            LIMIT 25;
            """
            intent = "Identify shared IMEI devices and IP addresses utilized across multiple phone numbers or cyber sessions."

        # Scenario: Temporal correlation within X minutes of calls / calls before transactions
        elif any(k in q_lower for k in ["transfers within", "calls before", "call before", "minutes of call", "mins of call", "window of call", "10 min", "10-min"]):
            sql_query = """
            SELECT bt.transaction_id, bt.timestamp as tx_time, bt.transaction_amount, bt.transaction_mode,
                   bt.sender_customer_name, bt.sender_account_number, bt.sender_phone_number,
                   bt.receiver_customer_name, bt.receiver_account_number,
                   cr.cdr_id, cr.call_start_time, cr.a_party_number, cr.b_party_number,
                   bcl.time_difference_seconds
            FROM bank_transactions bt
            JOIN bank_cdr_links bcl ON bt.transaction_id = bcl.transaction_id
            JOIN cdr_records cr ON bcl.cdr_id = cr.cdr_id
            ORDER BY ABS(bcl.time_difference_seconds) ASC, bt.transaction_amount DESC
            LIMIT 20;
            """
            intent = "Identify all financial transfers executed within a 10-minute window of correlated telecom calls."

        # Scenario: Rapid Layering
        elif any(k in q_lower for k in ["layering", "rapid layering", "structured layering", "fan out", "pass through"]):
            sql_query = """
            SELECT sender_account_number as account_number, sender_customer_name as holder_name,
                   COUNT(*) as transfer_count, SUM(transaction_amount) as total_layering_volume,
                   GROUP_CONCAT(DISTINCT receiver_account_number) as downstream_beneficiaries,
                   MIN(timestamp) as first_tx, MAX(timestamp) as last_tx
            FROM bank_transactions
            GROUP BY sender_account_number
            HAVING transfer_count > 1
            ORDER BY transfer_count DESC, total_layering_volume DESC
            LIMIT 15;
            """
            intent = "Identify bank accounts exhibiting rapid fund layering and high-frequency outbound dispersal."

        # Scenario: Mule account clusters
        elif any(k in q_lower for k in ["mule cluster", "mule account", "mule network", "mule clusters", "mules"]):
            sql_query = """
            SELECT receiver_account_number as mule_account, receiver_customer_name as account_holder,
                   receiver_bank_name as bank, COUNT(*) as incoming_transfers_count,
                   SUM(transaction_amount) as total_received_volume,
                   GROUP_CONCAT(DISTINCT transaction_mode) as payment_channels
            FROM bank_transactions
            GROUP BY receiver_account_number
            ORDER BY incoming_transfers_count DESC, total_received_volume DESC
            LIMIT 15;
            """
            intent = "Identify suspected money mule destination clusters based on aggregate incoming velocity."

        # Scenario: Most suspicious entity / top risk
        elif any(k in q_lower for k in ["most suspicious", "top risk", "highest risk", "who is suspicious", "suspicious entity", "most suspicious entity"]):
            sql_query = """
            SELECT bt.transaction_id, bt.timestamp, bt.transaction_amount, bt.transaction_mode,
                   bt.sender_customer_name, bt.sender_account_number, bt.sender_phone_number,
                   bt.receiver_customer_name, bt.receiver_account_number,
                   COALESCE(c.state, 'Flagged Velocity') as suspicion_flag,
                   COALESCE(c.acknowledgement_no, 'HIGH_VALUE_AML') as alert_ref
            FROM bank_transactions bt
            LEFT JOIN complaints c ON bt.receiver_account_number = c.account_no OR bt.sender_account_number = c.account_no
            ORDER BY (CASE WHEN c.account_no IS NOT NULL THEN 1 ELSE 0 END) DESC, bt.transaction_amount DESC
            LIMIT 15;
            """
            intent = "Surface the most suspicious entities and transactions based on composite risk scoring and high-value velocity."

        # Scenario: High-risk transfers / Largest transactions
        elif any(k in q_lower for k in ["largest transaction", "largest transactions", "high-risk transfer", "high risk transfer", "above 50,000", "above ₹50,000", "top 5"]):
            sql_query = """
            SELECT transaction_id, timestamp, transaction_amount, transaction_mode,
                   sender_customer_name, sender_account_number, sender_bank_name,
                   receiver_customer_name, receiver_account_number, receiver_bank_name
            FROM bank_transactions
            ORDER BY transaction_amount DESC
            LIMIT 20;
            """
            intent = "Retrieve the highest value financial transactions and potential AML threshold triggers."

        # Scenario A: tower / call location + time window + transfer
        elif any(k in q_lower for k in ["tower", "bts", "location", "originating", "circle", "5 minute"]):
            where_conditions = " OR ".join([f"cr.first_bts_location LIKE '{p}' OR cr.roaming_network_circle LIKE '{p}'" for p in matched_patterns])
            sql_query = f"""
            SELECT 
                bt.transaction_id, bt.timestamp as tx_time, bt.transaction_amount, 
                bt.sender_account_number, bt.receiver_account_number, bt.receiver_customer_name,
                cr.cdr_id, cr.call_start_time, cr.first_bts_location, cr.roaming_network_circle, cr.a_party_number,
                bcl.time_difference_seconds
            FROM bank_transactions bt
            JOIN bank_cdr_links bcl ON bt.transaction_id = bcl.transaction_id
            JOIN cdr_records cr ON bcl.cdr_id = cr.cdr_id
            WHERE ({where_conditions})
              AND ABS(bcl.time_difference_seconds) <= 300
            ORDER BY bt.transaction_amount DESC
            LIMIT 20;
            """
            intent = f"Identify all bank accounts receiving transfers within 5 minutes (300s) of calls originating from {matched_state} tower locations."

        # Scenario B: NCRP complaint ledger cross-reference
        elif any(k in q_lower for k in ["complaint", "ncrp", "acknowledgement", "police", "cyber cell", "beneficiary account"]):
            complaint_accs = re.findall(r'\b\d{4,16}\b', user_query)
            if not complaint_accs:
                complaint_accs = re.findall(r'\b[A-Z]{2,4}\d{2,16}\b', user_query)
            filter_sql = ""
            if complaint_accs:
                acc_pattern = " OR ".join(f"c.account_no LIKE '%{a}%'" for a in complaint_accs[:5])
                filter_sql = f" AND ({acc_pattern})"
                entity_hint = complaint_accs[0]
            sql_query = f"""
            SELECT c.acknowledgement_no, c.account_no, c.state, c.police_station, c.mobile,
                   bt.transaction_id, bt.timestamp, bt.transaction_amount, bt.transaction_mode,
                   bt.sender_account_number, bt.receiver_account_number, bt.receiver_customer_name
            FROM complaints c
            LEFT JOIN bank_transactions bt
              ON bt.sender_account_number = c.account_no OR bt.receiver_account_number = c.account_no
            WHERE c.account_no != ''{filter_sql}
            ORDER BY bt.timestamp ASC
            LIMIT 30;
            """
            intent = ("Cross-reference the NCRP police complaint ledger against observed bank activity "
                      "to surface fund flows touching complained fraud-beneficiary accounts.")

        # Scenario C: phone / subscriber lookup
        elif any(k in q_lower for k in ["phone", "msisdn", "number ", "caller", "subscriber"]):
            phone_m = re.search(r'(?<!\d)(91)?\d{10}(?!\d)', user_query)
            phone_raw = phone_m.group(0) if phone_m else ""
            phone10 = phone_raw[-10:] if phone_raw else ""
            sql_phone = "+91" + phone10
            variants = sorted({sql_phone, "91" + phone10, phone_raw, phone_raw.lstrip("+")}, key=len, reverse=True)
            entity_hint = phone10 or None
            if not phone10:
                sql_query = """
                SELECT phone, imsi, imei, name, circle, operator
                FROM subscribers ORDER BY phone LIMIT 20;
                """
                intent = "List all subscriber metadata recovered from the CDR dataset."
            else:
                in_clause = "(" + ", ".join(f"'{v}'" for v in variants) + ")"
                sql_query = f"""
                SELECT bt.transaction_id, bt.timestamp, bt.transaction_amount, bt.transaction_mode,
                       bt.sender_account_number, bt.receiver_account_number, bt.receiver_customer_name,
                       bt.sender_phone_number, bt.receiver_phone_number,
                       cr.cdr_id, cr.call_start_time, cr.call_duration_seconds, cr.first_bts_location,
                       ipr.ipdr_id, ipr.session_start_time, ipr.source_ip_address
                FROM bank_transactions bt
                LEFT JOIN cdr_records cr
                  ON cr.a_party_number IN {in_clause} OR cr.b_party_number IN {in_clause}
                LEFT JOIN ipdr_records ipr ON ipr.subscriber_msisdn IN {in_clause}
                WHERE bt.sender_phone_number IN {in_clause} OR bt.receiver_phone_number IN {in_clause}
                   OR cr.cdr_id IS NOT NULL OR ipr.ipdr_id IS NOT NULL
                ORDER BY bt.timestamp ASC
                LIMIT 30;
                """
                intent = f"Trace every bank transaction, CDR call and IPDR session touching phone number '{phone10}'."

        # Scenario D: account / customer lookup
        elif "account" in q_lower or "ifsc" in q_lower or "customer" in q_lower:
            acc_m = re.findall(r'\b\d{4,16}\b', user_query)
            if not acc_m:
                acc_m = re.findall(r'\b[A-Z]{2,4}\d{2,16}\b', user_query)
            acc = acc_m[0] if acc_m else ""
            entity_hint = acc or None
            acc_filter = (f"WHERE sender_account_number LIKE '%{acc}%' OR receiver_account_number LIKE '%{acc}%'"
                          if acc else "")
            sql_query = f"""
            SELECT transaction_id, timestamp, transaction_amount, transaction_mode,
                   sender_customer_name, sender_account_number,
                   receiver_customer_name, receiver_account_number, receiver_phone_number
            FROM bank_transactions
            {acc_filter}
            ORDER BY timestamp ASC
            LIMIT 30;
            """
            intent = (f"Pull the complete transaction profile for account '{acc}'."
                      if acc else "List the complete account activity present in the dataset.")

        # Scenario E: Mule chain / 3-hop trace
        elif "mule" in q_lower or "hop" in q_lower or "trace" in q_lower or "flow" in q_lower:
            target_acc = "ACC_1001"
            # Extract numbers (pure numeric or alphanumeric account tokens)
            found_nums = re.findall(r'\b\d{4,12}\b', user_query)
            if not found_nums:
                found_nums = re.findall(r'\b[A-Z]{2,4}\d{2,12}\b', user_query)
            if found_nums:
                target_acc = found_nums[0]

            graph_res = self.graph_engine.trace_mule_chain(target_acc, max_hops=3)

            sql_query = f"""
            SELECT transaction_id, timestamp, transaction_amount, sender_account_number, receiver_account_number, transaction_mode
            FROM bank_transactions
            WHERE sender_account_number = '{target_acc}' OR receiver_account_number = '{target_acc}'
            ORDER BY timestamp ASC;
            """

            intent = f"Perform 3-hop NetworkX mule money flow traversal starting from Account/Entity '{target_acc}'."
            results = self._execute_safe_sql(sql_query)

            cot_steps = [
                {"step": 1, "title": "Intent & Entity Extraction", "content": intent},
                {"step": 2, "title": "Query Generation (SQL + 3-Hop NetworkX)", "content": f"Graph Traversal: 3-hop BFS on target '{target_acc}'. SQL: {sql_query.strip()}"},
                {"step": 3, "title": "Execution Results", "content": f"Retrieved {len(results)} direct transactions and traversed {graph_res.get('total_nodes', 0)} connected graph nodes across 3 hops."},
                {"step": 4, "title": "Evidentiary Correlation", "content": f"Categorized entities into {len(graph_res.get('layers', {}).get('Layer-1 Mules', []))} Layer-1 Mules, {len(graph_res.get('layers', {}).get('Layer-2 Mules', []))} Layer-2 Mules, and {len(graph_res.get('layers', {}).get('Layer-3 Offramps', []))} Layer-3 Offramps."},
                {"step": 5, "title": "Executive Lead Summary", "content": f"Entity '{target_acc}' exhibits structured money laundering. Funds are rapidly dispersed across a 3-hop network within short time deltas. Recommended for immediate account freezing and subpoena of CDR tower records."}
            ]

            return self._finalize({
                "query": user_query,
                "intent": intent,
                "generated_sql": sql_query.strip(),
                "execution_success": True,
                "row_count": len(results),
                "records": results[:10],
                "graph_traversal": graph_res,
                "linking_tree": self.graph_engine.linking_tree(target_acc, max_hops=3),
                "chain_of_thought": cot_steps,
                "executive_summary": cot_steps[-1]["content"]
            }, entity_hint=target_acc)

        # Scenario F: amount / mode filters (high-value or mode-specific)
        elif any(k in q_lower for k in ["greater than", "more than", "above", "exceeding", "high value", "large", "round"]):
            amount_m = re.search(r'(?:[₹rs. ]*)(\d[\d,]*)', user_query)
            amount = 0.0
            if amount_m:
                try:
                    amount = float(amount_m.group(1).replace(",", ""))
                except ValueError:
                    amount = 0.0
            mode = next((m for m in ("UPI", "IMPS", "NEFT", "RTGS", "ATM", "NETBANKING", "CHEQUE")
                         if m in q_lower.upper()), "")
            mode_sql = f" AND transaction_mode = '{mode}'" if mode else ""
            sql_query = f"""
            SELECT transaction_id, timestamp, transaction_amount, transaction_mode,
                   sender_account_number, receiver_account_number, receiver_customer_name
            FROM bank_transactions
            WHERE transaction_amount >= {amount:.2f}{mode_sql}
            ORDER BY transaction_amount DESC
            LIMIT 30;
            """
            intent = (f"Identify all {'{' + mode + ' ' if mode else ''}transactions of ₹{amount:,.0f} or more." if amount
                      else f"Identify the highest-value {'{' + mode + ' ' if mode else ''}transactions in the dataset.")

        # Scenario G: layering / top receiver analytics
        elif any(k in q_lower for k in ["top receiver", "layering", "layered", "rapidly", "smurf"]):
            sql_query = """
            SELECT receiver_account_number, receiver_customer_name,
                   SUM(transaction_amount) as total_amount, COUNT(*) as tx_count,
                   COUNT(DISTINCT sender_account_number) as senders, MAX(transaction_amount) as max_leg
            FROM bank_transactions
            GROUP BY receiver_account_number
            ORDER BY total_amount DESC
            LIMIT 20;
            """
            intent = ("Rank receiver accounts by total inflow to detect layering / smurfing "
                      "patterns where funds are consolidated into a single beneficiary.")

        # Scenario H: Default fallback query (All high-value correlated transactions)
        else:
            sql_query = """
            SELECT 
                bt.transaction_id, bt.timestamp, bt.transaction_amount, bt.transaction_mode,
                bt.sender_customer_name, bt.sender_account_number,
                bt.receiver_customer_name, bt.receiver_account_number,
                bcl.cdr_id, bcl.time_difference_seconds
            FROM bank_transactions bt
            LEFT JOIN bank_cdr_links bcl ON bt.transaction_id = bcl.transaction_id
            ORDER BY bt.transaction_amount DESC
            LIMIT 15;
            """
            intent = "Retrieve high-value bank transactions cross-linked with CDR call events."

        results = self._execute_safe_sql(sql_query)
        summary_text, answer_text, risk_text = self._synthesize_records_narrative(user_query, sql_query, results)

        cot_steps = [
            {"step": 1, "title": "Intent & Entity Extraction", "content": intent},
            {"step": 2, "title": "Query Generation (SQLite)", "content": sql_query.strip()},
            {"step": 3, "title": "Execution Results", "content": f"Executed query successfully. Returned {len(results)} matched records."},
            {"step": 4, "title": "Evidentiary Correlation", "content": "Correlated Bank transaction records and linked telecom/counterparty activity."},
            {"step": 5, "title": "Executive Lead Summary", "content": summary_text}
        ]

        envelope = {
            "query": user_query,
            "intent": intent,
            "generated_sql": sql_query.strip(),
            "execution_success": True,
            "row_count": len(results),
            "records": results[:10],
            "chain_of_thought": cot_steps,
            "executive_summary": summary_text,
            "risk_summary": risk_text,
            "answer": answer_text,
            "mode": "deterministic"
        }
        # Graph computation deferred: no longer eagerly generate linking tree here.
        # envelope["linking_tree"] = self._linking_tree(entity_hint) if entity_hint else None
        return self._finalize(envelope, entity_hint=entity_hint)

    def _linking_tree(self, entity_hint: str) -> Optional[Dict[str, Any]]:
        """Best-effort enriched 3-hop linking tree (transactions <-> phones
        <-> accounts) for a resolved entity; None when the entity is not in
        the graph. Always the `linking_tree()` layer-list shape."""
        try:
            return self.graph_engine.linking_tree(str(entity_hint), max_hops=3)
        except Exception:
            return None

    # ------------------------------------------------------------ intel layer

    @staticmethod
    def _score_record(r: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic risk estimate (0-100) for a copilot result row.
        Rules: large-value, night-hour, fast-payment modes, telecom/internet
        correlation and round-amount signals. Never mutates the input."""
        score = 0
        amount = 0.0
        try:
            amount = float(r.get(_amount_key(r)) or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount >= 500_000:
            score += 30
        elif amount >= 100_000:
            score += 20
        elif amount >= 25_000:
            score += 10

        ts_raw = r.get(_ts_key(r)) or ""
        ts_s = str(ts_raw)
        try:
            hour = int(ts_s[11:13])
        except (IndexError, ValueError):
            hour = -1
        if 0 <= hour <= 5 or hour >= 22:
            score += 15

        mode = str(r.get(_mode_key(r)) or "").upper()
        if mode in ("UPI", "IMPS", "PAYTM", "WALLET"):
            score += 10
        elif mode in ("NEFT", "RTGS", "CHEQUE", "NETBANKING"):
            score += 5

        if r.get("cdr_id") or r.get("ipdr_id"):
            score += 8
        try:
            if abs(float(r.get("time_difference_seconds") or 0)) <= 300:
                score += 8
        except (TypeError, ValueError):
            pass
        if amount >= 10_000 and amount % 1000 == 0:
            score += 8

        score = min(100, score)
        return {"risk_score": score, "risk_band": _band(score)}

    def _resolve_entity_in_db(self, value: str) -> str:
        """DB-backed entity resolution: confirms ambiguous identifiers against
        the complaint ledger, bank accounts, subscriber phones and IFSC codes
        before the pure-regex classification is trusted."""
        v = (value or "").strip()
        t = _resolve_entity_type(v)
        if t in ("phone", "ip", "imei", "transaction", "ifsc"):
            return t
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT COUNT(*) c FROM complaints WHERE acknowledgement_no = ?",
            (v,)).fetchone()
        if row and row["c"]:
            return "complaint"
        row = cursor.execute(
            "SELECT COUNT(*) c FROM bank_transactions "
            "WHERE sender_account_number = ? OR receiver_account_number = ?",
            (v, v)).fetchone()
        if row and row["c"]:
            return "account"
        row = cursor.execute(
            "SELECT COUNT(*) c FROM subscribers WHERE phone = ? OR phone LIKE ?",
            (v, f"%{v[-10:]}")).fetchone()
        if row and row["c"]:
            return "phone"
        return t

    def _build_investigation_intel(
        self, records: List[Dict[str, Any]], entity_hint: Optional[str],
        user_query: str, total_found: int = 0) -> Dict[str, Any]:
        """The AI Investigation Assistant layer: entity resolution banner,
        INVESTIGATION SUMMARY, quick METRICS, AI INSIGHTS, next-action
        SUGGESTIONS and an EXPLANATION of why these records were returned.
        Works offline for every query path (deterministic + LLM)."""
        rows = records or []
        total_found = max(total_found, len(rows))
        amounts: List[float] = []
        accounts: Dict[str, int] = {}
        phones: Dict[str, int] = {}
        ips: List[str] = []
        receivers: Dict[str, int] = {}
        night_count = 0
        linked_count = 0
        mode_counts: Dict[str, int] = {}
        risk_scores: List[int] = []

        for r in rows:
            try:
                amt = float(r.get(_amount_key(r)) or 0.0)
            except (TypeError, ValueError):
                amt = 0.0
            amounts.append(amt)
            for a in (r.get("sender_account_number"), r.get("receiver_account_number")):
                if a:
                    accounts[str(a)] = accounts.get(str(a), 0) + 1
            ph = _phone_value(r)
            if ph:
                phones[ph] = phones.get(ph, 0) + 1
            ip = _ip_value(r)
            if ip and ip not in ips:
                ips.append(ip)
            recv = _receiver_value(r)
            if recv:
                receivers[recv] = receivers.get(recv, 0) + 1
            ts_s = str(r.get(_ts_key(r)) or "")
            try:
                hour = int(ts_s[11:13])
            except (IndexError, ValueError):
                hour = -1
            if 0 <= hour <= 5 or hour >= 22:
                night_count += 1
            if (r.get("cdr_id") not in (None, "", "None")) or (r.get("ipdr_id") not in (None, "", "None")):
                linked_count += 1
            mode = str(r.get(_mode_key(r)) or "").upper()
            if mode:
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
            risk_scores.append(self._score_record(r)["risk_score"])

        total_amount = sum(amounts)
        found = total_found or len(rows)
        highest = max(risk_scores) if risk_scores else 0
        avg = round(sum(risk_scores) / len(risk_scores)) if risk_scores else 0
        primary_account = max(accounts, key=accounts.get) if accounts else ""
        common_phone = max(phones, key=phones.get) if phones else ""
        top_receiver = max(receivers, key=receivers.get) if receivers else ""
        linked_ips = len(ips)

        entity_type = self._resolve_entity_in_db(entity_hint or "")

        narrative = (
            f"The query returned {found} matching forensic record{'s' if found != 1 else ''} "
            f"totalling ₹{total_amount:,.0f} with a peak risk score of {highest}/100. "
        )
        if primary_account:
            narrative += f"The primary account involved is {primary_account}. "
        if common_phone:
            narrative += f"A common phone {common_phone} recurs across the activity. "
        if top_receiver:
            narrative += f"Funds concentrated toward {top_receiver}. "
        if linked_ips:
            narrative += f"{linked_ips} distinct IP address{'es' if linked_ips != 1 else ''} are linked. "
        if not rows:
            narrative = ("No records matched this query. Try a phone number, account number, "
                         "transaction ID, IMEI, IP address or NCRP acknowledgement number, "
                         "or rephrase the question.")

        # ---- AI insights (pattern engine) ----
        insights: List[Dict[str, Any]] = []
        for recv, n in sorted(receivers.items(), key=lambda kv: -kv[1]):
            if n >= 2:
                insights.append({
                    "title": "Repeated Beneficiary",
                    "detail": f"{recv} appears in {n} of {found} records — funds may consolidate into one mule pocket.",
                    "severity": "high" if n >= 4 else "medium",
                })
        for ph, n in sorted(phones.items(), key=lambda kv: -kv[1]):
            if n >= 2:
                insights.append({
                    "title": "Shared Phone",
                    "detail": f"Phone {ph} recurs in {n} records, linking otherwise separate activity to one subscriber.",
                    "severity": "medium",
                })
        if found and night_count / found >= 0.4:
            insights.append({
                "title": "Night-Concentrated Activity",
                "detail": f"{round(night_count * 100 / found)}% of activity occurred between 22:00–06:00, a common evasion pattern.",
                "severity": "medium",
            })
        bursts = 0
        for a, n in accounts.items():
            if n >= 3:
                bursts += 1
        if bursts:
            insights.append({
                "title": "Velocity Burst",
                "detail": f"{bursts} account(s) show 3+ records in the result set — rapid sequential movement consistent with layering.",
                "severity": "high",
            })
        big = sum(1 for a in amounts if a >= 500_000)
        if big:
            insights.append({
                "title": "Large-Value Transfers",
                "detail": f"{big} record(s) exceed ₹5,00,000 — above the PMLA cash-threshold reporting band.",
                "severity": "high",
            })
        if linked_count and linked_count / found >= 0.3:
            insights.append({
                "title": "Telecom-Correlated Activity",
                "detail": f"{linked_count} of {found} records carry linked CDR/IPDR events, tying money movement to a live handset.",
                "severity": "medium",
            })
        if mode_counts and len(mode_counts) == 1:
            only = next(iter(mode_counts))
            insights.append({
                "title": "Single-Mode Concentration",
                "detail": f"All {found} records used {only} — uniform rail selection can indicate scripted mule behavior.",
                "severity": "low",
            })

        # ---- next-action suggestions (context aware, actionable, explained) ----
        suggestions: List[Dict[str, Any]] = []
        hint = entity_hint or primary_account or common_phone
        if hint:
            suggestions.append({
                "action": "Investigate Entity",
                "target": hint,
                "why": f"Start a fresh 3-hop investigation centered on {hint}.",
                "query": f"Trace the 3-hop mule flow from {hint}",
            })
        if primary_account:
            suggestions.append({
                "action": "Trace Money Flow",
                "target": primary_account,
                "why": f"{primary_account} is the most active account in this result set.",
                "query": f"Trace all transactions for account {primary_account}",
            })
            suggestions.append({
                "action": "Generate STR",
                "target": primary_account,
                "why": "Sufficient evidence exists for a Suspicious Transaction Report.",
                "query": f"Generate a report for account {primary_account}",
            })
        if common_phone:
            suggestions.append({
                "action": "Find Linked Calls",
                "target": common_phone,
                "why": f"Phone {common_phone} recurs across records — pull its CDR activity.",
                "query": f"Trace all activity for phone {common_phone}",
            })
        if hints_ips := ips[:3]:
            suggestions.append({
                "action": "Analyze IP",
                "target": hints_ips[0],
                "why": f"IP {hints_ips[0]} appears across the result set.",
                "query": f"Show activity for IP {hints_ips[0]}",
            })
        if top_receiver and top_receiver not in (primary_account, hint):
            suggestions.append({
                "action": "Investigate Receiver",
                "target": top_receiver,
                "why": f"{top_receiver} is the dominant inflow destination.",
                "query": f"Trace all activity for beneficiary {top_receiver}",
            })

        # ---- explanation (why these records) ----
        explanation: List[str] = []
        if entity_hint and entity_type != "identifier":
            explanation.append(
                f"Entity resolution: '{entity_hint}' was classified as a {entity_type} and used to filter the result set.")
        if found:
            explanation.append(
                f"{found} records matched the query intent '{user_query[:80]}'.")
        if total_amount >= 100_000:
            explanation.append(f"Combined value ₹{total_amount:,.0f} exceeds the high-value threshold.")
        for ins in insights[:4]:
            explanation.append(f"{ins['title']}: {ins['detail']}")
        if not explanation:
            explanation.append("No records matched; broaden the identifier or rephrase the question.")

        return {
            "entity_resolution": {
                "entity_id": entity_hint or primary_account or "",
                "entity_type": entity_type,
                "resolved": bool(entity_hint or primary_account),
            },
            "investigation_summary": {
                "found_transactions": found,
                "total_amount": round(total_amount, 2),
                "highest_risk": highest,
                "primary_account": primary_account,
                "common_phone": common_phone,
                "linked_ips": linked_ips,
                "linked_beneficiaries": len(receivers),
                "top_receiver": top_receiver,
                "narrative": narrative,
            },
            "metrics": {
                "records": found,
                "total_amount": round(total_amount, 2),
                "accounts": len(accounts),
                "phones": len(phones),
                "ips": linked_ips,
                "beneficiaries": len(receivers),
                "highest_risk": highest,
                "avg_risk": avg,
            },
            "insights": insights[:6],
            "suggestions": suggestions[:6],
            "explanation": explanation,
        }

    def _finalize(self, envelope: Dict[str, Any],
                  entity_hint: Optional[str] = None) -> Dict[str, Any]:
        """Attach per-record risk + the investigation-intel block to every
        query envelope, regardless of the path (deterministic or LLM)."""
        records = envelope.get("records") or []
        annotated = []
        for r in records:
            rec = dict(r)
            rec.update(self._score_record(rec))
            annotated.append(rec)
        envelope["records"] = annotated
        intel = self._build_investigation_intel(
            annotated, entity_hint, str(envelope.get("query") or ""),
            total_found=int(envelope.get("row_count") or 0))
        envelope.update(intel)
        
        if envelope.get("mode") == "sql":
            highest = intel.get("investigation_summary", {}).get("highest_risk", 0)
            if highest > 85:
                tx_ids = [r.get("transaction_id") for r in annotated if r.get("transaction_id")]
                reasons_text = []
                if tx_ids:
                    try:
                        in_clause = ",".join(f"'{x}'" for x in tx_ids)
                        cursor = self.conn.cursor()
                        cursor.execute(f"SELECT transaction_id, scenario_type FROM anomaly_records WHERE transaction_id IN ({in_clause}) AND is_suspicious = 1")
                        from backend.explain import _lookup
                        for row in cursor.fetchall():
                            stype = row["scenario_type"] if (isinstance(row, sqlite3.Row) or isinstance(row, dict)) else row[1]
                            tx_id = row["transaction_id"] if (isinstance(row, sqlite3.Row) or isinstance(row, dict)) else row[0]
                            if stype:
                                reasons_text.append(f"Transaction {tx_id}: {_lookup(str(stype))}.")
                    except Exception as e:
                        logger.debug("Anomaly lookup in _finalize skipped: %s", e)
                
                if reasons_text:
                    envelope["risk_summary"] = "This activity is classified as highly suspicious (Risk Score > 85). " + " ".join(reasons_text)
                else:
                    envelope["risk_summary"] = f"This activity is classified as highly suspicious (Risk Score: {highest}). It exhibits high-risk behavioural patterns (such as round amounts, unusual hours, or rapid telecom correlation) despite lacking an explicit ML anomaly label."
            else:
                envelope["risk_summary"] = f"According to the risk engine, this activity is NOT considered suspicious (Risk Score {highest} <= 85). No critical anomaly patterns were detected."
                
        return envelope

    def _execute_safe_sql(self, sql_query: str) -> List[Dict[str, Any]]:
        """Executes query with strict read-only safety validation."""
        sql_clean = sql_query.strip().upper()
        # Prevent non-SELECT statements
        if not sql_clean.startswith("SELECT") and not sql_clean.startswith("WITH"):
            raise ValueError("Security violation: Only SELECT queries are permitted.")

        # Reject write / meta / side-effect statements outright
        forbidden_keywords = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
            "REPLACE", "ATTACH", "DETACH", "PRAGMA", "EXPLAIN", "VACUUM",
            "REINDEX", "CREATE", "GRANT", "REVOKE",
        ]
        for kw in forbidden_keywords:
            if re.search(r'\b' + kw + r'\b', sql_clean):
                raise ValueError(f"Security violation: Query contains illegal keyword '{kw}'.")

        # Reject multi-statement payloads ("...; DROP ...")
        statements = [s.strip() for s in sql_query.split(";") if s.strip()]
        if len(statements) > 1:
            raise ValueError(
                "Security violation: multiple statements are not permitted.")

        cursor = self.conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def _remember(self, envelope: Dict[str, Any], user_query: str) -> None:
        """Feeds every answered query back into the learning memory so
        follow-up questions carry conversation + case continuity."""
        try:
            summary = str(envelope.get("executive_summary") or "").strip()
            if not summary:
                summary = str(envelope.get("intent") or "").strip()
            if summary:
                self.memory.remember_turn(user_query, summary)
        except Exception as e:
            logger.warning(f"Failed to update copilot memory: {e}")

    def _call_llm_api(self, user_query: str) -> Optional[Dict[str, Any]]:
        """Calls the live LLM (OpenRouter).

        Returns an envelope with ``mode``:
          * "sql"      — model generated SQL, executed against the copilot DB
          * "general"  — model answered from general knowledge (sql_query null)
        Returns None only when both providers failed; the caller falls back
        to the deterministic pipeline.
        """
        try:
            mem_block = self.memory.memory_block()
            rag_block = getattr(self, '_rag_block', '')
            
            # Cap RAG block and memory block to keep total prompt below ~1,500 tokens (prevents Groq HTTP 413)
            mem_snippet = mem_block[:1000] if len(mem_block) > 1000 else mem_block
            rag_snippet = rag_block[:1500] if len(rag_block) > 1500 else rag_block

            user_content = (
                f"CORPUS BRIEF + CONVERSATION MEMORY:\n{mem_snippet}"
                f"\n\n{rag_snippet}"
                f"\n\nINVESTIGATOR QUERY: {user_query}"
            )
            ok, parsed, meta = self.llm.generate_json(SYSTEM_PROMPT, user_content)
            self._last_llm_meta = meta
            if not ok or not parsed:
                logger.info(f"LLM unavailable ({meta.get('error')}); "
                            "deterministic pipeline will serve this query.")
                return None

            sql_q = str(parsed.get("sql_query") or "").strip()
            general_answer = str(parsed.get("general_answer") or "").strip()
            start_node = str(parsed.get("graph_start_node") or "").strip() or None

            if sql_q and not sql_q.upper().startswith("NULL"):
                records = []
                execution_success = True
                try:
                    records = self._execute_safe_sql(sql_q)
                except Exception as e:
                    execution_success = False
                    logger.warning(f"LLM generated invalid SQL: {e}")

                # Graph computation deferred
                graph_res = None
                tree_res = None
                
                # Second LLM call: interpretation
                interp_summary = ""
                interp_answer = ""
                interp_risk = ""
                cot = _normalize_cot(parsed.get("cot_reasoning", []))

                if execution_success and records:
                    import json
                    dumped_rows = json.dumps(records[:6], default=str)
                    if len(dumped_rows) > 2000:
                        dumped_rows = dumped_rows[:2000] + "... [truncated for brevity]"
                    interp_content = (
                        f"INVESTIGATOR QUERY: {user_query}\n\n"
                        f"SQL EXECUTED:\n{sql_q}\n\n"
                        f"EXECUTED QUERY ROWS:\n{dumped_rows}"
                    )
                    ok2, parsed2, meta2 = self.llm.generate_json(INTERPRETATION_PROMPT, interp_content)
                    if ok2 and parsed2:
                        def _clean_str(val: Any) -> str:
                            if not val:
                                return ""
                            s = str(val).strip()
                            s = s.replace("\u202f", " ").replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "").replace("\u2011", "-")
                            s = s.replace("\\n", "\n").replace(r"\n", "\n")
                            # Normalize table rows: convert double pipes "||" into "|\n|"
                            s = re.sub(r'\|\s*\|+', '|\n|', s)
                            return s

                        interp_summary = _clean_str(
                            parsed2.get("executive_summary")
                            or parsed2.get("summary")
                            or parsed2.get("overview")
                            or ""
                        )
                        interp_answer = _clean_str(
                            parsed2.get("final_answer")
                            or parsed2.get("answer")
                            or parsed2.get("detailed_answer")
                            or parsed2.get("response")
                            or ""
                        )
                        interp_risk = _clean_str(
                            parsed2.get("suspicion_reasoning")
                            or parsed2.get("risk_reasoning")
                            or parsed2.get("why_suspicious")
                            or ""
                        )
                        if "cot_reasoning" in parsed2:
                            cot.extend(_normalize_cot(parsed2["cot_reasoning"]))

                    # If LLM interpretation failed or was rate-limited, synthesize rich natural-language forensic summary
                    if not interp_answer:
                        fallback_sum, fallback_ans, fallback_risk = self._synthesize_records_narrative(user_query, sql_q, records)
                        if not interp_summary: interp_summary = fallback_sum
                        interp_answer = fallback_ans
                        if not interp_risk: interp_risk = fallback_risk
                else:
                    # When LLM generated bad SQL syntax or 0 records matched strict filters,
                    # check if deterministic pipeline yields actual corpus records
                    det = self._run_deterministic_pipeline(user_query)
                    if det and det.get("records") and len(det["records"]) > 0:
                        logger.info("Deterministic fallback retrieved matching records where LLM query yielded zero rows.")
                        det["llm_provider"] = meta.get("provider", "")
                        det["llm_model"] = meta.get("model", "")
                        det["llm_latency_ms"] = meta.get("latency_ms", 0)
                        self._remember(det, user_query)
                        return det
                    elif not execution_success:
                        if det:
                            det["llm_provider"] = meta.get("provider", "")
                            det["llm_model"] = meta.get("model", "")
                            det["llm_latency_ms"] = meta.get("latency_ms", 0)
                            self._remember(det, user_query)
                            return det
                    else:
                        fallback_sum, fallback_ans, fallback_risk = self._synthesize_records_narrative(user_query, sql_q, [])
                        interp_summary = fallback_sum
                        interp_answer = fallback_ans
                        interp_risk = fallback_risk

                envelope = self._finalize({
                    "query": user_query,
                    "intent": parsed.get("intent", user_query),
                    "generated_sql": sql_q,
                    "execution_success": execution_success,
                    "row_count": len(records),
                    "records": records[:10],
                    "graph_traversal": graph_res,
                    "linking_tree": tree_res,
                    "chain_of_thought": cot,
                    "executive_summary": interp_summary or "Executed forensic query. Summary compiled.",
                    "risk_summary": interp_risk or "",
                    "answer": interp_answer or interp_summary or "Forensic query executed.",
                    "mode": "sql",
                }, entity_hint=start_node)
            else:
                # Check if deterministic pipeline can answer analytical questions before returning generic text
                det = self._run_deterministic_pipeline(user_query)
                if det and det.get("records") and len(det["records"]) > 0:
                    det["llm_provider"] = meta.get("provider", "")
                    det["llm_model"] = meta.get("model", "")
                    det["llm_latency_ms"] = meta.get("latency_ms", 0)
                    self._remember(det, user_query)
                    return det

                # General / conceptual question — no SQL, full interpretive answer
                summary = (parsed.get("executive_summary") or general_answer
                           or f"Interpretation of: {user_query}")
                envelope = {
                    "query": user_query,
                    "intent": parsed.get("intent", user_query),
                    "generated_sql": "",
                    "execution_success": True,
                    "row_count": 0,
                    "records": [],
                    "graph_traversal": None,
                    "linking_tree": None,
                    "chain_of_thought": _normalize_cot(
                        parsed.get("cot_reasoning", [])),
                    "executive_summary": summary,
                    "general_answer": general_answer,
                    "answer": parsed.get("final_answer") or summary,
                    "mode": "general",
                }
                envelope.update(self._build_investigation_intel(
                    [], None, user_query, total_found=0))

            envelope["llm_provider"] = meta.get("provider", "")
            envelope["llm_model"] = meta.get("model", "")
            envelope["llm_latency_ms"] = meta.get("latency_ms", 0)
            self._remember(envelope, user_query)
            return envelope
        except Exception as e:
            logger.warning(f"LLM API call skipped/failed: {e}")
        return None
