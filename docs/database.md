# Storage and Database Architecture

Tri-Netra Forensics currently utilizes an agile, in-memory state bundle approach for persistence, optimized for rapid prototyping and local, containerized deployments.

## 1. The State Bundle (`backend/store.py`)

Instead of requiring a heavy, external relational database setup (like PostgreSQL) for the initial MVP, the backend manages the fused investigation state via an internal dictionary bundle.

* **In-Memory Operations**: All entities, events, and anomalies are held in memory during the active session. This allows the Graph Engine (NetworkX) and the Risk Engine to operate with zero-latency data access.
* **Disk Persistence (`backend.db`)**: Periodically, or upon specific pipeline transitions, the entire state bundle is serialized to disk as a JSON object (`backend.db`).
* **Session Rehydration**: Upon backend restart, `store.py` checks for the presence of `backend.db`. If found, it deserializes the bundle back into memory, restoring the previous investigation state instantly.

## 2. Advantages of the Current Approach
* **Zero Infrastructure Overhead**: Evaluators and users can run the entire system without provisioning a separate database container or configuring connection strings.
* **Extreme Agility**: The schema can evolve rapidly without requiring complex database migration scripts (e.g., Alembic).

## 3. Limitations and Future Scaling
While the JSON bundle approach is excellent for cases involving tens of thousands of rows, it will face memory bottlenecks at the scale of millions of rows.

**Future Architecture**:
For a production deployment spanning millions of telecom and banking records, `store.py` is designed to be swapped out for a persistent relational database:
* **PostgreSQL**: For storing the `Entity` and `Event` tables with proper indexing on timestamps and canonical identifiers.
* **Neo4j**: For handling the vast multi-domain relationship graphs currently managed by NetworkX in memory.

## 4. Resetting the Environment
To completely wipe the current investigation and start fresh, the user simply deletes the `backend.db` file and restarts the FastAPI server.
