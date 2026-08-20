# Troubleshooting Guide

## 1. Copilot / LLM Issues
**Symptom**: The AI Copilot returns an error, hangs indefinitely, or states it cannot connect.
**Cause**: The OpenRouter API key is missing, invalid, or rate-limited.
**Solution**:
1. Check `backend/.env` for a valid `OPEN_ROUTER_KEY_1` entry.
2. Check the backend console output for `429 Too Many Requests`.
3. If rate-limited, add a secondary key (`OPEN_ROUTER_KEY_2`) and restart the backend server (`uvicorn`). The system will automatically utilize the fallback.

## 2. Parsing Failures
**Symptom**: An uploaded file shows up in the `skipped` bin on the Ingestion dashboard.
**Cause**: The file fingerprint did not match any known schema (e.g., it's a completely unsupported bank format), or the file is password-protected.
**Solution**:
1. Ensure the PDF is not password protected.
2. If the format is currently unsupported, it must be added to the parser ecosystem (`backend/detect/fingerprints.py`). The system is designed to gracefully skip unknown files to prevent pipeline crashes.

## 3. Empty Graphs or Timelines
**Symptom**: Files upload successfully, but the Network Graph or Fused Transactions views are completely empty.
**Cause**: The datasets provided contain no overlapping entities (e.g., the Bank statement belongs to Account A, but the CDR belongs to Phone B, and there are no shared identifiers to link them).
**Solution**:
1. Ensure you are uploading a cohesive dataset (e.g., the provided `data/` demo files).
2. The Fusion Engine requires common linkage (a shared phone number, UPI ID, or IP address) to join the isolated datasets.

## 4. Frontend Connection Refused
**Symptom**: The Next.js UI displays "Network Error" or fails to load data.
**Cause**: The FastAPI backend is not running on port 10000.
**Solution**:
1. Verify the backend terminal is running without syntax errors.
2. If running via Docker, ensure `docker-compose ps` shows `trinetra-backend` as `Up`.
3. Check for port conflicts on `10000`.
