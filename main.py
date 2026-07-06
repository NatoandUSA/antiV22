"""Etsy niche research agent.

Commands:
  py main.py                     -> validate keywords.csv via Google Trends
  py main.py discover            -> pull live YTrends data and rank new ideas
  py main.py discover pod        -> print-on-demand keywords only
  py main.py discover embroidery -> embroidery keywords only (also: ideas pod / ideas embroidery)
  py main.py expand "keyword"    -> related keywords for a niche you like
  py main.py categories          -> which Etsy categories pay best per seller
  py main.py grow                -> auto-add viral/best-selling keywords + niches
  py main.py grow "niche keyword"       -> deep research one niche
  py main.py grow pod | grow embroidery -> auto-grow one product line
  py main.py daily [pod|embroidery]  -> THE team command: 5 clean reports
  py main.py images                  -> list AI design prompts (no API calls)
  py main.py images --all            -> generate design PNGs via OpenAI (needs OPENAI_API_KEY, costs money)
  py main.py web                     -> team report portal (read the reports in a browser; needs WEB_PASSWORD)
  py main.py rawreports [pod|embroidery] -> detailed/debug report set
  py main.py listreports         -> paths of every latest operational report
  py main.py tasks               -> daily team tasks report (9 roles)
  py main.py blockers            -> blocker report grouped by severity
  py main.py statusboard         -> product status board (csv+md+pdf)
  py main.py finalqa             -> final QA summary
  py main.py performance         -> performance report from shop_performance.csv
  py main.py openreports         -> open the latest report folder
  py main.py manager             -> Etsy Product Manager AI (full daily report)
  py main.py manager pod         -> manager for print-on-demand keywords only
  py main.py manager embroidery  -> manager for embroidery keywords only
  py main.py supplier pod "clear concert bag"        -> PULL_SUPPLIER_DETAILS_POD
  py main.py supplier embroidery "chenille name bag" -> PULL_SUPPLIER_DETAILS_EMBROIDERY
  py main.py pdfcheck            -> diagnose why PDF export fails on this PC
  py main.py selftest            -> verify the install works (no APIs needed)
  py main.py ideas               -> Best Etsy Idea Report (product clusters)
  py main.py listing "keyword"   -> complete listing draft pack (not publish-ready until QA)
  py main.py printify "pouch"    -> find Printify products + real US shipping
  py main.py printify cost 1090  -> shipping costs per print provider
"""
import csv
import sys


def load_keywords(path="keywords.csv"):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kw = (row.get("keyword") or "").strip()
            comp_raw = (row.get("competition") or "").strip()
            comp = int(comp_raw) if comp_raw.isdigit() else None
            if kw:
                rows.append((kw, comp))
    return rows


def research():
    from src.gtrends import fetch_momentum
    from src.scoring import opportunity_score
    from src.db import save_snapshot
    from src.report import write_report

    kws = load_keywords()
    print(f"Researching {len(kws)} keywords via Google Trends (takes a few minutes)...")
    stats = fetch_momentum([k for k, _ in kws])

    results = []
    for kw, comp in kws:
        s = stats.get(kw)
        if not s:
            print(f"  No trend data for: {kw}")
            continue
        results.append({
            "keyword": kw,
            "competition": comp,
            "opportunity": opportunity_score(s["avg_interest"], s["momentum_pct"], comp),
            **s,
        })

    results.sort(key=lambda r: r["opportunity"], reverse=True)
    save_snapshot([
        (r["keyword"], r["avg_interest"], r["momentum_pct"], r["competition"], r["opportunity"])
        for r in results
    ])
    path = write_report(results)

    print(f"\nDone. Full report: {path}\n")
    print("Top opportunities:")
    for i, r in enumerate(results[:10], 1):
        print(f"{i:2}. {r['keyword']:<32} "
              f"opportunity={r['opportunity']:<8} momentum={r['momentum_pct']}%")


def expand(tag):
    from src.ytrends_client import suggestions
    from src.trademark import check as tm_check
    rows = suggestions(tag)
    print(f"\nRelated keywords for '{tag}':\n")
    print(f"{'keyword':<34}{'listings':<10}{'avg rev':<10}{'conv':<8}{'TM':<9}action")
    for r in sorted(rows, key=lambda r: -(r.get("relevance_score") or 0))[:20]:
        risk, _ = tm_check(r.get("tag") or "")
        print(f"{(r.get('tag') or '')[:32]:<34}"
              f"{r.get('tag_listing_count') or '?':<10}"
              f"${r.get('avg_revenue') or 0:<9.0f}"
              f"{(r.get('avg_conversion_rate') or 0)*100:.1f}%   "
              f"{risk:<9}"
              f"{(r.get('recommended_action') or '').split(':')[0]}")


def show_categories():
    from src.ytrends_client import categories
    rows = categories()
    rows = [r for r in rows if r.get("seller_count")]
    for r in rows:
        r["rps"] = (r.get("total_revenue") or 0) / max(r["seller_count"], 1)
    rows.sort(key=lambda r: -r["rps"])
    print(f"\n{'category':<30}{'listings':<11}{'sellers':<10}{'$/seller':<11}{'conv':<8}{'competition':<12}action")
    for r in rows[:25]:
        print(f"{(r.get('category_path') or '')[:28]:<30}"
              f"{r.get('listing_count') or 0:<11}"
              f"{r.get('seller_count') or 0:<10}"
              f"${r['rps']:<10.0f}"
              f"{(r.get('avg_conversion_rate') or 0)*100:.1f}%   "
              f"{(r.get('competition_level') or ''):<12}"
              f"{(r.get('recommended_action') or '').split(':')[0]}")


# ---------------------------------------------------------------------------
# Command handlers. Every handler takes (cmd, args) where `cmd` is the command
# name (argv[1]) and `args` is the list of remaining arguments (argv[2:]).
# They are wired to command names in the COMMANDS table below.
# ---------------------------------------------------------------------------

def _usage_exit(message):
    """Print a one-line usage hint and exit with code 2 (bad invocation)."""
    print(message)
    sys.exit(2)


def cmd_pdfcheck(cmd, args):
    print(f"Python in use: {sys.executable}")
    try:
        import reportlab
        print(f"reportlab OK (version {reportlab.Version})")
    except ImportError:
        print("reportlab NOT installed for this Python.")
        print(f"Fix: \"{sys.executable}\" -m pip install reportlab")
        sys.exit(1)
    from pathlib import Path as _P
    # Write the probe outside reports/ so it never pollutes the report
    # tree that `selftest` scans for the timestamp header.
    _P("data").mkdir(exist_ok=True)
    test_md = _P("data/pdf_test.md")
    test_md.write_text("# PDF Test\n\nXin chao team! Vietnamese "
                       "text test.\n\n| A | B |\n|---|---|\n"
                       "| 1 | 2 |\n", encoding="utf-8")
    try:
        from src.pdf_export import md_to_pdf
        out = md_to_pdf(test_md)
        if out:
            print(f"SUCCESS: test PDF created at {out}")
            print("PDF export works. Rerun: python main.py allreports")
        else:
            print("md_to_pdf returned None - see message above.")
    except Exception:
        import traceback
        print("PDF generation crashed with this exact error:")
        traceback.print_exc()
        print("\nSend this error to Claude Code to fix.")


def cmd_listreports(cmd, args):
    from src.report_index import list_reports, list_reports_detailed
    if "--all" in args or "--include-selftest" in args:
        list_reports_detailed(include_selftest="--include-selftest" in args)
    else:
        list_reports()


def cmd_images(cmd, args):
    """Generate PNGs from the ChatGPT design prompts via the OpenAI API."""
    from src.image_gen import run_images
    run_images(args)


def cmd_web(cmd, args):
    """Serve the team web dashboard (run commands + read reports in a browser)."""
    from src.web import run_server
    run_server(args)


def cmd_ops(cmd, args):
    """Shared handler for tasks / blockers / statusboard / finalqa / performance."""
    from datetime import date as _date
    import src.ops_reports as ops
    _day = str(_date.today())
    _mgr = ops.load_mgr_json(_day)
    if cmd == "tasks":
        out = ops.write_daily_tasks(_day, _mgr)
    elif cmd == "blockers":
        out = ops.write_blockers(_day, _mgr)
    elif cmd == "statusboard":
        out = ops.write_statusboard(_day, _mgr)[1]
    elif cmd == "finalqa":
        out = ops.write_finalqa(_day, _mgr)
    else:  # performance
        out = ops.write_performance(_day)
    print(f"Report: {out}")
    if _mgr is None:
        print("(No manager data for today yet - report uses the "
              "no-data operational format. Run allreports first for "
              "full data.)")


def cmd_openreports(cmd, args):
    from src.report_index import open_reports
    open_reports()


def cmd_daily(cmd, args):
    """Shared handler for daily / allreports (the 5-report team set)."""
    from src.daily import run_daily
    run_daily(args[0].lower() if args else None)


def cmd_rawreports(cmd, args):
    from src.allreports import run_allreports
    run_allreports(args[0].lower() if args else None)
    print("\n(raw/debug set generated under reports/<date>/ - the "
          "team-facing set comes from: python main.py daily)")


def cmd_adhoc(cmd, args):
    """Shared handler for market / seller / designer single-report rebuilds."""
    from datetime import date as _date
    from pathlib import Path as _P
    import src.daily as dl
    from src.ops_reports import load_mgr_json
    _day = str(_date.today())
    _mgr = load_mgr_json(_day)
    if _mgr is None and not (_P("reports") / _day).exists():
        print("No data generated today yet. Run first: "
              "python main.py daily")
        sys.exit(1)
    builder = {"market": dl.build_market, "seller": dl.build_seller,
               "designer": dl.build_designer}[cmd]
    names = {"market": "02_MARKET_KEYWORD_OPPORTUNITY_REPORT",
             "seller": "03_SELLER_EXECUTION_REPORT",
             "designer": "04_DESIGNER_BRIEF_REPORT"}
    out_dir = _P("reports") / "adhoc"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = dl._emit(out_dir, names[cmd],
                 names[cmd].split("_", 1)[1].replace("_", " ").title(),
                 builder(_mgr, True, _day))
    print(f"Report: {p}")


def cmd_grow(cmd, args):
    from src.grow import harvest
    gargs = [a.strip('\'"') for a in args]
    g_mode = gargs[0].lower() if gargs and gargs[0].lower() in ("pod", "embroidery") else None
    g_seed = " ".join(gargs[1:]) if g_mode and len(gargs) > 1 else \
             (" ".join(gargs) if gargs and not g_mode else None)
    harvest(mode=g_mode, seed=g_seed or None)


def cmd_supplier(cmd, args):
    if len(args) < 2 or args[0].lower() not in ("pod", "embroidery"):
        _usage_exit('Usage: python main.py supplier pod|embroidery "keyword"')
    from src.supplier_pull import run_pull
    run_pull(args[0].lower(), " ".join(args[1:]).strip('\'"'))


def cmd_selftest(cmd, args):
    from src.selftest import run_selftest
    run_selftest()


def cmd_manager(cmd, args):
    from src.product_manager import run_manager
    run_manager(args[0].lower() if args else None)


def cmd_listing(cmd, args):
    if not args:
        _usage_exit('Usage: python main.py listing "keyword"')
    from src.listing_factory import run_listing
    run_listing(" ".join(args).strip('\'"'))


def cmd_printify(cmd, args):
    if not args:
        _usage_exit('Usage: python main.py printify "product"  |  '
                    'python main.py printify cost <blueprint_id>')
    from src.printify import search_blueprints, blueprint_costs
    if args[0] == "cost" and len(args) > 1:
        blueprint_costs(int(args[1]))
    else:
        search_blueprints(" ".join(args).strip('\'"'))


def cmd_ideas(cmd, args):
    from src.idea_report import run_ideas
    run_ideas(args[0].lower() if args else None)


def cmd_categories(cmd, args):
    show_categories()


def cmd_discover(cmd, args):
    from src.discover import run_discover
    run_discover(args[0].lower() if args else None)


def cmd_expand(cmd, args):
    if not args:
        _usage_exit('Usage: python main.py expand "keyword"')
    expand(" ".join(args).strip('\'"'))


# Single source of truth for command routing: name -> handler(cmd, args).
COMMANDS = {
    "pdfcheck": cmd_pdfcheck,
    "listreports": cmd_listreports,
    "tasks": cmd_ops, "blockers": cmd_ops, "statusboard": cmd_ops,
    "finalqa": cmd_ops, "performance": cmd_ops,
    "openreports": cmd_openreports,
    "daily": cmd_daily, "allreports": cmd_daily,
    "images": cmd_images,
    "web": cmd_web,
    "rawreports": cmd_rawreports,
    "market": cmd_adhoc, "seller": cmd_adhoc, "designer": cmd_adhoc,
    "grow": cmd_grow,
    "supplier": cmd_supplier,
    "selftest": cmd_selftest,
    "manager": cmd_manager,
    "listing": cmd_listing,
    "printify": cmd_printify,
    "ideas": cmd_ideas,
    "categories": cmd_categories,
    "discover": cmd_discover,
    "expand": cmd_expand,
}

# Commands that reach the live YTrends/Printify APIs. For YTrends-backed ones
# we fail fast with a helpful message when the API is unreachable, so the tool
# never hangs on a dead network/expired cookie.
LIVE_API_CMDS = {"grow", "listing", "discover", "ideas", "expand",
                 "categories", "supplier", "printify"}


def _live_api_guard(cmd):
    """Fail fast for YTrends-backed commands when the API is unreachable."""
    try:
        from src.ytrends_client import probe
        if cmd in ("supplier", "printify"):
            return  # Printify has its own auth errors; no YTrends needed
        if not probe():
            print(f"Cannot run '{cmd}': live YTrends API unreachable.")
            print("Fix: refresh YTRENDS_COOKIE in .env (see README) "
                  "and check your internet, then retry.")
            print("Reports that work offline: manager, allreports, "
                  "tasks, blockers, statusboard, finalqa, performance, "
                  "listreports.")
            sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        pass


def main(argv):
    try:
        from src.timestamp import set_command
        set_command("python main.py " + " ".join(argv[1:])
                    if len(argv) > 1 else "python main.py")
    except Exception:
        pass

    if len(argv) <= 1:
        # Bare command: Google Trends validation of keywords.csv.
        try:
            research()
        except ImportError as exc:
            print(f"Google Trends check unavailable: {exc}")
            print("Fix: py -m pip install pytrends")
            print("Or use: python main.py listreports / allreports / manager")
            sys.exit(1)
        return

    cmd = argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(2)

    if cmd in LIVE_API_CMDS:
        _live_api_guard(cmd)

    COMMANDS[cmd](cmd, argv[2:])


if __name__ == "__main__":
    main(sys.argv)
