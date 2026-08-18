import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import sqlite3
import shutil
import os

from backend.api import app, _state, lifespan
from backend import store, auth, config

@pytest.fixture(autouse=True)
def clean_environment():
    # Setup test env
    old_data_dir = os.environ.get("APP_DATA_DIR")
    temp_dir = Path(tempfile.mkdtemp())
    os.environ["APP_DATA_DIR"] = str(temp_dir)
    
    # Reset globals
    _state.clear()
    store._lock.acquire()
    try:
        # clear db cache to ensure clean connection
        if hasattr(store, '_connect_cache'):
            store._connect_cache = None
    finally:
        store._lock.release()
        
    yield
    
    # Cleanup
    if old_data_dir:
        os.environ["APP_DATA_DIR"] = old_data_dir
    else:
        del os.environ["APP_DATA_DIR"]
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def client():
    # Ensure startup events run, though we will just use TestClient which doesn't run lifespan automatically in some versions unless configured.
    with TestClient(app) as client:
        yield client

def test_multi_user_isolation(client):
    """
    Test that User A and User B have separate, isolated data stores.
    """
    # 1. Register User A
    client.post("/auth/register", json={"username": "userA", "password": "passwordA"})
    resA = client.post("/auth/login", json={"username": "userA", "password": "passwordA"})
    tokenA = resA.json()["access_token"]
    headersA = {"Authorization": f"Bearer {tokenA}"}

    # 2. Register User B
    client.post("/auth/register", json={"username": "userB", "password": "passwordB"})
    resB = client.post("/auth/login", json={"username": "userB", "password": "passwordB"})
    tokenB = resB.json()["access_token"]
    headersB = {"Authorization": f"Bearer {tokenB}"}

    # 3. User A creates an investigation
    res = client.post("/investigations", json={"title": "Investigation A", "notes": "Secret A"}, headers=headersA)
    assert res.status_code == 200
    invA_id = res.json()["investigation"]["id"]

    # 4. User B creates an investigation
    res = client.post("/investigations", json={"title": "Investigation B", "notes": "Secret B"}, headers=headersB)
    assert res.status_code == 200
    invB_id = res.json()["investigation"]["id"]

    # 5. User A tries to list investigations
    res = client.get("/investigations", headers=headersA)
    invs = res.json()["investigations"]
    assert len(invs) == 1
    assert invs[0]["title"] == "Investigation A"
    
    # 6. User B tries to list investigations
    res = client.get("/investigations", headers=headersB)
    invs = res.json()["investigations"]
    assert len(invs) == 1
    assert invs[0]["title"] == "Investigation B"
    
    # 7. User A attempts to read User B's investigation
    res = client.get(f"/investigations/{invB_id}", headers=headersA)
    assert res.status_code == 404
    
    # 8. User B attempts to delete User A's investigation
    res = client.delete(f"/investigations/{invA_id}", headers=headersB)
    # The delete shouldn't find it or just shouldn't affect it.
    
    # User A's investigation should still exist
    res = client.get(f"/investigations/{invA_id}", headers=headersA)
    assert res.status_code == 200

def test_bundle_isolation(client):
    """
    Test that uploading data as User A does not expose it to User B.
    """
    # Create test csv files
    base_dir = os.environ.get("APP_DATA_DIR")
    temp_dir_A = tempfile.mkdtemp(dir=base_dir)
    with open(os.path.join(temp_dir_A, "bank.csv"), "w") as f:
        f.write("account_no,date,narration,amount\nA1,2023-01-01,TestA,100\n")

    temp_dir_B = tempfile.mkdtemp(dir=base_dir)
    with open(os.path.join(temp_dir_B, "bank.csv"), "w") as f:
        f.write("account_no,date,narration,amount\nB1,2023-01-01,TestB,200\n")

    client.post("/auth/register", json={"username": "userA", "password": "passwordA"})
    tokenA = client.post("/auth/login", json={"username": "userA", "password": "passwordA"}).json()["access_token"]
    
    client.post("/auth/register", json={"username": "userB", "password": "passwordB"})
    tokenB = client.post("/auth/login", json={"username": "userB", "password": "passwordB"}).json()["access_token"]

    # User A ingests folder A
    res = client.post("/ingest", json={"folder": temp_dir_A}, headers={"Authorization": f"Bearer {tokenA}"})
    assert res.status_code == 200

    # User B ingests folder B
    res = client.post("/ingest", json={"folder": temp_dir_B}, headers={"Authorization": f"Bearer {tokenB}"})
    assert res.status_code == 200

    # Check status for User A
    resA = client.get("/ingest/status", headers={"Authorization": f"Bearer {tokenA}"})
    assert resA.json()["files_ok"] == 1

    # Check summary for User B - should only see their own accounts
    resB = client.get("/summary", headers={"Authorization": f"Bearer {tokenB}"})
    assert resB.status_code == 200
    assert len(resB.json()["files"]["ok"]) == 1
    
    # User A tries to call clear_bundle, shouldn't clear B's
    client.delete("/ingest", headers={"Authorization": f"Bearer {tokenA}"})
    
    resA2 = client.get("/ingest/status", headers={"Authorization": f"Bearer {tokenA}"})
    assert resA2.json()["loaded"] == False

    resB2 = client.get("/ingest/status", headers={"Authorization": f"Bearer {tokenB}"})
    assert resB2.json()["loaded"] == True
    assert resB2.json()["files_ok"] == 1
