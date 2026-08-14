import requests
import time
import threading

URL = "http://127.0.0.1:8000"

def login():
    res = requests.post(f"{URL}/auth/login", json={"username": "admin", "password": "password"})
    return res.cookies

def ingest(cookies):
    res = requests.post(f"{URL}/ingest/folder", json={"folder": "data"}, cookies=cookies)
    return res.json()

def test_endpoints(cookies):
    # Loop and monitor latency of /health, /ingest/pipeline-status, /scoring/alerts
    while True:
        t0 = time.time()
        try:
            h = requests.get(f"{URL}/health", timeout=2)
            h_time = time.time() - t0
            h_status = h.status_code
        except Exception as e:
            h_time = -1
            h_status = str(e)
            
        t0 = time.time()
        try:
            p = requests.get(f"{URL}/ingest/pipeline-status", timeout=2)
            p_time = time.time() - t0
            p_status = p.status_code
            p_json = p.json() if p_status == 200 else {}
        except Exception as e:
            p_time = -1
            p_status = str(e)
            p_json = {}
            
        t0 = time.time()
        try:
            s = requests.get(f"{URL}/api/scoring/alerts", timeout=2)
            s_time = time.time() - t0
            s_status = s.status_code
        except Exception as e:
            s_time = -1
            s_status = str(e)

        print(f"Health: {h_status} ({h_time:.3f}s) | Pipeline: {p_status} ({p_time:.3f}s) [{p_json.get('status', '???')}] | Alerts: {s_status} ({s_time:.3f}s)")
        
        if p_json.get("ready"):
            print("Pipeline is READY.")
            break
        elif p_json.get("status") == "ERROR":
            print(f"Pipeline ERROR: {p_json.get('error')}")
            break
            
        time.sleep(0.5)

if __name__ == "__main__":
    c = login()
    print("Logged in")
    print("Triggering ingest...")
    ingest(c)
    print("Ingest triggered, testing responsiveness:")
    test_endpoints(c)
