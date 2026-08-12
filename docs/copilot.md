# Investigative Copilot

The Investigative Copilot (`investigative_copilot/`) is an autonomous, Grounded RAG (Retrieval-Augmented Generation) assistant that allows investigators to query the fused case data using natural language in English, Hindi, or Gujarati.

## 1. Architecture Flow

1. **Natural Language Query**: The user asks a question (e.g., "Show me all transfers greater than 50,000 rupees connected to phone 9876543210").
2. **Intent & Entity Extraction**: The system parses the query to extract the core intent (`TRANSACTION_SEARCH`) and entities (`+919876543210`, `50000`).
3. **Data Access / SQL Execution**: The backend translates the intent into a programmatic query against the in-memory state bundle or NetworkX graph.
4. **Context Injection**: The raw JSON results (the "evidence") are retrieved.
5. **LLM Generation**: The prompt, containing the user's question and the strict JSON evidence, is sent to the LLM (powered by Groq).
6. **Grounded Answer**: The LLM generates a human-readable response strictly grounded in the provided evidence.

## 2. Evidence Grounding (No Hallucinations)
The Copilot operates under strict system prompts that forbid it from answering questions using its general pre-training data. If the answer is not present in the retrieved context bundle, the Copilot will explicitly state that the evidence does not exist in the current dataset.

## 3. Groq API Key Management
The Copilot utilizes the Groq inference engine for high-speed LLM generation.

* **Storage**: Keys are stored in `backend/.env` using the format `GROQ_API_KEY_{N}`.
* **Rotation**: The backend automatically loads all keys and rotates through them sequentially to load-balance requests.
* **Fallback**: If a key hits a rate limit, the system automatically falls back to the next available key. If all keys fail, the UI elegantly notifies the user or falls back to basic deterministic search.

**Security Note**: Never commit `.env` files to version control. The repository includes an `.env.example` file for reference.
