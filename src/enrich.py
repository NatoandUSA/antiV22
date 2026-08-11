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
Enrichment measures at ~11-17 s per keyword against the live MCP, so the whole
backlog can run for hours. A synchronous web request cannot hold that.

The "VPS IP is blocked from YTrends" note this docstring used to carry (echoed
in harvest.py and workflow_spine.py) was verified STALE 2026-08-11: a direct
call to shortlister_integration._enrich_row from the VPS itself succeeded in
17.3s with real data. That block was almost certainly about the legacy REST
transport (YTRENDS_COOKIE, which expires) — test_enrich.py's own
test_the_live_guard_probes_the_transport_the_command_actually_uses already
documents ytrends_client.probe() (REST) reading False while ytrends_mcp
(YTRENDS_API_TOKEN) answers fine. This module and enrichment_runner.py use the
MCP transport and DO run from the VPS now. Long-running/unattended callers
should still pass max_runtime_s (below) rather than assume they can finish.

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
* Per-keyword timeout (default 25s, generous over the ~17s measured) so one
  hung network call cannot freeze an unattended run - the same failure mode
  save_candidates was patched against (a 2min+ hang, audited).
* Nothing here ranks or publishes. It only fills in measurements.
"""
import csv
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
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
        log=print, timeout_s=25, max_runtime_s=None):
    """Top up unscored rows from the live MCP. Returns a counts dict.

    limit         stop after this many keywords (None = the whole backlog)
    pause         seconds between keywords; be a good citizen on a shared API
    save_every    flush the master every N keywords so Ctrl-C keeps the work
    timeout_s     per-keyword hard timeout (measured ~11-17s live; one hung
                  call must never freeze an unattended run)
    max_runtime_s stop starting new keywords once this many seconds have
                  elapsed (None = no bound, the historical/manual behaviour);
                  the run still saves whatever it finished before stopping
    """
    from src import shortlister_integration as si

    todo = unscored(mode)
    if limit:
        todo = todo[:limit]
    fieldnames, rows = _read(path)
    if not rows:
        log("no keyword_data.csv — nothing to enrich")
        return {"targeted": 0, "enriched": 0, "filled": 0, "written": 0,
                "timed_out": 0, "stopped_early": None}

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

    started = time.time()
    pool = ThreadPoolExecutor(max_workers=1)
    fails = 0
    enriched = filled = written = timed_out = 0
    stopped_early = None
    try:
        for i, kw in enumerate(todo, 1):
            if max_runtime_s and time.time() - started >= max_runtime_s:
                stopped_early = "max_runtime_s reached"
                break
            row = by_kw.get(kw.strip().lower())
            if row is None:                     # lane lead not yet in the master
                continue
            if fails >= 2:                       # MCP looks down - stop spending time
                stopped_early = "2 consecutive failures (MCP unreachable?)"
                break
            d = {"tag": kw}
            try:
                fut = pool.submit(si._enrich_row, d, mode)
                ok = bool(fut.result(timeout=timeout_s))
            except Exception as exc:            # noqa: BLE001 — timeout / bad keyword
                if type(exc).__name__ == "TimeoutError":
                    timed_out += 1
                log(f"  [{i}/{len(todo)}] {kw}: {str(exc)[:80]}")
                ok = False
            fails = 0 if ok else fails + 1
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
        stopped_early = stopped_early or "KeyboardInterrupt"
    finally:
        pool.shutdown(wait=False)
    _write(path, fieldnames, rows)
    written = len(todo)
    log(f"done · {enriched} keyword(s) returned data · {filled} field(s) filled"
        + (f" · stopped early: {stopped_early}" if stopped_early else ""))
    return {"targeted": len(todo), "enriched": enriched, "filled": filled,
            "written": written, "timed_out": timed_out,
            "stopped_early": stopped_early}
