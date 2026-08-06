"""Recover extension keywords that reached the master once and were destroyed.

WHY THIS EXISTS
`data/imports/ytrends_ext/*.json` holds every YTrends keyword table the team
ever captured. Those keywords were merged into the master at the time, then wiped
three times by the old PC->VPS overwrite (measured across the backups:
ext 455 -> 0 on Jul 29, 432 -> 2 on Jul 31, all non-mcp sources gone by Aug 3).
The raw payloads survived, so the keywords are recoverable from disk.

SAFE BY DEFAULT
`recover()` is a DRY RUN unless `write=True`, and a production write refuses to
start without a backup path. It touches `keyword_data.csv` and nothing else —
never app.db, agent.db or etsy.db.

IT ABORTS RATHER THAN DAMAGE
Revenue, conversion and price counts must not fall. If they would, the write is
refused and the file is left alone. This is the same guard harvest() carries,
for the same reason: an unattended rewrite that loses measured data is never
legitimate.

views_24h IS REPORTED DIFFERENTLY, ON PURPOSE
`harvest._f()` maps 0 -> None (a zero from an API means "I don't know"), so rows
holding a literal `views_24h = 0` normalise to blank on ANY write — harvest's
included. That drops the non-empty count without losing a measurement, so this
module tracks POSITIVE views instead, which is the number that must not fall.

CANONICAL DEDUPE
Dedupe uses `harvest._clean` — the same normaliser the writer uses. Comparing
with `.lower()` reported 1,432 orphans where only 1,193 were real: 239 were
keywords `_clean` rejects outright, and re-adding them would have written null
metrics over rows that already had data.
"""
import csv
import glob
import json
import os

EXT_DIR = "data/imports/ytrends_ext"
MASTER = "keyword_data.csv"
SOURCE = "ext_recovered"

# counts that may never fall on a recovery write
GUARDED = ("total_revenue", "conversion_rate", "avg_price")


def _clean(kw):
    from src import harvest as H
    return H._clean(kw)


def candidates(ext_dir=EXT_DIR):
    """{clean_key: raw_keyword} across every capture, plus a skip ledger."""
    from src import ytx_import as yi
    out, skipped = {}, {"amazon": 0, "no_headers": 0, "no_keyword_column": 0,
                        "unreadable": 0, "blank": 0}
    for f in sorted(glob.glob(os.path.join(ext_dir, "*.json"))):
        try:
            payload = json.loads(open(f, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            skipped["unreadable"] += 1
            continue
        headers = payload.get("headers") or []
        view = str(payload.get("view") or os.path.basename(f))
        if not headers:
            skipped["no_headers"] += 1
            continue
        if view.lower().startswith("amazon"):
            skipped["amazon"] += 1          # Amazon capture, not an Etsy keyword
            continue
        idx = yi._resolve(headers)
        if idx["keyword"] is None:
            skipped["no_keyword_column"] += 1
            continue
        ki = idx["keyword"]
        for row in (payload.get("rows") or []):
            if ki >= len(row):
                continue
            raw = str(row[ki] or "").strip()
            key = _clean(raw)
            if not key:
                skipped["blank"] += 1
                continue
            out.setdefault(key, raw)
    return out, skipped


def orphans(ext_dir=EXT_DIR, master=MASTER):
    """Candidates absent from the master, compared with the CANONICAL cleaner."""
    cands, skipped = candidates(ext_dir)
    have = set()
    try:
        with open(master, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                k = _clean(r.get("keyword"))
                if k:
                    have.add(k)
    except OSError:
        pass
    fresh = {k: v for k, v in cands.items() if k not in have}
    skipped["already_in_master"] = len(cands) - len(fresh)
    return fresh, skipped


def set_c(keywords):
    """The owner's strict set: things the shop can actually make.

    launchable by product_fit · multi-word · len > 2 · trademark not HIGH ·
    has a supplier product family.
    """
    from src import product_fit as pf, trademark as tm
    from src.supplier_ops import product_family
    keep, dropped = [], {"not_launchable": 0, "single_word": 0, "too_short": 0,
                         "trademark_high": 0, "no_product_family": 0}
    for kw in keywords:
        if len(kw) <= 2:
            dropped["too_short"] += 1
            continue
        if len(kw.split()) < 2:
            dropped["single_word"] += 1
            continue
        if not (pf.classify(kw, None) or {}).get("launchable"):
            dropped["not_launchable"] += 1
            continue
        if (tm.check(kw) or ("OK", ""))[0] == "HIGH":
            dropped["trademark_high"] += 1
            continue
        if product_family(kw) is None:
            dropped["no_product_family"] += 1
            continue
        keep.append(kw)
    return keep, dropped


def counts(path=MASTER):
    """Row/enrichment counts. `views_positive` is tracked separately because a
    literal 0 normalises to blank on any write (honest-nulls)."""
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    out = {"rows": len(rows),
           "unique": len({_clean(r.get("keyword")) for r in rows if _clean(r.get("keyword"))}),
           "views_positive": 0}
    for col in GUARDED:
        out[col] = sum(1 for r in rows if (r.get(col) or "").strip())
    for r in rows:
        try:
            if float(r.get("views_24h") or 0) > 0:
                out["views_positive"] += 1
        except ValueError:
            pass
    return out


def recover(keywords, path=MASTER, write=False, backup=None):
    """Union `keywords` into the master. DRY RUN unless write=True.

    Returns {"before", "after", "added", "aborted", "reason"}. A production write
    requires `backup` and refuses if a guarded count would fall.
    """
    from src import harvest as H
    before = counts(path)
    if write and not backup:
        return {"before": before, "after": before, "added": 0, "aborted": True,
                "reason": "production write requires a backup path"}

    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ext_recovery_")
    work = os.path.join(tmp, "keyword_data.csv")
    shutil.copy(path, work)
    try:
        store = {}
        for kw in keywords:
            H._add(store, kw, 0, SOURCE)         # no metrics: honest-nulls
        H.merge_existing(store, path=work)       # folds the master in, field-wise
        H.write_keyword_data(store, path=work)
        after = counts(work)
        fell = [c for c in GUARDED if after[c] < before[c]]
        if after["rows"] < before["rows"]:
            fell.append("rows")
        if after["views_positive"] < before["views_positive"]:
            fell.append("views_positive")
        if fell:
            return {"before": before, "after": after,
                    "added": after["rows"] - before["rows"], "aborted": True,
                    "reason": "would lose: " + ", ".join(
                        "%s %d->%d" % (c, before[c], after[c]) for c in fell)}
        if write:
            shutil.copy(path, backup)            # backup BEFORE the write
            shutil.copy(work, path)
        return {"before": before, "after": after,
                "added": after["rows"] - before["rows"], "aborted": False,
                "reason": None, "written": bool(write)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
