"""Discover mode: pull live YTrends data, rank, flag trademarks, mark FOCUS picks."""
import math
import re
from datetime import date
from pathlib import Path

from src.db import save_discovered
from src.trademark import check as tm_check
from src.ytrends_client import top_keywords, trending, hidden_gems, top_listings

EMBROIDERY_SIGNS = ("embroider", "chenille", "monogram", "applique",
                    "stitch", "patch", "crochet", "knit")

# BUG-1 fix (V35.5): match embroidery signals on TOKEN / word boundaries, not
# raw substrings. Prefix-stems (embroider*, applique*, monogram*, crochet*,
# chenille*) still catch their inflections (embroidered, monogrammed, ...),
# while the short ambiguous roots (stitch, patch, knit) match as WHOLE WORDS
# only (+ simple plural) so "patchwork", "dispatch" and "knitting" no longer
# collide into the embroidery lane. "cross stitch", "embroidered patch", etc.
# are unaffected.
_EMB_STEMS = ("embroider", "applique", "monogram", "crochet", "chenille")
_EMB_WHOLE = ("stitch", "patch", "knit")
_EMB_RE = re.compile(
    r"\b(?:" + "|".join(_EMB_STEMS) + r")\w*"
    r"|\b(?:" + "|".join(_EMB_WHOLE) + r")(?:es|s)?\b",
    re.I,
)


def matches_mode(tag, mode):
    """mode: None (all) | 'pod' | 'embroidery'.

    Token/word-boundary match (NOT substring): 'patch' no longer matches
    'patchwork'/'dispatch' and 'knit' no longer matches 'knitting', while real
    embroidery terms (embroidered, monogram, cross stitch, applique ...) still
    route correctly.
    """
    if not mode:
        return True
    emb = bool(_EMB_RE.search(tag or ""))
    return emb if mode == "embroidery" else not emb


GENERIC_JUNK = {
    "newest", "new", "best seller", "bestseller", "popular", "trending",
    "sale", "gift", "gifts", "handmade", "custom", "personalized",
}


def load_niche_terms(path="niches.txt"):
    p = Path(path)
    if not p.exists():
        return []
    return [
        line.strip().lower()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def looks_like_shop_name(tag):
    t = tag.strip().lower()
    if " " in t:
        return False
    if re.search(r"(studio|shop|store|design|tees|og)$", t) and len(t) >= 6:
        return True
    return len(t) >= 12


def score(r):
    revenue = r.get("avg_revenue") or 0
    conv = r.get("avg_conversion_rate") or 0
    momentum = r.get("momentum_score") or r.get("gem_score") or 0
    comp = max(r.get("listing_count") or 1000, 10)
    return round(
        math.log10(revenue + 1) * (conv * 100) * (1 + momentum / 100) * 100 / comp,
        2,
    )


def demand_signal(r):
    """Best available 24h demand number: total views, else avg views x listings."""
    if r.get("total_views_24h"):
        return int(r["total_views_24h"])
    avg_v = r.get("avg_views_24h") or 0
    return int(avg_v * (r.get("listing_count") or 0))


SERVICE_TERMS = {
    "psychic", "tarot", "reading", "readings", "spell", "reiki", "medium",
    "astrology", "horoscope", "prediction", "predictions", "oracle",
    "manifestation", "twin flame", "same day", "advice", "chart",
}

PRODUCT_TERMS = {
    "shirt", "tee", "tshirt", "t-shirt", "hoodie", "sweatshirt", "crewneck",
    "sweater", "tank", "apparel", "mug", "tumbler", "cup", "bag", "tote",
    "pouch", "purse", "necklace", "bracelet", "ring", "earring", "earrings",
    "pendant", "charm", "jewelry", "keychain", "ornament", "sticker", "decal",
    "print", "poster", "canvas", "hat", "cap", "beanie", "apron", "blanket",
    "pillow", "towel", "mat", "sign", "patch", "embroidered", "embroidery",
    "socks", "pajamas", "onesie", "bodysuit", "bandana",
}


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def listing_relevance(keyword, listing):
    """Return (score, reason). Blocks unrelated winner listings from reports."""
    kw_tokens = _tokens(keyword)
    title_tokens = _tokens(listing.get("title") or "")
    tag_tokens = set()
    for t in listing.get("tags") or []:
        tag_tokens |= _tokens(t)

    product_overlap = (kw_tokens & PRODUCT_TERMS) & (title_tokens | tag_tokens)
    exact_overlap = kw_tokens & (title_tokens | tag_tokens)
    service_hit = (title_tokens | tag_tokens) & SERVICE_TERMS

    if service_hit and not product_overlap:
        return 0.0, "service/spell listing unrelated to physical product keyword"
    if product_overlap:
        return 1.0, "product noun overlaps keyword"
    if len(exact_overlap) >= max(1, min(2, len(kw_tokens))):
        return 0.75, "keyword words overlap listing title/tags"
    return 0.0, "no product or keyword overlap"


def sellable_as_product(x, niche_terms):
    """Can our POD/embroidery shop actually make this?"""
    words = set(x["tag"].split())
    if words & SERVICE_TERMS:
        return False
    return bool(words & PRODUCT_TERMS) or x["in_my_niche"]


def is_focus(x, niche_terms):
    """FOCUS = sellable + low competition + real daily demand + converts + safe."""
    # YTrends emits lowercase ('low'); == "LOW" never matched, so this clause was
    # dead and low_comp silently collapsed to the listing_count fallback alone.
    low_comp = (str(x["competition_level"] or "").strip().lower() == "low") or (
        (x["listing_count"] or 99999) <= 300
    )
    demand = (x["demand_24h"] or 0) >= 500
    converts = (x["conversion"] or 0) >= 0.02
    rising = (x["momentum"] or 0) >= 30 or (x["avg_revenue"] or 0) >= 2000
    safe = x["tm_risk"] != "HIGH"
    return (sellable_as_product(x, niche_terms) and low_comp and demand
            and converts and rising and safe)


def run_discover(mode=None):
    niche_terms = load_niche_terms()
    mode_label = {"pod": " (POD)", "embroidery": " (Embroidery/Theu)"}.get(mode, "")
    print(f"Pulling live YTrends data{mode_label}...")

    sources = [
        ("keywords", top_keywords()),
        ("trending", trending()),
        ("hidden_gems", hidden_gems()),
    ]

    seen, results, skipped = set(), [], 0
    for source, rows in sources:
        for r in rows:
            tag = (r.get("tag") or "").strip().lower()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            if tag in GENERIC_JUNK or looks_like_shop_name(tag) \
                    or not matches_mode(tag, mode):
                skipped += 1
                continue
            risk, reason = tm_check(tag)
            x = {
                "source": source,
                "tag": tag,
                "listing_count": r.get("listing_count"),
                "seller_count": r.get("seller_count"),
                "demand_24h": demand_signal(r),
                "avg_price": r.get("avg_price"),
                "avg_revenue": r.get("avg_revenue"),
                "conversion": r.get("avg_conversion_rate"),
                "momentum": r.get("momentum_score") or r.get("gem_score"),
                "competition_level": r.get("competition_level"),
                "action": (r.get("recommended_action") or "").split(":")[0],
                "opportunity": score(r),
                "tm_risk": risk,
                "tm_reason": reason,
                "in_my_niche": any(term in tag for term in niche_terms),
            }
            x["focus"] = is_focus(x, niche_terms)
            results.append(x)

    results.sort(key=lambda x: (not x["focus"], -x["opportunity"]))
    save_discovered([
        (x["source"], x["tag"], x["listing_count"], x["avg_price"],
         x["avg_revenue"], x["conversion"], x["momentum"],
         x["competition_level"], x["action"], x["opportunity"])
        for x in results
    ])

    focus = [x for x in results if x["focus"]]
    print(f"Fetching top listings for {min(len(focus), 8)} FOCUS keywords...")
    for x in focus[:8]:
        try:
            ls = top_listings(x["tag"])[:3]
        except Exception as exc:
            print(f"  listings failed for '{x['tag']}': {exc}")
            ls = []
        filtered, rejected = [], []
        for l in ls:
            rel, reason = listing_relevance(x["tag"], l)
            item = {
                "title": (l.get("title") or "")[:80],
                "price": l.get("price_usd"),
                "sold": l.get("total_sold"),
                "revenue": l.get("revenue_usd"),
                "age_days": l.get("listing_age_days"),
                "verdict": l.get("listing_verdict"),
                "url": f"https://www.etsy.com/listing/{l.get('listing_id')}",
                "tags": l.get("tags") or [],
                "relevance_score": rel,
                "relevance_reason": reason,
            }
            if rel >= 0.75:
                filtered.append(item)
            else:
                rejected.append(item)
        x["top_listings"] = filtered[:3]
        x["rejected_top_listings"] = rejected[:5]
        x["age_profile"] = age_profile(x["top_listings"])

    path = write_discover_report(results, skipped, mode_label)
    print(f"\nDone. {len(results)} keywords analyzed, {skipped} junk tags filtered.")
    print(f"FOCUS picks: {len(focus)}  |  Report: {path}\n")
    for i, x in enumerate(focus[:12], 1):
        flag = "" if x["tm_risk"] == "OK" else f"  [{x['tm_risk']}]"
        print(f"{i:2}. {x['tag']:<30} listings={x['listing_count']:<6} "
              f"sellers={x['seller_count'] or '?':<5} views24h={x['demand_24h']:<7} "
              f"conv={(x['conversion'] or 0)*100:.1f}%{flag}")
    return results


def age_bucket(days):
    if days is None:
        return "unknown"
    if days <= 7:
        return "1 week old"
    if days <= 14:
        return "2 weeks old"
    if days <= 90:
        return "under 3 months"
    return "over 3 months"


def age_profile(top_listings):
    """Newcomer-friendliness from the ages of the WINNING listings."""
    ages = [l.get("age_days") for l in top_listings
            if l.get("age_days") is not None]
    if not ages:
        return {"label": "AGE UNKNOWN", "buckets": {}}
    buckets = {}
    for a in ages:
        buckets[age_bucket(a)] = buckets.get(age_bucket(a), 0) + 1
    youngest = min(ages)
    if youngest <= 7:
        label = "FRESH WINNER (1-week-old listing already earning - "\
                "a NEW shop can rank here)"
    elif youngest <= 14:
        label = "NEWCOMER FRIENDLY (2-week-old listing among winners)"
    elif youngest <= 90:
        label = "OPEN (winner under 3 months old)"
    else:
        label = "ENTRENCHED (all winners are 3+ months old - hard for a "\
                "new shop)"
    return {"label": label, "buckets": buckets, "youngest": youngest}


def _table(rows):
    lines = [
        "| Focus | Từ khóa | Listing Etsy | Seller | Views 24h | Giá TB | Doanh thu TB | Conv. | Momentum | Rủi ro TM |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for x in rows:
        focus = "**YES**" if x["focus"] else ""
        tm = x["tm_risk"] if x["tm_risk"] != "OK" else "ok"
        if x["tm_risk"] == "HIGH":
            tm = f"**HIGH** ({x['tm_reason']})"
        elif x["tm_risk"] == "CAUTION":
            tm = "CAUTION - verify"
        lines.append(
            f"| {focus} | {x['tag']} | {x['listing_count']} | {x['seller_count'] or '?'} | "
            f"{x['demand_24h']} | ${x['avg_price']} | ${x['avg_revenue']} | "
            f"{(x['conversion'] or 0)*100:.1f}% | {x['momentum'] or '-'} | {tm} |"
        )
    return lines


def write_discover_report(results, skipped, mode_label=""):
    from src.report_paths import rdir
    path = rdir(date.today(), "discover") / f"discover_{date.today()}.md"

    focus = [x for x in results if x["focus"]]
    mine = [x for x in results if x["in_my_niche"] and not x["focus"]]
    other = [x for x in results if not x["in_my_niche"] and not x["focus"]][:20]

    lines = [f"# Báo cáo khám phá từ khóa{mode_label} - {date.today()}", ""]
    lines.append(f"_{len(results)} keywords analyzed, {skipped} junk/brand tags filtered._")
    lines += ["", "## FOCUS - ưu tiên thiết kế trước",
              "_Cạnh tranh thấp + nhu cầu thật + tỷ lệ mua tốt + không dính thương hiệu._", ""]
    lines += _table(focus) if focus else ["_None today. Check again tomorrow._"]
    with_listings = [x for x in focus if x.get("top_listings")]
    if with_listings:
        lines += ["", "## Listing bán chạy nhất theo từ khóa FOCUS (tham khảo thị trường - KHÔNG copy)", ""]
        fresh = [x for x in with_listings
                 if x.get("age_profile", {}).get("youngest", 999) <= 14]
        if fresh:
            lines.append("**Uu tien cho shop moi / Newcomer priority:** "
                         + ", ".join(x["tag"] for x in fresh)
                         + " - listing thang chi 1-2 tuan tuoi.")
            lines.append("")
        lines += [
            "| FOCUS keyword | # | Winning listing | Price | Sold | Revenue "
            "| Age | Newcomer signal |",
            "|---|---|---|---|---|---|---|---|"]
        tag_notes = []
        for x in with_listings:
            ap = x.get("age_profile") or {}
            signal = ap.get("label", "")
            for i, l in enumerate(x["top_listings"], 1):
                title = (l.get("title") or "").replace("|", "/").replace(
                    "[", "(").replace("]", ")")
                kw = x["tag"] if i == 1 else ""
                sig = signal if i == 1 else ""
                price = f"${l['price']}" if l.get("price") is not None else "-"
                sold = l["sold"] if l.get("sold") is not None else "-"
                rev = f"${l['revenue']}" if l.get("revenue") is not None else "-"
                age = f"{l['age_days']}d" if l.get("age_days") is not None else "?"
                lines.append(
                    f"| {kw} | {i} | [{title}]({l['url']}) | {price} | {sold} "
                    f"| {rev} | {age} | {sig} |")
            all_tags = [t for l in x["top_listings"] for t in l["tags"]]
            seen_t, common = set(), []
            for t in all_tags:
                tl = t.lower()
                if all_tags.count(t) >= 2 and tl not in seen_t:
                    seen_t.add(tl); common.append(t)
            if common:
                tag_notes.append(f"- **{x['tag']}**: {', '.join(common[:13])}")
        lines.append("")
        if tag_notes:
            lines += ["**Common tags among these winning listings** (reference "
                      "for your own tags - do NOT copy the designs):", *tag_notes,
                      ""]

    lines += ["", "## Ngách của bạn (theo dõi)", ""]
    lines += _table(mine) if mine else ["_No additional matches._"]
    lines += ["", "## Các từ khóa khác (ý tưởng mở rộng)", ""]
    lines += _table(other)
    lines += [
        "",
        "### Cách dùng báo cáo này",
        "- FOCUS rows meet all criteria: listings <= 300 (or LOW level),",
        "  500+ views/day or $1000+ avg revenue, conversion >= 2%, rising.",
        "- 'Etsy listings' = competing listings for that keyword.",
        "  'Sellers' = shops sharing them. Fewer sellers = weaker moat.",
        "- TM risk is a heuristic, NOT legal advice. Before designing:",
        "  HIGH = skip it. CAUTION = search the phrase at tmsearch.uspto.gov",
        "  (Basic search, 'Live' filter); if a live mark exists in class 025",
        "  (apparel) or your product class, skip it. Keyword safety does not",
        "  cover the design: never copy another shop's artwork.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    from src.lang import finalize_report
    finalize_report(path)
    return path
