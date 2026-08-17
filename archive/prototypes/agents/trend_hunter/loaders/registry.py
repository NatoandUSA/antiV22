"""
Loader registry + fallback chain + daily budget guard.

Usage (this is the ONE call the Trend Hunter agent makes):

    from agents.trend_hunter.loaders.registry import get_trend_data

    signals = get_trend_data("pet portrait embroidery")   # walks the chain

Chain order = cost/ban-risk order (Vibe-Trading pattern):
    pytrends (free) -> reddit (free) -> pinterest (free) -> firecrawl (PAID, last)

Behavior:
- A source that fails or is unavailable is logged and skipped. Never fatal.
- Results ACCUMULATE across free sources (more evidence = better scoring).
- Paid sources (cost_per_call > 0) only fire if free sources returned nothing,
  AND the daily budget allows it.
- Same-day results per (keyword, source) are cached in Postgres, so re-runs
  cost zero.
"""

from __future__ import annotations

import logging
from datetime import date

from .base import LoaderError, TrendLoader, TrendSignal

log = logging.getLogger("trend_hunter.registry")

# ---------------------------------------------------------------- registry

_LOADERS: dict[str, TrendLoader] = {}

# Order matters: free & stable first, paid last. Edit here to re-order.
FALLBACK_CHAIN: list[str] = ["pytrends", "reddit", "pinterest", "firecrawl"]

DAILY_BUDGET_USD = 1.00   # hard cap, your rule


def register(cls: type[TrendLoader]) -> type[TrendLoader]:
    """Decorator: @register on a loader class adds an instance to the registry."""
    instance = cls()
    _LOADERS[instance.name] = instance
    return cls


# ---------------------------------------------------------------- budget

class BudgetGuard:
    """Tracks paid-API spend per calendar day. Fail-closed: if we can't
    verify budget, we do NOT spend. Persist via the spend_log table
    (see models.py) — this in-memory fallback covers single-process runs."""

    def __init__(self) -> None:
        self._day: date = date.today()
        self._spent: float = 0.0

    def _roll(self) -> None:
        if date.today() != self._day:
            self._day = date.today()
            self._spent = 0.0

    def can_spend(self, amount: float) -> bool:
        self._roll()
        return (self._spent + amount) <= DAILY_BUDGET_USD

    def record(self, amount: float) -> None:
        self._roll()
        self._spent += amount

    @property
    def spent_today(self) -> float:
        self._roll()
        return self._spent


budget = BudgetGuard()

# ---------------------------------------------------------------- cache hook

def _cache_get(keyword: str, source: str) -> list[TrendSignal] | None:
    """Look up same-day cached signals. Wire this to your Postgres
    trend_signal table:  WHERE keyword=:kw AND source=:src
                         AND fetched_at::date = CURRENT_DATE
    Return None on miss (or any DB error — cache must never break a run)."""
    try:
        from agents.trend_hunter import cache  # your SQLAlchemy-backed module
        return cache.get_today(keyword, source)
    except Exception:
        return None


def _cache_put(keyword: str, signals: list[TrendSignal]) -> None:
    try:
        from agents.trend_hunter import cache
        cache.put(keyword, signals)
    except Exception as exc:  # cache failure is never fatal
        log.warning("cache write failed: %s", exc)


# ---------------------------------------------------------------- main entry

def get_trend_data(
    keyword: str,
    *,
    geo: str = "US",
    chain: list[str] | None = None,
    min_free_signals: int = 3,
) -> list[TrendSignal]:
    """Walk the fallback chain for one keyword.

    Free sources: always tried (cheap evidence accumulation).
    Paid sources: only if free sources produced < min_free_signals
                  AND the daily budget allows it.
    """
    chain = chain or FALLBACK_CHAIN
    collected: list[TrendSignal] = []
    errors: dict[str, str] = {}

    for name in chain:
        loader = _LOADERS.get(name)
        if loader is None:
            errors[name] = "not registered"
            continue

        # Paid gate — the fail-closed check
        if loader.cost_per_call > 0:
            if len(collected) >= min_free_signals:
                log.info("skipping paid source %s: enough free signals", name)
                continue
            if not budget.can_spend(loader.cost_per_call):
                log.warning(
                    "skipping paid source %s: daily budget hit ($%.2f spent)",
                    name, budget.spent_today,
                )
                errors[name] = "budget exceeded"
                continue

        if not loader.is_available():
            errors[name] = "unavailable"
            log.info("source %s unavailable, walking chain", name)
            continue

        # Cache first — a same-day hit costs nothing
        cached = _cache_get(keyword, name)
        if cached:
            log.info("cache hit: %s / %s (%d signals)", keyword, name, len(cached))
            collected.extend(cached)
            continue

        try:
            signals = loader.fetch(keyword, geo=geo)
            if loader.cost_per_call > 0:
                budget.record(loader.cost_per_call)
            collected.extend(signals)
            _cache_put(keyword, signals)
            log.info("source %s returned %d signals", name, len(signals))
        except LoaderError as exc:
            errors[name] = str(exc)
            log.warning("source %s failed (non-fatal): %s", name, exc)
        except Exception as exc:  # unexpected bug in a loader: still non-fatal
            errors[name] = f"unexpected: {exc}"
            log.error("source %s crashed (non-fatal): %s", name, exc)

    if errors:
        log.info("chain summary for '%s': %d signals, errors=%s",
                 keyword, len(collected), errors)
    return collected


def chain_status() -> dict[str, dict]:
    """For your dashboard/health endpoint: which sources are alive right now."""
    return {
        name: {
            "registered": name in _LOADERS,
            "available": _LOADERS[name].is_available() if name in _LOADERS else False,
            "cost_per_call": getattr(_LOADERS.get(name), "cost_per_call", None),
        }
        for name in FALLBACK_CHAIN
    }
