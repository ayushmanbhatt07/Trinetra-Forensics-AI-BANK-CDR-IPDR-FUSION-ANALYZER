# Canonical Normalization

Normalization is a critical step executed in `backend/normalise.py`. Without strict normalization, cross-dataset fusion is impossible, as the same entity might be represented differently across Bank, CDR, and IPDR files.

## 1. Phone Numbers
Phone numbers appear wildly different across datasets:
* `9876543210`
* `09876543210`
* `+919876543210`
* `91-98765-43210`

**Normalization Logic**:
The system strips all non-numeric characters, removes leading zeroes, assumes Indian country code (+91) if 10 digits are present, and outputs a strict E.164 canonical string: `+919876543210`.

## 2. Timestamps
Timestamps are highly operator-dependent:
* `12/04/2023 14:30:00`
* `2023-04-12T14:30:00Z`
* `12-Apr-23 2:30 PM`

**Normalization Logic**:
Uses `dateutil.parser` and custom format strings to aggressively parse dates. All timestamps are converted to UTC and stored in strict ISO-8601 format.

## 3. Account Numbers
Bank statements often mask account numbers or include branch prefixes.
**Normalization Logic**:
Strips whitespace and special characters. Where partial masking is present (e.g., `XXXXXX1234`), it stores it as a `PARTIAL_ACCOUNT` entity, which can be probabilistically linked later.

## 4. UPI IDs and IPs
* **UPI IDs**: Converted to lowercase, whitespace removed (e.g., `user @ okicici` -> `user@okicici`).
* **IP Addresses**: Validated using the `ipaddress` module. IPv4 and IPv6 addresses are stored in their standard string representations. Leading zeroes in octets are stripped.
