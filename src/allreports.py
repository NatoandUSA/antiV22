"""allreports: generate EVERY report in one command, never hang,
never fail silently, always leave a manifest explaining what happened.

  py main.py allreports [pod|embroidery]
"""
import json
import shutil
import time
from datetime import date
from pathlib import Path

from src.report_paths import rdir
from src.timestamp import (get_report_timestamp, stamp_file,
                           report_type_for, get_command, data_is_fresh)
from src.version import VERSION

TODAY = str(date.today())


def data_available():
    """(ok, reason). True if fresh local data OR live API reachable."""
    p = Path("keyword_data.csv")
    if p.exists():
        try:
            import csv
            with p.open(newline="", encoding="utf-8") as f:
                dates = [r.get("collected_at", "")
                         for r in csv.DictReader(f)]
            if data_is_fresh(dates):
                return True, "recent keyword_data.csv (within freshness window)"
        except Exception:
            pass
    try:
        from src.ytrends_client import probe
        if probe():
            return True, "live YTrends API reachable"
    except Exception:
        pass
    return False, ("no fresh keyword_data.csv and live YTrends API "
                   "unreachable (check .env cookie/token and internet)")


def run_allreports(mode=None, data_ok=None):
    start_ts = get_report_timestamp()
    t0 = time.time()
    root = Path("reports")
    before = set(root.rglob("*")) if root.exists() else set()
    ran, failed = [], []

    if data_ok is None:
        data_ok, reason = data_available()
    else:
        reason = "forced by caller (test mode)"
    print(f"Data check: {'OK' if data_ok else 'UNAVAILABLE'} - {reason}")

    def step(name, fn, needs_data=True):
        if needs_data and not data_ok:
            failed.append((name, f"skipped: {reason}"))
            print(f"  [{name}] SKIPPED - {reason}")
            return None
        try:
            out = fn()
            ran.append(name)
            return out
        except SystemExit as exc:
            failed.append((name, str(exc)[:150]))
            print(f"  [{name}] stopped: {str(exc)[:100]}")
        except Exception as exc:
            failed.append((name, f"{type(exc).__name__}: {exc}"[:150]))
            print(f"  [{name}] FAILED: {exc}")
        return None

    def _manager():
        from src.product_manager import run_manager
        run_manager(mode, data_ok=True)
    step("manager (+design prompts, seller pack, tasks, json)", _manager)

    def _ideas():
        from src.idea_report import run_ideas
        run_ideas(mode)
    step("ideas", _ideas)

    def _discover():
        from src.discover import run_discover
        run_discover(mode)
    step("discover", _discover)

    def _listing():
        mgr_json = rdir(TODAY, "manager") / f"manager_{TODAY}.json"
        if not mgr_json.exists():
            raise RuntimeError("manager json missing - listing pack needs "
                               "the best cluster's primary keyword")
        d = json.loads(mgr_json.read_text(encoding="utf-8"))
        kws = sorted(d.get("keywords", []),
                     key=lambda x: -(x.get("views_24h") or 0))
        clean = [k for k in kws if not k.get("data_check")]
        if not clean:
            raise RuntimeError("no clean keyword available")
        from src.listing_factory import run_listing
        run_listing(clean[0]["keyword"])
    step("listing pack (best clean keyword)", _listing)

    # ---- operational reports: generated EVERY run, data or not ----
    import src.ops_reports as ops
    mgr = ops.load_mgr_json(TODAY) if data_ok else None
    nodata_reason = reason if not data_ok else ""

    if not data_ok:
        step("manager (no-data operational report)",
             lambda: ops.write_nodata_manager(TODAY, reason),
             needs_data=False)
        for cat, fname, title, rtype in (
                ("design", f"design_prompts_{TODAY}.md", "Design Prompts",
                 "Design Prompts"),
                ("seller", f"seller_pack_{TODAY}.md", "Seller Pack",
                 "Seller Pack"),
                ("ideas", f"ideas_{TODAY}.md", "Ideas Report",
                 "Ideas Report"),
                ("discover", f"discover_{TODAY}.md", "Discover Report",
                 "Discover Report"),
                ("listing", f"listing_nodata_{TODAY}.md", "Listing Pack",
                 "Listing Pack")):
            step(f"{cat} (no-data report)",
                 lambda c=cat, f=fname, t=title, rt=rtype:
                 ops.write_nodata_generic(TODAY, c, f, t, rt,
                                          nodata_reason),
                 needs_data=False)

    step("daily team tasks",
         lambda: ops.write_daily_tasks(TODAY, mgr, nodata_reason),
         needs_data=False)
    step("blocker report",
         lambda: ops.write_blockers(TODAY, mgr, nodata_reason),
         needs_data=False)
    step("product status board (csv+md+pdf)",
         lambda: ops.write_statusboard(TODAY, mgr), needs_data=False)
    step("final QA summary",
         lambda: ops.write_finalqa(TODAY, mgr, nodata_reason),
         needs_data=False)
    step("performance report",
         lambda: ops.write_performance(TODAY, nodata_reason),
         needs_data=False)
    step("research report (ideas + discover + performance combined)",
         lambda: ops.write_research_report(TODAY), needs_data=False)

    # ---- manifest (always written, even if everything failed) ----
    end_ts = get_report_timestamp()
    duration = round(time.time() - t0, 1)
    new_files = sorted(
        [f for f in (set(root.rglob("*")) - before)
         if f.is_file() and "latest" not in f.parts],
        key=lambda p: str(p))

    mpath = rdir(TODAY, "index") / f"manifest_{TODAY}.md"
    L = [f"# Report Manifest - {TODAY}", "",
         f"- Generation start: {start_ts['display']}",
         f"- Generation end: {end_ts['display']}",
         f"- Total generation duration: {duration} seconds",
         f"- Tool version: {VERSION}",
         f"- Command: {get_command()}",
         f"- Data availability: {'OK' if data_ok else 'UNAVAILABLE'} "
         f"({reason})",
         f"- Steps completed: {', '.join(ran) or 'NONE'}",
         "- Steps failed/skipped: "
         + ("; ".join(f"{n} -> {w}" for n, w in failed)
            if failed else "none"), ""]
    if not data_ok:
        L += ["**NO LIVE DATA THIS RUN.** Fix: log in to trends.ytuong.ai, "
              "refresh the cookie in .env (see README), or restore a fresh "
              "keyword_data.csv, then rerun `python main.py allreports`.",
              ""]
    L += ["## Files generated this run", "",
          "| File | Report type | PDF |", "|---|---|---|"]
    for f in new_files:
        if f.suffix == ".md":
            pdf = f.with_suffix(".pdf")
            L.append(f"| {f} | {report_type_for(f)} | "
                     f"{'yes' if pdf.exists() else '**MISSING - PDF export failed, keep the .md**'} |")
    if not any(f.suffix == ".md" for f in new_files):
        L.append("| (no report files generated) | - | - |")
    mpath.write_text("\n".join(L), encoding="utf-8")
    stamp_file(mpath, "Report Manifest", end_ts)
    try:
        from src.pdf_export import md_to_pdf
        if not md_to_pdf(mpath):
            print("  MANIFEST PDF FAILED - Markdown kept: install reportlab")
    except Exception as exc:
        print(f"  MANIFEST PDF FAILED ({exc}) - Markdown kept at {mpath}")

    print(f"\nMANIFEST: {mpath}")
    print(f"  start {start_ts['display']} -> end {end_ts['display']} "
          f"({duration}s)")
    return mpath
