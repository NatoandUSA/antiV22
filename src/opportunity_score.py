"""Composite Opportunity Score (0-100) + GO / CONDITIONAL / WATCH / SKIP verdict.

Turns a raw YTuong keyword/gem/opportunity row into ONE transparent, explainable
score for the DISCOVERY pages (Opportunities, Hidden gems, Daily brief) -- "is this
row worth a closer look?", scored from the row's own market fields.

Not to be confused with workspace.can_we_win, which answers a different question
one level deeper: once you're building a niche, WHERE are its actual rivals weak
(measured per-niche from their real listings). Discovery screens wide; can_we_win
digs into one. Both are measured -- neither hands out flat optimism.

    Overall = Market(M) + Competition(C) + Opportunity(O) + Private(P) + Feasibility(F)

HONEST-NULLS RULE (this project never invents data):
- A component whose source data is missing is scored `None`, NOT a default 50.
- Overall is the weighted average over the components we DO have (weights
  re-normalised), so a missing signal can't silently fabricate confidence.
- If any CORE market signal (M, C, or O) is missing, the verdict is capped at
  WATCH - we can't hand out a confident GO without the core evidence.
- HIGH trademark risk is always SKIP.

Private data (P) is different: an empty private history is NORMAL for a new shop,
so a missing P is neutral (it just doesn't lift the score) and never caps the
verdict on its own.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

# ROOT-relative: a CWD-relative path silently fell back to the defaults whenever
# the process ran from anywhere but the repo root (presets ignored, no warning).
CONFIG = Path(__file__).resolve().parent.parent / "config" / "scoring_weights.json"

# Etsy competition-level strings -> a 0-100 "intensity" (higher = more saturated).
COMP_INTENSITY = {"low": 25, "medium": 55, "med": 55, "moderate": 55,
                  "high": 85, "very high": 95, "saturated": 95}

# Overall-score verdict bands.
GO, CONDITIONAL, WATCH, SKIP = "GO", "CONDITIONAL", "WATCH", "SKIP"


@dataclass
class ScoringWeights:
    market: float = 0.32
    competition: float = 0.28
    opportunity: float = 0.15
    private: float = 0.15
    feasibility: float = 0.10


def load_weights(category=None):
    """Weights from config/scoring_weights.json (falls back to the dataclass
    defaults). A category hint selects a preset when one exists."""
    default = ScoringWeights()
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - config optional; never break scoring
        return default
    base = dict(cfg.get("default", {}))
    if category:
        preset = (cfg.get("presets", {}) or {}).get(str(category).lower())
        if preset:
            base = dict(preset)
    keys = ("market", "competition", "opportunity", "private", "feasibility")
    return ScoringWeights(**{k: base.get(k, getattr(default, k)) for k in keys})


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _first(row, *keys):
    for k in keys:
        v = _num(row.get(k))
        if v is not None:
            return v
    return None


# --- component scorers: each returns a 0-100 float, or None if no source data --

def _trend_signals(gt):
    """Google Trends dict -> (demand_corroboration, velocity) each 0-100 or None.

    avg_interest is already Google's 0-100 relative-demand index. momentum_pct is
    recent-vs-earlier % change; centre it on 50 (0% = neutral 50, +50% -> 100,
    -50% -> 0) so a rising niche lifts velocity and a cooling one drags it. A
    missing field stays None so it can't fabricate a signal (honest-nulls)."""
    if not isinstance(gt, dict):
        return None, None
    ai = _num(gt.get("avg_interest"))
    mp = _num(gt.get("momentum_pct"))
    demand = min(100.0, max(0.0, ai)) if ai is not None else None
    vel = min(100.0, max(0.0, 50.0 + mp)) if mp is not None else None
    return demand, vel


def _demand_from(row):
    """0-100 demand from the real market fields, or None. Prefers an explicit
    0-100 demand_score; otherwise builds it from REVENUE (the strongest, most
    cross-source-comparable demand signal - $ actually changing hands) blended
    with a views term. Revenue is log-scaled ($100 -> ~0, ~$300k -> 100) because
    niche revenue spans four orders of magnitude; views are a lighter secondary
    signal on a daily-count scale. Uses only the fields present (honest-nulls):
    with neither revenue nor views, demand is None and can't fabricate a score.

    UNITS (V37.6): this curve is calibrated for the NICHE TOTAL, not per-listing
    revenue - "how much money moves in this market". Read `niche_revenue` first,
    which is the only field guaranteed to carry that. V37.5 made harvest write
    `avg_revenue` as strictly per-listing (correctly - it had been mixing the two
    and one source read ~250x richer than another), but nothing then converted it
    back, so every row entered this curve ~57 demand points low at the median and
    NO keyword in the base could reach the GO band. `avg_revenue`/`revenue` stay
    as fallbacks for callers that still pass a niche figure there.
    """
    d = _first(row, "demand", "demand_score")
    if d is not None:
        return min(100.0, max(0.0, d))
    rev = _first(row, "niche_revenue", "avg_revenue", "revenue")
    v = _first(row, "views_24h", "views")
    parts = []
    if rev is not None and rev > 0:
        # log10: $100->~0, $1k->29, $10k->57, $100k->86, ~$316k->100
        parts.append((min(100.0, max(0.0, (math.log10(rev) - 2.0) / 3.5 * 100.0)), 0.7))
    if v is not None and v > 0:
        parts.append((min(100.0, v / 3.0), 0.3))   # ~300 views/24h -> 100
    if not parts:
        return None
    return round(sum(x * w for x, w in parts) / sum(w for _, w in parts), 1)


def _market(row, gt=None):
    """Demand (40%) + Velocity (35%) + Conversion (25%), over what's present.

    When a Google Trends read for this keyword is supplied it's blended in as an
    EXTERNAL corroboration (its own demand + velocity parts). Demand now uses real
    revenue (see _demand_from) instead of a views-only proxy, so niches with real
    money moving rise above thin ones."""
    demand = _demand_from(row)
    velocity = _first(row, "momentum_score", "velocity")
    cr = _first(row, "avg_conversion_rate", "conversion_rate", "conversion")
    # V33 CEO fix (3-review consensus): min(100, cr*2000) SATURATED at 5% -
    # a 12% converter tied a 5.1% one exactly where personalization wins.
    # Fixed piecewise transform (deterministic, cross-import comparable):
    # 0-5% -> 0-80 linear; above: 80 + 20*(1-e^(-25*(cr-.05)))
    # so 5%->80, 8%->90.6, 12%->96.5, asymptote 100.
    if cr is None:
        conversion = None
    elif cr <= 0.05:
        conversion = cr * 1600.0
    else:
        conversion = 80.0 + 20.0 * (1.0 - math.exp(-25.0 * (cr - 0.05)))
    parts = [(demand, 0.40), (velocity, 0.35), (conversion, 0.25)]
    gt_demand, gt_vel = _trend_signals(gt)
    if gt_demand is not None:
        parts.append((gt_demand, 0.15))   # external search-demand corroboration
    if gt_vel is not None:
        parts.append((gt_vel, 0.15))       # external rising/cooling signal
    avail = [(x, w) for x, w in parts if x is not None]
    if not avail:
        return None
    tw = sum(w for _, w in avail)
    return round(sum(x * w for x, w in avail) / tw, 1)


def _competition(row):
    """100 - saturation intensity. None if we have no competition signal at all."""
    ci = _first(row, "competition_intensity")
    if ci is None:
        # Sources disagree on form: the REST API says 'low', MCP research_keyword
        # says 'very_high'. Without normalising, the underscore form misses the map
        # and drops through to the listings/sellers ratio below, which scores a
        # 45k-listing keyword as a healthy open market.
        lvl = str(row.get("competition_level") or "").strip().lower().replace("_", " ")
        ci = COMP_INTENSITY.get(lvl)
    if ci is None:
        # No label to trust: fall back to how many listings you'd rank against.
        # This used to be (listings/sellers)*8, but measured over 150 live YTrends
        # keywords that DO carry a label, listings-per-seller is nearly constant
        # across them (median 1.43 low / 1.85 medium / 1.99 high) and the ranges
        # invert - 'low' keywords reach 4.38 while 'high' sits near 2.0 - so it
        # scored a 45k-listing keyword as a favourable market (MAE 69-72 vs the
        # label on high/very_high). Listing count separates them log-linearly
        # (median 38 / 374 / 1088), which is what this reproduces: MAE 5.2.
        listings = _num(row.get("listing_count"))
        if listings is not None:
            ci = max(10.0, min(95.0, -40.0 + 41.0 * math.log10(max(listings, 1.0))))
    if ci is None:
        return None
    return round(max(0.0, 100.0 - ci), 1)


def _opportunity(row):
    """Hidden-gem / opportunity / explore-niche 'enter now' signal. None if absent."""
    v = _first(row, "opportunity_score", "gem_score")
    if v is not None:
        return round(min(100.0, v), 1)
    if row.get("is_hidden_gem"):
        return 85.0
    ev = str(row.get("explore_niche_verdict") or "").lower()
    if "enter" in ev:
        return 88.0
    if "conditional" in ev:
        return 72.0
    if "study" in ev or "weak" in ev:
        return 35.0
    return None


def _private(keyword):
    """Private boost from our own proven winners (learning.py), WEIGHTED by the
    orders they actually sold -- not mere presence, so a keyword that sold 20 beats
    one that sold 1. None when the shop has NO history yet (normal pre-launch) so
    it neither helps nor hurts."""
    if not keyword:
        return None
    try:
        from src import learning
        if not learning.has_history():
            return None                  # no history at all -> neutral/omit
        orders = learning.winner_orders(keyword)
    except Exception:  # noqa: BLE001
        return None
    if orders <= 0:
        # V33 CEO fix (3-review consensus): the old flat 50 once ANY history
        # existed silently penalised every never-tried keyword (~-7.5 pts vs
        # renormalising away). Untried stays honest-None; only real wins score.
        return None
    return round(min(95.0, 60.0 + 7.0 * orders), 1)   # 1 order 67 ... 5+ -> 95


def _ip_penalties():
    """IP penalties from config.advanced.ip_risk_penalties (the config advertised
    these but the code used to hardcode them)."""
    default = {"low": 0.0, "medium": -12.0, "high": -30.0}
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        p = (cfg.get("advanced", {}) or {}).get("ip_risk_penalties") or {}
        return {k: float(p.get(k, d)) for k, d in default.items()}
    except Exception:  # noqa: BLE001 - config optional; never break scoring
        return default


def _feasibility(keyword, mode):
    """Design producibility + IP risk -> (score, ip_risk). Deterministic, so it's
    almost always available. IP HIGH is surfaced for the verdict override.

    For embroidery/chenille the design half blends in the REAL stitch-producibility
    read (gradients / photo-real / fine detail / tiny text don't stitch), not just
    "is this an embroidery keyword". POD prints almost anything, so it's unchanged.
    """
    ip_risk = "low"
    try:
        from src.trademark import check as _tm
        risk, _ = _tm((keyword or "").lower())
        ip_risk = {"HIGH": "high", "CAUTION": "medium", "OK": "low"}.get(risk, "medium")
    except Exception:  # noqa: BLE001
        ip_risk = "medium"
    design = 60.0
    try:
        from src import product_fit as pf
        c = pf.classify(keyword or "", mode)
        if c.get("launchable"):
            design = 85.0 if c.get("product_type") not in ("theme", "") else 65.0
        else:
            design = 35.0
        prod = pf.producibility(keyword or "", mode or c.get("product_type") or "")
        if prod and prod.get("label") != "PRINTS_FINE":   # embroidery/chenille only
            design = round(design * 0.5 + prod["score"] * 0.5, 1)
    except Exception:  # noqa: BLE001
        pass
    ip_pen = _ip_penalties()[ip_risk]
    # 20 baseline + 80 movable points, originally split design .45 / seasonality
    # .35. There is no per-keyword seasonality source (seasonal.py is a holiday
    # CALENDAR, not a per-tag score), so that leg was a hardcoded "neutral" 60 -
    # a fabricated constant that cost every row in the system 14 points and
    # capped F at 79.25 (design tops out at 85), dragging every composite toward
    # 79. Same anti-pattern as the flat-50 private boost (V33) and the constant-85
    # opportunity signal (V30.1), both already removed. Honest-nulls: renormalise
    # the 80 movable points onto the signal we actually measure. This widens the
    # spread in BOTH directions - a launchable product rises (79.2 -> 88.0), an
    # unmakeable one falls (56.8 -> 48.0) - instead of everything hugging 79.
    feas = max(0.0, (design * 0.80) + 20.0 + ip_pen)
    return round(min(100.0, feas), 1), ip_risk


def _rationale(subs, missing, ip_risk, core_missing, gt=None):
    r = []
    m, c, o, p, f = (subs["market_potential"], subs["competition_health"],
                     subs["opportunity_signal"], subs["private_boost"],
                     subs["feasibility_risk"])
    if isinstance(m, (int, float)) and m > 75:
        r.append("Strong demand + momentum")
    if isinstance(c, (int, float)) and c > 70:
        r.append("Favourable low-competition landscape")
    if isinstance(o, (int, float)) and o > 80:
        r.append("Hidden-gem / enter-now signal")
    if isinstance(p, (int, float)) and p > 70:
        r.append("Matches a proven private winner")
    if isinstance(gt, dict) and isinstance(gt.get("momentum_pct"), (int, float)):
        mp = gt["momentum_pct"]
        if mp >= 20:
            r.append(f"Google Trends rising (+{round(mp)}%)")
        elif mp <= -20:
            r.append(f"Google Trends cooling ({round(mp)}%)")
    if ip_risk == "high":
        r.append("HIGH trademark risk - do not build")
    elif isinstance(f, (int, float)) and f < 55:
        r.append(f"Feasibility / IP concern ({ip_risk})")
    if core_missing:
        r.append("Core market data incomplete (" + ", ".join(
            k for k in ("market_potential", "competition_health")
            if subs[k] is None) + ") - capped at WATCH")
    return r or ["Balanced profile across available metrics"]


def score(row, keyword=None, mode=None, private=None, category=None,
          gtrends_dir=None):
    """Score one row. Returns overall_score (or None), verdict, sub_scores (None
    allowed), the list of missing components, ip_risk, and a rationale.

    gtrends_dir: optional Google Trends read for THIS keyword
    ({"avg_interest": float, "momentum_pct": float}) - blended into the Market
    component as external corroboration. None (the default) leaves the score
    exactly as it was before Trends existed (honest-nulls: a secondary signal
    never fabricates confidence when it's absent)."""
    w = load_weights(category)
    keyword = keyword or row.get("tag") or row.get("keyword") or ""
    F, ip_risk = _feasibility(keyword, mode)
    subs = {
        "market_potential": _market(row, gtrends_dir),
        "competition_health": _competition(row),
        "opportunity_signal": _opportunity(row),
        "private_boost": _private(keyword) if private is None else private,
        "feasibility_risk": F,
    }
    wt_map = {"market_potential": w.market, "competition_health": w.competition,
              "opportunity_signal": w.opportunity, "private_boost": w.private,
              "feasibility_risk": w.feasibility}
    missing = [k for k, v in subs.items() if v is None]
    avail = [(v, wt_map[k]) for k, v in subs.items() if v is not None]
    overall = (round(sum(v * wt for v, wt in avail) / sum(wt for _, wt in avail), 1)
               if avail else None)
    # How much of the scoring weight is actually MEASURED (1.0 = every component
    # present). Renormalising over present components is right - it stops a
    # missing signal being read as a zero - but it also means a missing LOW leg
    # silently RAISES the average, so a data-poor row can outrank a data-rich one.
    # Surfaced here so views can rank complete evidence above thin evidence
    # without anyone inventing a number to fill the gap.
    evidence_weight = (round(sum(wt for _, wt in avail) / sum(wt_map.values()), 3)
                       if avail else 0.0)
    # CORE = Market + Competition only (V30.1, external review): the opportunity
    # signal is a bonus/discriminator, not a prerequisite - its absence must NOT
    # cap a fully-measured market row at WATCH. When O is absent its weight is
    # renormalised across the present components (M .376 / C .329 / P .176 /
    # F .118 with the default weights).
    core_missing = any(subs[k] is None for k in
                       ("market_potential", "competition_health"))
    # V37.6: with the core missing there is no market score to report. The number
    # was still being published (and sorted on), and because the remaining legs -
    # competition-from-listing-count and the deterministic feasibility read - are
    # both HIGH for an obscure keyword, 561 rows carrying no market data at all
    # scored ~76-87 and sat at the TOP of the inbox above every measured row.
    # A verdict cap alone didn't stop that; the score itself has to be honest.
    # (interactive.py already refused to display these - now it's the same
    # everywhere. Consumers guard with `score or 0`, so nulls sort last.)
    if core_missing:
        overall = None
    # V35.2 trust hotfix (3-review consensus): DEMAND-GROUNDED check. A market
    # score standing only on velocity/conversion - with NO real demand data
    # (no revenue, no views, no explicit demand score) - must never mint a
    # confident GO/CONDITIONAL: momentum-92 rows with zero listings were
    # scoring GO 83 on the strength of one leg. Such rows cap at WATCH (needs
    # enrichment). The lifetime Etsy-proof override in ranking_engine still
    # applies downstream, so a niche with REAL sales evidence is never held
    # back by this cap. Ranking math otherwise untouched (90-day freeze).
    demand_grounded = _demand_from(row) is not None
    if ip_risk == "high":
        verdict = SKIP
    elif overall is None or core_missing:
        verdict = WATCH                  # honest-nulls: no confident GO without core
    elif not demand_grounded and overall >= 50:
        verdict = WATCH                  # momentum/conversion-only: never GO
    elif overall >= 80:
        verdict = GO
    elif overall >= 65:
        verdict = CONDITIONAL
    elif overall >= 50:
        verdict = WATCH
    else:
        verdict = SKIP
    return {"keyword": keyword, "overall_score": overall, "verdict": verdict,
            "sub_scores": subs, "missing": missing, "ip_risk": ip_risk,
            "core_complete": not core_missing,
            "evidence_weight": evidence_weight,
            "demand_grounded": demand_grounded,
            "rationale": _rationale(subs, missing, ip_risk, core_missing,
                                    gtrends_dir)
            + ([] if demand_grounded else
               ["No real demand data (revenue/views) yet - capped at WATCH "
                "until enriched or proven"]),
            "weights_used": wt_map}


def opportunity_gap(subs, proven_orders=0):
    """Winner score (0-100) for the Winner Finder: it rewards the high-demand +
    low-competition CORNER specifically, not a good all-round score.

    It's the geometric mean of Market (demand) and Competition-health (= low
    saturation). Because it multiplies the two axes, a niche must be strong on
    BOTH to score high: high demand in a saturated niche, or an open niche with
    no demand, both get pulled down hard - which is exactly the trade-off the
    seller cares about. Returns None when either core axis is missing (honest-
    null: you can't call something a winner without both signals present).

    proven_orders is OUR OWN sales history for this keyword (learning loop): a
    niche we've actually sold gets a capped lift (1 sale -> +3 ... 10+ -> +12) so
    proven winners rise in the ranking. 0 (a brand-new shop) leaves the score
    exactly as the public data alone would put it - the edge only ever adds."""
    if not isinstance(subs, dict):
        return None
    m = subs.get("market_potential")
    c = subs.get("competition_health")
    if not isinstance(m, (int, float)) or not isinstance(c, (int, float)):
        return None
    base = math.sqrt(max(0.0, m) * max(0.0, c))
    po = proven_orders if isinstance(proven_orders, (int, float)) else 0
    if po and po > 0:
        base = min(100.0, base + min(12.0, 2.0 + po))
    return round(base, 1)


def gtrends_dirs(keywords, geo="US"):
    """Best-effort {keyword: {"avg_interest", "momentum_pct"}} for a batch of
    keywords, ready to hand to score(gtrends_dir=...).

    NEVER raises and never blocks a scoring run: Google Trends is a free but
    flaky secondary signal (offline, HTTP 429 rate-limit, pytrends missing), so
    any failure just returns {} and every keyword is scored as an honest null.
    De-duplicates and drops blanks before hitting the network."""
    kws = []
    seen = set()
    for k in keywords or []:
        k = (k or "").strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            kws.append(k)
    if not kws:
        return {}
    try:
        from src import gtrends
        return gtrends.fetch_momentum(kws, geo=geo) or {}
    except Exception:  # noqa: BLE001 - secondary signal; never break scoring
        return {}


def cell(row, keyword=None, mode=None):
    """Compact table cell: 'NN GO' when the core signals exist, else just the
    verdict (no misleading number when the score is built on partial data)."""
    s = score(row, keyword=keyword, mode=mode)
    if s["core_complete"] and s["overall_score"] is not None:
        return f"{s['overall_score']} {s['verdict']}"
    return s["verdict"]
