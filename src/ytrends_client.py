"""YTrends API client -- endpoints discovered from your own browser session.

Politeness rules built in (do not remove):
- Responses are cached in SQLite for the whole day: repeat runs cost 0 quota.
- Max 1 request per second.
- Warns when past 80% of your X-Daily-Limit quota.
"""
import json
import os
import time
from datetime import date

import requests
from dotenv import load_dotenv

from src.db import cache_get, cache_put
from src.ytrends_mcp import YTrendsApiError

load_dotenv()

BASE_URL = "https://trends.ytuong.ai/api"
API_TOKEN = os.getenv("YTRENDS_API_TOKEN")
COOKIE = os.getenv("YTRENDS_COOKIE")

HEADERS = {
    "accept": "application/json",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "referer": "https://trends.ytuong.ai/en",
}
if API_TOKEN:
    HEADERS["authorization"] = f"Bearer {API_TOKEN}"
    HEADERS["x-api-key"] = API_TOKEN
if COOKIE:
    HEADERS["cookie"] = COOKIE

AUTH_HELP = """
401 Unauthorized from YTrends. Fix (takes 1 minute):
  1. Open trends.ytuong.ai logged in. Press F12 -> Network tab -> refresh.
  2. Click the request named 'keywords'. In Headers, scroll to
     'Request Headers' and copy the FULL value of the 'cookie:' line.
  3. In your .env file add:  YTRENDS_COOKIE=<paste it here>
  4. Run the command again. (Cookies expire after a while -- if 401
     returns someday, just re-copy it.)
Never share the cookie or .env with anyone; it is your login session.
"""

_last_call = 0.0


def _get(path, params):
    global _last_call
    key = f"{path}?{json.dumps(params, sort_keys=True)}"
    today = str(date.today())

    cached = cache_get(key, today)
    if cached:
        return json.loads(cached)

    wait = 1.0 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)

    resp = None
    # (connect, read) timeout + 2 tries: fail fast when the API is unreachable
    # so web pages degrade to honest-nulls instead of freezing for minutes.
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            resp = requests.get(f"{BASE_URL}{path}", params=params,
                                headers=HEADERS, timeout=(4, 15))
        except requests.RequestException as exc:
            if attempt == max_attempts - 1:
                raise YTrendsApiError(f"YTrends network error after {max_attempts} tries: {exc}")
            print("  network error; retry in 2s...")
            time.sleep(2)
            continue
        if resp is not None and (resp.status_code == 429 or resp.status_code >= 500):
            if attempt == max_attempts - 1:
                raise YTrendsApiError(
                    f"YTrends returned {resp.status_code} after {max_attempts} tries. "
                    "Wait a while and rerun; your daily quota may be hit.")
            wait = 2 ** attempt * 2
            print(f"  HTTP {resp.status_code}; backing off {wait}s...")
            time.sleep(wait)
            continue
        break
    _last_call = time.time()

    used = resp.headers.get("X-Daily-Used") if resp is not None else None
    limit = resp.headers.get("X-Daily-Limit") if resp is not None else None
    if used and limit and limit.isdigit() and int(limit) > 0:
        if int(used) > int(limit) * 0.8:
            print(f"  WARNING: {used}/{limit} of today's YTrends quota used.")

    if resp is not None and resp.status_code in (401, 403):
        raise YTrendsApiError(AUTH_HELP)
    if resp is not None:
        resp.raise_for_status()
    data = resp.json()
    cache_put(key, today, json.dumps(data))
    return data


# ---------------------------------------------------------------------------
# MCP-first data. The functions below prefer the official YTrends MCP (which is
# reachable everywhere, including the VPS, and needs no cookie) and fall back to
# this legacy REST endpoint only if the MCP is unavailable. That lets the whole
# report pipeline run server-side on the VPS with no laptop in the loop.
# ---------------------------------------------------------------------------

def _mcp():
    from src import ytrends_mcp as m
    return m


def _kw_row(r):
    """Map an MCP tag row to the legacy keyword-row shape callers expect."""
    def pick(*ks):
        for k in ks:
            if r.get(k) is not None:
                return r[k]
        return None
    return {
        "tag": r.get("tag"),
        "listing_count": pick("listing_count", "listings"),
        "seller_count": pick("seller_count", "sellers"),
        "avg_price": pick("avg_price", "avg_price_usd"),
        "avg_revenue": r.get("avg_revenue"),
        "avg_conversion_rate": r.get("avg_conversion_rate"),
        "momentum_score": pick("momentum_score", "target_score"),
        "gem_score": pick("gem_score", "opportunity_score"),
        "competition_level": r.get("competition_level"),
        "total_views_24h": r.get("total_views_24h"),
        "avg_views_24h": r.get("avg_views_24h"),
        "rank_change_7d": r.get("rank_change_7d"),
        "first_seen_date": r.get("first_seen_date"),
        "recommended_action": r.get("recommended_action") or r.get("action_reason"),
        "action_reason": r.get("action_reason"),
    }


def _listing_row(r):
    return {
        "title": r.get("title"), "price": r.get("price"),
        "revenue": r.get("revenue"), "avg_revenue": r.get("revenue"),
        "tags": r.get("tags"), "total_sold": r.get("total_sold"),
        "sold_24h": r.get("sold_24h"), "conversion_rate": r.get("conversion_rate"),
        "favorites": r.get("favorites"), "views": r.get("views"),
        "listing_id": r.get("listing_id"), "shop_country": r.get("shop_country"),
    }


def _sugg_row(r):
    return {
        "tag": r.get("tag") or r.get("keyword") or r.get("title"),
        "relevance_score": r.get("relevance_score") or r.get("momentum_score") or 1.0,
        "tag_listing_count": r.get("listing_count") or r.get("listings")
                             or r.get("total_listings"),
        "avg_revenue": r.get("avg_revenue"),
        "avg_conversion_rate": r.get("avg_conversion_rate") or r.get("conversion"),
        "recommended_action": r.get("recommended_action") or "",
    }


def _rest(path, params):
    try:
        return _get(path, params).get("data", [])
    except (SystemExit, Exception):     # noqa: BLE001 - never crash the build
        return []


def top_keywords(sort="revenue", limit=50):
    try:
        rows = _mcp().trending_keywords(limit=limit)
        if rows:
            return [_kw_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return _rest("/keywords", {"sort": sort, "limit": limit})


def trending(sort="momentum", limit=50):
    try:
        rows = _mcp().trending_keywords(limit=limit)
        if rows:
            return [_kw_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return _rest("/trending", {"sort": sort, "limit": limit})


def hidden_gems(sort="conversion", limit=50):
    try:
        rows = _mcp().scout_opportunities(limit=limit)
        if rows:
            return [_kw_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return _rest("/hidden-gems", {"sort": sort, "limit": limit})


def top_listings(keyword, sort="revenue", limit=48):
    """Top Etsy listings for a keyword (MCP first, legacy REST fallback)."""
    try:
        rows = _mcp().hot_listings(keyword=keyword, limit=min(limit, 40))
        if rows:
            return [_listing_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return _rest("/listings", {"keyword": keyword, "sort": sort, "limit": limit})


def suggestions(tag, sort="relevance", limit=30):
    """Related keywords for a tag (MCP first, legacy REST fallback)."""
    try:
        rk = _mcp().research_keyword(tag)
        rel = rk.get("related_keywords") if isinstance(rk, dict) else None
        if not rel:
            en = _mcp().call("ytrends_explore_niche", seed=tag)
            rel = (en.get("data", {}) or {}).get("adjacent_tags")
        if rel:
            return [_sugg_row(r) for r in rel][:limit]
    except Exception:  # noqa: BLE001
        pass
    from urllib.parse import quote
    return _rest(f"/keywords/{quote(tag)}/suggestions",
                 {"sort": sort, "limit": limit})


def categories(sort="revenue", limit=30):
    """Etsy category-level market stats."""
    return _get("/categories", {"sort": sort, "limit": limit}).get("data", [])


def probe(timeout=8):
    """Quick connectivity check: one request, no retries. Never hangs."""
    try:
        resp = requests.get(f"{BASE_URL}/keywords",
                            params={"sort": "revenue", "limit": 1},
                            headers=HEADERS, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False
