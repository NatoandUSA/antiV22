"""
Concrete loaders: pytrends, Reddit, Pinterest, Firecrawl.

Each is thin on purpose — real fetch logic stays inside fetch(), everything
else (retry, cache, budget, fallback) lives in the registry. To add a source
later (e.g. TikTok Creative Center), copy any class here, change name/fetch,
done. No other file changes except adding the name to FALLBACK_CHAIN.

Import this module once at startup so @register fires:
    from agents.trend_hunter.loaders import sources  # noqa: F401
"""

from __future__ import annotations

import os

from .base import LoaderError, TrendLoader, TrendSignal
from .registry import register


@register
class PytrendsLoader(TrendLoader):
    """Google Trends via pytrends. Free, no key. Most stable signal.
    Momentum = normalized slope of last 90 days interest."""

    name = "pytrends"
    cost_per_call = 0.0

    def is_available(self) -> bool:
        try:
            import pytrends  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, keyword: str, *, geo: str = "US") -> list[TrendSignal]:
        try:
            from pytrends.request import TrendReq

            py = TrendReq(hl="en-US", tz=0, timeout=(5, 15))
            py.build_payload([keyword], timeframe="today 3-m", geo=geo)
            df = py.interest_over_time()
            if df.empty:
                return []

            series = df[keyword]
            # momentum: recent-4-weeks mean vs prior-8-weeks mean, scaled 0-100
            recent = series.tail(28).mean()
            prior = series.head(len(series) - 28).mean() or 1.0
            momentum = max(0.0, min(100.0, 50.0 * (recent / prior)))

            return [TrendSignal(
                trend_name=keyword,
                source=self.name,
                momentum_score=momentum,
                evidence_urls=[f"https://trends.google.com/trends/explore?q={keyword.replace(' ', '%20')}&geo={geo}"],
                raw_notes=f"recent28d_mean={recent:.1f} prior_mean={prior:.1f}",
            )]
        except Exception as exc:
            raise LoaderError(f"pytrends: {exc}") from exc


@register
class RedditLoader(TrendLoader):
    """Reddit public JSON search. Free, no key needed for read-only search.
    Momentum = post volume + upvote velocity in craft/gift subreddits."""

    name = "reddit"
    cost_per_call = 0.0
    SUBREDDITS = ["Embroidery", "CrossStitch", "crafts", "gifts", "EtsySellers"]

    def is_available(self) -> bool:
        try:
            import requests  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, keyword: str, *, geo: str = "US") -> list[TrendSignal]:
        import requests

        signals: list[TrendSignal] = []
        headers = {"User-Agent": "22etsy-agent/1.0 (trend research)"}
        try:
            for sub in self.SUBREDDITS[:3]:  # cap requests per run
                url = (f"https://www.reddit.com/r/{sub}/search.json"
                       f"?q={keyword}&restrict_sr=1&sort=top&t=month&limit=10")
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 429:
                    raise LoaderError("reddit: rate limited")
                resp.raise_for_status()
                posts = resp.json().get("data", {}).get("children", [])
                if not posts:
                    continue
                total_ups = sum(p["data"].get("ups", 0) for p in posts)
                momentum = max(0.0, min(100.0, len(posts) * 5 + total_ups / 50))
                signals.append(TrendSignal(
                    trend_name=keyword,
                    source=self.name,
                    momentum_score=momentum,
                    evidence_urls=[
                        f"https://reddit.com{p['data'].get('permalink', '')}"
                        for p in posts[:3]
                    ],
                    raw_notes=f"r/{sub}: {len(posts)} posts, {total_ups} upvotes (30d)",
                ))
            return signals
        except LoaderError:
            raise
        except Exception as exc:
            raise LoaderError(f"reddit: {exc}") from exc


@register
class PinterestLoader(TrendLoader):
    """Pinterest Trends (trends.pinterest.com). No official free API —
    this checks the public trends endpoint. Expect this one to be the
    flakiest of the free tier; that is fine, the chain absorbs it."""

    name = "pinterest"
    cost_per_call = 0.0

    def is_available(self) -> bool:
        try:
            import requests  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch(self, keyword: str, *, geo: str = "US") -> list[TrendSignal]:
        import requests

        try:
            url = ("https://trends.pinterest.com/api/v1/trends/keyword_volume/"
                   f"?keywords={keyword}&country={geo}")
            resp = requests.get(url, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                raise LoaderError(f"pinterest: HTTP {resp.status_code}")
            data = resp.json()
            vols = (data.get("data") or [{}])[0].get("volumes", [])
            if not vols:
                return []
            recent = sum(v.get("normalizedCount", 0) for v in vols[-4:]) / 4
            prior = (sum(v.get("normalizedCount", 0) for v in vols[:-4])
                     / max(1, len(vols) - 4)) or 1.0
            momentum = max(0.0, min(100.0, 50.0 * (recent / prior)))
            return [TrendSignal(
                trend_name=keyword,
                source=self.name,
                momentum_score=momentum,
                evidence_urls=[f"https://trends.pinterest.com/?trends={keyword}"],
                raw_notes=f"recent4w={recent:.2f} prior={prior:.2f}",
            )]
        except LoaderError:
            raise
        except Exception as exc:
            raise LoaderError(f"pinterest: {exc}") from exc


@register
class FirecrawlLoader(TrendLoader):
    """Firecrawl — PAID, last in chain. Only fires when free sources
    return too little AND budget allows. Scrapes general trend articles
    (never Etsy.com). Cost estimate ~$0.01/scrape on starter credits."""

    name = "firecrawl"
    cost_per_call = 0.05   # conservative estimate: 5 pages per fetch

    # General craft/gift trend pages — NO Etsy URLs, per your hard rule.
    SEED_QUERIES = [
        "https://www.google.com/search?q={kw}+gift+trend+2026",
    ]

    def is_available(self) -> bool:
        return bool(os.getenv("FIRECRAWL_API_KEY"))

    def fetch(self, keyword: str, *, geo: str = "US") -> list[TrendSignal]:
        try:
            from firecrawl import FirecrawlApp

            app = FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])
            result = app.search(
                f"{keyword} gift trend rising 2026",
                limit=5,
            )
            items = getattr(result, "data", None) or result.get("data", [])
            if not items:
                return []
            urls = [it.get("url", "") for it in items if it.get("url")]
            # Firecrawl gives evidence, not volume — score is presence-based;
            # the Opportunity Scoring agent weighs it lower than pytrends.
            return [TrendSignal(
                trend_name=keyword,
                source=self.name,
                momentum_score=40.0,
                evidence_urls=urls[:5],
                raw_notes=f"{len(items)} web results for rising-trend query",
            )]
        except KeyError as exc:
            raise LoaderError("firecrawl: FIRECRAWL_API_KEY missing") from exc
        except Exception as exc:
            raise LoaderError(f"firecrawl: {exc}") from exc
