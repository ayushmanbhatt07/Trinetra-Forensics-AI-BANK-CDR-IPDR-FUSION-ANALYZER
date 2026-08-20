# Groq API Key Management

Whenever the user says "Add this Groq API key" or provides a new Groq API key to be added to the project, you MUST automatically follow this protocol:

1. **Modify `backend/.env`**:
   - Append the new key to `backend/.env` using the scalable indexed format: `GROQ_API_KEY_{N}=<key>`.
   - Preserve the numbering sequence (e.g., if `GROQ_API_KEY_1` is the last one, add `GROQ_API_KEY_2`).

2. **Zero Code Changes**:
   - Do NOT modify any Python source code. `backend/config.py` is already programmed to automatically discover, load, de-duplicate, and rotate any environment variables that start with `GROQ_API_KEY`.
   - Ensure it is included in rotation and fallback automatically by the existing engine.
   - Verify every Groq integration automatically sees the new key by confirming the `.env` write was successful.
