"""
Trend Hunter agent (agent #1 of 9) — daily job.

Ties together:
  1. Fallback-chain loaders  (registry.get_trend_data)
  2. Kill switch             (filesystem flag, Vibe-Trading pattern)
  3. Run card                (auditable JSON per run: cost, results, errors)
  4. Embroidery feasibility  (stitch-safe heuristic flag)
  5. status='pending_review' (nothing auto-posts anywhere — your rule)

Adapt the class header to inherit from your existing BaseAgent.

APScheduler wiring (in your scheduler module):

    scheduler.add_job(
        TrendHunterAgent().run,
        trigger="cron", hour=6, minute=0,   # 6:00 VN time, before your workday
        id="trend_hunter_daily", replace_existing=True,
    )
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .loaders import sources  # noqa: F401  (import fires @register)
from .loaders.registry import budget, chain_status, get_trend_data

log = logging.getLogger("trend_hunter.agent")

KILL_SWITCH = Path(os.getenv("KILL_SWITCH_PATH", "./STOP_AGENTS"))
RUN_CARD_DIR = Path(os.getenv("RUN_CARD_DIR", "./run_cards"))

# Keywords to scan daily. Later: feed from Keyword Research agent output.
WATCHLIST: list[str] = [
    "pet portrait embroidery",
    "custom pet hoop art",
    "minimalist line art dog",
    "personalized cat gift",
    "embroidered family portrait",
]

# Stitch-safe red flags: if a trend name implies these, feasibility = False.
NOT_STITCH_SAFE = ("gradient", "photorealistic", "watercolor", "3d render",
                   "hyper detailed", "tiny text", "fine line shading")


def embroidery_feasible(trend_name: str, notes: str = "") -> bool:
    text = f"{trend_name} {notes}".lower()
    return not any(flag in text for flag in NOT_STITCH_SAFE)


class TrendHunterAgent:
    """Swap this header for: class TrendHunterAgent(BaseAgent):"""

    agent_name = "trend_hunter"

    def run(self) -> dict:
        started = datetime.now(timezone.utc)

        # ---- kill switch: fail-closed, checked before ANY work
        if KILL_SWITCH.exists():
            log.warning("kill switch present at %s — aborting run", KILL_SWITCH)
            return {"status": "killed", "reason": str(KILL_SWITCH)}

        results, errors = [], {}
        for kw in WATCHLIST:
            try:
                signals = get_trend_data(kw)
                for sig in signals:
                    record = sig.to_dict()
                    record["keyword"] = kw
                    record["embroidery_feasibility"] = embroidery_feasible(
                        sig.trend_name, sig.raw_notes)
                    record["status"] = "pending_review"   # manual gate
                    results.append(record)
                # TODO: persist records to your trends table here
                # (same SessionLocal pattern as cache.py)
            except Exception as exc:   # belt-and-braces: one keyword never kills the run
                errors[kw] = str(exc)
                log.error("keyword '%s' failed: %s", kw, exc)

        run_card = {
            "agent": self.agent_name,
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "keywords_scanned": len(WATCHLIST),
            "signals_found": len(results),
            "feasible_signals": sum(1 for r in results if r["embroidery_feasibility"]),
            "paid_spend_today_usd": round(budget.spent_today, 4),
            "budget_cap_usd": 1.00,
            "source_health": chain_status(),
            "errors": errors,
        }
        self._write_run_card(run_card)
        log.info("run complete: %d signals, $%.2f spent",
                 len(results), budget.spent_today)
        return {"status": "ok", "run_card": run_card, "records": results}

    @staticmethod
    def _write_run_card(card: dict) -> None:
        try:
            RUN_CARD_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = RUN_CARD_DIR / f"trend_hunter_{stamp}.json"
            path.write_text(json.dumps(card, indent=2, ensure_ascii=False))
        except Exception as exc:      # run card failure is never fatal
            log.warning("run card write failed: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    out = TrendHunterAgent().run()
    print(json.dumps(out["run_card"] if "run_card" in out else out, indent=2))
