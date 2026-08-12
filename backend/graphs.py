"""Graph analytics on the fused records (networkx).

- phone_call_graph:  CDR contact network (weighted, directed)
- money_graph:       account -> counterparty money flows
- account_phone_link: account -> phone edges (from narrations + IPDR)
- ego-network helpers for investigation dashboards
"""

from __future__ import annotations

import networkx as nx

from .fusion import phone_analysis, _fingerprint

_graph_cache = {}

def clear_graph_cache():
    _graph_cache.clear()

def cached_money_graph(bundle: dict) -> nx.DiGraph:
    key = ("money", _fingerprint(bundle))
    if key not in _graph_cache:
        _graph_cache[key] = money_graph(bundle.get("bank", []))
    return _graph_cache[key]

def cached_phone_call_graph(bundle: dict) -> nx.DiGraph:
    key = ("phone_call", _fingerprint(bundle))
    if key not in _graph_cache:
        _graph_cache[key] = phone_call_graph(bundle.get("cdr", []))
    return _graph_cache[key]

def cached_account_phone_graph(bundle: dict) -> nx.Graph:
    key = ("account_phone", _fingerprint(bundle))
    if key not in _graph_cache:
        _graph_cache[key] = account_phone_graph(bundle.get("bank", []), bundle.get("ipdr", []))
    return _graph_cache[key]


def phone_call_graph(cdr: list[dict]) -> nx.DiGraph:
    """A->B call graph; edge weight = call count, also total seconds."""
    g = nx.DiGraph()
    for r in cdr:
        a = r.get("a_number") or ""
        b = r.get("b_number") or ""
        if not a or not b:
            continue
        if a not in g:
            g.add_node(a, kind="phone")
        if b not in g:
            g.add_node(b, kind="phone")
        if g.has_edge(a, b):
            e = g[a][b]
            e["weight"] += 1
            e["seconds"] += r.get("duration_sec") or 0
        else:
            g.add_edge(a, b, weight=1, seconds=r.get("duration_sec") or 0)
    return g


def money_graph(bank: list[dict]) -> nx.DiGraph:
    """account -> counterparty graph. Nodes are accounts, UPI ids, names or
    phones; edge weight = count, edge amount = sum."""
    g = nx.DiGraph()
    for r in bank:
        acc = r.get("account_no") or ""
        if not acc:
            continue
        debit = r.get("debit") or 0.0
        credit = r.get("credit") or 0.0
        target = (r.get("receiver_account") or r.get("upi_id")
                  or r.get("counterparty_name") or r.get("receiver_phone") or "")
        if not target:
            continue
        src, dst = (acc, target) if debit > 0 else (target, acc)
        if src not in g:
            g.add_node(src, kind="account" if src == acc else "counterparty")
        if dst not in g:
            g.add_node(dst, kind="account" if dst == acc else "counterparty")
        amt = debit if debit > 0 else credit
        if g.has_edge(src, dst):
            e = g[src][dst]
            e["weight"] += 1
            e["amount"] += amt
        else:
            g.add_edge(src, dst, weight=1, amount=amt)
    return g


def account_phone_graph(bank: list[dict], ipdr: list[dict]) -> nx.Graph:
    """Undirected account<->phone links (phone from narration or IPDR)."""
    g = nx.Graph()
    for r in bank:
        acc = r.get("account_no") or ""
        if acc and acc not in g:
            g.add_node(acc, kind="account")
        for ph in (r.get("receiver_phone"), r.get("sender_phone")):
            if acc and ph:
                g.add_edge(acc, ph, kind="narration")
    for r in ipdr:
        msisdn = r.get("msisdn") or ""
        if msisdn and msisdn not in g:
            g.add_node(msisdn, kind="phone")
    return g


def ego_network(g: nx.Graph, node: str, depth: int = 1,
                min_weight: int = 0) -> dict:
    """Ego network of `node` as a serialisable dict (for the API / UI)."""
    try:
        nodes = set(nx.ego_graph(g, node, radius=depth))
    except (nx.NetworkXError, nx.NodeNotFound):
        return {"node": node, "nodes": [], "edges": []}
    out_nodes = []
    for n in sorted(nodes):
        attr = dict(g.nodes[n]) if n in g.nodes else {}
        if attr.get("kind") == "phone" and min_weight:
            pass
        out_nodes.append({"id": n, "kind": attr.get("kind", "")})
    out_edges = []
    for u, v, d in g.edges(nodes, data=True):
        w = d.get("weight", 1)
        if min_weight and w < min_weight:
            continue
        out_edges.append({
            "source": u, "target": v, "weight": w,
            "amount": d.get("amount", 0), "seconds": d.get("seconds", 0),
        })
    return {"node": node, "nodes": out_nodes, "edges": out_edges}


def central_phones(g: nx.DiGraph, top: int = 15) -> list[dict]:
    """Top phones by degree and by call volume (money-mule hunting)."""
    deg = dict(g.degree())
    out = []
    for n in g.nodes:
        out.append({
            "phone": n, "degree": deg.get(n, 0),
            "in": g.in_degree(n), "out": g.out_degree(n),
            "calls": sum(d.get("weight", 0) for _, _, d in g.edges(n, data=True)),
        })
    out.sort(key=lambda x: (-x["degree"], -x["calls"]))
    return out[:top]


def summary_graphs(bundle: dict) -> dict:
    """Pre-built graphs + lightweight stats for reports and the API."""
    cdr = bundle.get("cdr", [])
    bank = bundle.get("bank", [])
    ipdr = bundle.get("ipdr", [])
    pg = phone_call_graph(cdr)
    mg = money_graph(bank)
    apg = account_phone_graph(bank, ipdr)
    phones = phone_analysis(cdr)
    return {
        "phone_call_graph": {
            "nodes": pg.number_of_nodes(),
            "edges": pg.number_of_edges(),
            "isolates": nx.number_of_isolates(pg),
        },
        "money_graph": {
            "nodes": mg.number_of_nodes(),
            "edges": mg.number_of_edges(),
        },
        "account_phone_graph": {
            "nodes": apg.number_of_nodes(),
            "edges": apg.number_of_edges(),
        },
        "central_phones": central_phones(pg),
        "top_accounts": sorted(
            ({**d, "account_no": a}
             for a, d in _account_totals(bank).items()),
            key=lambda x: -x["debit"])[:15],
        "phone_profiles": dict(sorted(
            ((p, {"contacts": v["contacts"], "unique_contacts": v["unique_contacts"],
                  "sms": v["sms"], "voice": v["voice"]})
             for p, v in phones.items()),
            key=lambda kv: -kv[1]["contacts"])[:20]),
    }


def _account_totals(bank: list[dict]) -> dict:
    out = {}
    for r in bank:
        acc = r.get("account_no") or ""
        if not acc:
            continue
        d = out.setdefault(acc, {"account_no": acc, "debit": 0.0, "credit": 0.0,
                                 "txns": 0, "bank": r.get("bank") or ""})
        d["debit"] += r.get("debit") or 0.0
        d["credit"] += r.get("credit") or 0.0
        d["txns"] += 1
    return out
