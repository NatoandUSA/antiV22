"""Central timestamp for every report.

One function, one format, used by every writer. Timezone is the team's:
Asia/Ho_Chi_Minh (ICT). Filenames keep date-only; report headers carry
the exact generation time to the second.
"""
import os
import sys
from datetime import datetime
from src.version import VERSION

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:  # Windows without tzdata package: fixed UTC+7 (ICT)
    from datetime import timedelta, timezone
    _TZ = timezone(timedelta(hours=7), "ICT")
_COMMAND = "python main.py " + " ".join(sys.argv[1:]) if len(sys.argv) > 1 \
    else "python main.py"


def data_is_fresh(dates, max_age_days=None):
    """True if the newest collected_at date (YYYY-MM-DD strings) is within
    max_age_days of today; blanks are ignored.

    Default window is YTRENDS_FRESH_DAYS (env) or 7 days. This lets synced
    market data stay usable for a few days, so a headless server that can't
    fetch live data still serves valid reports between refreshes.
    """
    from datetime import date
    if max_age_days is None:
        try:
            max_age_days = int(os.getenv("YTRENDS_FRESH_DAYS") or "7")
        except ValueError:
            max_age_days = 7
    newest = max((d for d in dates if d), default="")
    if not newest:
        return False
    try:
        y, m, d = (int(x) for x in newest[:10].split("-"))
        return (date.today() - date(y, m, d)).days <= max_age_days
    except Exception:
        return False


def set_command(cmd):
    global _COMMAND
    _COMMAND = cmd


def get_command():
    return _COMMAND


def get_report_timestamp():
    now = datetime.now(_TZ)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": "Asia/Ho_Chi_Minh",
        "timezone_label": "ICT",
        "display": now.strftime("%Y-%m-%d %H:%M:%S ICT"),
        "iso": now.isoformat(),
    }


def build_report_header(report_type, version=None, command=None,
                        timestamp=None):
    ts = timestamp or get_report_timestamp()
    return (f"Generated on: {ts['display']}\n"
            f"Timezone: {ts['timezone']}\n"
            f"Tool version: {version or VERSION}\n"
            f"Report type: {report_type}\n"
            f"Command: {command or _COMMAND}\n\n")


REPORT_TYPES = {
    "manager": "Manager Report", "design_prompts": "Design Prompts",
    "seller_pack": "Seller Pack", "tasks": "Team Tasks",
    "discover": "Discover Report", "ideas": "Ideas Report",
    "listing": "Listing Pack", "report": "Google Trends Validation",
    "manifest": "Report Manifest", "research": "Research Report",
}


def report_type_for(path):
    # Windows-safe: normalize both separators before taking the filename
    stem = str(path).replace("\\", "/").split("/")[-1]
    for prefix, label in REPORT_TYPES.items():
        if stem.startswith(prefix):
            lang = " VI" if "_VI" in stem else \
                   " EN" if "_EN" in stem else ""
            return label + lang
    return "Report"


def stamp_file(path, report_type=None, timestamp=None):
    """Prepend the header to a markdown file (idempotent)."""
    from pathlib import Path
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if text.startswith("Generated on: "):
        return timestamp
    ts = timestamp or get_report_timestamp()
    header = build_report_header(report_type or report_type_for(p),
                                 timestamp=ts)
    p.write_text(header + text, encoding="utf-8")
    return ts
