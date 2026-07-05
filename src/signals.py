"""Multi-source demand cross-check (V17).

Etsy data alone is what every competitor sees. This module cross-checks the
best cluster's keywords against independent sources:

1. Google Trends (automatic, via pytrends) - 12-month momentum
2. social_signals.csv (manual, 5-min researcher task) - Pinterest trends,
   X/Twitter, TikTok, or any other source. No affordable APIs exist for
   these, so the researcher checks them by hand and logs what they saw.
   The system NEVER invents a social signal.

Verdicts per keyword:
  CONFIRMED   - Etsy demand + at least one independent source agrees
  MIXED       - independent sources disagree
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
        elif "DECLINING" in signals and "RISING" in signals:
            verdict = "MIXED"
        elif all(s == "DECLINING" for s in signals):
            verdict = "DECLINING"
        elif "RISING" in signals:
            verdict = "CONFIRMED"
        else:
            verdict = "CONFIRMED" if signals else "ETSY_ONLY"
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
