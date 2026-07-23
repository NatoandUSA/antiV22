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


_METRICS = ("age", "listings", "sellers", "comp", "price", "conv", "revenue", "sold",
            "views")


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
         conv=None, sellers=None, revenue=None, sold=None, views=None, age=None):
    c = _clean(tag)
    if not c:
        return
    rec = {"tag": c, "score": float(score or 0), "source": source,
           "listings": listings, "sellers": sellers, "comp": comp,
           "price": price, "conv": conv, "revenue": revenue, "sold": sold,
           "views": _est_views(views, sold, conv) or None, "age": age}
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
                     revenue=r.get("total_revenue_usd"),
                     sold=r.get("avg_sold_24h"))
        except Exception:
            pass

    def _trend(t, src="trending"):
        _add(store, t.get("tag"), t.get("momentum_score"), src,
             listings=t.get("listing_count"), sellers=t.get("seller_count"),
             comp=t.get("competition_level"), price=t.get("avg_price"),
             conv=t.get("avg_conversion_rate"), revenue=t.get("avg_revenue"),
             sold=t.get("total_sold_24h"), views=t.get("total_views_24h"))

    def _scout(r):
        _add(store, r.get("tag"), r.get("opportunity_score"), "opportunity",
             listings=r.get("listings"), sellers=r.get("sellers"),
             price=r.get("avg_price_usd"), conv=r.get("avg_conversion_rate"),
             revenue=r.get("total_revenue_usd"), sold=r.get("avg_sold_24h"))

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
                "avg_price", "avg_revenue", "conversion_rate", "momentum",
                "niche_age_days", "tm_risk", "source", "collected_at"]


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
    rows = sorted(store.values(), key=lambda r: r["score"], reverse=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KDATA_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({
                "keyword": r["tag"],
                "etsy_listings": _num(r["listings"], int),
                "seller_count": _num(r["sellers"], int),
                "views_24h": _num(r["views"], int),     # 24h demand (views, or
                                                        # sales/conversion est.)
                "avg_price": round(_num(r["price"]), 2),
                "avg_revenue": round(_num(r["revenue"]), 2),
                "conversion_rate": round(_num(r["conv"]), 4),
                "momentum": round(r["score"], 2),
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
        # Fuel the reports: overwrite keyword_data.csv from the full live pull.
        # (keywords.csv, the small curated Google-Trends seed list, is left
        #  alone; the permanent archive of discoveries is the DB below.)
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
    return s
