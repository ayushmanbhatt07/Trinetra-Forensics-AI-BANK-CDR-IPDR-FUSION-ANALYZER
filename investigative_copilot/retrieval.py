"""Lightweight RAG retrieval for the Investigative Co-Pilot.

Extracts entity hints (phone / TXN / account / IMEI / IP / amount / mode /
location / name) from the investigator's natural-language query, pulls the top
matching rows from the fused copilot DB (bank, CDR, IPDR, subscribers,
complaints, anomaly_records) and formats them as a compact evidence context block that is
injected into the LLM prompt. This grounds every answer in the *uploaded
dataset* instead of general knowledge.
"""
import re
from typing import Any, Dict, List, Optional

PHONE_RE = re.compile(r"\b(?:\+?91)?[6-9]\d{9}\b|\b\d{10}\b|\b91\d{10}\b")
IMEI_RE = re.compile(r"\b\d{15}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Match real dataset transaction IDs: prefixes TXN/ATM/UPI/IMPS/NEFT/RTGS/CHEQUE
# followed by alphanumeric chars (e.g. TXN2501013A3ZMF, UPI250101CQ99CH).
TXN_RE = re.compile(
    r"\b((?:TXN|ATM|UPI|IMPS|NEFT|RTGS|CHEQUE)[A-Za-z0-9]{4,})\b",
    re.IGNORECASE,
)
CDR_RE = re.compile(r"\b(CDR\d{6,})\b", re.IGNORECASE)
IPDR_RE = re.compile(r"\b(IPDR\d{6,})\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"\b(?:inr|rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)\s*(lakh|crore|k)?", re.IGNORECASE)
ACCOUNT_RE = re.compile(r"\b\d{6,18}\b")

MODES = ("UPI", "IMPS", "NEFT", "RTGS", "ATM", "CHEQUE", "NETBANKING", "PAYTM", "WALLET")

_NAME_STOP = {
    "the", "and", "for", "from", "with", "that", "this", "have", "show", "find",
    "give", "what", "when", "where", "which", "about", "account", "transaction",
    "details", "record", "records", "anomalies", "anomaly", "anomalous", "suspicious",
    "flagged", "mule", "layering", "fraud", "transfers", "transfer", "bank", "cdr",
    "ipdr", "call", "calls", "session", "sessions", "phone", "number", "named",
    "all", "list", "trace", "summary", "overview", "top", "highest", "largest",
    "greater", "less", "between", "under", "above", "exceeding", "inr", "rs", "rupees",
    "why", "how", "is", "are", "were", "was", "any", "get", "who", "whom"
}


def extract_entities(query: str) -> Dict[str, List[str]]:
    """Pulls structured hints out of the free-text query."""
    out: Dict[str, List[str]] = {
        "phone": [], "txn": [], "cdr": [], "ipdr": [],
        "imei": [], "ip": [], "account": [],
        "amount": [], "mode": [], "location": [],
        "name": [],
    }
    q = query or ""
    raw_phones = list(dict.fromkeys(PHONE_RE.findall(q)))
    norm_phones = []
    for p in raw_phones:
        norm_phones.append(p)
        if len(p) == 12 and p.startswith("91"):
            norm_phones.append(p[2:])
        elif len(p) == 13 and p.startswith("+91"):
            norm_phones.append(p[3:])
            norm_phones.append(p[1:])
        elif len(p) == 10:
            norm_phones.append("91" + p)
            norm_phones.append("+91" + p)
    out["phone"] = list(dict.fromkeys(norm_phones))

    out["txn"] = [t.upper() for t in dict.fromkeys(TXN_RE.findall(q))]
    out["cdr"] = [t.upper() for t in dict.fromkeys(CDR_RE.findall(q))]
    out["ipdr"] = [t.upper() for t in dict.fromkeys(IPDR_RE.findall(q))]
    out["imei"] = list(dict.fromkeys(IMEI_RE.findall(q)))
    out["ip"] = list(dict.fromkeys(IP_RE.findall(q)))
    out["account"] = [a for a in dict.fromkeys(ACCOUNT_RE.findall(q)) if a not in out["phone"] and a not in out["imei"]]

    for m in MODES:
        if m in q.upper():
            out["mode"].append(m)

    for amt in AMOUNT_RE.findall(q):
        digits = amt[0].replace(",", "")
        if not digits:
            continue
        value = float(digits)
        suffix = (amt[1] or "").lower()
        if suffix == "crore":
            value *= 1e7
        elif suffix == "lakh":
            value *= 1e5
        elif suffix == "k":
            value *= 1e3
        if 100 <= value <= 1e10:
            out["amount"].append(value)

    out["location"] = [loc for loc in ("west bengal", "kolkata", "delhi", "mumbai", "gujarat", "rajasthan", "bihar", "tamil nadu", "karnataka", "assam") if loc in q.lower()]

    # Extract name candidates
    words = [w.strip(".,!?:;\"'()[]{}") for w in q.split() if w.strip(".,!?:;\"'()[]{}")]
    name_candidates = []
    for w in words:
        wl = w.lower()
        if wl not in _NAME_STOP and len(w) >= 3 and not w.isdigit() and not any(w.upper().startswith(p) for p in ("TXN", "ATM", "UPI", "IMPS", "CDR", "IPDR")):
            name_candidates.append(w)
    out["name"] = name_candidates

    return out


def _rows(cursor, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    try:
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []


def _txn_snippet(r: Dict[str, Any]) -> str:
    amt = r.get("transaction_amount")
    amt_s = f" ₹{amt:,.0f}" if isinstance(amt, (int, float)) else ""
    return (f"{r.get('transaction_id')}{amt_s} {r.get('transaction_mode') or ''} "
            f"{r.get('date') or ''} {r.get('timestamp') or ''} "
            f"from={r.get('sender_account_number')} ({r.get('sender_customer_name') or ''}) "
            f"to={r.get('receiver_account_number')} ({r.get('receiver_customer_name') or ''})")


def _cdr_snippet(r: Dict[str, Any]) -> str:
    return (f"{r.get('cdr_id')} {r.get('call_date')} {r.get('call_start_time')} "
            f"{r.get('call_type') or ''} {r.get('call_duration_seconds') or 0}s "
            f"{r.get('a_party_number')} -> {r.get('b_party_number')} "
            f"tower={r.get('first_bts_location') or ''} circle={r.get('roaming_network_circle') or ''}")


def _ipdr_snippet(r: Dict[str, Any]) -> str:
    return (f"{r.get('ipdr_id')} {r.get('session_date')} {r.get('session_start_time')} "
            f"msisdn={r.get('subscriber_msisdn')} imei={r.get('device_imei')} "
            f"{r.get('source_ip_address')} -> {r.get('destination_ip_address')} "
            f"port={r.get('destination_port')} {r.get('session_duration_seconds') or 0}s")


def _anomaly_snippet(r: Dict[str, Any]) -> str:
    amt = r.get("amount")
    amt_s = f" ₹{amt:,.0f}" if isinstance(amt, (int, float)) else ""
    return (f"ANOMALY {r.get('anomaly_id')}{amt_s} txn={r.get('transaction_id')} "
            f"cust={r.get('customer_name') or ''} ({r.get('customer_id') or ''}) "
            f"acc={r.get('account_no') or ''} risk={r.get('risk_score') or 0} "
            f"band={r.get('risk_band') or ''} scenario={r.get('scenario_type') or ''} "
            f"rules={r.get('rules_fired') or ''}")


def retrieve_context(conn, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """Returns up to ``top_k`` evidence rows relevant to the query, each as
    ``{"table": ..., "id": ..., "snippet": ...}``."""
    hints = extract_entities(query)
    cursor = conn.cursor()
    out: List[Dict[str, Any]] = []

    def push(table: str, idv: Any, snippet: str) -> None:
        if not idv or len(out) >= top_k * 3:
            return
        out.append({"table": table, "id": str(idv), "snippet": snippet.strip()})

    # 1. Exact entity lookups (phone / txn / account / imei / ip / name)
    for ph in hints["phone"]:
        pat = f"%{ph[-10:]}%" if len(ph) >= 10 else f"%{ph}%"
        for r in _rows(cursor, "SELECT * FROM bank_transactions WHERE sender_phone_number LIKE ? OR receiver_phone_number LIKE ? LIMIT 3", (pat, pat)):
            push("bank_transactions", r["transaction_id"], _txn_snippet(r))
        for r in _rows(cursor, "SELECT * FROM cdr_records WHERE a_party_number LIKE ? OR b_party_number LIKE ? LIMIT 3", (pat, pat)):
            push("cdr_records", r["cdr_id"], _cdr_snippet(r))
        for r in _rows(cursor, "SELECT * FROM ipdr_records WHERE subscriber_msisdn LIKE ? LIMIT 3", (pat,)):
            push("ipdr_records", r["ipdr_id"], _ipdr_snippet(r))
        for r in _rows(cursor, "SELECT * FROM subscribers WHERE phone LIKE ? LIMIT 2", (pat,)):
            push("subscribers", r.get("phone"), f"subscriber {r.get('name')} circle={r.get('circle')} imsi={r.get('imsi')} imei={r.get('imei')}")

    for name in hints["name"]:
        pat = f"%{name}%"
        for r in _rows(cursor, "SELECT * FROM anomaly_records WHERE customer_name LIKE ? ORDER BY risk_score DESC LIMIT 3", (pat,)):
            push("anomaly_records", r["anomaly_id"], _anomaly_snippet(r))
        for r in _rows(cursor, "SELECT * FROM bank_transactions WHERE sender_customer_name LIKE ? OR receiver_customer_name LIKE ? LIMIT 3", (pat, pat)):
            push("bank_transactions", r["transaction_id"], _txn_snippet(r))
        for r in _rows(cursor, "SELECT * FROM subscribers WHERE name LIKE ? LIMIT 2", (pat,)):
            push("subscribers", r.get("phone"), f"subscriber {r.get('name')} circle={r.get('circle')} phone={r.get('phone')}")

    for txn in hints["txn"]:
        for r in _rows(cursor, "SELECT * FROM anomaly_records WHERE transaction_id = ? LIMIT 2", (txn,)):
            push("anomaly_records", r["anomaly_id"], _anomaly_snippet(r))
        for r in _rows(cursor, "SELECT * FROM bank_transactions WHERE transaction_id = ? LIMIT 3", (txn,)):
            push("bank_transactions", r["transaction_id"], _txn_snippet(r))
    for cdr_id in hints["cdr"]:
        for r in _rows(cursor, "SELECT * FROM cdr_records WHERE cdr_id = ? LIMIT 3", (cdr_id,)):
            push("cdr_records", r["cdr_id"], _cdr_snippet(r))
    for ipdr_id in hints["ipdr"]:
        for r in _rows(cursor, "SELECT * FROM ipdr_records WHERE ipdr_id = ? LIMIT 3", (ipdr_id,)):
            push("ipdr_records", r["ipdr_id"], _ipdr_snippet(r))
    for acc in hints["account"]:
        for r in _rows(cursor, "SELECT * FROM anomaly_records WHERE account_no LIKE ? LIMIT 2", (f"%{acc}%",)):
            push("anomaly_records", r["anomaly_id"], _anomaly_snippet(r))
        for r in _rows(cursor, "SELECT * FROM bank_transactions WHERE sender_account_number = ? OR receiver_account_number = ? LIMIT 3", (acc, acc)):
            push("bank_transactions", r["transaction_id"], _txn_snippet(r))
        for r in _rows(cursor, "SELECT * FROM complaints WHERE account_no = ? LIMIT 2", (acc,)):
            push("complaints", r.get("complaint_id"), f"NCRP complaint {r.get('complaint_id')} acc={r.get('account_no')} state={r.get('state')} {r.get('complainant_name')}")
    for imei in hints["imei"]:
        for r in _rows(cursor, "SELECT * FROM ipdr_records WHERE device_imei = ? LIMIT 3", (imei,)):
            push("ipdr_records", r["ipdr_id"], _ipdr_snippet(r))
    for ip in hints["ip"]:
        for r in _rows(cursor, "SELECT * FROM ipdr_records WHERE source_ip_address = ? OR destination_ip_address = ? LIMIT 3", (ip, ip)):
            push("ipdr_records", r["ipdr_id"], _ipdr_snippet(r))

    # 2. Amount / mode filters (high-value interpretation)
    amt = max(hints["amount"]) if hints["amount"] else None
    if amt:
        for r in _rows(cursor, "SELECT * FROM bank_transactions WHERE transaction_amount >= ? ORDER BY transaction_amount DESC LIMIT 5", (amt,)):
            push("bank_transactions", r["transaction_id"], _txn_snippet(r))
    for mode in hints["mode"]:
        for r in _rows(cursor, "SELECT * FROM bank_transactions WHERE UPPER(transaction_mode) = ? ORDER BY transaction_amount DESC LIMIT 5", (mode,)):
            push("bank_transactions", r["transaction_id"], _txn_snippet(r))
    for loc in hints["location"]:
        pat = f"%{loc.replace(' ', '')}%"
        for r in _rows(cursor, "SELECT * FROM cdr_records WHERE first_bts_location LIKE ? OR roaming_network_circle LIKE ? LIMIT 5", (pat, pat)):
            push("cdr_records", r["cdr_id"], _cdr_snippet(r))

    # 3. High-level analytic intents (top movers / suspicious / anomalies / layering)
    ql = query.lower()
    if not out:
        _candidate = _extract_candidate_id(query)
        if _candidate:
            for r in _rows(cursor, "SELECT * FROM anomaly_records WHERE transaction_id = ? OR customer_id = ? COLLATE NOCASE LIMIT 2", (_candidate, _candidate)):
                push("anomaly_records", r["anomaly_id"], _anomaly_snippet(r))
            for r in _rows(cursor, "SELECT * FROM bank_transactions WHERE transaction_id = ? COLLATE NOCASE LIMIT 3", (_candidate,)):
                push("bank_transactions", r["transaction_id"], _txn_snippet(r))
            for r in _rows(cursor, "SELECT * FROM cdr_records WHERE cdr_id = ? COLLATE NOCASE LIMIT 3", (_candidate,)):
                push("cdr_records", r["cdr_id"], _cdr_snippet(r))
            for r in _rows(cursor, "SELECT * FROM ipdr_records WHERE ipdr_id = ? COLLATE NOCASE LIMIT 3", (_candidate,)):
                push("ipdr_records", r["ipdr_id"], _ipdr_snippet(r))

        if not out:
            if any(w in ql for w in ("anomal", "flagged", "alert", "suspicious", "mule", "fraud", "risk")):
                for r in _rows(cursor, "SELECT * FROM anomaly_records ORDER BY risk_score DESC LIMIT 8"):
                    push("anomaly_records", r["anomaly_id"], _anomaly_snippet(r))
            elif any(w in ql for w in ("largest", "top", "highest", "biggest", "high value", "large")):
                for r in _rows(cursor, "SELECT * FROM bank_transactions ORDER BY transaction_amount DESC LIMIT 8"):
                    push("bank_transactions", r["transaction_id"], _txn_snippet(r))
            elif any(w in ql for w in ("call", "cdr", "phone", "telecom")):
                for r in _rows(cursor, "SELECT * FROM cdr_records ORDER BY call_duration_seconds DESC LIMIT 8"):
                    push("cdr_records", r["cdr_id"], _cdr_snippet(r))
            elif any(w in ql for w in ("ip", "internet", "ipdr", "session")):
                for r in _rows(cursor, "SELECT * FROM ipdr_records ORDER BY session_duration_seconds DESC LIMIT 8"):
                    push("ipdr_records", r["ipdr_id"], _ipdr_snippet(r))
            elif any(w in ql for w in ("complaint", "ncrp", "fraud account")):
                for r in _rows(cursor, "SELECT * FROM complaints LIMIT 8"):
                    push("complaints", r.get("complaint_id"), f"NCRP complaint {r.get('complaint_id')} acc={r.get('account_no')} state={r.get('state')} {r.get('complainant_name')}")
            elif any(w in ql for w in ("all", "summary", "overview", "list", "show", "recent")):
                for r in _rows(cursor, "SELECT * FROM bank_transactions ORDER BY transaction_amount DESC LIMIT 8"):
                    push("bank_transactions", r["transaction_id"], _txn_snippet(r))

    return out[:top_k]


def format_context(rows: List[Dict[str, Any]]) -> str:
    """Formats retrieved rows into a compact, prompt-friendly evidence block."""
    if not rows:
        return ""
    lines = ["RETRIEVED CORPUS CONTEXT (authoritative rows from the uploaded dataset):"]
    for i, r in enumerate(rows, 1):
        lines.append(f"[{i}] table={r['table']} id={r['id']} | {r['snippet']}")
    return "\n".join(lines)


def best_entity_hint(hints: Dict[str, List[str]]) -> Optional[str]:
    """Best single entity to seed the linking tree, if any was mentioned."""
    for key in ("txn", "cdr", "ipdr", "account", "phone", "imei", "ip", "name"):
        if hints.get(key):
            return hints[key][0]
    return None


_CANDIDATE_ID_RE = re.compile(
    r"\b([A-Za-z]{2,6}\d[A-Za-z0-9]{4,})\b"
)


def _extract_candidate_id(query: str) -> Optional[str]:
    """Returns the most likely database identifier from the query, or None."""
    _STOP = {"the", "and", "for", "from", "with", "that", "this", "have",
             "show", "find", "give", "what", "when", "where", "which",
             "about", "account", "transaction", "details", "record"}
    for m in _CANDIDATE_ID_RE.finditer(query):
        token = m.group(1)
        if token.lower() not in _STOP and len(token) >= 6:
            return token
    return None
