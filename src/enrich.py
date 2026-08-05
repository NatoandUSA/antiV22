"""Backfill the market data that leaves a keyword unscored.

WHY THIS EXISTS
---------------
Measured on the live master: 843 of 1,523 keywords carry no overall score, because
the two biggest harvest sources arrive without demand fields — `mcp:search` adds a
NAME only and `mcp:ranking` adds a listing count only. opportunity_score needs
Market and Competition, so those rows are `core_missing` -> score None -> WATCH,
and they sit undifferentiated at the bottom of the Inbox forever.

The data exists: `research_keyword` answers with revenue, views, conversion,
listings and sellers for essentially every one of them (14/14 in a random sample).
Nothing in the app was topping them up — the one-click enrich was scoped to
capture-lane leads, of which there are zero.

WHY A CLI AND NOT A BUTTON
--------------------------
Enrichment measures at ~11.6 s per keyword against the live MCP, so the whole
backlog is ~2h45m. A web request cannot hold that, and `workflow_spine` records
that the VPS IP is blocked from YTrends anyway — this has to run on the PC, like
`harvest`. The result travels to the server through the existing
`harvest.merge_master()` sync.

SAFETY
------
* Fills BLANKS only. A value already in the master is never overwritten.
* Honest-nulls: a field the server has no number for stays empty (see
  shortlister_integration._enrich_row, which refuses to write a zero).
* Writes through a temp file + one backup, so an interrupted run cannot leave a
  half-written master.
* Flushes every `save_every` keywords, so Ctrl-C keeps the work already done.
* Resumable by construction: the work list is "rows the engine could not score",
  so a re-run simply skips everything the last run fixed.
* Nothing here ranks or publishes. It only fills in measurements.
"""
import csv
import shutil
import time
from pathlib import Path

MASTER = "keyword_data.csv"

# scorer field (what _enrich_row produces) -> master column (what harvest writes)
FIELD_MAP = {
    "listing_count": "etsy_listings",
    "seller_count": "seller_count",
    "views_24h": "views_24h",
    "avg_price": "avg_price",
    "revenue": "avg_revenue",
    "niche_revenue": "total_revenue",
    "avg_conversion_rate": "conversion_rate",
    "momentum_score": "momentum",
    "opportunity_score": "opportunity_score",
}


def _blank(v):
    return v is None or str(v).strip() == ""


def _read(path):
    """(fieldnames, rows). Returns ([], []) when the master is absent."""
    p = Path(path)
    if not p.is_file():
        return [], []
    with p.open(encoding="utf-8-sig") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames or []), list(rd)


def _write(path, fieldnames, rows):
    """Atomic-ish rewrite: temp file, then replace. Never leaves a partial master."""
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(p)


def unscored(mode=None):
    """The keywords the engine could not score — the work list, newest logic in
    opportunity_inbox so the CLI and the Inbox badge can never disagree."""
    from src import opportunity_inbox as oi
    return oi.lead_keywords(mode, limit=10 ** 9)


def run(limit=None, mode=None, pause=0.5, save_every=25, path=MASTER,
        log=print):
    """Top up unscored rows from the live MCP. Returns a counts dict.

    limit      stop after this many keywords (None = the whole backlog)
    pause      seconds between keywords; be a good citizen on a shared API
    save_every flush the master every N keywords so Ctrl-C keeps the work
    """
    from src import shortlister_integration as si

    todo = unscored(mode)
    if limit:
        todo = todo[:limit]
    fieldnames, rows = _read(path)
    if not rows:
        log("no keyword_data.csv — nothing to enrich")
        return {"targeted": 0, "enriched": 0, "filled": 0, "written": 0}

    # The master has drifted a column behind harvest.KDATA_FIELDS (no
    # opportunity_score locally). Append any canonical column we are about to
    # write values into; existing columns and their order are preserved.
    for col in FIELD_MAP.values():
        if col not in fieldnames:
            fieldnames.append(col)
            for r in rows:
                r.setdefault(col, "")

    by_kw = {}
    for r in rows:
        by_kw.setdefault((r.get("keyword") or "").strip().lower(), r)

    backup = Path(path).with_suffix(".bak.csv")
    shutil.copyfile(path, backup)
    log(f"{len(todo)} keyword(s) to enrich · backup at {backup}")

    enriched = filled = written = 0
    try:
        for i, kw in enumerate(todo, 1):
            row = by_kw.get(kw.strip().lower())
            if row is None:                     # lane lead not yet in the master
                continue
            d = {"tag": kw}
            try:
                ok = si._enrich_row(d, mode)
            except Exception as exc:            # noqa: BLE001 — one bad keyword
                log(f"  [{i}/{len(todo)}] {kw}: {str(exc)[:80]}")
                ok = False
            if ok:
                enriched += 1
            got = 0
            for src_field, col in FIELD_MAP.items():
                val = d.get(src_field)
                if val in (None, "", 0, 0.0):   # honest-nulls: no zeros, no guesses
                    continue
                if _blank(row.get(col)):        # fill BLANKS only, never overwrite
                    row[col] = val
                    got += 1
            filled += got
            log(f"  [{i}/{len(todo)}] {kw:<34} {'+' + str(got) if got else '—'}")
            if i % save_every == 0:
                _write(path, fieldnames, rows)
                written = i
                log(f"  … saved after {i}")
            if pause:
                time.sleep(pause)
    except KeyboardInterrupt:
        log("\ninterrupted — saving what has been enriched so far")
    _write(path, fieldnames, rows)
    written = len(todo)
    log(f"done · {enriched} keyword(s) returned data · {filled} field(s) filled")
    return {"targeted": len(todo), "enriched": enriched, "filled": filled,
            "written": written}
