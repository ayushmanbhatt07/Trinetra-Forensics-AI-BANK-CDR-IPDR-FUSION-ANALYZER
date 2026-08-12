import time
import requests

def measure_workflow():
    print("--- RUN ---")
    start = time.time()
    
    # 1. Start Ingestion
    print("Uploading...")
    t0 = time.time()
    r = requests.post("http://localhost:10000/ingest", json={"folder": "F:/SCRATCH/AI-BANK-TRANSACTIONS-TELECOM-ANALYZER/data/surat_police_samples"})
    ingest_time = time.time() - t0
    print(f"Ingest POST returned in {ingest_time:.2f}s")
    
    # 2. Wait for Fused Ready
    t0 = time.time()
    while True:
        ps = requests.get("http://localhost:10000/ingest/pipeline-status").json()
        if ps.get("status") not in ("PARSING", "FUSING"):
            break
        time.sleep(0.5)
    fused_ready_time = time.time() - t0
    print(f"Fused ready in {fused_ready_time:.2f}s")
    
    # 3. Request Fused Page (with risk_annotate=1 as frontend does)
    t0 = time.time()
    r = requests.get("http://localhost:10000/data/fused?offset=0&limit=50&risk_annotate=1")
    fused_page_time = time.time() - t0
    print(f"Fused page returned in {fused_page_time:.2f}s")
    
    # 4. Wait for Anomalies Ready (SCORING -> READY)
    t0 = time.time()
    while True:
        ps = requests.get("http://localhost:10000/ingest/pipeline-status").json()
        if ps.get("ready"):
            break
        time.sleep(0.5)
    anomalies_ready_time = time.time() - t0
    print(f"Anomalies ready in {anomalies_ready_time:.2f}s")
    
    # 5. Request Anomalies Page
    t0 = time.time()
    r = requests.get("http://localhost:10000/scoring/alerts?min_risk=50&limit=200")
    anomalies_page_time = time.time() - t0
    print(f"Anomalies page returned in {anomalies_page_time:.2f}s")
    
    return {
        "ingest": ingest_time,
        "fused_ready": fused_ready_time,
        "fused_page": fused_page_time,
        "anomalies_ready": anomalies_ready_time,
        "anomalies_page": anomalies_page_time,
    }

headers = {"Authorization": "Bearer TEST"}

print("Setting up auth token... skipping auth for script by mocking or using a valid token.")
# Let's bypass auth for local testing by modifying api.py to allow it, or just use the UI.
# Actually, the user wants us to run the workflow 3 times. We can just login first.

def login_and_measure():
    r = requests.post("http://localhost:10000/auth/register", json={"username": "testaudit", "password": "TestPass123!"})
    r = requests.post("http://localhost:10000/auth/login", json={"username": "testaudit", "password": "TestPass123!"})
    token = r.json().get("access_token")
    if not token:
        print("Login failed:", r.json())
        return
    global headers
    headers = {"Authorization": f"Bearer {token}"}
    
    # Override requests.get and post to inject auth
    original_get = requests.get
    original_post = requests.post
    requests.get = lambda url, **kwargs: original_get(url, headers=headers, **kwargs)
    requests.post = lambda url, **kwargs: original_post(url, headers=headers, **kwargs)

    results = []
    for i in range(3):
        requests.delete("http://localhost:10000/ingest")
        res = measure_workflow()
        results.append(res)
        time.sleep(2)
        
    print("\n--- RESULTS ---")
    for key in results[0].keys():
        vals = [r[key] for r in results]
        print(f"{key}: avg {sum(vals)/3:.2f}s (min {min(vals):.2f}s, max {max(vals):.2f}s)")

login_and_measure()
