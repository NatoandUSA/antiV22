"""Cross-check a keyword's YTrends signal against OUTSIDE sources.

YTrends tells us what is moving *on Etsy*. This module adds a second opinion
from the wider web so the team can tell "real cross-platform demand" apart from
"Etsy-only blip". Three sources, in order of how easily they turn on:

  - Google Trends  -- works out of the box (pip install pytrends). Free, but
      unofficial + rate-limited, so we treat it as a DIRECTION signal, cache
      hard, and cross-check only a handful of top keywords per run.
  - Pinterest      -- the closest platform to Etsy buyers. Needs a Pinterest
      business app + PINTEREST_ACCESS_TOKEN in .env. Off until that exists.
  - X / Twitter    -- real-time buzz. Needs a paid X API + X_BEARER_TOKEN.
      Off until that exists.

Design rules: every source is OPTIONAL and NON-BLOCKING. A missing library,
missing token, rate-limit, or "no data" never crashes a report -- the source
just returns None and we note it as unavailable. Nothing here fabricates a
number: no data means we say so.
"""
import os
from datetime import date

from dotenv import load_dotenv

from src.db import cache_get, cache_put

load_dotenv()

PINTEREST_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip() or None
X_BEARER = os.getenv("X_BEARER_TOKEN", "").strip() or None

# Keep external calls small: only the strongest few keywords get cross-checked.
MAX_CROSSCHECK = 8


# --------------------------------------------------------------------------
# Google Trends (pytrends) -- the one that works with no setup.
# --------------------------------------------------------------------------

def _pytrends_available():
    try:
        import pytrends  # noqa: F401
        return True
    except Exception:
        return False


def google_trends_signal(keyword):
    """Direction of a keyword on Google over the last ~3 months (US).

    Returns dict(interest_now, momentum_pct, direction, rising) or a dict with
    a 'status' explaining why there's no number. Cached per day.
    """
    today = str(date.today())
    ckey = f"gtrends:{keyword.lower()}"
    hit = cache_get(ckey, today)
    if hit is not None:
        import json
        return json.loads(hit)

    if not _pytrends_available():
        return {"status": "disabled",
                "note": "run: pip install pytrends  (to enable Google Trends)"}

    import json
    result = {"status": "no_data",
              "note": "not indexed on Google Trends yet (Etsy-native / very "
                      "long-tail -- can mean you're early)"}
    try:
        from pytrends.request import TrendReq
        py = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        py.build_payload([keyword], timeframe="today 3-m", geo="US")
        df = py.interest_over_time()
        if df is not None and not df.empty and keyword in df:
            s = df[keyword]
            vals = [v for v in s.tolist() if isinstance(v, (int, float))]
            if vals and sum(vals) > 0:
                head = vals[: max(1, len(vals) // 4)]
                tail = vals[-max(1, len(vals) // 4):]
                base = (sum(head) / len(head)) or 1
                recent = sum(tail) / len(tail)
                mom = round((recent - base) / base * 100)
                result = {
                    "status": "ok",
                    "interest_now": int(vals[-1]),
                    "momentum_pct": mom,
                    "direction": ("rising" if mom > 15 else
                                  "falling" if mom < -15 else "flat"),
                    "rising": [],
                }
                try:
                    rq = py.related_queries().get(keyword) or {}
                    rising = rq.get("rising")
                    if rising is not None and not rising.empty:
                        result["rising"] = rising["query"].head(3).tolist()
                except Exception:
                    pass
    except Exception as exc:
        result = {"status": "error",
                  "note": f"Google Trends unreachable/rate-limited ({exc})"}

    cache_put(ckey, today, json.dumps(result))
    return result


# --------------------------------------------------------------------------
# Pinterest -- best Etsy-adjacent source. Credential-gated.
# --------------------------------------------------------------------------

def pinterest_signal(keyword):
    """Pinterest interest for a keyword. Requires PINTEREST_ACCESS_TOKEN.

    Returns None when not configured (with a reason available via status()).
    Uses Pinterest's trends keyword endpoint; fail-fast on a bad token.
    """
    if not PINTEREST_TOKEN:
        return None
    today = str(date.today())
    ckey = f"pinterest:{keyword.lower()}"
    hit = cache_get(ckey, today)
    if hit is not None:
        import json
        return json.loads(hit)

    import json
    import requests
    out = {"status": "no_data"}
    try:
        # Pinterest Trends API (business apps): keyword interest by region.
        r = requests.get(
            "https://api.pinterest.com/v5/trends/keywords/US/top/GROWING",
            headers={"Authorization": f"Bearer {PINTEREST_TOKEN}"},
            params={"limit": 50}, timeout=25)
        if r.status_code == 401:
            out = {"status": "auth_error",
                   "note": "token rejected (401) -- expired or invalid. The "
                           "'Production Limited' test tokens are short-lived; "
                           "regenerate PINTEREST_ACCESS_TOKEN and restart the app."}
        elif r.status_code == 403:
            out = {"status": "no_access",
                   "note": "token valid but no Trends API access (403). Trial read "
                           "scopes (pins/boards) can't read keyword trends -- request "
                           "Trends/full access on the app, or wait for trial approval."}
        elif r.ok:
            kws = {t.get("keyword", "").lower()
                   for t in (r.json().get("trends") or [])}
            out = {"status": "ok",
                   "on_growing_list": keyword.lower() in kws}
    except Exception as exc:
        out = {"status": "error", "note": f"Pinterest unreachable ({exc})"}
    cache_put(ckey, today, json.dumps(out))
    return out


# --------------------------------------------------------------------------
# X / Twitter -- real-time buzz. Paid, credential-gated.
# --------------------------------------------------------------------------

def x_signal(keyword):
    """Recent tweet volume for a keyword. Requires X_BEARER_TOKEN (paid API)."""
    if not X_BEARER:
        return None
    today = str(date.today())
    ckey = f"x:{keyword.lower()}"
    hit = cache_get(ckey, today)
    if hit is not None:
        import json
        return json.loads(hit)

    import json
    import requests
    out = {"status": "no_data"}
    try:
        r = requests.get(
            "https://api.twitter.com/2/tweets/counts/recent",
            headers={"Authorization": f"Bearer {X_BEARER}"},
            params={"query": f'"{keyword}" -is:retweet lang:en'}, timeout=25)
        if r.status_code in (401, 403):
            out = {"status": "auth_error",
                   "note": "X_BEARER_TOKEN rejected -- check your X API plan."}
        elif r.ok:
            total = r.json().get("meta", {}).get("total_tweet_count")
            out = {"status": "ok", "tweets_7d": total}
    except Exception as exc:
        out = {"status": "error", "note": f"X unreachable ({exc})"}
    cache_put(ckey, today, json.dumps(out))
    return out


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def status():
    """Which cross-check sources are live this run, and why."""
    g = ("live" if _pytrends_available()
         else "off (pip install pytrends)")
    p = "live" if PINTEREST_TOKEN else "off (set PINTEREST_ACCESS_TOKEN in .env)"
    x = "live" if X_BEARER else "off (set X_BEARER_TOKEN in .env; paid API)"
    return {"Google Trends": g, "Pinterest": p, "X / Twitter": x}


def confirm(keyword):
    """Combined cross-source read for one keyword. Non-blocking; each field is
    None/'unavailable' when that source is off."""
    return {
        "google": google_trends_signal(keyword),
        "pinterest": pinterest_signal(keyword),
        "x": x_signal(keyword),
    }


def confirm_many(keywords):
    """Cross-check the top MAX_CROSSCHECK keywords (rest are skipped to respect
    external rate limits). Returns {keyword: confirm(keyword)}."""
    out = {}
    for kw in list(keywords)[:MAX_CROSSCHECK]:
        out[kw] = confirm(kw)
    return out


if __name__ == "__main__":  # smoke test: py -m src.crosscheck "custom tote bag"
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("sources:", status())
    kw = sys.argv[1] if len(sys.argv) > 1 else "personalized tote bag"
    print(f"\n{kw!r} ->")
    for src, sig in confirm(kw).items():
        print(f"  {src}: {sig}")
