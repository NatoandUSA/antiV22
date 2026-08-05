"""YTrends MCP client -- talks to the OFFICIAL YTrends MCP server over HTTP.

This is the modern, supported data source (replacing the old reverse-engineered
REST client in src/ytrends_client.py). It speaks the MCP "streamable HTTP"
protocol directly from plain Python -- no Claude/LLM needed at runtime -- so the
batch team dashboard can pull the newest YTrends surfaces (trending keywords,
hidden gems, hot listings, market snapshot, seasonal calendar).

Server: https://mcp.trends.ytuong.ai/mcp   (see https://github.com/YTuong/ytrends-skills)

Politeness + safety rules (do NOT remove):
- Results are cached in SQLite for the whole day: repeat runs cost 0 quota.
- Max 1 request per second.
- FAIL-FAST probe guard: on first use we verify the server is reachable and the
  tools we depend on still exist. If the API changed, we stop with a clear
  message instead of silently producing wrong numbers (same philosophy as the
  probe guards in src/ytrends_client.py).
- An API token is OPTIONAL. The server currently answers without one; if you set
  YTRENDS_API_TOKEN in .env it is sent as a bearer token (raises your limits).
"""
import json
import os
import threading
import time
from datetime import date

import requests
from dotenv import load_dotenv

from src.db import cache_get, cache_put

load_dotenv()

MCP_URL = os.getenv("YTRENDS_MCP_URL", "https://mcp.trends.ytuong.ai/mcp").strip()
API_TOKEN = os.getenv("YTRENDS_API_TOKEN", "").strip()
# Placeholder from .env.example should never be treated as a real token.
if API_TOKEN in ("", "your_ytrends_api_token"):
    API_TOKEN = None

PROTOCOL_VERSION = "2025-06-18"

# The tools this codebase depends on. If the server ever drops one, the probe
# guard stops the run with a clear message rather than shipping a blank report.
REQUIRED_TOOLS = {
    "ytrends_market_snapshot",
    "ytrends_find_trending_keywords",
    "ytrends_find_hidden_gems",
    "ytrends_find_hot_listings",
    "ytrends_trend_calendar",
}

CHANGED_HELP = """
The YTrends MCP server responded, but the tools we rely on are missing or
renamed: {missing}
This usually means YTrends changed their API. Re-check the tool list at
https://github.com/YTuong/ytrends-skills (or open {url} ) and update
REQUIRED_TOOLS / the helper calls in src/ytrends_mcp.py. Reports that need live
YTrends data are skipped until this is fixed -- no guessed numbers are shipped.
"""

_session_id = None      # MCP session, established once per process
_tool_names = None      # cached tools/list result
_last_call = 0.0
# The web app is multi-threaded (Flask serves requests concurrently) and the
# warm job can fan out across surfaces, so the throttle + session bookkeeping
# below is shared across threads. This lock serialises the rate-limit slot and
# the one-time session init; threads still overlap on the actual network wait
# (the lock is released before the POST), so concurrency stays polite AND fast.
_lock = threading.RLock()   # reentrant: session-init holds it while _post issues
_next_slot = 0.0        # earliest time the next request may be ISSUED


def _throttle_slot():
    """Reserve the next >=1s-apart request slot atomically, then sleep to it
    OUTSIDE the lock. N threads each get a distinct slot (so issue-rate stays
    <=1/s, polite) while their responses overlap (so a fan-out is faster)."""
    global _next_slot
    with _lock:
        start = max(time.time(), _next_slot)
        _next_slot = start + 1.0
    wait = start - time.time()
    if wait > 0:
        time.sleep(wait)


class YTrendsMCPError(RuntimeError):
    """Raised when a tool call comes back as an MCP error."""


def _headers():
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
        h["x-api-key"] = API_TOKEN
    if _session_id:
        h["Mcp-Session-Id"] = _session_id
    return h


def _parse(resp):
    """MCP streamable HTTP answers as JSON or as SSE (text/event-stream).

    Decode as UTF-8 explicitly: requests defaults text/* to ISO-8859-1 when the
    server omits a charset, which turns em-dashes etc. into mojibake."""
    raw = resp.content.decode("utf-8", "replace")
    if "text/event-stream" in resp.headers.get("content-type", ""):
        last = None
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    last = json.loads(line[5:].strip())
                except ValueError:
                    pass
        return last
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _post(method, params, notify=False):
    """One JSON-RPC POST with 1 req/s politeness + backoff on 429/5xx."""
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notify:
        body["id"] = 1

    _throttle_slot()

    resp = None
    # (connect, read) timeout + 2 tries: an unreachable MCP fails a call in
    # ~12s instead of freezing a page for minutes (audited: 4 tries x 45s +
    # exponential backoff stacked to 3.5 min PER CALL on pages that make many).
    for attempt in range(2):
        try:
            resp = requests.post(MCP_URL, headers=_headers(), json=body,
                                 timeout=(4, 15))
        except requests.RequestException as exc:
            if attempt == 1:
                raise SystemExit(
                    f"YTrends MCP network error after 2 tries: {exc}\n"
                    f"Is {MCP_URL} reachable from this machine?")
            time.sleep(2)
            continue
        if resp.status_code in (429,) or resp.status_code >= 500:
            if attempt == 3:
                raise SystemExit(
                    f"YTrends MCP returned {resp.status_code} after 4 tries. "
                    "Wait a bit and rerun.")
            time.sleep(2 ** attempt * 6)
            continue
        break

    if resp.status_code in (401, 403):
        raise SystemExit(
            f"YTrends MCP refused the request (HTTP {resp.status_code}). "
            "If a token is required now, add YTRENDS_API_TOKEN to .env "
            "(get it from your trends.ytuong.ai account).")
    return resp


def _ensure_session():
    """Initialize the MCP session once, then run the fail-fast probe guard."""
    global _session_id, _tool_names
    if _tool_names is not None:
        return
    with _lock:
        if _tool_names is not None:      # another thread won the race
            return
        _init_session_locked()


def _init_session_locked():
    global _session_id, _tool_names
    init = _post("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "etsy-agent", "version": "1.0"},
    })
    _session_id = (init.headers.get("Mcp-Session-Id")
                   or init.headers.get("mcp-session-id"))
    _post("notifications/initialized", {}, notify=True)

    listing = _parse(_post("tools/list", {}))
    tools = ((listing or {}).get("result") or {}).get("tools") or []
    _tool_names = {t.get("name") for t in tools}

    missing = REQUIRED_TOOLS - _tool_names
    if missing:
        raise SystemExit(CHANGED_HELP.format(missing=sorted(missing),
                                             url=MCP_URL))


def _reset_session():
    """Drop the cached MCP session so the next call re-runs `initialize`. The MCP
    session expires server-side after idle time; a long-running dashboard would
    otherwise keep sending a dead session id and get 'Mcp-Session-Id required'."""
    global _session_id, _tool_names
    _session_id = None
    _tool_names = None


def call(tool, cache=True, response_format="concise", skip_bad=False,
         refresh=False, **arguments):
    """Call an MCP tool, return the parsed payload dict. Cached per day.

    skip_bad=True: when a page fails the server's OWN output validation (a poison
    row, e.g. tier=0), cache an EMPTY payload under the same key and return it
    instead of raising. That makes the failure cacheable, so a pre-warmed page
    load is a cache hit next time rather than a repeated live re-fetch+re-fail.

    refresh=True: skip the cache READ (force a live fetch) but still WRITE the
    result, so a scheduled warm --fresh pulls current data and overwrites the
    day's cache instead of returning this morning's copy."""
    if response_format and "response_format" not in arguments:
        arguments["response_format"] = response_format
    today = str(date.today())
    key = f"mcp:{tool}:{json.dumps(arguments, sort_keys=True)}"

    if cache and not refresh:
        hit = cache_get(key, today)
        if hit is not None:
            return json.loads(hit)

    def _bad(msg):
        if skip_bad and "validation" in msg.lower():
            if cache:
                cache_put(key, today, json.dumps({}))
            return True
        return False

    _ensure_session()
    resp = _post("tools/call", {"name": tool, "arguments": arguments})
    parsed = _parse(resp)

    # The MCP session expires server-side; this process caches it, so a
    # long-running dashboard eventually gets "Mcp-Session-Id ... required" (or an
    # invalid-session error). Re-establish the session once and retry before
    # giving up, so the workspace build recovers on its own instead of erroring.
    if parsed and parsed.get("error") \
            and "session" in json.dumps(parsed["error"]).lower():
        _reset_session()
        _ensure_session()
        resp = _post("tools/call", {"name": tool, "arguments": arguments})
        parsed = _parse(resp)

    result = (parsed or {}).get("result") or {}

    if parsed and parsed.get("error"):
        msg = json.dumps(parsed["error"])
        if _bad(msg):
            return {}
        raise YTrendsMCPError(f"{tool}: {msg[:300]}")

    content = result.get("content") or []
    text = content[0].get("text", "") if content else ""
    if result.get("isError"):
        if _bad(text):
            return {}
        raise YTrendsMCPError(f"{tool}: {text[:300]}")

    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {"_raw": text}

    # Cache REAL answers only. The cache key is (request, DAY), so caching an
    # empty result pins that emptiness until midnight: one MCP hiccup at 09:00
    # blanks Trending/Gems/Opportunities for the rest of the working day, and it
    # looks like "no data" rather than "the call failed". Measured in the live
    # data/agent.db: 65 of 535 cached rows were empty payloads, including
    # offset-0 pages that plainly should have returned rows.
    # The deliberate exception stays untouched: _bad() still caches {} for a
    # VALIDATION error, because that request is known-bad and retrying it all day
    # is the waste this cache exists to prevent.
    if cache and data not in ({}, [], None):
        cache_put(key, today, json.dumps(data))
    return data


def available():
    """(ok, message) -- safe to call anywhere (never raises). Used to decide
    whether to include live-YTrends sections in a report or selftest."""
    try:
        _ensure_session()
        return True, f"YTrends MCP OK ({len(_tool_names)} tools)"
    except SystemExit as exc:
        return False, str(exc).strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001 - never let this break a report
        return False, f"YTrends MCP unavailable: {exc}"


# ----------------------------------------------------------------------------
# Typed helpers. Each returns clean Python (list/dict); the report builders
# decide how to render and filter (e.g. POD vs embroidery) on top of these.
# ----------------------------------------------------------------------------

def _rows(payload, key):
    d = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(d, dict):
        return d.get(key) or []
    return []


def _list_call(tool, key, limit, **args):
    """Some YTrends tools intermittently fail their OWN output validation on a
    bad record at higher limits (e.g. a tier=0 row). Retry with progressively
    smaller limits so one bad row doesn't cost us the whole list."""
    attempts = []
    for n in (limit, 24, 15, 8, 5):
        if n and n not in attempts and n <= limit:
            attempts.append(n)
    last = None
    for lim in attempts:
        try:
            return _rows(call(tool, limit=lim, **args), key)
        except YTrendsMCPError as exc:
            if "validation" in str(exc).lower():
                last = exc
                continue
            raise
    if last:
        raise last
    return []


def _gather(tool, key, limit, step=10, refresh=False, **args):
    """These surfaces CAP each call at ~10 rows and IGNORE a big `limit` (the
    server pages its data), so asking for 90 still returns 10. We walk `offset`
    to collect up to `limit`, dedup by tag, and stop as soon as a page adds
    nothing new (end of data). Every page is cached per day, so repeat loads are
    free. Mirrors the pagination already used by browse_new_listings.

    Robustness: some pages contain a record that fails the server's OWN output
    schema (e.g. a tier=0 row) -> the whole page errors. We walk FIXED offsets and
    use skip_bad so a poison page is cached as empty and skipped (losing ~10 rows
    of that band, but keeping the walk deterministic + fully cacheable — vital so
    a pre-warmed page loads from cache instead of re-fetching). A few extra pages
    compensate for skipped bands; several empties in a row = real end-of-data."""
    out, seen = [], set()
    max_pages = (limit + step - 1) // step + 4
    empties = 0
    for i in range(max_pages):
        rows = _rows(call(tool, limit=step, offset=i * step, skip_bad=True,
                          refresh=refresh, **args), key)
        if not rows:
            empties += 1
            if empties >= 3:           # 3 blank pages running = end of data
                break
            continue
        empties = 0
        for r in rows:
            tg = (r.get("tag") or "").strip().lower()
            if tg and tg in seen:
                continue
            if tg:
                seen.add(tg)
            out.append(r)
        if len(out) >= limit:
            break
    return out[:limit]


def market_snapshot(country=None):
    p = call("ytrends_market_snapshot",
             **({"country": country} if country else {}))
    return p.get("data", p) if isinstance(p, dict) else {}


def trending_keywords(limit=25, search=None, refresh=False):
    args = {"search": search} if search else {}
    return _gather("ytrends_find_trending_keywords", "tags", limit,
                   refresh=refresh, **args)


def hidden_gems(limit=25, search=None, refresh=False):
    args = {"search": search} if search else {}
    return _gather("ytrends_find_hidden_gems", "tags", limit,
                   refresh=refresh, **args)


def hot_listings(limit=15, keyword=None, search=None):
    args = {}
    if keyword:
        args["keyword"] = keyword
    if search:
        args["search"] = search
    return _list_call("ytrends_find_hot_listings", "listings", limit, **args)


def trend_calendar(window="next_90d", limit=15):
    return _rows(call("ytrends_trend_calendar", window=window, limit=limit),
                 "events")


def scout_opportunities(limit=25, refresh=False, **filters):
    return _gather("ytrends_scout_opportunities", "results", limit,
                   refresh=refresh, **filters)


def browse_new_listings(limit=50, keyword=None, search=None):
    """Fresh, high-performing NEW listings (young + already outperforming peers).

    Each row carries listing_age_days, conversion_rate, views_24h, favorites,
    sold_24h, performance_score, outperforms_peers_on, peer_*_ratio, shop_id,
    shop_country, primary_tag, price_usd, image_url. The server pages ~10 rows
    at a time, so we paginate with offset to gather up to `limit`. keyword= gives
    a tightly-scoped niche; search= is broader. Deduped by listing_id."""
    step = 10
    out, seen = [], set()
    for i in range((limit + step - 1) // step):
        args = {"offset": i * step}
        if keyword:
            args["keyword"] = keyword
        if search:
            args["search"] = search
        try:
            rows = _list_call("ytrends_browse_new_listings", "listings", step, **args)
        except YTrendsMCPError:
            break
        added = 0
        for r in rows:
            lid = r.get("listing_id") or r.get("id")
            if lid in seen:
                continue
            seen.add(lid)
            out.append(r)
            added += 1
        if added == 0 or len(out) >= limit:
            break
    return out[:limit]


def analyze_competition(seed, seed_type="keyword"):
    """Niche competition snapshot: top_shops (revenue/listings/country),
    saturation, new_entrant_rate, avg_listing_age_days, seller_concentration."""
    p = call("ytrends_analyze_competition", seed=seed, seed_type=seed_type)
    return p.get("data", p) if isinstance(p, dict) else {}


def browse_rankings(mode="top", limit=50, offset=0, **filters):
    """Rank-based discovery surface. mode='top' (highest ranked) or 'new'.
    total is in the hundreds of thousands, so paginate with offset. Each entry
    has tag, rank, tier, target_score, rank_change_*d, listing_count."""
    return _list_call("ytrends_browse_rankings", "entries", limit,
                      mode=mode, offset=offset, **filters)


def search(query, limit=25, kinds=None):
    """Unified search across keywords/listings/categories. Great for pulling
    keywords that contain a seed term (e.g. every 'embroidered ...' keyword)."""
    args = {"query": query, "limit": limit}
    if kinds:
        args["kinds"] = kinds
    return _rows(call("ytrends_search", **args), "results")


def research_keyword(keyword, days=30):
    p = call("ytrends_research_keyword", keyword=keyword, days=days)
    return p.get("data", p) if isinstance(p, dict) else {}


if __name__ == "__main__":  # quick manual smoke test: py -m src.ytrends_mcp
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ok, msg = available()
    print(msg)
    if ok:
        snap = market_snapshot().get("overview", {})
        print("listings:", snap.get("total_listings"),
              "avg_price:", snap.get("avg_price"))
        for t in trending_keywords(limit=5):
            print(f"  TREND  {t.get('tag'):<28} momentum={t.get('momentum_score')} "
                  f"comp={t.get('competition_level')} rank={t.get('rank')}")
        for g in hidden_gems(limit=5):
            print(f"  GEM    {g.get('tag'):<28} gem_score={g.get('gem_score')} "
                  f"conv={g.get('avg_conversion_rate')}")
