"""Multi-source demand cross-check (V17).

Etsy data alone is what every competitor sees. This module cross-checks the
best cluster's keywords against independent sources:

1. Google Trends (automatic, via pytrends) - 12-month momentum
2. social_signals.csv (manual, 5-min researcher task) - Pinterest trends,
   X/Twitter, TikTok, or any other source. No affordable APIs exist for
   these, so the researcher checks them by hand and logs what they saw.
   The system NEVER invents a social signal.

Verdicts per keyword:
  CONFIRMED   - Etsy demand + at least one independent source is RISING
  MIXED       - independent sources disagree (both rising and declining)
  STABLE      - only steady signals: demand holds but isn't growing (not a green light)
  ETSY_ONLY   - no independent confirmation yet (not bad - just unverified)
  DECLINING   - independent sources point down: extra caution
"""
import csv
from pathlib import Path

SOCIAL_CSV = Path("social_signals.csv")
SOCIAL_FIELDS = ["keyword", "source", "signal", "note", "checked_at"]
# signal: RISING | STABLE | DECLINING


def _google(keywords):
    """12-month Google Trends momentum. {} on failure (rate limits etc.)."""
    try:
        from src.gtrends import fetch_momentum
        return fetch_momentum(keywords[:5])  # cap: avoid rate limits
    except Exception as exc:
        print(f"  (Google Trends unavailable: {exc})")
        return {}


def load_social():
    rows = {}
    if SOCIAL_CSV.exists():
        with SOCIAL_CSV.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                kw = (r.get("keyword") or "").strip().lower()
                if kw:
                    rows.setdefault(kw, []).append(r)
    return rows


def ensure_social_template(keywords):
    """Seed rows for the researcher to fill (never overwrites their work)."""
    existing = load_social()
    new = [k for k in keywords if k not in existing]
    if not new:
        return
    write_header = not SOCIAL_CSV.exists()
    with SOCIAL_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(SOCIAL_FIELDS)
        for k in new[:10]:
            w.writerow([k, "pinterest", "", "check trends.pinterest.com", ""])
            w.writerow([k, "x_twitter", "", "search the phrase on X", ""])


def cross_check(keywords):
    """Return {keyword: {google, social, verdict, evidence}}."""
    gt = _google(keywords)
    social = load_social()
    ensure_social_template(keywords)
    out = {}
    for k in keywords:
        g = gt.get(k)
        g_dir = None
        if g:
            g_dir = ("RISING" if g["momentum_pct"] >= 10 else
                     "DECLINING" if g["momentum_pct"] <= -10 else "STABLE")
        s_rows = [r for r in social.get(k, [])
                  if (r.get("signal") or "").strip()]
        s_dirs = [(r["signal"] or "").strip().upper() for r in s_rows]
        signals = ([g_dir] if g_dir else []) + s_dirs
        if not signals:
            verdict = "ETSY_ONLY"
        elif "RISING" in signals and "DECLINING" in signals:
            verdict = "MIXED"
        elif "RISING" in signals:
            verdict = "CONFIRMED"
        elif "DECLINING" in signals:
            # any independent down-signal (no rising) = caution, never green
            verdict = "DECLINING"
        else:
            # only STABLE signals: steady, not growing -- NOT a "confirmed" green
            verdict = "STABLE"
        evidence = []
        if g:
            evidence.append(f"Google Trends {g['momentum_pct']:+.0f}% "
                            f"(avg interest {g['avg_interest']})")
        for r in s_rows:
            evidence.append(f"{r['source']}: {r['signal']}"
                            + (f" - {r['note']}" if r.get("note") else ""))
        out[k] = {"google": g_dir or "unavailable",
                  "social": s_dirs or ["not checked"],
                  "verdict": verdict,
                  "evidence": "; ".join(evidence) or
                              "no independent source checked yet"}
    return out


def trend_velocity(momentum_score=None, rank_change_7d=None):
    """Classify a keyword's trend PHASE, separating RISING (still accelerating)
    from PEAKED (high interest but momentum flattening/declining) -- the "get in
    now" vs "window has closed" distinction the plain rising/cooling read misses.

    momentum_score: 0-100 (higher = faster growth). rank_change_7d: 7-day change
    in Etsy rank (NEGATIVE = moving toward #1 = improving). Returns (phase, note).
    """
    ms = momentum_score if isinstance(momentum_score, (int, float)) else None
    rc = rank_change_7d if isinstance(rank_change_7d, (int, float)) else None
    if rc is not None and rc <= -3:
        return "RISING", "climbing the rankings fast — get in early"
    if ms is not None and ms >= 60:
        return "RISING", "strong momentum — still accelerating"
    if rc is not None and rc >= 3:
        return "PEAKED", "slipping in the rankings — likely past peak"
    if ms is not None and ms < 30:
        return "PEAKED", "low momentum — likely past its peak"
    if ms is not None and 30 <= ms < 50:
        return "PEAKING", "high but flattening — window is closing"
    return "STEADY", "holding steady — no strong trend either way"
