# Cross-Dataset Fusion Engine

The Fusion Engine (`backend/fusion.py`) is the core intelligence layer of Tri-Netra Forensics. It is responsible for finding the "invisible lines" connecting disparate datasets (Bank, CDR, IPDR).

## 1. Unified Event Model
Before fusion can occur, all parsed and normalized records are cast into the Unified Event Model (see [Data Model](data-model.md)). This strips away provider-specific schemas and places every call, IP session, and money transfer onto a single, universal timeline.

## 2. Temporal Correlation
The most powerful forensic evidence often involves temporal coincidence. The Fusion Engine scans the unified timeline using sliding windows (e.g., 5 minutes, 10 minutes) to detect clustered activity.

### Example: The "Call -> IP -> Transfer" Pattern
1. **CALL**: Suspect A (`+919876543210`) calls Victim B (`+919000000000`) at 14:00 UTC.
2. **IP SESSION**: Suspect A's phone initiates an IPDR data session at 14:02 UTC.
3. **BANK TRANSFER**: A fraudulent IMPS transfer occurs from Victim B's account to Suspect A's mule account at 14:04 UTC.

The Fusion Engine flags this cluster because the events occurred within a tightly bound temporal window and share related entities, establishing a clear forensic narrative.

## 3. Shared Identifier Linking
Entities are linked across domains via shared attributes:
* **Account / Phone Linking**: A bank statement transaction might list a UPI ID (e.g., `9876543210@paytm`). The engine extracts the phone number and links the Bank Account entity to the Phone entity.
* **IP Linking**: An IPDR session logs a specific IP address. If that same IP address appears in bank login logs or complaint ledgers, the engine fuses the telecom and financial identities.

## 4. Graph Construction
Once entities are linked, the Fusion Engine feeds the relationships to the Graph Engine (`backend/graphs.py`), constructing the underlying `NetworkX` topology that powers the UI visualizations.
