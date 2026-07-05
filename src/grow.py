"""Keyword & niche growth engine.

Commands:
  py main.py grow                          -> auto-harvest: trending + hidden
                                              gems + suggestions seeded from
                                              niches.txt and keywords.csv
  py main.py grow "embroidered sweatshirt" -> research one niche deeply
  py main.py grow pod / grow embroidery    -> auto-harvest, one product line
  py main.py grow embroidery "name patch"  -> niche research within a mode

What it updates (data-driven, deduplicated, trademark-filtered):
  keywords.csv     -> new keywords with competition filled from live data
  niches.txt       -> new recurring niche terms (marked auto-added)
  keyword_data.csv -> full rows so 'py main.py manager' scores them next run
"""
import csv
from datetime import date
from pathlib import Path

from src.discover import (GENERIC_JUNK, SERVICE_TERMS, looks_like_shop_name,
                          matches_mode, load_niche_terms)
from src.trademark import check as tm_check
from src.ytrends_client import suggestions, trending, hidden_gems, top_keywords

TODAY = str(date.today())
MAX_SEEDS = 12          # suggestions calls per run (quota-friendly)
MAX_NEW_KEYWORDS = 40   # new keywords accepted per run

STOPWORDS = {"gift", "gifts", "custom", "personalized", "for", "her", "him",
             "the", "and", "with", "cute", "best", "new", "mini", "set"}


def _existing_keywords():
    kws = set()
    p = Path("keywords.csv")
    if p.exists():
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("keyword"):
                    kws.add(r["keyword"].strip().lower())
    return kws


def _existing_data_keywords():
    kws = set()
    p = Path("keyword_data.csv")
    if p.exists():
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("keyword"):
                    kws.add(r["keyword"].strip().lower())
    return kws


def _viral_score(c):
    """Best-for-sale ranking: money x conversion x lift vs competition."""
    rev = c.get("avg_revenue") or 0
    conv = c.get("avg_conversion_rate") or 0
    lift = c.get("lift") or c.get("momentum_score") or c.get("gem_score") or 0
    comp = max(c.get("tag_listing_count") or c.get("listing_count") or 1000, 10)
    sold = c.get("avg_sold_24h") or 0
    return round((rev * conv * (1 + lift / 100) + sold * 50) / comp, 3)


def _derive_views(c):
    """views/day = total sold/day / conversion (honest derivation)."""
    sold = (c.get("avg_sold_24h") or 0) * (c.get("tag_listing_count") or 0)
    conv = c.get("avg_conversion_rate") or 0
    if sold and conv:
        return int(sold / conv)
    return c.get("total_views_24h") or 0


def harvest(mode=None, seed=None, quiet=False):
    existing = _existing_keywords()
    existing_data = _existing_data_keywords()
    niche_terms = load_niche_terms()

    # 1) gather candidates: the three live lists...
    candidates = {}
    for source, rows in (("trending", trending()),
                         ("hidden_gems", hidden_gems()),
                         ("keywords", top_keywords())):
        for r in rows:
            tag = (r.get("tag") or "").strip().lower()
            if tag:
                r["_source"] = source
                candidates.setdefault(tag, r)

    # 2) ...plus suggestions from seeds (given niche, or auto)
    if seed:
        seeds = [seed.strip().lower()]
    else:
        winners = sorted(candidates.values(), key=_viral_score, reverse=True)
        seeds = [w["tag"] for w in winners
                 if matches_mode(w["tag"], mode)][:MAX_SEEDS // 2]
        seeds += [k for k in existing if matches_mode(k, mode)][
            :MAX_SEEDS - len(seeds)]
    calls = 0
    for s in seeds[:MAX_SEEDS]:
        try:
            for r in suggestions(s):
                tag = (r.get("tag") or "").strip().lower()
                if tag and tag not in candidates:
                    r["_source"] = f"suggestions:{s}"
                    candidates[tag] = r
            calls += 1
        except Exception as exc:
            if not quiet:
                print(f"  suggestions failed for '{s}': {exc}")

    # 3) filter: dedupe, junk, services, TM HIGH, mode
    accepted, skipped = [], {"exists": 0, "junk": 0, "service": 0,
                             "trademark": 0, "mode": 0}
    for tag, c in candidates.items():
        if tag in existing and tag in existing_data:
            skipped["exists"] += 1
            continue
        if tag in GENERIC_JUNK or looks_like_shop_name(tag) or len(tag) < 4:
            skipped["junk"] += 1
            continue
        if set(tag.split()) & SERVICE_TERMS:
            skipped["service"] += 1
            continue
        if tm_check(tag)[0] == "HIGH":
            skipped["trademark"] += 1
            continue
        if not matches_mode(tag, mode):
            skipped["mode"] += 1
            continue
        c["_tag"] = tag
        accepted.append(c)
    accepted.sort(key=_viral_score, reverse=True)
    accepted = accepted[:MAX_NEW_KEYWORDS]

    # 4) append to keywords.csv (keyword, competition)
    new_kw_rows = [c for c in accepted if c["_tag"] not in existing]
    if new_kw_rows:
        write_header = not Path("keywords.csv").exists()
        with open("keywords.csv", "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["keyword", "competition"])
            for c in new_kw_rows:
                w.writerow([c["_tag"],
                            c.get("tag_listing_count")
                            or c.get("listing_count") or ""])

    # 5) append full rows to keyword_data.csv for the manager
    data_fields = ["keyword", "etsy_listings", "seller_count", "views_24h",
                   "avg_price", "avg_revenue", "conversion_rate", "momentum",
                   "tm_risk", "source", "collected_at"]
    new_data = [c for c in accepted if c["_tag"] not in existing_data]
    if new_data:
        exists = Path("keyword_data.csv").exists()
        with open("keyword_data.csv", "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=data_fields)
            if not exists:
                w.writeheader()
            for c in new_data:
                w.writerow({
                    "keyword": c["_tag"],
                    "etsy_listings": c.get("tag_listing_count")
                                     or c.get("listing_count") or 0,
                    "seller_count": c.get("seller_count") or 0,
                    "views_24h": _derive_views(c),
                    "avg_price": c.get("avg_price") or 0,
                    "avg_revenue": c.get("avg_revenue") or 0,
                    "conversion_rate": c.get("avg_conversion_rate") or 0,
                    "momentum": c.get("lift") or c.get("momentum_score")
                                or c.get("gem_score") or 0,
                    "tm_risk": tm_check(c["_tag"])[0],
                    "source": c.get("_source", "grow"),
                    "collected_at": TODAY,
                })

    # 6) grow niches.txt: recurring meaningful tokens not yet tracked
    counts = {}
    for c in accepted:
        for w in c["_tag"].split():
            if len(w) >= 4 and w not in STOPWORDS \
                    and not any(w in t or t in w for t in niche_terms):
                counts[w] = counts.get(w, 0) + 1
    new_niches = sorted([w for w, n in counts.items() if n >= 2])[:10]
    if new_niches:
        with open("niches.txt", "a", encoding="utf-8") as f:
            f.write(f"# auto-added {TODAY} (review and delete any you "
                    f"don't want)\n")
            for w in new_niches:
                f.write(w + "\n")

    if not quiet:
        print(f"\nGROW summary ({'seed: ' + seed if seed else 'auto'}"
              f"{', mode: ' + mode if mode else ''})")
        print(f"  candidates found: {len(candidates)} "
              f"(suggestions calls used: {calls})")
        print(f"  skipped: {skipped}")
        print(f"  new keywords -> keywords.csv: {len(new_kw_rows)}")
        print(f"  new data rows -> keyword_data.csv: {len(new_data)}")
        print(f"  new niche terms -> niches.txt: {new_niches or 'none'}")
        print("\nTop 10 new keywords by best-for-sale score:")
        for c in accepted[:10]:
            risk = tm_check(c['_tag'])[0]
            flag = f"  [{risk}]" if risk != "OK" else ""
            print(f"  {c['_tag']:<32} listings="
                  f"{c.get('tag_listing_count') or c.get('listing_count') or '?':<7}"
                  f" rev=${c.get('avg_revenue') or 0:<9.0f}"
                  f" conv={(c.get('avg_conversion_rate') or 0)*100:.1f}%{flag}")
        print("\nNext: py main.py manager  (new keywords are scored "
              "automatically)")
    return len(new_data)
