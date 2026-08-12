# Data Model

Tri-Netra Forensics operates on a Canonical Entity and Unified Event model. Because raw datasets (Bank, CDR, IPDR) arrive in varying schemas, the system forces all records into this strictly typed internal representation.

## 1. Canonical Entity Model

All actors in the system are represented as "Entities". An entity is the core node in the network graph.

### `Entity`
* **`entity_id`**: A globally unique hash of the identifier.
* **`type`**: The canonical type of the entity (`PHONE`, `ACCOUNT`, `IP`, `UPI`, `IMEI`, `IMSI`).
* **`value`**: The normalized value (e.g., `+919876543210`).
* **`metadata`**: A dictionary of inferred attributes (e.g., operator name, bank name, location tags).
* **`risk_score`**: An aggregated float representing the entity's suspicion level.

## 2. Unified Event Model

Every action—whether a phone call, a money transfer, or an internet session—is represented as an "Event". This allows the timeline to plot everything on a single axis.

### `Event`
* **`event_id`**: Unique identifier for the event.
* **`timestamp`**: ISO-8601 formatted UTC timestamp.
* **`event_type`**: `TRANSACTION`, `CALL`, `SMS`, `IP_SESSION`, `COMPLAINT`.
* **`source_entity_id`**: The entity initiating the event (e.g., Caller, Remitter).
* **`target_entity_id`**: The entity receiving the event (e.g., Receiver, Beneficiary).
* **`attributes`**: Event-specific data (e.g., `amount`, `duration`, `cell_tower_id`, `data_volume`).
* **`anomalies`**: Array of flags attached to this event by the Risk Engine.

## 3. Relationships (Graph Model)

The `NetworkX` graph is built directly from the Unified Event Model:
* **Nodes**: `Entity` instances.
* **Edges**: Directed links representing aggregated `Event` instances between two entities, weighted by frequency or monetary volume.
