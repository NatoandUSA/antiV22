"""Opportunity Inbox — rank the real YTrends keyword data by the composite score.

The team's daily start point: read the accumulated YTrends keyword data
(keyword_data.csv, the merged master that the extension + MCP feed into) and rank
EVERY keyword by the transparent Composite Opportunity Score (opportunity_score.py)
into GO / CONDITIONAL / WATCH / SKIP. Every input is a REAL market field
(competition, views, revenue, conversion, momentum) — nothing invented, honest-nulls
throughout, verdict + sub-scores + rationale shown so it's explainable, never a
black box.

This replaces the earlier sold/revenue-from-a-spy-file approach: Alex's real
exports carry sold/revenue/conversion at the KEYWORD level (YTrends), not per
listing — so we rank the keywords, and the Spy listings feed the Pattern Miner
(competitor intelligence) separately.
"""
import csv
from pathlib import Path

from src import opportunity_score as osc
from src import ranking_engine as re_eng

# The merged master the extension/MCP accumulate into. Fall back to the newest
# raw extension import if the master isn't present yet.
MASTER = Path("keyword_data.csv")
MASTER_ALT = Path("data/processed/keyword_data.csv")


def _num(v):
    try:
        if v in (None, ""):
            return None
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _load_master():
    """Rows from keyword_data.csv as dicts, or [] if absent/unreadable."""
    for p in (MASTER, MASTER_ALT):
        if p.is_file():
            try:
                with p.open(encoding="utf-8-sig") as fh:
                    return list(csv.DictReader(fh))
            except Exception:  # noqa: BLE001
                continue
    return []


def _to_scorer(row):
    """One keyword_data.csv row -> the field names opportunity_score.score reads.
    Only real fields; missing ones stay absent (honest-nulls)."""
    kw = (row.get("keyword") or row.get("tag") or "").strip()
    d = {"tag": kw}
    comp = _num(row.get("etsy_listings") or row.get("listing_count"))
    if comp is not None:
        d["listing_count"] = comp
    sc = _num(row.get("seller_count"))
    if sc is not None:
        d["seller_count"] = sc
    v = _num(row.get("views_24h") or row.get("views"))
    if v is not None:
        d["views_24h"] = v
    rev = _num(row.get("avg_revenue") or row.get("revenue"))
    if rev is not None:
        d["avg_revenue"] = rev
    price = _num(row.get("avg_price"))
    if price is not None:
        d["avg_price"] = price
    cr = _num(row.get("conversion_rate") or row.get("avg_conversion_rate"))
    if cr is not None:
        d["avg_conversion_rate"] = cr
    mom = _num(row.get("momentum") or row.get("momentum_score"))
    if mom is not None:
        # momentum = the VELOCITY input only. It must NOT also be copied into
        # gem_score: that double-counts one input (0.32*0.35 velocity + 0.15
        # opportunity = ~26% of the overall from a single field). Audited + fixed.
        d["momentum_score"] = mom
    # V30.1 (external review consensus): provenance is NOT a numeric opportunity
    # signal. A same-source feed made O a constant 85 for every row - pure score
    # inflation with zero ranking information. O now stays an honest null unless a
    # REAL discriminating signal exists (explicit gem/opportunity score column),
    # its weight renormalises away, and core = Market+Competition so its absence
    # no longer caps the verdict at WATCH. Provenance stays visible as `source`.
    d["source"] = str(row.get("source") or "").strip()
    lvl = (row.get("competition_level") or "").strip()
    if lvl:
        d["competition_level"] = lvl
    return d, comp, v, rev, cr, mom


def _short(n):
    if n is None:
        return None
    n = float(n)
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return f"{n:.0f}"


def _evidence(comp, views, rev, cr, mom):
    bits = []
    if comp is not None:
        bits.append(f"{int(comp)} listings")
    if rev is not None:
        bits.append(f"${_short(rev)} rev")
    if cr is not None:
        bits.append(f"{cr*100:.1f}% conv")
    if mom is not None:
        bits.append(f"mom {int(mom)}")
    if views is not None:
        bits.append(f"{int(views)} views/24h")
    return " · ".join(bits) or "—"


_TIER = {"GO": 0, "CONDITIONAL": 1, "WATCH": 2, "SKIP": 3}

# Small in-process cache: scoring ~1,100 keywords on every homepage load is wasteful.
# Key on (mode, master mtime, proof mtime) so it auto-invalidates when data changes.
_CACHE = {}


_PROOF_LATEST = Path("data/imports/etsy_proof/latest.json")


def _data_stamp():
    def mt(p):
        try:
            return Path(p).stat().st_mtime
        except OSError:
            return 0.0
    return (mt(MASTER), mt(MASTER_ALT), mt(_PROOF_LATEST))


def build_inbox(mode=None, limit=80):
    """Cached wrapper: recompute only when the underlying data files change."""
    stamp = (mode,) + _data_stamp()
    hit = _CACHE.get(stamp)
    if hit is not None:
        return {"counts": hit["counts"], "rows": hit["rows"][:limit],
                "has_proof": hit["has_proof"]}
    full = _build_inbox(mode, limit=100000)
    _CACHE.clear()                      # only ever keep the newest stamp
    _CACHE[stamp] = full
    return {"counts": full["counts"], "rows": full["rows"][:limit],
            "has_proof": full["has_proof"]}


def _build_inbox(mode=None, limit=80):
    """Rank the master keyword data through the LAYERED engine. Returns {counts, rows}.

    Per keyword: L0 risk/product-fit gate (product_fit + trademark) can BLOCK or CAP,
    L2 composite Market-Signal score, then an L4 Final Action. Rows carry both the
    market signal AND the final action, sorted by final action then market score, so
    a high market score on a broad / theme / risky term never reads as 'Build'."""
    raw = _load_master()
    try:
        from src import etsy_proof as ep
        proof_map = ep.build_proof(mode)
    except Exception:  # noqa: BLE001
        proof_map = {}
    best = {}
    for row in raw:
        d, comp, views, rev, cr, mom = _to_scorer(row)
        kw = d.get("tag")
        if not kw:
            continue
        try:
            s = osc.score(d, keyword=kw, mode=mode)
        except Exception:  # noqa: BLE001
            continue
        proof = None
        if proof_map:
            try:
                from src import etsy_proof as ep
                proof = ep.proof_for(kw, proof_map)
            except Exception:  # noqa: BLE001
                proof = None
        try:
            act = re_eng.decide(kw, s["verdict"], mode=mode, proof=proof)
        except Exception:  # noqa: BLE001
            act = {"action": "WATCH", "reason": "", "route": "analyze",
                   "fit_status": "", "fit_label": "", "launchable": False,
                   "priority": 2, "proof_tier": 9, "proof": None}
        rec = {
            "keyword": kw,
            "verdict": s["verdict"],          # L2 market-signal verdict
            "score": s["overall_score"],      # L2 market-signal score
            "sub_scores": s["sub_scores"],
            "rationale": s["rationale"],
            "ip_risk": s.get("ip_risk"),
            "action": act["action"],          # L4 final action
            "action_reason": act["reason"],
            "route": act["route"],
            "fit_status": act["fit_status"],
            "fit_label": act["fit_label"],
            "priority": act["priority"],
            "proof_tier": act.get("proof_tier", 9),   # L1: 0 proven, 1 selling
            "proof": act.get("proof"),
            "comp": comp, "views": views, "rev": rev, "conv": cr, "momentum": mom,
            "evidence": _evidence(comp, views, rev, cr, mom),
            "tier": _TIER.get(s["verdict"], 9),
        }
        # WATCH sub-rank (review consensus): momentum x conversion bubbles the most
        # promising of a big WATCH pool to the top ("Next 20 to investigate").
        rec["watch_rank"] = round((mom or 0.0) * (cr or 0.0) * 100, 1)
        k = kw.lower()
        cur = best.get(k)
        # keep the stronger row: proof tier, then final-action priority, then score
        rank = (-rec["proof_tier"], rec["priority"], rec["score"] or 0)
        if cur is None or rank > (-cur["proof_tier"], cur["priority"],
                                  cur["score"] or 0):
            best[k] = rec

    # sort: Etsy-proof group first, then final action, then (for WATCH rows) the
    # momentum x conversion sub-rank, then market score (spec order + review fix)
    rows = sorted(best.values(),
                  key=lambda r: (r["proof_tier"], -r["priority"],
                                 -(r["watch_rank"] if r["action"] == "WATCH" else 0),
                                 -(r["score"] or 0)))
    counts = {
        "total": len(rows),
        "proven": sum(1 for r in rows if r["proof_tier"] == 0),
        "selling": sum(1 for r in rows if r["proof_tier"] in (1, 2)),
        "build": sum(1 for r in rows if r["action"] == "BUILD_NOW"),
        "confirm": sum(1 for r in rows if r["action"] == "CONFIRM_FIRST"),
        "review": sum(1 for r in rows if r["action"] == "REVIEW"),
        "watch": sum(1 for r in rows if r["action"] == "WATCH"),
        "skip": sum(1 for r in rows if r["action"] == "SKIP"),
        "blocked": sum(1 for r in rows if r["action"] == "BLOCKED"),
    }
    return {"counts": counts, "rows": rows[:limit], "has_proof": bool(proof_map)}
