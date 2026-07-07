"""Market Pulse -- the 'what's hot right now' report, straight from the live
YTrends MCP index, cross-checked against Google Trends / Pinterest / X.

One per mode (Print on Demand, Embroidery). It is deliberately market-INTEL:
it shows what is winning so the team can decide *what kind of thing* to make --
it never tells anyone to copy a listing. All numbers come from live tools; if
the data source is down, the report says so instead of inventing figures.
"""
from datetime import date

from src.discover import matches_mode
from src.report_paths import rdir
from src import ytrends_mcp as mcp
from src import crosscheck

MODE_LABEL = {"pod": "Print on Demand", "embroidery": "Embroidery",
              None: "All"}


# ------------------------------- helpers ---------------------------------

def _clean(text):
    return str(text or "").replace("|", "/").replace("\n", " ").strip()


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _int(v):
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "-"


def _pct(v):
    """For 0-1 fractions (e.g. conversion 0.026 -> 2.6%)."""
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _pctval(v):
    """For values already expressed as a percent (e.g. 65.91 -> 65.9%)."""
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "-"


def _delta(v):
    try:
        n = int(round(float(v)))
        return f"+{n}" if n > 0 else str(n)
    except (TypeError, ValueError):
        return "-"


def _tag_mode(tag, mode):
    return matches_mode((tag or "").lower(), mode)


def _listing_mode(listing, mode):
    """Classify a hot listing by its tags + primary tag + title."""
    hay = " ".join([
        _clean(listing.get("primary_tag")),
        _clean(listing.get("title")),
        " ".join(str(t) for t in (listing.get("tags") or [])),
    ]).lower()
    return matches_mode(hay, mode)


def _gcell(sig):
    """Render a Google Trends signal compactly for a table cell."""
    if not sig or sig.get("status") == "disabled":
        return "-"
    st = sig.get("status")
    if st == "ok":
        arrow = {"rising": "up", "falling": "down", "flat": "flat"}.get(
            sig.get("direction"), "?")
        return f"G:{arrow} {sig.get('momentum_pct')}%"
    if st == "no_data":
        return "G:new"          # not on Google yet -> Etsy-native / early
    return "G:n/a"


# ------------------------------- sections --------------------------------

def _market_health(L):
    snap = mcp.market_snapshot()
    ov = snap.get("overview", {}) if isinstance(snap, dict) else {}
    mk = snap.get("market", {}) if isinstance(snap, dict) else {}
    if not ov:
        L += ["_Market snapshot unavailable this run._", ""]
        return
    L += [
        "## Market health (whole Etsy indexed market)", "",
        f"- **{_int(ov.get('total_listings'))} listings** across "
        f"**{_int(ov.get('total_sellers'))} sellers** | avg price "
        f"**{_money(ov.get('avg_price'))}** (median {_money(ov.get('median_price'))})",
        f"- Avg conversion **{_pct(ov.get('avg_conversion_rate'))}** | "
        f"est. **{_money(ov.get('estimated_daily_revenue'))}/day** market revenue "
        f"| avg listing age {_int(ov.get('avg_listing_age_days'))}d",
        f"- Price bands: p25 {_money(mk.get('price_p25'))} | "
        f"p75 {_money(mk.get('price_p75'))} | p90 {_money(mk.get('price_p90'))} | "
        f"{_pctval(mk.get('pct_listings_with_sales'))} of listings have sales",
        f"- Read: _{_clean(ov.get('recommended_action'))}_",
        "",
    ]


def _trending(L, mode, cross):
    tags = mcp.trending_keywords(limit=45)
    picks = [t for t in tags if _tag_mode(t.get("tag"), mode)][:15]
    L += [f"## Trending now — {MODE_LABEL.get(mode)} keywords gaining momentum", ""]
    if not picks:
        L += ["_No mode-matching trending keywords in the index this run._", ""]
        return []
    L += ["_Momentum = freshness-weighted rank velocity. Cross = Google Trends "
          "second opinion (up/down/flat %, or 'new' = not on Google yet)._", "",
          "| Keyword | Momentum | Competition | Rank | Δ7d | Avg price | Conv | "
          "Cross | Signal |",
          "|---|---|---|---|---|---|---|---|---|"]
    for t in picks:
        tag = _clean(t.get("tag"))
        L.append(
            f"| {tag} | {t.get('momentum_score', '-')} | "
            f"{_clean(t.get('competition_level'))} | {t.get('rank', '-')} | "
            f"{_delta(t.get('rank_change_7d'))} | {_money(t.get('avg_price'))} | "
            f"{_pct(t.get('avg_conversion_rate'))} | "
            f"{_gcell(cross.get(tag, {}).get('google'))} | "
            f"{_clean(t.get('action_reason'))} |")
    L.append("")
    return [t.get("tag") for t in picks]


def _hidden_gems(L, mode):
    tags = mcp.hidden_gems(limit=45)
    picks = [t for t in tags if _tag_mode(t.get("tag"), mode)][:12]
    L += [f"## Hidden gems — underexploited {MODE_LABEL.get(mode)} niches", ""]
    if not picks:
        L += ["_No mode-matching hidden gems in the index this run._", ""]
        return
    L += ["_High conversion + low competition. gem_score is YTrends' "
          "opportunity rank (higher = better)._", "",
          "| Keyword | Gem score | Sellers | Conv | Avg price | Trend | Action |",
          "|---|---|---|---|---|---|---|"]
    for t in picks:
        L.append(
            f"| {_clean(t.get('tag'))} | {t.get('gem_score', '-')} | "
            f"{_int(t.get('seller_count'))} | "
            f"{_pct(t.get('avg_conversion_rate'))} | "
            f"{_money(t.get('avg_price'))} | "
            f"{_clean(t.get('trend_direction'))} | "
            f"{_clean(t.get('recommended_action'))} |")
    L.append("")


def _hot_listings(L, mode):
    rows = mcp.hot_listings(limit=40)
    picks = [r for r in rows if _listing_mode(r, mode)][:12]
    L += ["## What's winning right now (market intel — do NOT copy)", ""]
    if not picks:
        L += ["_No mode-matching hot listings in the index this run._", ""]
        return
    L += ["_Individual listings outperforming their niche. Study the ANGLE "
          "(what/why), never the design._", "",
          "| Listing | Price | Sold 24h | Total sold | Conv | Age | Sample tags |",
          "|---|---|---|---|---|---|---|"]
    for r in picks:
        title = _clean(r.get("title"))[:70]
        tags = ", ".join(_clean(t) for t in (r.get("tags") or [])[:4])
        L.append(
            f"| {title} | {_money(r.get('price'))} | "
            f"{_int(r.get('sold_24h'))} | {_int(r.get('total_sold'))} | "
            f"{_pct(r.get('conversion_rate'))} | "
            f"{_int(r.get('listing_age_days'))}d | {tags} |")
    L.append("")


def _calendar(L):
    events = mcp.trend_calendar(window="next_90d", limit=12)
    L += ["## Upcoming seasonal events (next 90 days)", ""]
    if not events:
        L += ["_No seasonal events returned this run._", ""]
        return
    L += ["| Event | Date | Lead time | Note |", "|---|---|---|---|"]
    for e in events:
        L.append(
            f"| {_clean(e.get('event') or e.get('name'))} | "
            f"{_clean(e.get('date') or e.get('event_date'))} | "
            f"{_clean(e.get('days_until') or e.get('lead_time') or '-')} | "
            f"{_clean(e.get('note') or e.get('recommended_action') or '')} |")
    L.append("")


def _crosscheck_footer(L):
    st = crosscheck.status()
    L += ["## Cross-check sources this run", "",
          "| Source | Status |", "|---|---|"]
    for name, state in st.items():
        L.append(f"| {name} | {state} |")
    L += ["",
          "_Google Trends confirms whether an Etsy trend has wider web demand. "
          "'new' means it isn't on Google yet — often an early Etsy-native "
          "trend. Turn on Pinterest / X by adding their tokens to .env._", ""]


# ------------------------------- entrypoint ------------------------------

def build_market_pulse(mode, day=None, do_crosscheck=True):
    """Write reports/<day>/market_pulse/market_pulse_<day>.md and return path."""
    day = day or date.today()
    label = MODE_LABEL.get(mode, "All")
    L = [f"# Market Pulse — {label} — {day}", "",
         "_Live from the YTrends indexed Etsy market (updated hourly), "
         "cross-checked against the wider web. Market intelligence — study the "
         "angles, do NOT copy listings._", ""]

    ok, msg = mcp.available()
    if not ok:
        L += ["## DATA_UNAVAILABLE", "",
              f"The YTrends MCP data source is not reachable this run: {msg}", "",
              "No trending numbers are shown rather than guessing. Re-run once "
              "the source is back; the last good Market Pulse is kept.", ""]
    else:
        def _safe(fn, *a):
            """A single flaky tool must never kill the whole report."""
            try:
                return fn(*a)
            except Exception as exc:  # noqa: BLE001
                L.append(f"_(section unavailable this run: {exc})_")
                L.append("")

        _safe(_market_health, L)
        cross = {}
        if do_crosscheck:
            try:
                tags = mcp.trending_keywords(limit=45)
                top_for_cross = [t.get("tag") for t in tags
                                 if _tag_mode(t.get("tag"), mode)][:6]
                if top_for_cross:
                    cross = crosscheck.confirm_many(top_for_cross)
            except Exception:  # noqa: BLE001
                cross = {}
        _safe(_trending, L, mode, cross)
        _safe(_hidden_gems, L, mode)
        _safe(_hot_listings, L, mode)
        _safe(_calendar, L)
        _safe(_crosscheck_footer, L)

    path = rdir(day, "market_pulse") / f"market_pulse_{day}.md"
    path.write_text("\n".join(L), encoding="utf-8")
    try:
        from src.timestamp import stamp_file
        stamp_file(path, "Market Pulse")
    except Exception:
        pass
    return path


if __name__ == "__main__":  # py -m src.market_pulse pod
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    m = sys.argv[1] if len(sys.argv) > 1 else "pod"
    p = build_market_pulse(m)
    print("wrote", p)
    print("\n".join(p.read_text(encoding="utf-8").splitlines()[:40]))
