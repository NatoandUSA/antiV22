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
import io
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

IMPORTS = Path("data/imports")
RAW_DIR = IMPORTS / "ytrends_ext"
CATEGORY_CSV = IMPORTS / "category_intel.csv"

# Upload guard: a keyword export is at most a few hundred rows; cap well above
# that so a giant/accidental file can't balloon memory on the VPS. The web layer
# also caps the raw request body (MAX_CONTENT_LENGTH), so this is belt-and-braces.
MAX_UPLOAD_ROWS = 5000


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
    before = set(store)                 # keywords already in the master
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
    new_kws = len(set(store) - before)  # genuinely NEW (not dupes/updates)
    harvest.write_keyword_data(store, path)
    return added, new_kws


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
        merged, new_kws = _merge_keywords(view, rows, idx)
        out["keyword_rows_merged"] = merged
        out["keywords_new"] = new_kws   # NEW keywords (dupes excluded)
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


def _records_to_table(records):
    """A JSON array of objects -> (headers, rows) preserving first-seen key order."""
    headers = []
    for rec in records:
        if isinstance(rec, dict):
            for k in rec.keys():
                if str(k) not in headers:
                    headers.append(str(k))
    rows = []
    for rec in records:
        if isinstance(rec, dict):
            rows.append([rec.get(h) for h in headers])
        elif isinstance(rec, (list, tuple)):
            rows.append(list(rec))
    return headers, rows


def parse_upload(filename, raw):
    """Turn a MANUALLY uploaded CSV or JSON export into the ingest() payload shape
    {view, captured_at, source, headers, rows}. This is the file-upload twin of the
    browser extension's JSON POST — it lands in the SAME pipeline, so the Winner
    Finder / score-import read it with no new code path.

    Accepts: the extension's own {headers, rows} JSON, a JSON array of objects, a
    JSON {rows:[...]} object, or a plain CSV (first row = headers). Pure parsing —
    no network, tiny memory. Raises ValueError on unusable input."""
    text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    text = text.strip()
    if not text:
        raise ValueError("the file is empty")
    name = (filename or "").lower()
    stem = re.sub(r"[^a-z0-9]+", "-", name.rsplit(".", 1)[0]).strip("-") or "upload"
    is_json = name.endswith(".json") or text[:1] in ("{", "[")
    headers, rows, view = [], [], stem
    if is_json:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"not valid JSON: {exc}")
        if isinstance(data, dict) and isinstance(data.get("headers"), list) \
                and isinstance(data.get("rows"), list):
            headers = [str(h) for h in data["headers"]]
            rows = data["rows"]
            view = str(data.get("view") or stem)
        elif isinstance(data, dict) and isinstance(data.get("rows"), list):
            headers, rows = _records_to_table(data["rows"])
            view = str(data.get("view") or stem)
        elif isinstance(data, list):
            headers, rows = _records_to_table(data)
        else:
            raise ValueError("unrecognised JSON — expected an array of rows or "
                             "an object with headers + rows")
    else:
        reader = csv.reader(io.StringIO(text))
        allrows = [r for r in reader if any(str(c).strip() for c in r)]
        if not allrows:
            raise ValueError("no rows found in the CSV")
        headers = [str(h).strip() for h in allrows[0]]
        rows = allrows[1:]
    if not headers:
        raise ValueError("no column headers found")
    norm = []
    for r in rows[:MAX_UPLOAD_ROWS]:
        if isinstance(r, dict):
            norm.append([r.get(h) for h in headers])
        elif isinstance(r, (list, tuple)):
            norm.append(list(r))
        else:
            norm.append([r])
    return {"view": view, "source": "file-upload",
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "headers": headers, "rows": norm}


def parse_uploads(files):
    """Merge SEVERAL uploaded exports into ONE ingest payload so they rank together
    in the Winner Finder. `files` is a list of (filename, raw_bytes).

    Each file is parsed with parse_upload; the columns are unioned (first-seen
    order), every row is remapped to the merged header set, and rows are de-duped
    by keyword (first occurrence wins) so the same keyword across two exports isn't
    double-counted. Returns (payload, n_files_used). Skips unparseable files but
    raises ValueError only if NONE were usable."""
    parsed, errors = [], []
    for fn, raw in files:
        try:
            parsed.append(parse_upload(fn, raw))
        except ValueError as exc:
            errors.append(f"{fn}: {exc}")
    if not parsed:
        raise ValueError("no usable files"
                         + (" — " + "; ".join(errors) if errors else ""))
    if len(parsed) == 1:
        return parsed[0], 1

    merged_headers = []
    for p in parsed:
        for h in p["headers"]:
            if h not in merged_headers:
                merged_headers.append(h)
    kw_idx = _resolve(merged_headers)["keyword"]
    merged_rows, seen = [], set()
    for p in parsed:
        hp = p["headers"]
        for r in p["rows"]:
            d = {hp[i]: (r[i] if i < len(r) else None) for i in range(len(hp))}
            row = [d.get(h) for h in merged_headers]
            if kw_idx is not None and kw_idx < len(row):
                key = str(row[kw_idx] or "").strip().lower()
                if key:
                    if key in seen:
                        continue
                    seen.add(key)
            merged_rows.append(row)
            if len(merged_rows) >= MAX_UPLOAD_ROWS:
                break
        if len(merged_rows) >= MAX_UPLOAD_ROWS:
            break
    return {"view": f"merged-{len(parsed)}-files", "source": "file-upload-merged",
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "headers": merged_headers, "rows": merged_rows}, len(parsed)


def latest_categories():
    """Rows from the last category import (for the /categories fallback), or []."""
    if not CATEGORY_CSV.is_file():
        return []
    with CATEGORY_CSV.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
