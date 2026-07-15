"""YTrends browser-extension ingest.

The YTrends Exporter extension POSTs the table you're viewing as JSON:
    {"view": "...", "captured_at": "...", "source": "...",
     "headers": ["Keyword","Gem Score",...], "rows": [[...], ...]}

This module normalises that into the same fuel the rest of the pipeline reads:
- keyword / hidden-gem / trending views  -> MERGED into keyword_data.csv
  (load existing first, add/refresh, write back - never blanks the file)
- category views                         -> data/imports/category_intel.csv
  (the /categories page reads this as a fallback when the REST API is off)
- anything else                          -> data/imports/<view>_<date>.csv

Every payload is also saved raw under data/imports/ytrends_ext/ for audit.
Nothing here publishes anything.
"""
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

IMPORTS = Path("data/imports")
RAW_DIR = IMPORTS / "ytrends_ext"
CATEGORY_CSV = IMPORTS / "category_intel.csv"


# ---- number parsing (handles "$1,234.56", "5.1%", "1,234", "-", "") ----------
def parse_number(s):
    if s is None:
        return None
    t = str(s).strip()
    if t.lower() in ("", "-", "—", "n/a", "na", "none"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    # thousands / millions / billions suffix, e.g. "1.8K" -> 1800, "3.4M" -> 3.4e6.
    # YTrends abbreviates large view/revenue counts; without this they parse ~1000x
    # too small (1.8K -> 1.8) and wipe out demand.
    mult = 1.0
    m = re.search(r"([kmb])\b", t, re.I)
    if m and re.search(r"\d", t):
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[m.group(1).lower()]
    t = re.sub(r"[^0-9.\-]", "", t.replace(",", ""))
    if t in ("", "-", ".", "--"):
        return None
    try:
        v = float(t) * mult
    except ValueError:
        return None
    return -v if neg else v


def parse_percent(s):
    """'5.1%' -> 0.051 ; '0.05' -> 0.05 (values > 1 are treated as percents)."""
    v = parse_number(s)
    if v is None:
        return None
    return v / 100.0 if v > 1 else v


def _find(headers, *needles, exclude=()):
    for i, h in enumerate(headers):
        hl = str(h).lower()
        if any(n in hl for n in needles) and not any(x in hl for x in exclude):
            return i
    return None


def _resolve(headers):
    return {
        "keyword": _find(headers, "keyword"),
        "category": _find(headers, "category"),
        "listings": _find(headers, "listing", exclude=("/", "seller")),
        "sellers": _find(headers, "seller", exclude=("/",)),
        "price": _find(headers, "avg price", "price"),
        "revenue": _find(headers, "revenue"),
        "conv": _find(headers, "conversion", "conv"),
        "sold": _find(headers, "sold"),
        "views": _find(headers, "views vel", "view"),
        "score": _find(headers, "gem score", "opportunity", "momentum", "score"),
        "comp": _find(headers, "competition"),
    }


def _cell(row, i):
    return row[i] if (i is not None and i < len(row)) else None


def _save_raw(view, payload):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p = RAW_DIR / f"{view}_{stamp}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


# ---- keyword / gem / trending views -> merge into keyword_data.csv -----------
def _merge_keywords(view, rows, idx, path="keyword_data.csv"):
    from src import harvest
    store = {}
    p = Path(path)
    if p.is_file():                       # load existing so we MERGE, never wipe
        with p.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                harvest._add(
                    store, r.get("keyword"), parse_number(r.get("momentum")) or 0,
                    (r.get("source") or "").replace("mcp:", ""),
                    listings=parse_number(r.get("etsy_listings")),
                    sellers=parse_number(r.get("seller_count")),
                    price=parse_number(r.get("avg_price")),
                    conv=parse_number(r.get("conversion_rate")),
                    revenue=parse_number(r.get("avg_revenue")),
                    views=parse_number(r.get("views_24h")))
    added = 0
    for row in rows:
        kw = (_cell(row, idx["keyword"]) or "").strip()
        if not kw:
            continue
        harvest._add(
            store, kw, parse_number(_cell(row, idx["score"])) or 0, "ext:" + view,
            listings=parse_number(_cell(row, idx["listings"])),
            sellers=parse_number(_cell(row, idx["sellers"])),
            price=parse_number(_cell(row, idx["price"])),
            conv=parse_percent(_cell(row, idx["conv"])),
            revenue=parse_number(_cell(row, idx["revenue"])),
            sold=parse_number(_cell(row, idx["sold"])),
            views=parse_number(_cell(row, idx["views"])),
            comp=(_cell(row, idx["comp"]) or None))
        added += 1
    harvest.write_keyword_data(store, path)
    return added


def _write_csv(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        for r in rows:
            w.writerow(list(r)[:len(headers)] + [""] * (len(headers) - len(r)))
    return str(path)


def ingest(payload):
    """Normalise one extension payload. Returns a summary dict (never raises on
    empty input; raises ValueError only on a structurally invalid payload)."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    headers = payload.get("headers") or []
    rows = payload.get("rows") or []
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise ValueError("headers and rows must be arrays")
    view = re.sub(r"[^a-z0-9]+", "-", str(payload.get("view") or "unknown").lower()).strip("-")
    raw = _save_raw(view, payload)
    idx = _resolve(headers)
    out = {"view": view, "rows_received": len(rows), "raw_file": raw,
           "type": None, "keyword_rows_merged": 0, "files": []}
    if not rows:
        out["type"] = "empty"
        return out
    if idx["keyword"] is not None:
        out["type"] = "keywords"
        out["keyword_rows_merged"] = _merge_keywords(view, rows, idx)
    elif idx["category"] is not None:
        out["type"] = "categories"
        out["files"].append(_write_csv(CATEGORY_CSV, headers, rows))
        out["files"].append(_write_csv(IMPORTS / f"categories_{date.today()}.csv",
                                       headers, rows))
    else:
        out["type"] = "generic"
        out["files"].append(_write_csv(IMPORTS / f"{view}_{date.today()}.csv",
                                       headers, rows))
    return out


def latest_categories():
    """Rows from the last category import (for the /categories fallback), or []."""
    if not CATEGORY_CSV.is_file():
        return []
    with CATEGORY_CSV.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
