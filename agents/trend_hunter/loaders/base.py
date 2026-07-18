"""
TrendLoader base — Vibe-Trading loader pattern adapted for 22etsy-agent.

Every data source (pytrends, Reddit, Pinterest, Firecrawl) implements this
interface. The registry walks a fallback chain ordered by cost/ban-risk:
free & never-banned sources first, paid (Firecrawl) last.

Rules enforced here:
- Failures are NON-FATAL: fetch() raises LoaderError, the chain continues.
- Every loader declares cost_per_call so the budget guard can enforce <$1/day.
- No Etsy scraping. Etsy data only via official API (not part of this chain).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


class LoaderError(Exception):
    """Raised by a loader on any failure. Registry catches it and moves on."""


@dataclass
class TrendSignal:
    """One piece of trend evidence from one source. Normalized shape —
    every loader must return this, so downstream agents never care
    which source the data came from."""

    trend_name: str
    source: str                     # loader name, e.g. "pytrends"
    momentum_score: float           # 0-100, source-local scoring
    evidence_urls: list[str] = field(default_factory=list)
    raw_notes: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "trend_name": self.trend_name,
            "source": self.source,
            "momentum_score": round(self.momentum_score, 1),
            "evidence_urls": self.evidence_urls,
            "raw_notes": self.raw_notes,
            "fetched_at": self.fetched_at.isoformat(),
        }


class TrendLoader(ABC):
    """Duck-typed loader contract (mirrors Vibe-Trading's DataLoaderProtocol)."""

    name: str = "base"              # value used in fallback chain config
    cost_per_call: float = 0.0      # USD; budget guard reads this
    requires_auth: bool = False

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap check: API key present? Library importable? Network OK?
        Must NEVER raise — return False on any doubt."""

    @abstractmethod
    def fetch(self, keyword: str, *, geo: str = "US") -> list[TrendSignal]:
        """Fetch trend signals for a keyword.
        Raise LoaderError on failure — the registry handles it."""
