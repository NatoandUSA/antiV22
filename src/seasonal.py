"""Seasonal calendar planner — what to launch next, timed.

Two sources, merged:
- A curated table of the big fixed Etsy/e-commerce selling events (Valentine's,
  Mother's/Father's Day, Halloween, Black Friday, Christmas, ...) with real dates
  and a suggested product + keyword angle per mode. These always show even if the
  live index is thin that day.
- The LIVE YTrends trend_calendar (upcoming demand spikes) with peak_date,
  recommended_listing_start, opportunity_grade, competition — mapped onto the
  nearest event so the team sees real rising keywords, not just holidays.

Every event shows a **launch-by** date (peak − prep window) so listings have time
to rank. Nothing here auto-publishes.
"""
from datetime import date, timedelta

from src import ytrends_mcp as mcp
from src.trademark import check as tm_check

# Big selling events with real dates (US retail calendar). Extend the year lists
# as needed — the planner only ever shows events still ahead of today.
HOLIDAYS = [
    ("New Year / resolutions", ["2027-01-01", "2028-01-01", "2029-01-01"],
     ["new year gift", "new year goals shirt", "resolution planner"],
     {"pod": "motivational shirt / mug", "embroidery": "embroidered dated keepsake"}),
    ("Valentine's Day", ["2027-02-14", "2028-02-14", "2029-02-14"],
     ["couple gift", "valentines shirt", "anniversary gift for her"],
     {"pod": "couple shirt / mug", "embroidery": "embroidered couple hoodie"}),
    ("St. Patrick's Day", ["2027-03-17", "2028-03-17", "2029-03-17"],
     ["st patricks day shirt", "lucky shirt", "irish gift"],
     {"pod": "green graphic tee", "embroidery": "embroidered shamrock hat"}),
    ("Easter", ["2027-03-28", "2028-04-16", "2029-04-01"],
     ["easter gift", "easter basket name", "spring shirt"],
     {"pod": "easter kids shirt", "embroidery": "embroidered easter basket"}),
    ("Mother's Day", ["2027-05-09", "2028-05-14", "2029-05-13"],
     ["mothers day gift", "mom shirt personalized", "gift for grandma"],
     {"pod": "mom shirt / mug", "embroidery": "embroidered mom sweatshirt"}),
    ("Graduation", ["2027-05-15", "2028-05-15", "2029-05-15"],
     ["graduation gift", "class of shirt", "senior gift"],
     {"pod": "class-of shirt", "embroidery": "embroidered grad stole / hat"}),
    ("Father's Day", ["2026-06-21", "2027-06-20", "2028-06-18"],
     ["fathers day gift", "dad shirt personalized", "grandpa gift"],
     {"pod": "dad shirt / mug", "embroidery": "embroidered dad hat / hoodie"}),
    ("Independence Day (4th of July)", ["2026-07-04", "2027-07-04", "2028-07-04"],
     ["4th of july shirt", "patriotic shirt", "usa flag gift"],
     {"pod": "patriotic tee", "embroidery": "embroidered flag hat"}),
    ("Back to School", ["2026-08-18", "2027-08-18", "2028-08-16"],
     ["back to school", "teacher gift personalized", "school name tote"],
     {"pod": "teacher shirt", "embroidery": "embroidered name backpack / tote"}),
    ("Halloween", ["2026-10-31", "2027-10-31", "2028-10-31"],
     ["halloween shirt", "spooky shirt", "halloween costume tee"],
     {"pod": "halloween graphic tee", "embroidery": "embroidered halloween sweatshirt"}),
    ("Thanksgiving", ["2026-11-26", "2027-11-25", "2028-11-23"],
     ["thanksgiving shirt", "fall shirt", "family thanksgiving gift"],
     {"pod": "fall / thanksgiving tee", "embroidery": "embroidered fall sweatshirt"}),
    ("Black Friday / Cyber Monday", ["2026-11-27", "2027-11-26", "2028-11-24"],
     ["holiday gift", "christmas gift idea", "bestseller gift"],
     {"pod": "bundle-ready bestsellers", "embroidery": "embroidered gift set"}),
    ("Christmas", ["2026-12-25", "2027-12-25", "2028-12-25"],
     ["christmas gift personalized", "family christmas shirt", "christmas ornament name"],
     {"pod": "family christmas shirt", "embroidery": "embroidered stocking / ornament"}),
]

PREP_DAYS = 45   # launch ~6 weeks before the peak so listings have time to rank


def _parse(d):
    y, m, dd = (int(x) for x in d.split("-"))
    return date(y, m, dd)


def _next_date(dates, today):
    """First listed date still ahead of today; if the hardcoded year lists are
    exhausted, AUTO-ROLL the pattern (month/day of the last known date) to the
    next future year so events never silently disappear. Exact for fixed-date
    holidays; within a few days for floating ones (fine for a 6-week lead)."""
    parsed = sorted(_parse(x) for x in dates)
    fut = [d for d in parsed if d >= today]
    if fut:
        return fut[0]
    if not parsed:
        return None
    last = parsed[-1]
    for yy in (today.year, today.year + 1):
        try:
            cand = date(yy, last.month, last.day)
        except ValueError:          # e.g. Feb 29 in a non-leap year
            continue
        if cand >= today:
            return cand
    return None


def _launch_status(days_until, launch_by, today):
    """Where we stand vs. the ideal launch-by date (peak − ~6 weeks)."""
    if days_until > 150:
        return "NEXT_YEAR_PREP"      # far off — plan, don't rush
    if launch_by >= today:
        return "PREP_NOW" if days_until <= 90 else "PREP_EARLY"
    # past the ideal launch-by but the peak is still ahead
    return "LATE_TEST_ONLY"


def upcoming_holidays(today=None, horizon_days=180, mode=None):
    """Curated events whose peak is within the horizon, soonest first. Each event
    carries a launch_status so passed/late windows aren't shown as fresh chances."""
    today = today or date.today()
    out = []
    for name, dates, kws, products in HOLIDAYS:
        peak = _next_date(dates, today)
        if not peak:
            continue
        days = (peak - today).days
        if days > horizon_days:
            continue
        launch_by = peak - timedelta(days=PREP_DAYS)
        product = products.get(mode) if mode in ("pod", "embroidery") else \
            f"{products['pod']}  ·  {products['embroidery']}"
        out.append({
            "event": name, "peak": peak, "days_until": days,
            "launch_by": launch_by, "keywords": kws, "product": product,
            "launch_status": _launch_status(days, launch_by, today)})
    out.sort(key=lambda e: e["peak"])
    return out


def _live_events(mode=None, limit=25):
    """Live rising keywords from trend_calendar, best-opportunity first."""
    try:
        events = mcp.trend_calendar(window="next_90d", limit=limit)
    except Exception:  # noqa: BLE001
        return []
    from src.discover import matches_mode
    rows = []
    for e in events:
        tag = (e.get("tag") or "").strip()
        if not tag or not matches_mode(tag.lower(), None if mode in (None, "both") else mode):
            continue
        risk, _ = tm_check(tag.lower())
        rows.append({
            "tag": tag,
            "peak_date": e.get("peak_date"),
            "launch_by": e.get("recommended_listing_start"),
            "grade": e.get("opportunity_grade"),
            "opportunity": e.get("opportunity_score"),
            "competition": e.get("competition_level"),
            "avg_price": e.get("avg_price_usd"),
            "sold_24h": e.get("total_sold_24h"),
            "action": e.get("recommended_action"),
            "trademark": risk})
    rows.sort(key=lambda r: (r.get("opportunity") or 0), reverse=True)
    return rows


def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


RANGES = {"7d": 7, "30d": 30, "60d": 60, "90d": 90, "6mo": 180, "year": 366}
_STATUS_TIP = {"PREP_NOW": "✅ prep + launch now", "PREP_EARLY": "🕒 plan ahead",
               "LATE_TEST_ONLY": "⚠️ past ideal launch-by — small test only",
               "NEXT_YEAR_PREP": "📌 next-year prep"}


def calendar_plan(mode=None, today=None, days=180):
    """Full 'what to launch next, timed' plan — Markdown. `days` = horizon range."""
    today = today or date.today()
    mlabel = {"pod": "Print on Demand", "embroidery": "Embroidery"}.get(
        mode, "All lines")
    rlabel = {7: "next 7 days", 30: "next 30 days", 60: "next 60 days",
              90: "next 90 days", 180: "next 6 months", 366: "full year"}.get(days, "next 6 months")
    L = [f"# 📅 Seasonal calendar — what to launch next ({mlabel})", "",
         f"_As of {today}. **Launch by** each date so listings have ~6 weeks to "
         "rank before the peak. Passed / late windows are labelled so you don't "
         "chase a missed one. Verify every keyword's trademark before listing._",
         "", f"## Upcoming selling events ({rlabel})", "",
         "| Event | Peak | Days away | 🚀 Launch by | Status | Suggested product | Keyword angles |",
         "|---|---|---|---|---|---|---|"]
    hols = upcoming_holidays(today, horizon_days=days, mode=mode)
    if hols:
        for e in hols:
            st = e.get("launch_status", "")
            L.append(f"| **{e['event']}** | {e['peak']} | {e['days_until']}d "
                     f"| {e['launch_by']} | {_STATUS_TIP.get(st, st)} | {e['product']} "
                     f"| {', '.join(e['keywords'])} |")
    else:
        L.append(f"| _No major events in the {rlabel}_ | | | | | | |")

    live = _live_events(mode)
    L += ["", "## Live rising keywords right now (from the index)", "",
          "_These are gaining demand today — pair one with a product above._", ""]
    if live:
        L += ["| Keyword | Peak | 🚀 Launch by | Grade | Opportunity | Competition | Avg price | TM |",
              "|---|---|---|---|---|---|---|---|"]
        for r in live[:15]:
            L.append(f"| {r['tag']} | {r.get('peak_date','-')} "
                     f"| {r.get('launch_by','-')} | {r.get('grade','-')} "
                     f"| {r.get('opportunity','-')} | {r.get('competition','-')} "
                     f"| {_money(r.get('avg_price'))} | {r['trademark']} |")
    else:
        L.append("_No live calendar data right now — the events above still apply._")

    if hols:
        nxt = hols[0]
        L += ["", "## Do next", "",
              f"- **{nxt['event']}** is closest ({nxt['days_until']} days). "
              f"Launch by **{nxt['launch_by']}**.",
              f"- Build a {nxt['product']} around: "
              f"_{', '.join(nxt['keywords'])}_.",
              "- Run each keyword through **Analyze** + the **Command Center** "
              "before designing. Never auto-published."]
    return "\n".join(L)
