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
    for attempt in range(4):
        try:
            resp = requests.get(f"{BASE_URL}{path}", params=params,
                                headers=HEADERS, timeout=30)
        except requests.RequestException as exc:
            if attempt == 3:
                raise SystemExit(f"YTrends network error after 4 tries: {exc}")
            wait = 2 ** attempt * 5
            print(f"  network error ({exc}); retry in {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == 3:
                raise SystemExit(
                    f"YTrends returned {resp.status_code} after 4 tries. "
                    "Wait a while and rerun; your daily quota may be hit.")
            wait = 2 ** attempt * 10
            print(f"  HTTP {resp.status_code}; backing off {wait}s...")
            time.sleep(wait)
            continue
        break
    _last_call = time.time()

    used = resp.headers.get("X-Daily-Used")
    limit = resp.headers.get("X-Daily-Limit")
    if used and limit and limit.isdigit() and int(limit) > 0:
        if int(used) > int(limit) * 0.8:
            print(f"  WARNING: {used}/{limit} of today's YTrends quota used.")

    if resp.status_code == 401:
        raise SystemExit(AUTH_HELP)
    resp.raise_for_status()
    data = resp.json()
    cache_put(key, today, json.dumps(data))
    return data


def top_keywords(sort="revenue", limit=50):
    return _get("/keywords", {"sort": sort, "limit": limit}).get("data", [])


def trending(sort="momentum", limit=50):
    return _get("/trending", {"sort": sort, "limit": limit}).get("data", [])


def hidden_gems(sort="conversion", limit=50):
    return _get("/hidden-gems", {"sort": sort, "limit": limit}).get("data", [])


def top_listings(keyword, sort="revenue", limit=48):
    """Top Etsy listings for a keyword (from YTrends' database)."""
    return _get("/listings", {"keyword": keyword, "sort": sort, "limit": limit}).get("data", [])


def suggestions(tag, sort="relevance", limit=30):
    """Related keywords that co-occur with this tag."""
    from urllib.parse import quote
    return _get(f"/keywords/{quote(tag)}/suggestions", {"sort": sort, "limit": limit}).get("data", [])


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
