"""Entity Intelligence Engine.

Unifies the ledger's identifiers — account, phone, IMEI, IMSI, IP, UPI,
beneficiary, customer — into a shared-entity graph and computes:

  * entity concentration — how many accounts/entities share each identifier
    (a single phone on 12 accounts is a mule pocket, not a coincidence),
  * entity risk — per-identifier 0-100 score from concentration + incident
    context (NCRP complaint hits, call-network activity, IP/device sharing),
  * account entity risk — how much shared-entity exposure each account has.

`_shared_map` builds one map per identifier kind; `entity_risk` returns the
per-kind aggregated structure consumed by the ensemble and the explainability
engine.
"""

from __future__ import annotations

from collections import Counter, defaultdict

KINDS = ("phone", "imei", "imsi", "ip", "upi", "beneficiary", "customer")


def _entity_values(t: dict) -> dict[str, list[str]]:
    """Identifier values attached to one bank transaction."""
    vals: dict[str, list[str]] = {}
    phone = []
    for ph in (t.get("sender_phone"), t.get("receiver_phone")):
        if ph:
            phone.append(str(ph))
    if phone:
        vals["phone"] = phone
    for key, kind in (("imei", "imei"), ("imsi", "imsi"), ("ip", "ip"),
                      ("upi_id", "upi")):
        v = t.get(key)
        if v:
            vals[kind] = [str(v)]
    if t.get("receiver_account"):
        vals["beneficiary"] = [str(t["receiver_account"])]
    cust = t.get("customer_id") or t.get("account_no") or ""
    if cust:
        vals["customer"] = [str(cust)]
    return vals


def _shared_map(bundle: dict) -> dict[str, dict[str, set]]:
    """kind -> identifier -> set of account_no (ledger) + customer ids."""
    out: dict[str, dict[str, set]] = {k: defaultdict(set) for k in KINDS}
    for t in bundle.get("bank", []):
        acc = t.get("account_no") or ""
        cust = t.get("customer_id") or acc
        for kind, values in _entity_values(t).items():
            for v in values:
                out[kind][v].add(acc or cust)
    return out


def _concentration_score(accounts: set, n_accounts_total: int) -> float:
    """0-100 risk from how many accounts share one identifier."""
    k = len(accounts)
    if k <= 1:
        return 0.0
    if k >= 12:
        return 100.0
    return round(min(100.0, 25.0 * k), 2)


def _ncrp_hits(bundle: dict) -> set:
    return {str(c.get("account_no") or "").strip()
            for c in bundle.get("complaints", [])}


def entity_risk(bundle: dict) -> dict:
    """Per-identifier risk + account exposure summary.

    Returns {
      "entities": {kind: [{entity, kind, accounts, account_count,
                           entity_risk, ncrp, reasons}]},
      "account_exposure": {account_no: {entity_risk, shared_entities,
                                        kinds, reasons}},
      "stats": {kind: {entity_count, flagged_count, max_share}},
    }
    """
    shared = _shared_map(bundle)
    ncrp = _ncrp_hits(bundle)
    entities: dict[str, list[dict]] = {k: [] for k in KINDS}
    stats: dict[str, dict] = {}

    for kind in KINDS:
        flagged = 0
        max_share = 0
        for value, accounts in shared[kind].items():
            accounts = {a for a in accounts if a}
            conc = _concentration_score(accounts, len(bundle.get("bank", [])))
            if conc <= 0:
                continue
            reasons = []
            if len(accounts) >= 3:
                reasons.append(f"shared by {len(accounts)} accounts")
            if len(accounts) >= 6:
                reasons.append("high fan-out — possible mule pocket")
            if kind == "phone":
                reasons.append("device-to-account fan-out")
            ncrp_hit = bool(accounts & ncrp)
            if ncrp_hit:
                reasons.append("account listed in NCRP complaint ledger")
                conc = min(100.0, conc + 25.0)
            score = round(min(100.0, conc), 2)
            if score >= 25:
                flagged += 1
            max_share = max(max_share, len(accounts))
            entities[kind].append({
                "entity": value, "kind": kind,
                "accounts": sorted(accounts)[:50],
                "account_count": len(accounts),
                "entity_risk": score,
                "ncrp": ncrp_hit,
                "reasons": reasons,
            })
        for ent in entities[kind]:
            ent["accounts"] = ent["accounts"][:50]
        stats[kind] = {
            "entity_count": len(entities[kind]),
            "flagged_count": flagged,
            "max_share": max_share,
        }

    # Account exposure: aggregate the risk of every identifier attached to
    # the account's transactions.
    account_exposure: dict[str, dict] = {}
    kind_by_account: dict[str, Counter] = defaultdict(Counter)
    for kind in KINDS:
        for ent in entities[kind]:
            for acc in ent["accounts"]:
                kind_by_account[acc][kind] += 1

    by_account: dict[str, list[dict]] = defaultdict(list)
    for kind in KINDS:
        for ent in entities[kind]:
            for acc in ent["accounts"]:
                by_account[acc].append(ent)
    for acc, ents in by_account.items():
        scores = [e["entity_risk"] for e in ents]
        account_exposure[acc] = {
            "entity_risk": round(min(100.0, 0.4 * max(scores)
                                     + 0.35 * (sum(scores) / len(scores))),
                                 2),
            "shared_entities": sum(
                1 for e in ents if e["account_count"] > 1),
            "entity_kinds": dict(kind_by_account[acc]),
            "reasons": list(dict.fromkeys(
                r for e in ents[:10] for r in e["reasons"]))[:6],
        }

    return {
        "entities": entities,
        "account_exposure": account_exposure,
        "stats": stats,
    }
