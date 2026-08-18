import re
import sys

def patch_copilot(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Replace globals
    globals_old = r'''_engine: Optional\[InvestigativeCoPilotEngine\] = None
_engine_bundle: Optional\[Dict\[str, Any\]\] = None'''
    globals_new = r'''_engines: Dict[str, InvestigativeCoPilotEngine] = {}
_engine_bundles: Dict[str, Dict[str, Any]] = {}'''
    content = re.sub(globals_old, globals_new, content)
    
    # Replace _current_bundle
    cb_old = r'''def _current_bundle\(\) -> Optional\[Dict\[str, Any\]\]:
    import sys
    for mod_name in \("api", "backend.api"\):
        if mod_name in sys.modules:
            mod = sys.modules\[mod_name\]
            if hasattr\(mod, "_state"\):
                b = getattr\(mod, "_state", \{\}\).get\("bundle"\)
                if b and \(b.get\("bank"\) or b.get\("cdr"\) or b.get\("ipdr"\)\):
                    return b
    try:
        from backend import store
        return store.load_bundle\(\)
    except Exception:
        return None'''
    cb_new = r'''def _current_bundle(username: str) -> Optional[Dict[str, Any]]:
    import sys
    for mod_name in ("api", "backend.api"):
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            if hasattr(mod, "_state"):
                user_state = getattr(mod, "_state", {}).get(username, {})
                b = user_state.get("bundle")
                if b and (b.get("bank") or b.get("cdr") or b.get("ipdr")):
                    return b
    try:
        from backend import store
        return store.load_bundle(username)
    except Exception:
        return None'''
    content = re.sub(cb_old, cb_new, content)

    # Replace reset_engine
    reset_old = r'''def reset_engine\(\) -> None:
.*?global _engine, _engine_bundle
    _engine = None
    _engine_bundle = None
    reset_copilot_db\(\)'''
    reset_new = r'''def reset_engine(username: str = None) -> None:
    global _engines, _engine_bundles
    if username:
        _engines.pop(username, None)
        _engine_bundles.pop(username, None)
    else:
        _engines.clear()
        _engine_bundles.clear()
    reset_copilot_db()'''
    content = re.sub(reset_old, reset_new, content, flags=re.DOTALL)

    # Replace learn_bundle
    learn_old = r'''def learn_bundle\(bundle: Dict\[str, Any\]\) -> None:'''
    learn_new = r'''def learn_bundle(bundle: Dict[str, Any], username: str = None) -> None:'''
    content = re.sub(learn_old, learn_new, content)
    
    # Replace get_engine
    ge_old = r'''def get_engine\(\) -> InvestigativeCoPilotEngine:
    global _engine, _engine_bundle
    bundle = _current_bundle\(\)
    if bundle is None:
        raise HTTPException\(
            status_code=status.HTTP_409_CONFLICT,
            detail="no data loaded; POST /ingest first"
        \)
    if _engine is None or _engine_bundle is not bundle:
        _engine = InvestigativeCoPilotEngine\(conn=get_copilot_db\(bundle\),
                                             bundle=bundle\)
        _engine_bundle = bundle
    return _engine'''
    ge_new = r'''def get_engine(username: str) -> InvestigativeCoPilotEngine:
    global _engines, _engine_bundles
    bundle = _current_bundle(username)
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no data loaded; POST /ingest first"
        )
    if username not in _engines or _engine_bundles.get(username) is not bundle:
        _engines[username] = InvestigativeCoPilotEngine(conn=get_copilot_db(bundle),
                                             bundle=bundle)
        _engine_bundles[username] = bundle
    return _engines[username]'''
    content = re.sub(ge_old, ge_new, content)
    
    # Replace get_engine() calls
    content = content.replace('engine = get_engine()', 'engine = get_engine(user["username"])')
    
    # Replace copilot_health
    health_old = r'''        bundle = _api._state.get\("bundle"\)
        ms = MemoryStore\(bundle\)'''
    health_new = r'''        user_state = _api._state.get(user["username"], {})
        bundle = user_state.get("bundle")
        ms = MemoryStore(bundle)'''
    content = re.sub(health_old, health_new, content)

    # Replace _current_bundle() inside get_entity_full_details
    content = content.replace('bundle = _current_bundle()', 'bundle = _current_bundle(user["username"])')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Patched copilot router.py")

patch_copilot(r"d:\OMNIWATCHER LATENCY\AI-BANK-TRANSACTIONS-TELECOM-ANALYZER\investigative_copilot\router.py")
