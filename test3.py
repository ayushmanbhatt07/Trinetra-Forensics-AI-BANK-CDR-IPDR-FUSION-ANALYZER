import requests
import time

URL = "http://127.0.0.1:8000"

s = requests.Session()
r = s.post(f"{URL}/auth/login", json={"username": "admin", "password": "password"})
print(f"Login: {r.status_code}")

# The session needs the token, maybe it's returning a token instead of a cookie?
# Ah! In this project, login returns a token: {"access_token": "...", "token_type": "bearer"}
if r.status_code == 200:
    token = r.json().get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})

r = s.post(f"{URL}/ingest/folder", json={"folder": "data"})
print(f"Ingest: {r.status_code}")

log_file = open("latency_log.txt", "w")
while True:
    t0 = time.time()
    h = s.get(f"{URL}/health", timeout=2)
    dt_h = time.time() - t0
    
    t0 = time.time()
    p = s.get(f"{URL}/ingest/pipeline-status", timeout=2)
    dt_p = time.time() - t0
    
    t0 = time.time()
    a = s.get(f"{URL}/hybrid/transactions", timeout=2)
    dt_a = time.time() - t0
    
    status_str = f"Health: {h.status_code} ({dt_h:.3f}s) | Pipeline: {p.status_code} ({dt_p:.3f}s) | Alerts: {a.status_code} ({dt_a:.3f}s)\n"
    print(status_str.strip())
    log_file.write(status_str)
    log_file.flush()
    
    p_json = p.json() if p.status_code == 200 else {}
    if p_json.get("ready") or p_json.get("status") == "ERROR":
        break
    time.sleep(1)

log_file.close()
