"""Internet (IPDR) Intelligence Engine.

Correlates IPDR sessions with transactions, calls and devices:

  * shared-IP analysis — many subscribers behind one public IP (VPN / NAT
    aggregation / fraud staging),
  * device (IMEI) & SIM (IMSI) change detection around transactions,
  * location change — cell change between sessions (location jumps),
  * per-transaction internet context score.

Each signal emits (score, reason) pairs so the ensemble + explainability
layer can cite the exact evidence.
"""

from __future__ import annotations

import bisect
from collections import Counter, defaultdict

_WINDOW = 1800


def _index(bundle: dict) -> dict:
    sess_by_phone: dict[str, list] = defaultdict(list)
    ip_by_phone: dict[str, Counter] = defaultdict(Counter)
    imsi_by_phone: dict[str, list] = defaultdict(list)
    imei_by_phone: dict[str, list] = defaultdict(list)
    cell_by_phone: dict[str, list] = defaultdict(list)
    ip_subscribers: dict[str, set] = defaultdict(set)
    for r in bundle.get("ipdr", []):
        ts = float(r.get("start_ts") or 0.0)
        phone = r.get("msisdn") or ""
        if not ts:
            continue
        if phone:
            sess_by_phone[phone].append(ts)
            if r.get("ip"):
                ip_by_phone[phone][r["ip"]] += 1
            if r.get("imsi"):
                imsi_by_phone[phone].append((ts, r["imsi"]))
            if r.get("imei"):
                imei_by_phone[phone].append((ts, r["imei"]))
            if r.get("cell_id") or r.get("bts_location"):
                cell_by_phone[phone].append(
                    (ts, r.get("cell_id") or r.get("bts_location")))
        if r.get("ip"):
            ip_subscribers[r["ip"]].add(phone or "?")

    for d in (sess_by_phone, imsi_by_phone, imei_by_phone, cell_by_phone):
        for k in d:
            d[k].sort()
    return {
        "sess_by_phone": sess_by_phone,
        "ip_by_phone": ip_by_phone,
        "imsi_by_phone": imsi_by_phone,
        "imei_by_phone": imei_by_phone,
        "cell_by_phone": cell_by_phone,
        "ip_subscribers": ip_subscribers,
    }


def shared_ip_risk(idx: dict) -> dict[str, dict]:
    """Per-IP concentration: subscribers behind one IP."""
    out = {}
    for ip, subs in idx["ip_subscribers"].items():
        subs = {s for s in subs if s and s != "?"}
        k = len(subs)
        if k < 2:
            continue
        score = min(100.0, 20.0 * k)
        out[ip] = {
            "ip": ip,
            "subscribers": sorted(subs),
            "subscriber_count": k,
            "shared_ip_score": round(score, 2),
            "reasons": [f"{k} subscribers share IP {ip}"]
                       + (["VPN / NAT concentration"] if k >= 5 else []),
        }
    return out


def txn_internet_scores(bundle: dict, window_sec: int = _WINDOW) -> dict[str, dict]:
    """Per-transaction internet-context score (0-100) + reasons."""
    idx = _index(bundle)
    shared_ips = shared_ip_risk(idx)
    out: dict[str, dict] = {}
    w = float(window_sec)
    for t in bundle.get("bank", []):
        tid = t.get("txn_id") or ""
        ts = float(t.get("ts") or 0.0)
        phone = t.get("sender_phone") or ""
        if not tid or not ts:
            continue
        reasons: list[str] = []
        score = 0.0

        def add(points: float, why: str) -> None:
            nonlocal score
            score = min(score + points, 100.0)
            reasons.append(why)

        if phone:
            sess = idx["sess_by_phone"].get(phone) or []
            n = bisect.bisect_right(sess, ts + w) - bisect.bisect_left(sess, ts - w)
            if n >= 3:
                add(20, f"{n} data sessions within ±{int(w // 60)} min")

            ips = idx["ip_by_phone"].get(phone) or Counter()
            for ip, cnt in ips.most_common(3):
                hit = shared_ips.get(ip)
                if hit and hit["subscriber_count"] >= 3:
                    add(25, f"phone shares IP {ip} with "
                            f"{hit['subscriber_count']} other subscribers")

            def _novel(hist: list, before, after) -> set:
                i0 = bisect.bisect_left(hist, (ts, before))
                prior = {v for _, v in hist[:i0]}
                i1 = bisect.bisect_left(hist, (ts + w, after))
                near = {v for _, v in hist[i0:i1]}
                return near - prior

            new_imsi = _novel(idx["imsi_by_phone"].get(phone) or [],
                              "", "\uffff")
            if new_imsi:
                add(30, f"SIM (IMSI) {sorted(new_imsi)[0]} first seen around txn")
            new_imei = _novel(idx["imei_by_phone"].get(phone) or [],
                              "", "\uffff")
            if new_imei:
                add(30, f"device (IMEI) {sorted(new_imei)[0]} first seen around txn")
            new_cell = _novel(idx["cell_by_phone"].get(phone) or [], "", "\uffff")
            if new_cell:
                add(15, f"location (cell {sorted(new_cell)[0]}) first seen around txn")
            if not sess and (new_imsi or new_imei or new_cell):
                add(10, "device/SIM/location change with no prior session history")

        out[tid] = {
            "internet_score": round(score, 2),
            "reasons": reasons,
            "window_sec": int(w),
        }
    return out


def internet_scores(bundle: dict, window_sec: int = _WINDOW) -> dict:
    txn = txn_internet_scores(bundle, window_sec)
    shared_ips = shared_ip_risk(_index(bundle))
    return {
        "txn": txn,
        "shared_ips": shared_ips,
        "stats": {"shared_ips": len(shared_ips),
                  "flagged_txns": sum(1 for v in txn.values()
                                      if v["internet_score"] >= 25)},
    }
