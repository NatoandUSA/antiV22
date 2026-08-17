"""
Postgres same-day cache for trend signals (SQLAlchemy).

Add TrendSignalRow to your existing models.py / Base, then run a migration.
Cache misses and DB errors return None/no-op — cache must never break a run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Session

from db import Base, SessionLocal  # adjust import to your project layout
from .loaders.base import TrendSignal

log = logging.getLogger("trend_hunter.cache")


class TrendSignalRow(Base):
    __tablename__ = "trend_signals"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(200), index=True, nullable=False)
    trend_name = Column(String(200), nullable=False)
    source = Column(String(50), index=True, nullable=False)
    momentum_score = Column(Float, nullable=False)
    evidence_urls = Column(JSON, default=list)
    raw_notes = Column(String(2000), default="")
    fetched_at = Column(DateTime(timezone=True), index=True,
                        default=lambda: datetime.now(timezone.utc))


def get_today(keyword: str, source: str) -> list[TrendSignal] | None:
    try:
        with SessionLocal() as s:  # type: Session
            rows = (
                s.query(TrendSignalRow)
                .filter(
                    TrendSignalRow.keyword == keyword,
                    TrendSignalRow.source == source,
                    func.date(TrendSignalRow.fetched_at) == func.current_date(),
                )
                .all()
            )
        if not rows:
            return None
        return [
            TrendSignal(
                trend_name=r.trend_name,
                source=r.source,
                momentum_score=r.momentum_score,
                evidence_urls=r.evidence_urls or [],
                raw_notes=r.raw_notes or "",
                fetched_at=r.fetched_at,
            )
            for r in rows
        ]
    except Exception as exc:
        log.warning("cache read failed: %s", exc)
        return None


def put(keyword: str, signals: list[TrendSignal]) -> None:
    if not signals:
        return
    try:
        with SessionLocal() as s:
            for sig in signals:
                s.add(TrendSignalRow(
                    keyword=keyword,
                    trend_name=sig.trend_name,
                    source=sig.source,
                    momentum_score=sig.momentum_score,
                    evidence_urls=sig.evidence_urls,
                    raw_notes=sig.raw_notes[:2000],
                    fetched_at=sig.fetched_at,
                ))
            s.commit()
    except Exception as exc:
        log.warning("cache write failed: %s", exc)
