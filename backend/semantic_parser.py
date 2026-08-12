"""Semantic Narration Engine for Forensic Intelligence.

Transforms unstructured raw bank narrations into highly structured investigation
objects using a batched LLM classification pipeline. Extracts Merchants, Payment
Gateways, Purpose, and tags Behavioural & Risk indicators.
"""

from typing import List, Dict, Any
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from investigative_copilot.llm_client import LlmClient

logger = logging.getLogger(__name__)

SEMANTIC_PROMPT = """You are a digital forensics expert analyzing bank transaction narrations.
You will be provided with a JSON array of transaction objects containing 'txn_id' and 'narration'.
For each transaction, extract the following structured intelligence:
- merchant_name: Unified name of the business/person (e.g. "Swiggy", "Rahul", "Amazon") or ""
- merchant_category: e.g. "Food", "Shopping", "Travel", "Salary", "Investment", "Utility", "Unknown"
- payment_gateway: e.g. "NPCI", "Razorpay", "BillDesk", "PayU", "UPI", ""
- purpose: Inferred purpose of the transfer or ""
- risk_tags: List of strings (e.g. "High Value", "Suspicious Merchant", "Crypto") or []
- salary_flag: 1 if it looks like a salary deposit, else 0
- recurring_flag: 1 if it looks like a subscription or EMI, else 0
- loan_flag: 1 if it's a loan disbursement or repayment, else 0

Return ONLY a valid JSON object with a key 'results' mapping 'txn_id' to the extracted intelligence object.
Example:
{
  "results": {
    "txn_123": {
      "merchant_name": "Swiggy",
      "merchant_category": "Food",
      "payment_gateway": "UPI",
      "purpose": "Food Delivery",
      "risk_tags": [],
      "salary_flag": 0,
      "recurring_flag": 0,
      "loan_flag": 0
    }
  }
}
"""

import re

def _rule_based_enrichment(r: Dict[str, Any]) -> dict:
    enrichment = {}
    narration = str(r.get("narration", "")).upper()
    
    # Extract UPI Merchants (UPI-MERCHANT-...)
    upi_match = re.search(r'UPI-(.*?)-(?:GPAY|PHONEPE|PAYTM|BHIM|Q\d+|[\w\.]+@\w+)', narration)
    if upi_match:
        enrichment["merchant_name"] = upi_match.group(1).strip()
        enrichment["payment_gateway"] = "UPI"
    
    # Extract UPI P2M/P2A
    p2m_match = re.search(r'UPI[/\\]P2[MA][/\\]([^/\\]+)', narration)
    if p2m_match:
        enrichment["merchant_name"] = p2m_match.group(1).strip()
        enrichment["payment_gateway"] = "UPI"
    
    # Extract NEFT/RTGS/IMPS senders
    neft_match = re.search(r'(NEFT|RTGS|IMPS)-[A-Z0-9]+-(.*?)-', narration)
    if neft_match:
        enrichment["payment_gateway"] = neft_match.group(1)
        enrichment["merchant_name"] = neft_match.group(2).strip()

    # Identify category hints
    if any(k in narration for k in ["SWIGGY", "ZOMATO", "RESTAURANT", "FOOD", "CAFE"]):
        enrichment["merchant_category"] = "Food"
    elif any(k in narration for k in ["AMAZON", "FLIPKART", "MYNTRA", "SHOP"]):
        enrichment["merchant_category"] = "Shopping"
    elif any(k in narration for k in ["SALARY", "SAL", "PAYROLL"]):
        enrichment["merchant_category"] = "Salary"
        enrichment["salary_flag"] = 1
    elif any(k in narration for k in ["LOAN", "EMI", "FINANCE"]):
        enrichment["loan_flag"] = 1
    
    if "ATM" in narration or "CASH" in narration:
        enrichment["payment_gateway"] = "ATM/CASH"

    return enrichment

def enrich_bank_transactions(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Takes normalized bank records and applies rule-based semantic enrichment."""
    if not records:
        return records

    for r in records:
        rule_enrichment = _rule_based_enrichment(r)
        
        r["merchant_name"] = rule_enrichment.get("merchant_name", "")
        r["merchant_category"] = rule_enrichment.get("merchant_category", "Unknown")
        r["payment_gateway"] = rule_enrichment.get("payment_gateway", "")
        r["purpose"] = ""
        r["geo_location"] = ""
        r["risk_tags"] = ""
            
        r["confidence_score"] = 95 if r["merchant_name"] else 50
        r["salary_flag"] = rule_enrichment.get("salary_flag", 0)
        r["recurring_flag"] = 0
        r["loan_flag"] = rule_enrichment.get("loan_flag", 0)
        r["suspicious_flag"] = 0
        r["cash_burst_flag"] = 1 if "ATM" in str(r.get("narration", "")).upper() and (r.get("debit") or 0) > 20000 else 0

    return records
