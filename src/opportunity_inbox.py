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
import re
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
    # The demand leg is calibrated for the NICHE TOTAL, but avg_revenue has been
    # strictly per-listing since V37.5, so hand the scorer the total explicitly:
    # the harvested column when we have it, else per-listing x listings (exactly
    # the inverse of harvest._add's conversion). Without this every row entered
    # the curve ~57 demand points low and nothing could reach GO.
    rev_total = _num(row.get("total_revenue"))
    if rev_total is None and rev is not None and comp:
        rev_total = rev * comp
    if rev_total is not None and rev_total > 0:
        d["niche_revenue"] = rev_total
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
    #
    # V37.6: that "REAL discriminating signal" now arrives. scout_opportunities
    # returns its own `opportunity_score` (independent of, and different from,
    # momentum_score and competition_score), which harvest used to discard into
    # the dedup field and now writes to the master. NOT sourced from
    # discovered_keywords.opportunity: that column is discover.score(), which is
    # log10(revenue) x conversion x momentum / listings - every input already a
    # leg here, so it would double-count all four and amplify them.
    opp = _num(row.get("opportunity_score"))
    if opp is not None:
        d["opportunity_score"] = opp
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
_CAPTURE_DIR = Path("data/imports/etsy_spy")
_PIN_DIR = Path("data/imports/pinterest")
_SUP_DIR = Path("data/imports/supplier")


def _data_stamp():
    def mt(p):
        try:
            return Path(p).stat().st_mtime
        except OSError:
            return 0.0

    def newest(d):
        try:  # newest file in a capture lane (proof / pinterest / supplier)
            return max((f.stat().st_mtime for f in Path(d).glob("*.json")),
                       default=0.0)
        except OSError:
            return 0.0
    # data/learning/winner.json feeds the private_boost score component -
    # without it in the stamp, logging a sale never re-ranked anything until an
    # unrelated file changed (audit fix).
    # V35.2: the durable proof LEDGER is .jsonl, which the *.json glob missed -
    # a ledger-only change (rotation/rebuild) never busted this cache, so the
    # inbox could serve proof rows that no longer exist. Stamp it explicitly.
    # V37.12: the supplier LIBRARY (not the capture lane) feeds the feasibility
    # badge. Without it in the stamp, importing a supplier CSV would leave every
    # badge stale until some unrelated file changed — and the gate's whole
    # promise is that a block/flag revives automatically.
    return (mt(MASTER), mt(MASTER_ALT), mt(_PROOF_LATEST),
            mt("data/learning/winner.json"),
            mt("data/history/keyword_snapshots.csv"),
            mt(_CAPTURE_DIR / "_proof_ledger.jsonl"),
            mt("data/suppliers/supplier_products.csv"),
            newest(_CAPTURE_DIR), newest(_PIN_DIR), newest(_SUP_DIR))


def _tokens(text):
    """Singularized token set for fuzzy keyword matching (shirt==shirts)."""
    try:
        from src.supplier_trend import _singular
    except Exception:  # noqa: BLE001
        def _singular(w):
            return w
    return {_singular(t) for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) > 1}


def focus_rows(rows, q):
    """Rows related to the typed keyword q, in engine-rank order (biggest token
    overlap first). q='patchwork usa tee' matches 'personalized patchwork usa
    shirt' etc. — the FOCUS view that makes the Inbox keyword-aware."""
    toks = _tokens(q)
    if not toks:
        return []
    need = min(len(toks), 2)            # 1-word q -> 1 shared; else >= 2 shared
    out = []
    for r in rows:
        shared = len(toks & _tokens(r["keyword"]))
        if shared >= need:
            out.append((shared, r))
    out.sort(key=lambda t: -t[0])       # stable: keeps engine order within ties
    return [r for _, r in out]


def build_inbox(mode=None, limit=80, q=None, show_archived=False):
    """Cached wrapper: recompute only when the underlying data files change.
    Pass q to also get `focus`: the rows related to that keyword (full-list
    search, not just the visible slice). show_archived=True includes the
    stale-WATCH archive in the rows."""
    ds = _data_stamp()
    stamp = (mode,) + ds
    full = _CACHE.get(stamp)
    if full is None:
        full = _build_inbox(mode, limit=100000)
        # Evict only entries built from OLDER data - never the sibling MODES
        # built from the same data. A clear-everything cache meant one home
        # page load (health card + opportunity queue ask for mode='pod', the
        # workflow spine asks for mode=None) evicted itself twice and rebuilt
        # all ~2,000 rows on every single request, forever: measured 0.365s
        # per home load, of which 0.35s was this. Bounded by the mode count.
        for k in [k for k in _CACHE if k[1:] != ds]:
            del _CACHE[k]
        _CACHE[stamp] = full
    rows = full["rows"]
    if show_archived:
        rows = rows + full.get("archived", [])
    res = {"counts": full["counts"], "rows": rows[:limit],
           "has_proof": full["has_proof"], "sources": full.get("sources", {}),
           "supplier": full.get("supplier") or {}}
    if q:
        # focus searches the FULL pool incl. archive - a typed keyword should
        # always find its niche even if the rows aged out of the main list
        res["focus"] = focus_rows(full["rows"] + full.get("archived", []), q)[:30]
        res["focus_q"] = q
    return res


def lead_keywords(mode=None, limit=12):
    """Lane-derived candidates still missing ALL market data - the
    Needs-Enrichment queue (one-click MCP enrich fills them)."""
    full = build_inbox(mode, limit=100000)
    return [r["keyword"] for r in full["rows"]
            if str(r.get("source", "")).endswith("-lead")
            and r["comp"] is None and r["rev"] is None][:limit]


def _trend_map():
    """kw -> (arrow, detail) from the last two snapshot dates per keyword.
    V33 (CEO reviews' top ROI): rising / stable / fading, from real history."""
    p = Path("data/history/keyword_snapshots.csv")
    if not p.is_file():
        return {}
    hist = {}
    try:
        with p.open(encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                kw = (r.get("keyword") or "").strip().lower()
                d = r.get("date") or ""
                try:
                    m = float(r.get("momentum") or "")
                except ValueError:
                    continue
                if kw and d:
                    hist.setdefault(kw, {})[d] = m
    except OSError:
        return {}
    out = {}
    for kw, by_date in hist.items():
        if len(by_date) < 2:
            continue
        d2, d1 = sorted(by_date)[-2:]
        prev, cur = by_date[d2], by_date[d1]
        if cur - prev > 5:
            out[kw] = ("\u2197", f"mom {prev:.0f}\u2192{cur:.0f}")   # rising
        elif prev - cur > 5:
            out[kw] = ("\u2198", f"mom {prev:.0f}\u2192{cur:.0f}")   # fading
        else:
            out[kw] = ("\u2192", f"mom stable {cur:.0f}")
    return out


def _build_inbox(mode=None, limit=80):
    """Rank the master keyword data through the LAYERED engine. Returns {counts, rows}.

    Per keyword: L0 risk/product-fit gate (product_fit + trademark) can BLOCK or CAP,
    L2 composite Market-Signal score, then an L4 Final Action. Rows carry both the
    market signal AND the final action, sorted by final action then market score, so
    a high market score on a broad / theme / risky term never reads as 'Build'."""
    raw = _load_master()
    trends = _trend_map()
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
        ev = _evidence(comp, views, rev, cr, mom)
        # seller concentration label (review item): same listing count, very
        # different game when 3 shops hold it all vs. many small shops
        sellers = _num(row.get("seller_count"))
        if comp and sellers and sellers > 0:
            ratio = comp / sellers
            if ratio >= 3:
                ev += f" · ⚠ {int(sellers)} sellers hold {int(comp)} listings"
            else:
                ev += f" · {int(sellers)} sellers"
        # your OWN sales history lifting this keyword (learning loop, visible)
        if (s["sub_scores"].get("private_boost") or 0) > 50:
            ev += " · \U0001F4C8 boosted by your sales"
        tr = trends.get(kw.lower())
        if tr:
            ev += f" · trend {tr[0]} ({tr[1]})"
        # niche age (from YTrends FRESHNESS): young niches are beatable markets
        nage = _num(row.get("niche_age_days"))
        if nage is not None:
            ev += (f" · \U0001F331 young niche ({int(nage)}d)" if nage <= 45
                   else f" · niche age {int(nage)}d")
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
            "launchable": act.get("launchable", False),
            "priority": act["priority"],
            "proof_tier": act.get("proof_tier", 9),   # L1: 0 proven, 1 selling
            "proof": act.get("proof"),
            "comp": comp, "views": views, "rev": rev, "conv": cr, "momentum": mom,
            # niche TOTAL revenue, kept beside the per-listing avg so a reader can
            # tell the two apart (harvest used to write the total into avg_revenue
            # for opportunity-sourced rows). Carried for display/selection only —
            # the scorer never reads it, so L2 is untouched.
            "rev_total": _num(row.get("total_revenue")),
            "evidence": ev,
            "collected_at": (row.get("collected_at") or "").strip(),
            "source": str(row.get("source") or "").strip(),
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

    # --- CAPTURE LANES FEED THE RANK TOO (owner: "data must be USED, not just
    # shown"): titles from the Pinterest + supplier lanes are reduced to
    # launchable keywords (supplier_trend.extract_keyword) and enter the SAME
    # layered engine as honest-null candidates — no market numbers invented, so
    # they rank as WATCH/CONFIRM until YTrends data or Etsy proof backs them,
    # and a lane keyword that matches your Etsy captures lights the proof tier.
    lane_counts = {"pinterest": 0, "supplier": 0}
    lane_new = 0
    try:
        from src import supplier_trend as st
        for _lane in ("pinterest", "supplier"):
            try:
                res = st.analyze_latest(mode, limit=40, source=_lane)
            except Exception:  # noqa: BLE001
                continue
            for lead in (res.get("leads") or []):
                kw = (lead.get("keyword") or "").strip().lower()
                if not kw:
                    continue
                lane_counts[_lane] += 1
                cur = best.get(kw)
                if cur is not None:     # already ranked from the master — tag it
                    if f"{_lane}-lead" not in (cur.get("also_from") or []):
                        cur.setdefault("also_from", []).append(f"{_lane}-lead")
                    continue
                try:
                    s = osc.score({"tag": kw, "source": f"{_lane}-lead"},
                                  keyword=kw, mode=mode)
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
                    continue
                nsup = lead.get("supplier_count") or lead.get("n")
                best[kw] = {
                    "keyword": kw, "verdict": s["verdict"],
                    "score": s["overall_score"], "sub_scores": s["sub_scores"],
                    "rationale": s["rationale"], "ip_risk": s.get("ip_risk"),
                    "action": act["action"], "action_reason": act["reason"],
                    "route": act["route"], "fit_status": act["fit_status"],
                    "fit_label": act["fit_label"], "priority": act["priority"],
                    "launchable": act.get("launchable", False),
                    "proof_tier": act.get("proof_tier", 9),
                    "proof": act.get("proof"),
                    "comp": None, "views": None, "rev": None, "conv": None,
                    "momentum": None,
                    "evidence": (f"{_lane} lead"
                                 + (f" · {int(nsup)} products" if nsup else "")
                                 + " · no market data yet"),
                    "tier": _TIER.get(s["verdict"], 9),
                    "watch_rank": 0.0, "source": f"{_lane}-lead",
                }
                lane_new += 1
    except Exception:  # noqa: BLE001 — lanes must never break the inbox
        pass

    # sort: Etsy-proof group first, then final action, then (for WATCH rows) the
    # momentum x conversion sub-rank, then market score (spec order + review fix)
    # V37.4 improvement: within the same proof tier + action, a LAUNCHABLE real
    # product ranks above a non-launchable theme/broad fragment (e.g. "next 12
    # month"). Without this, a junk phrase with a high conversion could outrank a
    # real product in the same CONFIRM_FIRST tier. Ordering only — scores/verdicts
    # /actions are unchanged (frozen L0-L4 untouched).
    rows = sorted(best.values(),
                  key=lambda r: (r["proof_tier"], -r["priority"],
                                 0 if r.get("launchable") else 1,
                                 -(r["watch_rank"] if r["action"] == "WATCH" else 0),
                                 -(r["score"] or 0)))
    # WATCH lifecycle (V32, review consensus): a WATCH row with no proof and no
    # data refresh for watch_expire_days is ARCHIVED out of the main list -
    # 900 stale rows must not bury the fresh signal. Undated rows (new lane
    # leads) stay active; the archive stays reachable (?show=all) and the
    # Focus search still covers it.
    archived = []
    try:
        from datetime import date as _d, timedelta as _td
        from src import engine_config as _ec
        _exp = int(_ec.get("watch_expire_days") or 0)
        if _exp > 0:
            cutoff = (_d.today() - _td(days=_exp)).isoformat()
            keep = []
            for r in rows:
                if (r["action"] == "WATCH" and r.get("proof_tier", 9) >= 9
                        and r.get("collected_at")
                        and r["collected_at"] < cutoff):
                    r["stale"] = True
                    archived.append(r)
                else:
                    keep.append(r)
            rows = keep
    except Exception:  # noqa: BLE001 - lifecycle must never break the inbox
        archived = []
    # V37.12 — supplier feasibility BADGE (workflow step 3, owner's item E).
    # It used to be asked only at the PUBLISH gate, after the title, 13 tags,
    # description, design brief and photo plan were written for a product the
    # shop cannot make. This is display only: the library is incomplete (7 of 8
    # registered suppliers have no products on file), so feasibility_gate can
    # never return NOT_MAKEABLE and therefore never changes an action or a score.
    # Enforcement switches itself on when the library reaches 'complete'.
    supplier_cov, supplier_counts = None, None
    try:
        from src import feasibility_gate as fg
        supplier_cov = fg.coverage()
        if supplier_cov["status"] != fg.COV_NONE:
            for r in rows:
                fg.apply_to_row(r, mode)
            supplier_counts = fg.summary(rows)
    except Exception:  # noqa: BLE001 - the badge must never break the inbox
        supplier_cov, supplier_counts = None, None
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
        "archived": len(archived),
        "needs_enrichment": sum(
            1 for r in rows if str(r.get("source", "")).endswith("-lead")
            and r["comp"] is None and r["rev"] is None),
    }
    # honest provenance: exactly which sources fed THIS ranking
    sources = {
        "master_rows": len(raw),
        "keyword_lab": sum(1 for r in raw
                           if (r.get("source") or "").strip() == "keyword-lab"),
        "proof_listings": len(proof_map),
        "pinterest_leads": lane_counts["pinterest"],
        "supplier_leads": lane_counts["supplier"],
        "lane_new": lane_new,
    }
    return {"counts": counts, "rows": rows[:limit], "has_proof": bool(proof_map),
            "sources": sources, "archived": archived,
            "supplier": {"coverage": supplier_cov, "fit": supplier_counts}}
