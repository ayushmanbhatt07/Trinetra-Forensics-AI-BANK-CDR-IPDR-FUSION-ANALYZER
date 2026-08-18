import re

def patch_api_py(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Replace _AutoBundleState class and _state initialization
    content = re.sub(
        r'class _AutoBundleState\(dict\):.*?(?=_state = _AutoBundleState\(\))',
        '',
        content,
        flags=re.DOTALL
    )
    content = content.replace('_state = _AutoBundleState()', '_state: dict = {}')

    # 2. _persist function
    content = re.sub(
        r'def _persist\(\) -> None:\n    b = _state\.get\("bundle"\)\n    if b:\n        # Run serialization asynchronously in background so HTTP response returns instantly\n        _persist_executor\.submit\(store\.save_bundle, b\)',
        r'''def _persist(username: str) -> None:
    b = _state.get(username, {}).get("bundle")
    if b:
        _persist_executor.submit(store.save_bundle, b, username)''',
        content
    )
    
    # 3. lifespan - Since clear_on_startup is hard without a user, we just skip store.clear_bundle() or rely on something else.
    # We will just remove store.clear_bundle() from lifespan for now, as it's dev-only and users can delete backend.db.
    # And we remove the restore logic since it must be lazy loaded per user.
    lifespan_new = '''@asynccontextmanager
async def lifespan(app: FastAPI):
    _log.info("[AUTH] Storage database path resolved to: %s", store._db_path().resolve())
    try:
        if config.clear_on_startup():
            with _lock:
                _state.clear()
            copilot_router.reset_engine()
            import glob, shutil
            for tmp_folder in glob.glob(os.path.join(tempfile.gettempdir(), "backend_upload_*")):
                try:
                    shutil.rmtree(tmp_folder, ignore_errors=True)
                except Exception:
                    pass
    except Exception as e:
        _log.warning("Failed during startup lifecycle: %s", e)
    yield'''
    content = re.sub(r'@asynccontextmanager\nasync def lifespan\(app: FastAPI\):.*?yield', lifespan_new, content, flags=re.DOTALL)

    # 4. _require_bundle
    require_bundle_new = '''def _require_bundle(user: dict) -> dict:
    username = user["username"]
    user_state = _state.get(username, {})
    if "bundle" not in user_state:
        b = store.load_bundle(username)
        if b and (b.get("bank") or b.get("cdr") or b.get("ipdr")):
            user_state["bundle"] = b
            _state[username] = user_state
            copilot_router.learn_bundle(b, username)
            return b
        else:
            raise HTTPException(409, "no data loaded; POST /ingest first")
    return user_state["bundle"]'''
    content = re.sub(r'def _require_bundle\(\) -> dict:.*?return _state\["bundle"\]', require_bundle_new, content, flags=re.DOTALL)

    # 5. _require_bundle() calls
    content = re.sub(r'_require_bundle\(\)', r'_require_bundle(user)', content)

    # 6. /ingest/status
    ingest_status_old = r'b = _state\.get\("bundle"\)\n    return {\n        "loaded": bool\(b\),\n        "last_ingested": store\.last_ingested\(\),'
    ingest_status_new = r'''b = _state.get(user["username"], {}).get("bundle")
    return {
        "loaded": bool(b),
        "last_ingested": store.last_ingested(user["username"]),'''
    content = re.sub(ingest_status_old, ingest_status_new, content)

    # 7. health
    health_old = r'b = _state\.get\("bundle"\)\n    return {\n        "status": "ok",\n        "loaded": bool\(b\),\n        "last_ingested": store\.last_ingested\(\),'
    health_new = r'''b = None
    return {
        "status": "ok",
        "loaded": False,
        "last_ingested": None,'''
    content = re.sub(health_old, health_new, content)

    # 8. pipeline status
    content = content.replace('orchestrator.get_status()', 'orchestrator.get_status(user["username"])')
    
    # 9. ingest_clear
    ingest_clear_old = r'''    with _lock:
        if "bundle" in _state:
            _state.pop\("bundle", None\)
        dict\.clear\(_state\)
    store\.clear_bundle\(\)
    orchestrator\.reset\(\)'''
    ingest_clear_new = r'''    username = user["username"]
    with _lock:
        if username in _state:
            _state.pop(username, None)
    store.clear_bundle(username)
    orchestrator.reset(username)'''
    content = re.sub(ingest_clear_old, ingest_clear_new, content)

    # 10. ingest
    ingest_old = r'''    with _lock:
        _state\["bundle"\] = ingest_folder\(folder_str\)
        _persist\(\)
    copilot_router\.reset_engine\(\)
    risk\.clear_cache\(\)
    risk\.clear_hybrid_cache\(\)
    clear_fusion_cache\(\)
    clear_report_cache\(\)
    clear_graph_cache\(\)
    
    orchestrator\.start_pipeline\(_state\["bundle"\]\)
    b = _state\["bundle"\]

    copilot_router\.learn_bundle\(b\)'''
    
    ingest_new = r'''    username = user["username"]
    with _lock:
        if username not in _state:
            _state[username] = {}
        _state[username]["bundle"] = ingest_folder(folder_str)
        _persist(username)
    
    orchestrator.start_pipeline(_state[username]["bundle"], username)
    b = _state[username]["bundle"]

    copilot_router.learn_bundle(b, username)'''
    content = re.sub(ingest_old, ingest_new, content)

    # 11. /upload/parse-multi
    upload_old = r'''    def _do_ingest\(\):
        with _lock:
            _state\["bundle"\] = ingest_folder\(tmp\)
            _persist\(\)
            
    from fastapi\.concurrency import run_in_threadpool
    await run_in_threadpool\(_do_ingest\)
    copilot_router\.reset_engine\(\)
    risk\.clear_cache\(\)
    risk\.clear_hybrid_cache\(\)
    clear_fusion_cache\(\)
    clear_report_cache\(\)
    clear_graph_cache\(\)
    
    orchestrator\.start_pipeline\(_state\["bundle"\]\)
    b = _state\["bundle"\]
    copilot_router\.learn_bundle\(b\)'''

    upload_new = r'''    username = user["username"]
    def _do_ingest():
        with _lock:
            if username not in _state:
                _state[username] = {}
            _state[username]["bundle"] = ingest_folder(tmp)
            _persist(username)
            
    from fastapi.concurrency import run_in_threadpool
    await run_in_threadpool(_do_ingest)
    
    orchestrator.start_pipeline(_state[username]["bundle"], username)
    b = _state[username]["bundle"]
    copilot_router.learn_bundle(b, username)'''
    content = re.sub(upload_old, upload_new, content)

    # 12. loading_status
    loading_old = r'''@app\.get\("/loading/status"\)
def loading_status\(user: dict = Depends\(auth\.require_user\)\):
    b = _state\.get\("bundle"\)
    if not b:
        return {"loaded": False, "detail": "no bundle ingested yet"}
    return {
        "loaded": True,
        "bank": len\(b\.get\("bank", \[\]\)\),
        "cdr": len\(b\.get\("cdr", \[\]\)\),
        "ipdr": len\(b\.get\("ipdr", \[\]\)\),
        "complaints": len\(b\.get\("complaints", \[\]\)\),
        "entities": len\(b\.get\("entities", \[\]\)\),
        "last_ingested": store\.last_ingested\(\),
        "cache_warm": bool\(_state\.get\("hybrid_warm", False\)\),
    }'''

    loading_new = r'''@app.get("/loading/status")
def loading_status(user: dict = Depends(auth.require_user)):
    username = user["username"]
    user_state = _state.get(username, {})
    b = user_state.get("bundle")
    if not b:
        return {"loaded": False, "detail": "no bundle ingested yet"}
    return {
        "loaded": True,
        "bank": len(b.get("bank", [])),
        "cdr": len(b.get("cdr", [])),
        "ipdr": len(b.get("ipdr", [])),
        "complaints": len(b.get("complaints", [])),
        "entities": len(b.get("entities", [])),
        "last_ingested": store.last_ingested(username),
        "cache_warm": bool(user_state.get("hybrid_warm", False)),
    }'''
    content = re.sub(loading_old, loading_new, content)

    # 13. store investigations
    content = content.replace('store.list_investigations()', 'store.list_investigations(user["username"])')
    content = content.replace('store.create_investigation(body.title, body.notes)', 'store.create_investigation(body.title, user["username"], body.notes)')
    content = content.replace('store.get_investigation(investigation_id)', 'store.get_investigation(investigation_id, user["username"])')
    content = content.replace('store.update_investigation(investigation_id, title=body.title,\n                                     notes=body.notes, status=body.status)', 'store.update_investigation(investigation_id, user["username"], title=body.title,\n                                     notes=body.notes, status=body.status)')
    content = content.replace('store.delete_investigation(investigation_id)', 'store.delete_investigation(investigation_id, user["username"])')
    content = content.replace('store.add_finding(investigation_id, body.kind, body.title,\n                                detail=body.detail, severity=body.severity)', 'store.add_finding(investigation_id, user["username"], body.kind, body.title,\n                                detail=body.detail, severity=body.severity)')
    content = content.replace('store.list_findings(investigation_id)', 'store.list_findings(investigation_id, user["username"])')
    
    # 14. Fix remaining last_ingested()
    content = content.replace('store.last_ingested()', 'store.last_ingested(user["username"])')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Patched api.py")

patch_api_py(r"d:\OMNIWATCHER LATENCY\AI-BANK-TRANSACTIONS-TELECOM-ANALYZER\backend\api.py")
