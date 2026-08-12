"""Money-Flow Intelligence Engine.

N-hop traversal over the account money-flow network to detect:

  * layering — funds move through several intermediate accounts before
    landing (chain depth on the debit path),
  * circular flow — money returns to the source within a few hops
    (A -> B -> C -> A),
  * cash-out / payout fan-out — one account radiating many payouts,
  * rapid forwarding — rapid re-transfer from a receiver account,
  * money-mule chains — long linear chains of thin accounts forwarding
    funds onward.

Traversal is set-based BFS limited to `MAX_HOPS`, computed once per source
set per hop (O(E) per hop overall), so large bundles stay fast.  Cycle
detection runs only on accounts with degree >= 3 (mule-shaped nodes).
"""

from __future__ import annotations

from collections import defaultdict

import networkx as nx

from .graph_features import money_flow_graph

MAX_HOPS = 3
_MIN_LAYER_EDGE = 10000.0
# Per-source BFS budget: chain depth needs only a handful of nodes, so a
# bounded budget keeps worst-case work linear-ish on huge bundles while
# preserving layering detection for real chains.
_MAX_SOURCE_EXPANSIONS = 200
_MAX_CYCLE_SCC = 60
_MAX_CYCLES = 50


def _account_nodes(g: nx.DiGraph) -> set:
    return {n for n in g.nodes if not str(n).startswith("CTP:")}


def _hop_reach(g: nx.DiGraph, sources: set, n_accounts: set,
               cutoff: int = MAX_HOPS) -> dict[str, int]:
    """max-hop reachable account depth for each source account (BFS, one
    sweep per hop over the graph, per-source expansion budget capped)."""
    adj = {n: set(g.successors(n)) for n in g.nodes}
    depth: dict[str, int] = {}
    frontier: dict[str, set] = {}
    for s in sources:
        nxt = adj[s] & n_accounts
        nxt.discard(s)
        if nxt:
            frontier[s] = nxt
            depth[s] = 1
    seen: dict[str, set] = {s: {s} for s in sources}
    budget = {s: _MAX_SOURCE_EXPANSIONS for s in sources}
    for hop in range(2, cutoff + 1):
        nxt_frontier: dict[str, set] = {}
        changed = False
        for s, cur in frontier.items():
            if not cur or budget[s] <= 0:
                continue
            nxt = set()
            for v in cur:
                if budget[s] <= 0:
                    break
                budget[s] -= 1
                for w in adj[v]:
                    if w in n_accounts and w != s and w not in seen[s]:
                        nxt.add(w)
            nxt -= seen[s]
            if nxt:
                nxt_frontier[s] = nxt
                seen[s] |= nxt
                depth[s] = max(depth.get(s, 0), hop)
                changed = True
        frontier = nxt_frontier
        if not changed:
            break
    return depth


def detect_cycles(g: nx.DiGraph, max_len: int = 6,
                  cap: int = _MAX_CYCLES) -> tuple[list[list[str]], set]:
    """Directed cycles via strongly-connected components. Cycles are
    enumerated only inside small SCCs; members of giant SCCs are simply
    marked circular (no expensive enumeration)."""
    acc = _account_nodes(g)
    cycles: list[list[str]] = []
    circular_nodes: set = set()
    for scc in nx.strongly_connected_components(g):
        members = scc & acc
        if len(members) < 2:
            continue
        if len(scc) <= _MAX_CYCLE_SCC:
            try:
                for c in nx.simple_cycles(g.subgraph(scc)):
                    cl = [n for n in c if n in acc]
                    if 2 <= len(cl) <= max_len:
                        cycles.append(cl)
                        circular_nodes |= set(cl)
                    if len(cycles) >= cap:
                        break
            except nx.NetworkXError:
                pass
        else:
            circular_nodes |= members
    return cycles, circular_nodes


def _flows(bundle: dict) -> dict:
    """Per-account debit fan-out (large debits to distinct receivers)."""
    fanout: dict[str, int] = defaultdict(int)
    total_debit: dict[str, float] = defaultdict(float)
    recv_set: dict[str, set] = defaultdict(set)
    for r in bundle.get("bank", []):
        acc = r.get("account_no") or ""
        if not acc:
            continue
        amt = float(r.get("debit") or 0.0)
        total_debit[acc] += amt
        recv = r.get("receiver_account") or ""
        if amt >= _MIN_LAYER_EDGE and recv:
            if recv not in recv_set[acc]:
                recv_set[acc].add(recv)
                fanout[acc] += 1
    return {"fanout": dict(fanout), "total_debit": dict(total_debit)}


def money_flow_analysis(bundle: dict, max_hops: int = MAX_HOPS) -> dict:
    """Per-account money-flow scenario signals.

    Returns {accounts: {account_no: {layering_depth, circular, cash_out,
                                     rapid_forward, mule_chain, flow_score,
                                     reasons}},
             cycles: [[account, ...], ...],
             stats: {...}}
    """
    g = money_flow_graph(bundle.get("bank", []))
    accounts = _account_nodes(g)
    flow = _flows(bundle)
    cycles, circular_nodes = detect_cycles(g)

    depths = _hop_reach(g, accounts, accounts, cutoff=max_hops)
    fanout = flow["fanout"]
    total_debit = flow["total_debit"]

    out: dict[str, dict] = {}
    for acc in accounts:
        reasons: list[str] = []
        score = 0.0
        depth = depths.get(acc, 0)
        circular = acc in circular_nodes
        cash_out = fanout.get(acc, 0)
        rapid_forward = False
        mule_chain = False

        if depth >= 3:
            score += 25
            reasons.append(f"funds layer through {depth} hops")
        elif depth == 2:
            score += 10
            reasons.append("funds reach accounts 2 hops away")

        if circular:
            score += 30
            reasons.append("account is part of a circular money-flow ring")

        if cash_out >= 8:
            score += 25
            reasons.append(f"radiates {cash_out} high-value payouts (cash-out pattern)")
        elif cash_out >= 4:
            score += 15
            reasons.append(f"radiates {cash_out} high-value payouts")

        in_deg = g.in_degree(acc)
        out_deg = g.out_degree(acc)
        deb = total_debit.get(acc, 0.0)
        if in_deg >= 3 and deb >= 100000:
            rapid_forward = True
            score += 15
            reasons.append("receives from many sources and forwards large totals")

        if out_deg >= 3 and in_deg >= 2 and depth >= 2:
            mule_chain = True
            score += 15
            reasons.append("mid-chain node on a multi-hop forwarding path")

        out[acc] = {
            "layering_depth": depth,
            "circular": circular,
            "cash_out_payouts": cash_out,
            "rapid_forward": rapid_forward,
            "mule_chain": mule_chain,
            "flow_score": round(min(score, 100.0), 2),
            "reasons": reasons,
        }

    return {
        "accounts": out,
        "cycles": cycles[:50],
        "stats": {"cycles": len(cycles),
                  "flagged_accounts": sum(
                      1 for a in out.values() if a["flow_score"] >= 25)},
    }
