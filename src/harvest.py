"""Harvest fresh, data-driven keyword suggestions from the live YTrends index
and add the best NEW ones to keywords.csv — so the daily POD + Embroidery
reports research a rich, current keyword universe instead of a short hand-typed
seed list. This is the "more keywords" engine.

Sources (all official YTrends MCP tools — the same data YTuong's dashboard,
/trending, /hot, /best-seller, /popular-now show; no scraping):
  - browse_rankings(top)    highest-momentum keywords across Etsy, paginated
  - scout_opportunities     sweet-spot niches (low competition + high momentum)
  - find_trending_keywords  this week's risers
  - search(seed)            every keyword containing a POD / embroidery seed term

Run:  py main.py harvest        (append to keywords.csv)
      py main.py harvest --dry  (audit only, write nothing)
"""
import csv
import re
from pathlib import Path

from src import ytrends_mcp as mcp
from src.discover import matches_mode, looks_like_shop_name, GENERIC_JUNK

KEYWORDS_CSV = Path("keywords.csv")

# Seed terms we actively search so BOTH modes get targeted expansion. Embroidery
# is the starved one, so it gets the deeper seed list.
EMB_SEEDS = ["embroidered", "embroidery", "monogram", "monogrammed", "chenille",
             "applique", "patch", "needlepoint", "cross stitch", "custom embroidery",
             "embroidered hat", "embroidered sweatshirt", "embroidered hoodie",
             "embroidered tote", "embroidered beanie", "embroidered baby",
             "embroidered crewneck", "embroidered denim", "personalized embroidery",
             "embroidered flower", "embroidered pet"]
POD_SEEDS = ["personalized", "custom name", "funny shirt", "retro", "vintage",
             "comfort colors", "trendy", "aesthetic", "matching", "couples",
             "bachelorette", "bridesmaid", "teacher", "nurse", "mama",
             "dog mom", "birthday", "groovy", "western", "coquette"]


# This tool serves a PHYSICAL print-on-demand + embroidery business (shirts,
# hoodies, caps, totes, embroidered goods). Drop keywords that are digital
# downloads, design files, or off-domain (occult/spell) noise — they pollute a
# product-research pool even when they rank high on Etsy overall.
_BLOCK_WORDS = {
    "svg", "png", "jpg", "jpeg", "pdf", "dxf", "eps", "psd", "ai",
    "pes", "dst", "jef", "bx", "hus", "vp3",          # embroidery machine files
    "clipart", "printable", "sublimation", "cricut", "procreate",
    "font", "fonts", "mockup", "mockups", "preset", "presets", "lightroom",
    "spell", "spells", "ritual", "witchcraft", "hex", "curse", "psychic",
}
_BLOCK_SUB = ("clip art", "cut file", "digital download", "embroidery design",
              "embroidery file", "machine embroidery", "svg file", "png file",
              "digital paper", "seamless pattern")


def _clean(tag):
    t = (tag or "").strip().lower()
    if not t or t in GENERIC_JUNK or looks_like_shop_name(t):
        return None
    words = t.split()
    if not (1 <= len(words) <= 6):
        return None
    if not any(c.isalpha() for c in t):
        return None
    if " " not in t and len(t) > 18:          # long single-token handle
        return None
    if re.search(r"https?://|www\.|@|\.com", t):
        return None
    if any(w in _BLOCK_WORDS for w in words):
        return None
    if any(sub in t for sub in _BLOCK_SUB):
        return None
    return t


_METRICS = ("age", "listings", "sellers", "comp", "price", "conv", "revenue",
            "revenue_total", "momentum", "sold", "views", "opportunity")


def _est_views(views, sold, conv):
    """Best 24h demand: real views, else back it out of sales / conversion
    (views = units sold / conversion rate)."""
    if views:
        return float(views)
    if sold and conv:
        try:
            return float(sold) / float(conv)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
    return 0.0


def _add(store, tag, score, source, listings=None, comp=None, price=None,
         conv=None, sellers=None, revenue=None, sold=None, views=None, age=None,
         revenue_total=None, momentum=None, opportunity=None):
    """Merge one pulled tag into the store.

    `revenue` is ALWAYS revenue per listing and `revenue_total` is ALWAYS the
    niche total — the two are never mixed in one field. YTrends returns
    `avg_revenue` (per listing) from trending and `total_revenue_usd` (niche
    total) from opportunities; writing both into one column made an
    opportunity-sourced keyword look ~250x richer than an identical
    trending-sourced one and swung the demand sub-score by ~60 points on
    provenance alone. `momentum` is the measured momentum only — never a
    stand-in score, so a row without one stays an honest null.

    `opportunity` is YTrends' OWN opportunity/gem score — an independent vendor
    estimate — and must be passed ONLY by the callers that actually receive one.
    Do not route the positional `score` here: it is whatever number the source
    happened to return (opportunity 66-91, rank 38-75, trending = momentum,
    search a flat 40), so it is provenance, not signal. Feeding momentum in as
    an opportunity signal would double-count the velocity leg, which is the
    failure V30.1 removed.
    """
    c = _clean(tag)
    if not c:
        return
    if revenue is None and revenue_total is not None and listings:
        try:                       # niche total -> per listing, so units match
            revenue = float(revenue_total) / float(listings)
        except (TypeError, ValueError, ZeroDivisionError):
            revenue = None
    rec = {"tag": c, "score": float(score or 0), "source": source,
           "listings": listings, "sellers": sellers, "comp": comp,
           "price": price, "conv": conv, "revenue": revenue,
           "revenue_total": revenue_total, "momentum": momentum, "sold": sold,
           "views": _est_views(views, sold, conv) or None, "age": age,
           "opportunity": opportunity}
    cur = store.get(c)
    if cur is None or rec["score"] > cur["score"]:
        if cur:  # keep any metrics we already learned from another source
            for k in _METRICS:
                if rec[k] is None:
                    rec[k] = cur[k]
        store[c] = rec
    elif cur:    # lower score, but fill any metrics it was missing
        for k in _METRICS:
            if cur[k] is None and rec[k] is not None:
                cur[k] = rec[k]


def _pull(store, log=lambda s: None):
    # 1) top rankings, paginated — the highest-momentum keywords across Etsy
    got = 0
    for off in (0, 50, 100, 150, 200, 250):
        try:
            page = mcp.browse_rankings(mode="top", limit=50, offset=off)
        except Exception:
            break
        if not page:
            break
        for e in page:
            # browse_rankings carries rank/target_score + listing_count only —
            # no demand fields, and target_score is a RANK score, not momentum.
            _add(store, e.get("tag"), e.get("target_score"), "ranking",
                 listings=e.get("listing_count"))
        got += len(page)
    log(f"  rankings: pulled {got}")

    # 2) sweet-spot opportunities (low/medium competition)
    for filt in ({}, {"max_competition": "low"}, {"max_competition": "medium"}):
        try:
            for r in mcp.scout_opportunities(limit=50, **filt):
                _add(store, r.get("tag"), r.get("opportunity_score"),
                     "opportunity", listings=r.get("listings"),
                     sellers=r.get("sellers"), price=r.get("avg_price_usd"),
                     conv=r.get("avg_conversion_rate"),
                     revenue=r.get("avg_revenue"),
                     revenue_total=r.get("total_revenue_usd"),
                     momentum=r.get("momentum_score"),
                     opportunity=r.get("opportunity_score"),
                     sold=r.get("avg_sold_24h"))
        except Exception:
            pass

    def _trend(t, src="trending"):
        _add(store, t.get("tag"), t.get("momentum_score"), src,
             listings=t.get("listing_count"), sellers=t.get("seller_count"),
             comp=t.get("competition_level"), price=t.get("avg_price"),
             conv=t.get("avg_conversion_rate"), revenue=t.get("avg_revenue"),
             momentum=t.get("momentum_score"),
             sold=t.get("total_sold_24h"), views=t.get("total_views_24h"))

    def _scout(r):
        _add(store, r.get("tag"), r.get("opportunity_score"), "opportunity",
             listings=r.get("listings"), sellers=r.get("sellers"),
             price=r.get("avg_price_usd"), conv=r.get("avg_conversion_rate"),
             revenue=r.get("avg_revenue"),
             revenue_total=r.get("total_revenue_usd"),
             momentum=r.get("momentum_score"),
             opportunity=r.get("opportunity_score"),
             sold=r.get("avg_sold_24h"))

    # 3) this week's risers (broad)
    try:
        for t in mcp.trending_keywords(limit=40):
            _trend(t)
    except Exception:
        pass

    # 4) targeted, METRIC-RICH pulls per seed — so niche keywords (especially
    #    embroidery) arrive with real demand/conversion, not just a name. This
    #    is what lets them clear the reports' demand + margin gates.
    seeds = EMB_SEEDS + POD_SEEDS
    for seed in seeds:
        try:
            for t in mcp.trending_keywords(limit=15, search=seed):
                _trend(t, "trending")
        except Exception:
            pass
        try:
            for r in mcp.scout_opportunities(limit=25, search=seed):
                _scout(r)
        except Exception:
            pass

    # 5) plain search adds extra breadth (names; demand is filled in if the tag
    #    also surfaced in a metric-rich source above)
    for seed in seeds:
        try:
            for r in mcp.search(seed, limit=25, kinds=["keyword"]):
                if r.get("kind") == "keyword":
                    _add(store, r.get("title"), 40, "search")
        except Exception:
            pass
    log(f"  after opportunities + trending + {len(seeds)} seed pulls: "
        f"{len(store)} unique clean tags")


def _existing():
    keys = set()
    if KEYWORDS_CSV.exists():
        for row in csv.reader(KEYWORDS_CSV.open(encoding="utf-8")):
            if row and row[0].strip().lower() != "keyword":
                keys.add(row[0].strip().lower())
    return keys


def _num(v, cast=float, default=0):
    try:
        return cast(float(v))
    except (TypeError, ValueError):
        return default


# keyword_data.csv is the file the manager/ideas/discover reports actually read.
# Writing it from the live MCP pull is what makes the harvested keywords show up
# in the reports (not just sit in keywords.csv). Schema must match exactly what
# product_manager.load_keyword_data expects.
KDATA_FIELDS = ["keyword", "etsy_listings", "seller_count", "views_24h",
                "avg_price", "avg_revenue", "total_revenue", "conversion_rate",
                "momentum", "opportunity_score", "niche_age_days", "tm_risk",
                "source", "collected_at"]


# master column -> store key, for the fields that carry enrichment. One map, so
# the carry-over branch and the preserve branch below cannot drift apart.
_ENRICHED = {
    "etsy_listings": "listings", "seller_count": "sellers",
    "views_24h": "views", "avg_price": "price", "avg_revenue": "revenue",
    "total_revenue": "revenue_total", "conversion_rate": "conv",
    "momentum": "momentum", "niche_age_days": "age",
    "opportunity_score": "opportunity",
}


def merge_existing(store, path="keyword_data.csv", report=False):
    """Fold the keywords ALREADY in the master back into a fresh pull.

    harvest() used to hand write_keyword_data() nothing but the live MCP pull,
    and write_keyword_data() opens the file with "w" — so every keyword the MCP
    did not return that run was deleted. That silently wiped every Keyword Lab
    long-tail, every Pinterest/supplier lane lead and every extension import on
    the next `main.py harvest`.

    BLANK NEVER BEATS KNOWN (the second half of that same bug). Carrying only the
    keywords the pull MISSED still lost data: for a keyword the pull DID return,
    this kept the fresh row and copied nothing but `source`. The VPS IP is
    blocked from YTrends, so its pulls come back thin — and every thin row
    overwrote a rich one. Measured on the server, one 06:00 cron took revenue
    from 998 rows to 256 and conversion from 1,458 to 721 while correctly adding
    97 new keywords.

    There was a guard for a TOTAL outage (harvest() skips the write on an empty
    store) but none for a PARTIAL one, which is the case that actually happens.

    So a keyword present in BOTH is now merged field by field: a fresh value wins
    only when it is actually a value. `_f()` maps blank AND zero to None, so a
    zero from an API — which usually means "I don't know" — cannot overwrite a
    measurement either.

    Returns the carried count, or a {carried, preserved, fields_preserved} report
    when report=True: silent preservation is as hard to trust as silent loss.
    """
    carried = preserved = fields_preserved = 0
    try:
        with open(path, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return {"carried": 0, "preserved": 0, "fields_preserved": 0} if report else 0

    def _f(row, key):
        v = _num(row.get(key), float, None)
        return v if v else None

    for row in rows:
        tag = (row.get("keyword") or "").strip().lower()
        if not tag:
            continue
        src = (row.get("source") or "").strip()
        cur = store.get(tag)
        if cur is not None:
            cur["source"] = src or cur["source"]      # provenance is sticky
            hit = 0
            for col, key in _ENRICHED.items():
                if _num(cur.get(key), float, None):
                    continue                          # the pull has a real value
                old = _f(row, col)
                if old is not None:
                    cur[key] = old                    # keep what we already knew
                    hit += 1
            if hit:
                preserved += 1
                fields_preserved += hit
            continue
        store[tag] = {
            "tag": tag, "score": _num(row.get("momentum")), "source": src,
            "comp": None, "sold": None,
            **{key: _f(row, col) for col, key in _ENRICHED.items()},
        }
        carried += 1
    if report:
        return {"carried": carried, "preserved": preserved,
                "fields_preserved": fields_preserved}
    return carried


# Channels that record WHO added a keyword. When the same keyword exists on both
# machines, this provenance wins over a bare mcp: pull — the MCP would have found
# it anyway, but only one side knows a human/lab put it there first.
def _is_provenance(src):
    s = (src or "").strip()
    return bool(s) and not s.startswith("mcp:")


def merge_master(other_path, path="keyword_data.csv"):
    """Union another machine's keyword master into this one. Never deletes.

    The PC harvests and the VPS collects what the team adds through the web UI
    — Keyword Lab, long-tail pulls, extension imports. (This docstring used to
    say the VPS IP is blocked from YTrends; verified 2026-08-11 that a direct
    MCP call from the VPS itself succeeds — see src/enrich.py's docstring. The
    PC/VPS harvest split may now be a workflow choice rather than a hard
    requirement, but that is a separate decision from this sync's own job.)
    deploy/push-to-vps.ps1 used to scp the PC's file straight
    over the server's, so every keyword added ON the VPS was destroyed on the
    next data sync — the same deletion bug as merge_existing(), across the
    machine boundary.

    Rows only the other side has are carried in. For a keyword both sides hold,
    the local (freshly harvested) metrics win, but any field local left BLANK is
    filled from the other side, the non-mcp provenance is kept, and the earliest
    collected_at survives. Returns (carried_in, enriched).
    """
    try:
        with open(other_path, encoding="utf-8-sig") as fh:
            other = list(csv.DictReader(fh))
    except OSError:
        return 0, 0
    try:
        with open(path, encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            header = rd.fieldnames or list(KDATA_FIELDS)
            local = list(rd)
    except OSError:
        header, local = list(KDATA_FIELDS), []
    for col in KDATA_FIELDS:                 # tolerate an older/newer schema
        if col not in header:
            header.append(col)
    by_kw = {(r.get("keyword") or "").strip().lower(): r for r in local}
    carried = enriched = 0
    for row in other:
        kw = (row.get("keyword") or "").strip().lower()
        if not kw:
            continue
        cur = by_kw.get(kw)
        if cur is None:
            by_kw[kw] = row
            local.append(row)
            carried += 1
            continue
        filled = False
        for col in header:                   # never lose a value we don't have
            if col in ("keyword", "source", "collected_at"):
                continue
            if not str(cur.get(col) or "").strip() and str(row.get(col) or "").strip():
                cur[col] = row[col]
                filled = True
        if _is_provenance(row.get("source")) and not _is_provenance(cur.get("source")):
            cur["source"] = row["source"]
            filled = True
        a, b = (cur.get("collected_at") or ""), (row.get("collected_at") or "")
        if b and (not a or b < a):
            cur["collected_at"] = b
        if filled:
            enriched += 1
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in local:
            w.writerow({c: r.get(c, "") for c in header})
    return carried, enriched


# Fields worth guarding: the ones a thin pull actually destroyed in production.
_GUARDED = ("total_revenue", "conversion_rate", "avg_price", "views_24h")
# A rewrite may lose a little to genuine corrections; losing a tenth of the
# shop's measured data is never a correction.
_MAX_DROP = 0.10


def _enrichment_density(path="keyword_data.csv"):
    """{field: how many rows carry a value} for the master on disk."""
    out = {f: 0 for f in _GUARDED}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                for f in _GUARDED:
                    if (row.get(f) or "").strip():
                        out[f] += 1
    except OSError:
        pass
    return out


def _density_of_store(store):
    """The same count for what is ABOUT to be written."""
    keys = {"total_revenue": "revenue_total", "conversion_rate": "conv",
            "avg_price": "price", "views_24h": "views"}
    out = {f: 0 for f in _GUARDED}
    for rec in (store or {}).values():
        for f, k in keys.items():
            if _num(rec.get(k), float, None):
                out[f] += 1
    return out


def _density_drop(before, after, max_drop=_MAX_DROP):
    """A human-readable reason to abort, or None when the write is safe."""
    for f in _GUARDED:
        b, a = before.get(f, 0), after.get(f, 0)
        if b and a < b * (1 - max_drop):
            return (f"{f} {b} -> {a} "
                    f"({round(100 * (b - a) / b)}% of the measured rows)")
    return None


def write_keyword_data(store, path="keyword_data.csv"):
    from datetime import date
    today = str(date.today())
    # collected_at = FIRST-SEEN date. The old behaviour re-stamped EVERY row
    # with today's date on every rewrite, destroying the growth history the
    # owner needs ("how fast is the keyword base updated?"). Preserve the
    # existing date per keyword; only genuinely NEW keywords get today.
    first_seen = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = (r.get("keyword") or "").strip().lower()
                d = (r.get("collected_at") or "").strip()
                if k and d:
                    first_seen[k] = d
    except OSError:
        pass
    # V36: stamp the trademark risk at write-time so the base carries it (it was
    # always blank before). Pure local regex gate; never blocks a write.
    try:
        from src import trademark as _tm
        def _risk(kw):
            lvl = (_tm.check(kw) or ("OK", ""))[0]
            return "" if lvl == "OK" else lvl      # blank = clear, else CAUTION/HIGH
    except Exception:  # noqa: BLE001
        def _risk(kw):
            return ""
    # Absent metric -> BLANK, never 0. Writing 0 for "the source didn't tell us"
    # made a never-measured keyword indistinguishable from one measured at zero:
    # the scorer read conversion 0.0 as a real datapoint, so a row with nothing
    # behind it still produced a market score. Blank keeps honest-nulls intact
    # all the way from the pull to the scorer (which already treats missing as
    # missing).
    def _opt(v, cast=float, nd=2):
        if v is None:
            return ""
        n = _num(v, cast, None)
        if n is None:
            return ""
        return n if cast is int else round(n, nd)

    def _views(v):
        """views_24h, preserving POSITIVE FRACTIONS.

        `_opt(v, int)` truncated every value below 1.0 to 0. Measured on the live
        master: 155 rows hold fractional views (0.81, 0.97, 0.43) and lost them
        on EVERY write — the 06:00 cron included, so the loss repeated daily and
        looked like the data had simply never been there.

        Integers still write as integers, so the column does not grow 169.0-style
        noise, and the zero/blank behaviour is unchanged: `_f()` in
        merge_existing already maps 0 -> None on the carry path, so a 0 reaching
        here is a genuine store value and stays 0 exactly as before.
        """
        if v is None:
            return ""
        n = _num(v, float, None)
        if n is None:
            return ""
        return int(n) if float(n).is_integer() else round(n, 2)

    rows = sorted(store.values(), key=lambda r: r["score"], reverse=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KDATA_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({
                "keyword": r["tag"],
                "etsy_listings": _opt(r["listings"], int),
                "seller_count": _opt(r["sellers"], int),
                "views_24h": _views(r["views"]),        # 24h demand (views, or
                                                        # sales/conversion est.)
                "avg_price": _opt(r["price"]),
                "avg_revenue": _opt(r["revenue"]),
                "total_revenue": _opt(r.get("revenue_total")),
                "conversion_rate": _opt(r["conv"], float, 4),
                # MEASURED momentum only. This used to be r["score"] — whatever
                # score the source happened to return (opportunity 66-91, rank
                # 38-75, trending 21-52, plain search a hardcoded 40) — so the
                # velocity leg of the market score was provenance, not market.
                # No measurement -> honest null, exactly like every other field.
                "momentum": _opt(r.get("momentum")),
                # YTrends' OWN opportunity/gem score — an independent vendor
                # estimate, written only where a source actually returned one.
                # Never the positional `score` (see _add): that is provenance.
                "opportunity_score": _opt(r.get("opportunity")),
                "niche_age_days": _num(r.get("age"), int) if r.get("age") is not None else "",
                "tm_risk": _risk(r["tag"]),
                # keep the TRUE channel: only bare MCP view names get the mcp:
                # prefix. ext:*/keyword-lab/*-lead rows keep their identity so
                # the growth history can say WHERE keywords came from.
                "source": (r["source"] if (":" in (r["source"] or "")
                                           or (r["source"] or "") == "keyword-lab"
                                           or (r["source"] or "").endswith("-lead"))
                           else "mcp:" + (r["source"] or "")),
                "collected_at": first_seen.get(r["tag"].strip().lower()) or today,
            })
    return len(rows)


def write_raw_and_processed(store):
    """Audit trail (spec §5): dump the raw pull to data/raw/ytuong/ and a
    normalized copy to data/processed/keyword_data.csv (with source,
    raw_source_url, data_check_status). The root keyword_data.csv stays the
    report fuel; these are the transparency/audit files."""
    from datetime import date
    from pathlib import Path
    from urllib.parse import quote
    import json as _json
    today = str(date.today())
    raw_dir = Path("data/raw/ytuong")
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"keywords_{today}.json").write_text(
        _json.dumps(list(store.values()), indent=2, default=str), encoding="utf-8")

    proc = Path("data/processed")
    proc.mkdir(parents=True, exist_ok=True)
    fields = ["keyword", "source", "views_24h", "revenue", "avg_price",
              "conversion_rate", "etsy_listings", "seller_count", "collected_at",
              "raw_source_url", "data_check_status"]
    with (proc / "keyword_data.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(store.values(), key=lambda x: x["score"], reverse=True):
            conv, price = _num(r["conv"]), _num(r["price"])
            dc = ("CHECK_CONVERSION" if conv > 0.15 else
                  "CHECK_PRICE" if price and price < 3 else "OK")
            w.writerow({
                "keyword": r["tag"], "source": "mcp:" + r["source"],
                "views_24h": _num(r["views"], int),
                "revenue": round(_num(r["revenue"]), 2),
                "avg_price": round(price, 2),
                "conversion_rate": round(conv, 4),
                "etsy_listings": _num(r["listings"], int),
                "seller_count": _num(r["sellers"], int),
                "collected_at": today,
                "raw_source_url": f"https://trends.ytuong.ai/en/keyword/{quote(r['tag'])}",
                "data_check_status": dc})
    return raw_dir / f"keywords_{today}.json"


def harvest(append=True, cap_pod=140, cap_emb=90, log=lambda s: None):
    store = {}
    _pull(store, log)
    existing = _existing()
    new = [r for r in store.values() if r["tag"] not in existing]
    emb = sorted((r for r in new if matches_mode(r["tag"], "embroidery")),
                 key=lambda r: r["score"], reverse=True)[:cap_emb]
    pod = sorted((r for r in new if matches_mode(r["tag"], "pod")),
                 key=lambda r: r["score"], reverse=True)[:cap_pod]
    chosen = emb + pod

    wrote_data = 0
    # Never overwrite the report fuel with an EMPTY pull. A total source
    # outage yields a zero-tag store; writing it would blank keyword_data.csv
    # (header only) until the next good pull. Keep the previous file instead.
    if append and not store:
        log("  [!] pull returned ZERO tags (source outage?) -- KEEPING the "
            "existing keyword_data.csv, not overwriting it with an empty file")
    elif append:
        # Fuel the reports: rewrite keyword_data.csv from the live pull MERGED
        # with what the master already held, so a pull never deletes the
        # keywords it simply didn't return this time (Keyword Lab long-tails,
        # lane leads, extension imports).
        # (keywords.csv, the small curated Google-Trends seed list, is left
        #  alone; the permanent archive of discoveries is the DB below.)
        before_density = _enrichment_density()
        rep = merge_existing(store, report=True)
        if rep["carried"]:
            log(f"  carried over {rep['carried']} existing keyword(s) not in "
                "this pull")
        if rep["preserved"]:
            log(f"  preserved {rep['fields_preserved']} enriched field(s) on "
                f"{rep['preserved']} keyword(s) the pull returned thin")
        # BELT AND BRACES. merge_existing now protects field-by-field, but a
        # future writer, a column rename or an alias drift could still gut the
        # master, and the cron runs unattended at 06:00. A wholesale rewrite that
        # LOSES enrichment is never legitimate: refuse it and keep the file.
        after_density = _density_of_store(store)
        drop = _density_drop(before_density, after_density)
        if drop:
            log("  [!] ABORTING the keyword_data.csv write — enrichment would "
                f"fall {drop}. Existing file kept untouched. Fields: "
                f"before={before_density} after={after_density}")
        else:
            wrote_data = write_keyword_data(store)
        try:                       # audit trail (spec §5): raw + normalized
            write_raw_and_processed(store)
        except Exception:  # noqa: BLE001 - never let the audit dump break harvest
            pass
        try:
            from src.db import save_discovered
            save_discovered([("harvest", r["tag"], r["listings"], r["price"],
                              r["revenue"], r["conv"], r["score"],
                              r["comp"] or "", "", r["score"])
                             for r in chosen])
        except Exception:
            pass

    if append and store:
        try:   # growth ledger: the MCP pull is a channel like any other
            from src.import_ledger import record as _lrec
            _lrec(user="mcp-auto", channel="mcp", view="harvest",
                  rows=len(store), kw_new=len(new))
        except Exception:  # noqa: BLE001
            pass
    return {"scanned": len(store), "wrote_data": wrote_data,
            "new_total": len(new),
            "new_emb": sum(1 for r in new if matches_mode(r["tag"], "embroidery")),
            "new_pod": sum(1 for r in new if matches_mode(r["tag"], "pod")),
            "top_emb": len(emb), "top_pod": len(pod),
            "emb_sample": [r["tag"] for r in emb[:18]],
            "pod_sample": [r["tag"] for r in pod[:18]]}


def run_harvest(argv=None):
    argv = argv or []
    dry = "--dry" in argv or "--dry-run" in argv
    print(f"Harvesting keywords from the live YTrends index"
          f"{' (DRY RUN - writing nothing)' if dry else ''}...")
    s = harvest(append=not dry, log=print)
    print(f"\nScanned {s['scanned']} unique clean keywords from the index.")
    print(f"NEW vs current seed list: {s['new_total']} "
          f"(embroidery {s['new_emb']}, POD {s['new_pod']})")
    if s.get("emb_sample"):
        print(f"\nTop embroidery picks ({s['top_emb']}): "
              + ", ".join(s["emb_sample"]))
    if s.get("pod_sample"):
        print(f"Top POD picks ({s['top_pod']}): " + ", ".join(s["pod_sample"]))
    if dry:
        print("\n(DRY RUN — nothing written. Re-run without --dry to apply.)")
    else:
        print(f"\nWrote {s['wrote_data']} keywords to keyword_data.csv — this is "
              "what fuels the reports.")
        print("Next `daily pod` / `daily embroidery` will research them all.")
        try:
            from src import rank_snapshot as rsnap
            rsnap.snapshot(source="harvest")
        except Exception:  # noqa: BLE001 - a snapshot failure can't break harvest
            pass
    return s
