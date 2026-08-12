"""Graph analytics features for the risk engine.

Builds the account money-flow network (accounts + non-ledger counterparties)
and derives per-account features:

  * structural centrality — degree (in/out), PageRank, betweenness
    (sampled on large graphs), clustering coefficient,
  * community signal — greedy modularity community size,
  * Node2Vec embedding signals — L2 distance to the centroid, mean distance
    to the k nearest neighbours, and PCA reconstruction error over a
    DeepWalk-style Word2Vec embedding.

The graph scorer normalises these into a single 0-100 anomaly score: money
mules concentrate funds and radiate payouts, which inflates out-degree,
betweenness and embedding outlier-ness relative to normal accounts.
"""

from __future__ import annotations

import logging
from collections import Counter

import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)

EMBED_DIM = 32
WALKS_PER_NODE = 10
WALK_LENGTH = 20
# Large-graph switch points: exact algorithms below, sampled/linear
# approximations above (keeps big bundles fast).
_LARGE_GRAPH = 1000
_FULL_BETWEENNESS = 400
_CTP_PREFIX = "CTP:"


def money_flow_graph(bank: list[dict]) -> nx.DiGraph:
    """Account money-flow graph: accounts as nodes, counterparties (non-ledger
    receivers) as `CTP:` nodes, edges weighted by count + amount."""
    ledger_accounts = {r.get("account_no") for r in bank if r.get("account_no")}
    g = nx.DiGraph()
    edges: dict[tuple[str, str], list[float]] = {}
    for r in bank:
        src = r.get("account_no") or ""
        if not src:
            continue
        amt = float(r.get("debit") or 0.0)
        tgt_raw = r.get("receiver_account") or ""
        if not tgt_raw:
            tgt = _CTP_PREFIX + (r.get("counterparty_name") or "?")[:40]
        else:
            tgt = tgt_raw if tgt_raw in ledger_accounts else _CTP_PREFIX + tgt_raw
        g.add_node(src)
        g.add_node(tgt)
        key = (src, tgt)
        edges.setdefault(key, []).append(amt if amt > 0 else 0.0)
    for (u, v), amounts in edges.items():
        g.add_edge(u, v, count=len(amounts), amount=sum(amounts))
    return g


def _betweenness(g: nx.DiGraph) -> dict[str, float]:
    n = g.number_of_nodes()
    if n <= _FULL_BETWEENNESS:
        return nx.betweenness_centrality(g, normalized=True)
    # sampled approximation for large graphs (k random seeds, deterministic)
    k = min(150, max(40, n // 20))
    return nx.betweenness_centrality(g, k=k, seed=42, normalized=True)


def node2vec_embedding(g: nx.DiGraph) -> tuple[dict[str, np.ndarray], list[str]]:
    """DeepWalk-style random walks + Word2Vec embeddings.

    Returns (node -> vector, ordered node list).  Empty dict when the graph
    is too small for meaningful embeddings.  Walk volume shrinks on large
    graphs so the embedding stays fast for big bundles.
    """
    if g.number_of_nodes() < 8:
        return {}, []
    try:
        from gensim.models import Word2Vec
    except ImportError:  # pragma: no cover - gensim is an optional dep
        return {}, []

    big = g.number_of_nodes() >= _LARGE_GRAPH
    walks_per_node = 4 if big else WALKS_PER_NODE
    walk_len = 14 if big else WALK_LENGTH
    epochs = 3 if big else 5
    dim = 24 if big else EMBED_DIM

    nodes = list(g.nodes())
    successors = {n: list(g.successors(n)) for n in nodes}
    predecessors = {n: list(g.predecessors(n)) for n in nodes}

    rng = np.random.default_rng(42)
    walks: list[list[str]] = []
    for _ in range(walks_per_node):
        for n in nodes:
            walk = [n]
            for _step in range(walk_len - 1):
                cur = walk[-1]
                nbrs = successors[cur]
                if not nbrs and rng.random() < 0.5:
                    nbrs = predecessors[cur]
                if not nbrs:
                    break
                walk.append(nbrs[int(rng.integers(0, len(nbrs)))])
            walks.append(walk)
    model = Word2Vec(walks, vector_size=dim, window=5, min_count=1,
                     workers=1, epochs=epochs, seed=42, sg=1)
    return {n: model.wv[n] for n in nodes}, nodes


def _embedding_signals(embeddings: dict[str, np.ndarray]) -> dict[str, dict]:
    """Per-node embedding outlier-ness: centroid distance, kNN distance,
    PCA reconstruction error."""
    if not embeddings:
        return {}
    nodes = list(embeddings.keys())
    mat = np.vstack([embeddings[n] for n in nodes])
    centroid = mat.mean(axis=0)
    dist_centroid = np.linalg.norm(mat - centroid, axis=1)

    from sklearn.decomposition import PCA
    k = min(5, len(nodes) - 1)
    pca = PCA(n_components=min(mat.shape[1], len(nodes) - 1))
    recon = pca.fit_transform(mat)
    recon = pca.inverse_transform(recon)
    recon_err = np.linalg.norm(mat - recon, axis=1)

    try:
        from scipy.spatial import cKDTree
        tree = cKDTree(mat)
        _d, idx = tree.query(mat, k=k + 1)
        knn = np.zeros(len(nodes))
        for i in range(len(nodes)):
            d = idx[i][1:]
            knn[i] = float(np.linalg.norm(mat[i] - mat[d], axis=1).mean())
    except Exception:  # noqa: BLE001 — scipy absent / degenerate input
        knn = np.zeros(len(nodes))
        for i in range(len(nodes)):
            d = np.linalg.norm(mat - mat[i], axis=1)
            d[i] = np.inf
            j = np.argpartition(d, k)[:k]
            knn[i] = float(d[j].mean())
    return {n: {
        "embed_dist_centroid": float(dist_centroid[i]),
        "embed_knn_dist": float(knn[i]),
        "embed_pca_error": float(recon_err[i]),
    } for i, n in enumerate(nodes)}


def _communities(und: nx.Graph) -> tuple[list, dict[str, int]]:
    """Community assignment: label propagation on large graphs (linear),
    greedy modularity on small ones (higher quality)."""
    if und.number_of_nodes() >= _LARGE_GRAPH:
        try:
            comms = list(nx.community.asyn_lpa_communities(und, seed=42))
        except Exception:  # noqa: BLE001
            comms = []
    else:
        try:
            comms = list(nx.community.greedy_modularity_communities(und))
        except Exception:  # noqa: BLE001
            comms = []
    comm_of = {n: i for i, c in enumerate(comms) for n in c}
    comm_size = {n: len(comms[i]) for n, i in comm_of.items()}
    return comms, comm_size


def graph_features(bundle: dict, max_nodes: int = 6000) -> tuple[dict, dict]:
    """Per-account graph features + graph-level metadata.

    Returns ({account_no: {feat: value}}, {"nodes", "edges", "communities"}).
    Large graphs are pruned to the `max_nodes` most active accounts.
    """
    bank = bundle.get("bank", [])
    if len(bank) < 4:
        return {}, {"nodes": 0, "edges": 0, "communities": 0}

    g = money_flow_graph(bank)
    if g.number_of_nodes() > max_nodes:
        activity = Counter(r.get("account_no") for r in bank if r.get("account_no"))
        keep = set(a for a, _ in activity.most_common(max_nodes))
        remove = [n for n in g.nodes() if n not in keep]
        g.remove_nodes_from(remove)
    if g.number_of_nodes() < 4:
        return {}, {"nodes": 0, "edges": 0, "communities": 0}

    pagerank = nx.pagerank(g, alpha=0.85, max_iter=100)
    between = _betweenness(g)
    und = g.to_undirected()
    cluster = nx.clustering(und)
    communities, comm_size = _communities(und)

    embeddings, nodes = node2vec_embedding(g)
    embed = _embedding_signals(embeddings)

    out: dict[str, dict] = {}
    for n in g.nodes():
        if str(n).startswith(_CTP_PREFIX) or n not in g:
            continue
        deg = g.degree(n)
        in_amt = sum(d["amount"] for _, _, d in g.in_edges(n, data=True))
        out_amt = sum(d["amount"] for _, _, d in g.out_edges(n, data=True))
        out[n] = {
            "account_no": n,
            "degree": float(deg),
            "out_degree": float(g.out_degree(n)),
            "in_degree": float(g.in_degree(n)),
            "pagerank": float(pagerank.get(n, 0.0)),
            "betweenness": float(between.get(n, 0.0)),
            "clustering": float(cluster.get(n, 0.0)),
            "community_size": float(comm_size.get(n, 1.0)),
            "in_amount": float(in_amt),
            "out_amount": float(out_amt),
            **embed.get(n, {
                "embed_dist_centroid": 0.0, "embed_knn_dist": 0.0,
                "embed_pca_error": 0.0}),
        }
    return out, {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "communities": len(communities),
    }


def _min_max(values: np.ndarray) -> np.ndarray:
    lo, hi = values.min(), values.max()
    if hi <= lo:
        return np.zeros_like(values)
    return (values - lo) / (hi - lo)


GRAPH_FEATURE_COLS = ("degree", "out_degree", "in_degree", "pagerank",
                      "betweenness", "out_amount", "in_amount",
                      "community_size", "embed_dist_centroid",
                      "embed_knn_dist", "embed_pca_error")


def graph_score(features: dict) -> dict[str, float]:
    """Normalised 0-100 graph anomaly score per account."""
    if not features:
        return {}
    sample = next(iter(features.values()))
    cols = [c for c in GRAPH_FEATURE_COLS if c in sample]
    mat = np.array([[features[acc][c] for c in cols]
                    for acc in features], dtype=float)
    logmat = np.log1p(np.abs(mat))
    std = logmat.std(axis=0)
    std[std == 0] = 1.0
    z = (logmat - logmat.mean(axis=0)) / std
    z = np.clip(z, 0, 6)
    score = np.sqrt(z.mean(axis=1) / 6.0)
    scaled = _min_max(score) * 100.0
    return {acc: round(float(scaled[i]), 2)
            for i, acc in enumerate(features)}
