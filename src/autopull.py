"""Auto-pull competitor feeds for the learning library — self-serve, no operator.

Both feeds come from the OFFICIAL YTrends MCP (never scraped from Etsy):

- pull_listings: young listings (<= max_age_days, default 3 months) that are
  ALREADY outperforming their niche. Ranked by the real signals that exist —
  performance_score, conversion_rate, views_24h, favorites, sold_24h. Etsy never
  exposes add-to-cart, so favorites + conversion are the closest public proxies.

- pull_shops: NEW shops already selling well. The feed has no shop-creation date,
  so we aggregate the fresh high-performer listings by shop_id and keep shops
  whose sampled listings are all recent (youngest & oldest under max_age_days,
  default 1 year) with real sales + high conversion. Ranked by conversion.
  Honestly labelled as *listing-age* based — it is a new-shop proxy, not a
  registration date.

Learning only: study structure + the gap they leave open, never copy artwork,
titles, descriptions, photos, or branding.
"""
from src import ytrends_mcp as mcp
from src.discover import matches_mode
from src.trademark import check as tm_check

# Seed keywords that keep the fresh-listing feed on-topic for each mode.
MODE_SEEDS = {
    "pod": ["shirt", "sweatshirt", "tote bag", "mug", "poster"],
    "embroidery": ["embroidered", "machine embroidery", "embroidered sweatshirt",
                   "embroidered hat"],
    "both": ["shirt", "embroidered", "sweatshirt", "tote bag"],
    None: ["shirt", "embroidered", "tote bag"],
}


def _num(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def listing_url(lid):
    """Public canonical Etsy listing URL (id-based) — for reference, not scraping."""
    return f"https://www.etsy.com/listing/{lid}" if lid else ""


def _pool(mode, target=60, country=None):
    """Fresh high-performer listings scoped to a product mode, deduped."""
    seen, pool = set(), []
    cc = (country or "").upper()
    real_mode = None if mode in (None, "both") else mode

    def take(rows):
        for r in rows:
            lid = r.get("listing_id") or r.get("id")
            if not lid or lid in seen:
                continue
            txt = f"{r.get('title', '')} {r.get('primary_tag', '')}".lower()
            if not matches_mode(txt, real_mode):
                continue
            if cc and (r.get("shop_country") or "").upper() != cc:
                continue
            seen.add(lid)
            pool.append(r)

    take(mcp.browse_new_listings(limit=target))
    for seed in MODE_SEEDS.get(mode, MODE_SEEDS["both"]):
        if len(pool) >= target:
            break
        take(mcp.browse_new_listings(limit=20, keyword=seed))
    return pool


# ---------------------------------------------------------------- listings ----
def pull_listings(mode=None, max_age_days=90, country=None, limit=20):
    """Young, high-performing listings to LEARN from (<= ~3 months old)."""
    out = []
    for r in _pool(mode, target=70, country=country):
        age = r.get("listing_age_days")
        if not isinstance(age, (int, float)) or age > max_age_days:
            continue
        title = (r.get("title") or "").strip()
        tag = (r.get("primary_tag") or "").strip()
        risk, _ = tm_check(f"{title} {tag}".lower())
        out.append({
            "listing_id": r.get("listing_id") or r.get("id"),
            "title": title[:140],
            "primary_tag": tag,
            "shop_id": r.get("shop_id"),
            "shop_country": r.get("shop_country"),
            "listing_age_days": int(age),
            "conversion_rate": _num(r.get("conversion_rate")),
            "views_24h": r.get("views_24h"),
            "favorites": r.get("favorites"),
            "sold_24h": r.get("sold_24h"),
            "performance_score": _num(r.get("performance_score")),
            "price_usd": r.get("price_usd") or r.get("price"),
            "outperforms_peers_on": r.get("outperforms_peers_on") or [],
            "peer_conversion_ratio": r.get("peer_conversion_ratio"),
            "peer_views_ratio": r.get("peer_views_ratio"),
            "peer_sales_ratio": r.get("peer_sales_ratio"),
            "image_url": r.get("image_url"),
            "url": listing_url(r.get("listing_id") or r.get("id")),
            "trademark": risk,
        })
    out.sort(key=lambda x: (x["performance_score"], x["conversion_rate"]),
             reverse=True)
    return out[:limit]


# ------------------------------------------------------------------- shops ----
def pull_shops(mode=None, max_age_days=365, min_sold=0.0, min_conv=0.02,
               country=None, limit=15):
    """NEW shops already selling well — aggregated from the fresh-winner feed."""
    groups = {}
    for r in _pool(mode, target=90, country=country):
        sid = r.get("shop_id")
        age = r.get("listing_age_days")
        if not sid or not isinstance(age, (int, float)):
            continue
        groups.setdefault(sid, []).append(r)

    shops = []
    for sid, rows in groups.items():
        ages = [x.get("listing_age_days") for x in rows
                if isinstance(x.get("listing_age_days"), (int, float))]
        if not ages or max(ages) > max_age_days:   # all sampled listings recent
            continue
        sold = sum(_num(x.get("sold_24h")) for x in rows)
        convs = [_num(x.get("conversion_rate")) for x in rows]
        avg_conv = sum(convs) / len(convs) if convs else 0.0
        if sold < min_sold or avg_conv < min_conv:
            continue
        revenue = sum(_num(x.get("price_usd") or x.get("price")) * _num(x.get("sold_24h"))
                      for x in rows)
        top = max(rows, key=lambda x: _num(x.get("performance_score")))
        risk, _ = tm_check((top.get("primary_tag") or "").lower())
        shops.append({
            "shop_id": sid,
            "shop_country": rows[0].get("shop_country"),
            "fresh_winners": len(rows),
            "youngest_age_days": int(min(ages)),
            "oldest_age_days": int(max(ages)),
            "sold_24h": round(sold, 1),
            "avg_conversion_rate": round(avg_conv, 4),
            "total_favorites": int(sum(_num(x.get("favorites")) for x in rows)),
            "total_views_24h": int(sum(_num(x.get("views_24h")) for x in rows)),
            "revenue_24h_est": round(revenue, 2),
            "top_tag": top.get("primary_tag"),
            "sample_titles": [(x.get("title") or "")[:70] for x in rows[:3]],
            "trademark": risk,
        })
    shops.sort(key=lambda x: (x["avg_conversion_rate"], x["sold_24h"]),
               reverse=True)
    return shops[:limit]


# --------------------------------------------------------------- rendering ----
def _pct(v):
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def listings_md(rows, mode=None):
    label = {"pod": "Print on Demand", "embroidery": "Embroidery"}.get(mode, "All lines")
    L = [f"# 📌 Listings to learn from — {label}", "",
         "_Young listings (≤ ~3 months) already **outperforming their niche**. "
         "Ranked by performance, conversion, views, favorites, sales. Add-to-cart "
         "is not in Etsy's public data — favorites + conversion stand in. Study "
         "structure + the gap, **never copy**._", ""]
    if not rows:
        return "\n".join(L + ["_No fresh high-performers matched right now — "
                              "try again later or widen the mode._"])
    L += ["| Listing | Age | CR | Views/day | Favs | Sold/day | Perf | Beats peers on | TM |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        beats = ", ".join(r.get("outperforms_peers_on") or []) or "-"
        L.append(f"| {r['title'][:52]} | {r['listing_age_days']}d "
                 f"| {_pct(r['conversion_rate'])} | {r.get('views_24h','-')} "
                 f"| {r.get('favorites','-')} | {r.get('sold_24h','-')} "
                 f"| {int(r['performance_score'])} | {beats} | {r['trademark']} |")
    return "\n".join(L)


def shops_md(rows, mode=None):
    label = {"pod": "Print on Demand", "embroidery": "Embroidery"}.get(mode, "All lines")
    L = [f"# 🏪 New shops already selling — {label}", "",
         "_Shops whose listings are all **recent (< 1 year)** and already **convert + "
         "sell**. There is no shop-registration date in the feed, so this is a "
         "*young-listing* proxy for a new shop. Ranked by conversion. Learn their "
         "structure, **never copy**._", ""]
    if not rows:
        return "\n".join(L + ["_No qualifying new shops right now — try again later._"])
    L += ["| Shop (id) | Country | Fresh winners | Youngest | Avg CR | Sold/day | Favs | Rev/day est | Top niche | TM |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['shop_id']} | {r.get('shop_country','-')} "
                 f"| {r['fresh_winners']} | {r['youngest_age_days']}d "
                 f"| {_pct(r['avg_conversion_rate'])} | {r['sold_24h']} "
                 f"| {r['total_favorites']} | ${r['revenue_24h_est']:,.0f} "
                 f"| {r.get('top_tag','-')} | {r['trademark']} |")
    return "\n".join(L)
