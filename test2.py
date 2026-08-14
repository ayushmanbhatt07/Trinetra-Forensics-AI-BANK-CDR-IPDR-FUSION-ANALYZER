import requests
import time

URL = "http://127.0.0.1:8000"
s = requests.Session()
s.post(f"{URL}/auth/login", json={"username": "admin", "password": "password"})
print("Logged in")

res = s.post(f"{URL}/ingest/folder", json={"folder": "data"})
print("Ingest triggered:", res.status_code)

while True:
    t0 = time.time()
    h = s.get(f"{URL}/health", timeout=2).status_code
    dt_h = time.time() - t0
    
    t0 = time.time()
    p = s.get(f"{URL}/ingest/pipeline-status", timeout=2)
    dt_p = time.time() - t0
    p_json = p.json() if p.status_code == 200 else {}
    
    t0 = time.time()
    a = s.get(f"{URL}/hybrid/transactions", timeout=2).status_code
    dt_a = time.time() - t0
    
    print(f"Health: {h} ({dt_h:.3f}s) | Pipeline: {p.status_code} ({dt_p:.3f}s) [{p_json.get('status')}] | Alerts: {a} ({dt_a:.3f}s)")
    if p_json.get("ready") or p_json.get("status") == "ERROR":
        break
    time.sleep(1)
