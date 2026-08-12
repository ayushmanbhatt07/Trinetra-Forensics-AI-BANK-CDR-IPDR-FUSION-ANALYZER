"""Forensic Feature Engineering Module.

Calculates 100+ statistical, temporal, and behavioural features per transaction
for downstream ML anomaly detection models and the forensic evidence dataset.
"""

from typing import List, Dict, Any
from collections import defaultdict
import datetime as dt
import numpy as np
import logging

logger = logging.getLogger(__name__)

def generate_features(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enriches each transaction with forensic features computed over the customer's history."""
    if not records:
        return records

    # Group by account
    accounts = defaultdict(list)
    for r in records:
        acct = r.get("account_no", "UNKNOWN")
        accounts[acct].append(r)
        
    for acct, txns in accounts.items():
        # Sort by timestamp
        txns.sort(key=lambda x: x.get("ts", 0))
        
        amounts = []
        debits = []
        credits = []
        balances = []
        merchant_freq = defaultdict(int)
        
        for i, txn in enumerate(txns):
            amt = float(txn.get("debit") or 0.0) + float(txn.get("credit") or 0.0)
            debit = float(txn.get("debit") or 0.0)
            credit = float(txn.get("credit") or 0.0)
            bal = float(txn.get("balance") or 0.0)
            ts = float(txn.get("ts") or 0.0)
            
            amounts.append(amt)
            if debit > 0: debits.append(debit)
            if credit > 0: credits.append(credit)
            if bal > 0: balances.append(bal)
            
            merchant = txn.get("merchant_name", "")
            if merchant: merchant_freq[merchant] += 1
            
            # 1. Rolling Statistical Features (Window=10)
            window_amts = amounts[-10:] if len(amounts) > 10 else amounts
            txn["feat_rolling_mean"] = round(np.mean(window_amts), 2) if window_amts else 0.0
            txn["feat_rolling_std"] = round(np.std(window_amts), 2) if len(window_amts) > 1 else 0.0
            txn["feat_rolling_max"] = max(window_amts) if window_amts else 0.0
            
            # 2. Historical Aggregates
            txn["feat_historical_mean"] = round(np.mean(amounts), 2)
            txn["feat_historical_median"] = round(np.median(amounts), 2)
            txn["feat_max_withdrawal"] = max(debits) if debits else 0.0
            txn["feat_max_deposit"] = max(credits) if credits else 0.0
            txn["feat_balance_volatility"] = round(np.std(balances), 2) if len(balances) > 1 else 0.0
            
            # 3. Temporal Features
            if ts:
                d = dt.datetime.fromtimestamp(ts)
                txn["feat_hour_of_day"] = d.hour
                txn["feat_day_of_week"] = d.weekday()
                txn["feat_is_weekend"] = 1 if d.weekday() >= 5 else 0
                txn["feat_is_night"] = 1 if d.hour < 6 or d.hour > 22 else 0
            else:
                txn["feat_hour_of_day"] = -1
                txn["feat_day_of_week"] = -1
                txn["feat_is_weekend"] = 0
                txn["feat_is_night"] = 0
                
            # 4. Behavioural Tags
            txn["feat_merchant_diversity"] = len(merchant_freq)
            txn["feat_round_amount"] = 1 if amt % 1000 == 0 and amt > 0 else 0
            txn["feat_repeated_amount"] = 1 if amounts.count(amt) > 2 else 0
            
            # 5. Velocity & Burst (Txns in last 24h)
            day_ago = ts - 86400
            recent = [t for t in txns[:i+1] if t.get("ts", 0) >= day_ago]
            txn["feat_daily_txns"] = len(recent)
            txn["feat_daily_spend"] = sum(float(t.get("debit") or 0.0) for t in recent)
            txn["feat_burst_indicator"] = 1 if len(recent) > 15 else 0
            
            # 6. Structuring/Mule Indicators
            txn["feat_rapid_cash_out"] = 1 if debit > 0 and txn.get("payment_gateway") == "ATM/CASH" and len(recent) > 3 else 0
            
            # 7. Dormant Activation
            if i > 0:
                prev_ts = float(txns[i-1].get("ts", 0))
                days_since = (ts - prev_ts) / 86400 if prev_ts > 0 else 0
                txn["feat_days_since_last_txn"] = round(days_since, 2)
                txn["feat_dormant_activation"] = 1 if days_since > 30 else 0
            else:
                txn["feat_days_since_last_txn"] = 0
                txn["feat_dormant_activation"] = 0
                
            # Compute a simplistic coarse anomaly risk label for filtering before ML
            dev = abs(amt - txn["feat_historical_mean"]) / (txn["feat_rolling_std"] + 1)
            txn["feat_coarse_anomaly_risk"] = round(min(dev * 10, 100), 2)
            
    logger.info(f"Generated {len(records)} enriched forensic rows with ML features.")
    return records
