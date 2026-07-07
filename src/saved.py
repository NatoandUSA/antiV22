"""Saved Shops + Saved Listings — a competitor-LEARNING library.

Team members save Etsy shops / listings they want to learn from and record a
structured analysis + scores over time. This is for market learning ONLY: the
tool never scrapes Etsy, and every view repeats the rule — study structure,
never copy artwork, titles, photos, branding, or trademarks; always create an
original angle. For a saved listing's main keyword we DO pull live market
context (via the MCP) and suggest an original idea from the gap.
"""
import json
from datetime import date
from pathlib import Path

SHOPS = Path("data/saved_shops.json")
LISTINGS = Path("data/saved_listings.json")

SHOP_STATUS = ["watching", "strong competitor", "inspiration", "avoid"]
LISTING_STATUS = ["inspiration", "competitor", "test idea", "avoid"]

SHOP_SCORES = ["SEO Pattern", "Photo Quality", "Product Focus",
               "Personalization", "Competitive Strength", "Learning Value"]
LISTING_SCORES = ["Title SEO", "Keyword", "Photo", "Description", "Pricing",
                  "Personalization", "Conversion", "Niche Opportunity",
                  "Differentiation", "Overall"]

SHOP_FRAMEWORK = [
    "Positioning & main product types", "Design style (what look repeats)",
    "Pricing pattern (low / mid / premium)", "Bestseller clues (badges, review counts)",
    "Listing quality & SEO title style", "Photo style (hero, lifestyle, mockup)",
    "Personalization strategy", "Shipping / processing promise",
    "Strengths to learn from (structurally)", "Weaknesses we can beat",
    "Opportunity gaps they leave open"]

LISTING_FRAMEWORK = [
    "Title SEO (keyword front-loaded? long-tail?)", "Main keyword + buyer intent",
    "Photo strength (hero + lifestyle + personalization)",
    "Description clarity & structure", "Pricing vs value",
    "Personalization offered", "Signals of conversion (reviews, sales)",
    "Niche opportunity & differentiation gap", "Weak points to beat"]

DO_NOT_COPY = ("Study structure, never the art. Do NOT copy their artwork, "
               "titles, descriptions, photos, branding, or trademarks. Always "
               "create an original design + your own copy.")


def _load(p):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return []


def _save(p, rows):
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def load_shops():
    return _load(SHOPS)


def load_listings():
    return _load(LISTINGS)


def _add(p, d):
    rows = _load(p)
    d["id"] = max([r.get("id", 0) for r in rows], default=0) + 1
    d["last_analyzed_at"] = str(date.today())
    rows.append(d)
    _save(p, rows)
    return d


def add_shop(d):
    return _add(SHOPS, d)


def add_listing(d):
    return _add(LISTINGS, d)


def delete_shop(sid):
    _save(SHOPS, [r for r in load_shops() if r.get("id") != sid])


def delete_listing(lid):
    _save(LISTINGS, [r for r in load_listings() if r.get("id") != lid])


def overall(scores):
    vals = [v for v in (scores or {}).values() if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals)) if vals else None


def listing_market_context(keyword):
    """Live market context for a saved listing's main keyword (via the MCP)."""
    if not keyword:
        return {}
    try:
        from src import ytrends_mcp as mcp
        rk = mcp.research_keyword(keyword)
        s = rk.get("stats", {}) if isinstance(rk, dict) else {}
        related = [(r.get("tag") or r.get("keyword") or r.get("title"))
                   for r in (rk.get("related_keywords") or [])[:6]]
        related = [r for r in related if r]
        idea = None
        if related:
            idea = (f"Original angle: pair '{related[0]}' with a personalization "
                    f"(name/date) the saved listing lacks — same demand, your own design.")
        return {"listings": s.get("total_listings"),
                "sellers": s.get("total_sellers"),
                "avg_price": s.get("avg_price"),
                "conversion": s.get("avg_conversion_rate"),
                "related": related, "original_idea": idea}
    except Exception:  # noqa: BLE001
        return {}
