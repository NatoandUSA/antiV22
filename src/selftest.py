"""Offline self-test: verifies the whole Product Manager pipeline using
synthetic fixture data (no APIs, no network). Run: py main.py selftest
"""
import json
from pathlib import Path

import src.product_manager as pm
import src.team_packs as tp
tp.TODAY = "selftest"


def rp(cat, name):
    from pathlib import Path
    return Path("reports") / "selftest" / cat / name


def run_selftest():
    fx = json.loads(Path("tests/fixtures.json").read_text(encoding="utf-8"))
    pm.TODAY = "selftest"
    pm.load_keyword_data = lambda path="ignored": fx["keywords"]
    pm.top_listings = lambda tag, **k: fx["listings"]
    import src.signals as sig
    sig._google = lambda kws: {k: {"momentum_pct": 25.0, "avg_interest": 40}
                               for k in kws}

    print("Running offline self-test (synthetic data)...")
    pm.run_manager(data_ok=True)

    results, ok = [], True
    report = rp("manager", "manager_selftest.md")
    data_p = rp("manager", "manager_selftest.json")

    def check(name, cond):
        nonlocal ok
        results.append((name, cond))
        ok = ok and cond

    check("report file created", report.exists())
    check("json file created", data_p.exists())
    check("tasks file created", rp("tasks", "tasks_selftest.md").exists())
    if data_p.exists():
        d = json.loads(data_p.read_text(encoding="utf-8"))
        check("QA_REPORT_READY true", d["qa_checks"]["result"] == "READY")
        check("bags cluster found", (d.get("best_cluster") or {}).get("name")
              == "bags & pouches")
        rej = {r["keyword"]: r for r in d["rejected_ideas"]}
        check("service keyword skipped", "psychic reading" in rej)
        check("brand keyword blocked",
              rej.get("taylor swift hoodie", {}).get("decision") == "BLOCKED")
        check("season-passed skipped", "fathers day print" in rej)
        sus = [k for k in d["keywords"] if k["keyword"] == "weird data bag"]
        check("suspicious data flagged",
              not sus or sus[0]["data_check"] is True)
        check("5 listing packages", len(d["listing_package"]) == 5)
        check("packages have 13 tags",
              all(len(p["tags"]) == 13 for p in d["listing_package"]))
        check("packages DESIGN_PREP_READY",
              all(p["status"] == "DESIGN_PREP_READY"
                  for p in d["listing_package"]))
        check("publish blocked (supplier unconfirmed)",
              all(p["publish_status"] == "NOT_PUBLISH_READY"
                  and "supplier_confirmed" in p["blocked_by"]
                  for p in d["listing_package"]))
        check("listing_status = NEED_SUPPLIER_DETAILS",
              all(p["listing_status"] == "NEED_SUPPLIER_DETAILS"
                  for p in d["listing_package"]))
        check("production types classified",
              all(p["production_type"] in ("POD_PRINT", "EMBROIDERY",
                                           "CHENILLE_PATCH")
                  for p in d["listing_package"]))
        rep = rp("manager", "manager_selftest.md").read_text(encoding="utf-8")
        check("triple status in report",
              "QA_REPORT_READY" in rep and "PUBLISH_READY" in rep)
        check("conditional publish plan",
              "IF PUBLISH_READY = true" in rep)
        check("design prompts file created",
              rp("design", "design_prompts_selftest.md").exists())
        check("seller pack file created",
              rp("seller", "seller_pack_selftest.md").exists())
        check("seller pack VI created",
              rp("seller", "seller_pack_selftest_VI.md").exists())
        check("design prompts VI created",
              rp("design", "design_prompts_selftest_VI.md").exists())
        check("Vietnamese manager report created",
              rp("manager", "manager_selftest_VI.md").exists())
        dp = rp("design", "design_prompts_selftest.md").read_text(encoding="utf-8")
        check("prompts include market data",
              "ETSY MARKET DATA" in dp and "STRICTLY AVOID" in dp)
        vi = rp("manager", "manager_selftest_VI.md").read_text(encoding="utf-8")
        check("VI report translated",
              "Trang thai bao cao" in vi and "KHONG dang" in vi)
        check("sales execution summary present",
              "Sales Execution Summary" in rep and "What to sell" in rep)
        check("multi-source signal check present",
              "Multi-Source Signal Check" in rep and "CONFIRMED" in rep)
        check("competitive edge plan present",
              "Competitive Edge Plan" in rep and "Owner" in rep)
        check("edges injected into design prompts",
              "COMPETITIVE EDGE TO EXPRESS" in dp)
        check("no false PUBLISH_READY",
              d["qa_checks"]["checks"]["no_false_publish_ready"])
        # V18 acceptance criteria
        from src.version import VERSION
        check("version consistent in report", VERSION in rep)
        check("flagged keyword is NOT primary",
              "weird data bag" not in json.dumps(d["product_ideas"])
              and all("weird data bag" not in p["seo_title"]
                      for p in d["listing_package"]))
        from src.validators import validate_title, validate_tags
        vok, _ = validate_title("Bag Bag Bag Custom Bag Personalized Bag, "
                                "Cute Bag, Gift Bag, Best Bag, Trendy Bag, "
                                "New Bag, Nice Bag Pouch")
        check("stuffed title FAILS validation", not vok)
        vok, _ = validate_title("Personalized Clear Concert Bag with Name - "
                                "Stadium Approved Festival Purse")
        check("clean title PASSES validation", vok)
        vok, _ = validate_tags(["clear bag"] * 13)
        check("duplicate tags FAIL validation", not vok)
        vok, _ = validate_tags(["clear concert bag"] * 6 + ["a"] * 6)
        check("12 tags FAIL validation", not vok)
        from src.publish_gate import publish_gate
        g = publish_gate({"title": "Personalized Clear Concert Bag with "
                          "Name - Stadium Purse", "tags": ["x"] * 13,
                          "supplier_status": "SUPPLIER_PARTIAL",
                          "supplier_record": {}, "tm_states": ["TM_BLOCKED"],
                          "description": "d"})
        check("trademark blocks -> final BLOCKED",
              g["final_status"] == "BLOCKED")
        g2 = publish_gate({"title": "Personalized Clear Concert Bag with "
                           "Name - Stadium Purse", "tags": ["x"] * 13,
                           "supplier_status": "SUPPLIER_PARTIAL",
                           "supplier_record": {},
                           "tm_states": ["TM_VERIFIED_CLEAR"],
                           "description": "d"})
        check("missing supplier -> INSUFFICIENT_DATA",
              g2["final_status"] == "INSUFFICIENT_DATA"
              and "supplier_confirmed" in g2["blocked_by"])
        check("partner disclosure gate exists",
              "production_partner_disclosed" in g2["gates"])
        check("audit OK recognized (no false blocker)",
              "competitor audit incomplete (COMPETITOR_AUDIT_OK)" not in rep)
        # V19 acceptance criteria
        exec_sec = rep.split("Sales Execution Summary")[1].split("## 2")[0] \
            if "Sales Execution Summary" in rep else ""
        check("flagged keyword NOT in exec summary",
              "weird data bag" not in exec_sec)
        check("publish gate dashboard present",
              "Publish Gate Dashboard" in rep
              and "Next required action" in rep)
        check("explicit no-publish-ready line",
              "No products are publish-ready today." in rep)
        sp_pack = rp("seller", "seller_pack_selftest.md").read_text(
            encoding="utf-8")
        check("seller pack: draft/publish allowed lines",
              "Draft allowed:" in sp_pack and "Publish allowed: NO" in sp_pack)
        check("seller pack: no unconditional after-publish language",
              "POST-PUBLISH ACTIONS: hidden until final QA status is PUBLISH_READY" in sp_pack)
        check("seller pack blocks placeholder customer copy",
              "DESCRIPTION - COPY BLOCKED" in sp_pack
              and "NEED_SUPPLIER_DETAILS (material & size from supplier page)" not in sp_pack)
        from src.discover import listing_relevance
        rel, _ = listing_relevance("summer pouch", {
            "title": "Avoidant to Obsessed Love Spell Twin Flame Ritual",
            "tags": ["love spell", "witchcraft", "twin flame"],
        })
        check("discover rejects irrelevant love-spell listings", rel == 0.0)
        rel2, _ = listing_relevance("summer pouch", {
            "title": "Personalized Summer Pouch Makeup Bag",
            "tags": ["summer pouch", "makeup bag"],
        })
        check("discover accepts relevant product listings", rel2 >= 0.75)
        tasks = rp("tasks", "tasks_selftest.md").read_text(encoding="utf-8")
        check("TM task table complete or explicit none",
              "Required decision" in tasks
              and ("| CLEAR / CAUTION / BLOCKED |" in tasks
                   or "(none today" in tasks))
        from src.publish_gate import publish_gate, partner_status
        g3 = publish_gate({"title": "Personalized Clear Concert Bag with "
                           "Name - Stadium Purse", "tags": ["x"] * 13,
                           "supplier_status": "SUPPLIER_CONFIRMED",
                           "supplier_record": {"production_partner_required":
                                               "yes"},
                           "tm_states": ["TM_VERIFIED_CLEAR"],
                           "description": "d"})
        check("partner 4-state: REQUIRED_NOT_DISCLOSED",
              g3["production_partner_status"] == "REQUIRED_NOT_DISCLOSED")
        check("field-level supplier gates exist",
              all(k in g3["gates"] for k in
                  ("material_verified", "base_cost_verified",
                   "processing_time_verified")))
        from src.discover import age_bucket, age_profile
        check("age buckets correct",
              age_bucket(5) == "1 week old" and age_bucket(12) == "2 weeks old"
              and age_bucket(60) == "under 3 months"
              and age_bucket(200) == "over 3 months")
        ap = age_profile([{"age_days": 6}, {"age_days": 300}])
        check("fresh winner detected", "FRESH WINNER" in ap["label"])

    # timestamp acceptance criteria
    import re
    md_files = [f for f in Path("reports").rglob("*.md") if "latest" not in f.parts]
    stamped = [f for f in md_files
               if f.read_text(encoding="utf-8").startswith("Generated on: ")]
    check("every .md report starts with timestamp header",
          len(md_files) > 0 and len(stamped) == len(md_files))
    sample_txt = md_files[0].read_text(encoding="utf-8") if md_files else ""
    check("timestamp includes seconds + ICT label",
          bool(re.search(r"Generated on: \d{4}-\d{2}-\d{2} "
                         r"\d{2}:\d{2}:\d{2} ICT", sample_txt)))
    check("timezone line present",
          "Timezone: Asia/Ho_Chi_Minh" in sample_txt)
    from src.version import VERSION
    check("tool version in header", f"Tool version: {VERSION}" in sample_txt)
    check("report type + command lines present",
          "Report type: " in sample_txt and "Command: " in sample_txt)
    vi_hdr = rp("manager", "manager_selftest_VI.md").read_text(
        encoding="utf-8")[:300]
    en_hdr = rp("manager", "manager_selftest.md").read_text(
        encoding="utf-8")[:300]
    same_time = re.search(r"Generated on: (.+)", en_hdr).group(1) == \
        re.search(r"Generated on: (.+)", vi_hdr).group(1)
    check("EN and VI share the same timestamp", same_time)
    check("VI header labeled VI", "Report type: Manager Report VI" in vi_hdr)
    # manifest format (direct writer test, no live APIs)
    import src.allreports as ar
    import src.product_manager as pmod
    ar.run_manifest_ok = True
    from src.timestamp import get_report_timestamp
    mpath = rp("index", "manifest_selftest.md")
    mpath.parent.mkdir(parents=True, exist_ok=True)
    s = get_report_timestamp()
    mpath.write_text("placeholder", encoding="utf-8")
    mpath.write_text(
        f"# Report Manifest\n- Generation start: {s['display']}\n"
        f"- Generation end: {s['display']}\n"
        f"- Total generation duration: 0.1 seconds\n", encoding="utf-8")
    from src.timestamp import stamp_file
    stamp_file(mpath, "Report Manifest")
    mtxt = mpath.read_text(encoding="utf-8")
    check("manifest has start/end/duration + stamp",
          "Generation start:" in mtxt and "Generation end:" in mtxt
          and "duration:" in mtxt and mtxt.startswith("Generated on: "))
    check("json carries generation timestamp",
          "generated_on" in json.dumps(d) and "tool_version" in json.dumps(d))

    # ---- V19.4: operational workflow acceptance criteria ----
    import shutil as _sh
    import src.report_index as ri
    import src.allreports as ar
    check("listreports command exists (module callable)",
          callable(ri.list_reports) and callable(ri.scan_latest))
    # selftest folder must never be operational-latest
    check("selftest folder ignored by latest_day_dir",
          ri.latest_day_dir() is None
          or ri.latest_day_dir().name != "selftest")
    check("scan_latest empty when only selftest exists",
          ri.latest_day_dir() is not None or ri.scan_latest() == {})
    # openreports must not claim success when no launcher exists
    real_which = _sh.which
    import src.report_index as _ri2
    _ri2.shutil.which = lambda *_: None
    _had_startfile = hasattr(_ri2.os, "startfile")
    _real_startfile = getattr(_ri2.os, "startfile", None)

    def _boom(*_a, **_k):
        raise OSError("simulated launcher failure")
    _ri2.os.startfile = _boom
    res = ri.open_reports(really_open=True)
    _ri2.shutil.which = real_which
    if _had_startfile:
        _ri2.os.startfile = _real_startfile
    else:
        del _ri2.os.startfile
    check("openreports does not claim success when launch fails",
          isinstance(res, dict) and res["claimed_open"] is False)
    check("report_type_for handles Windows backslash paths",
          __import__("src.timestamp", fromlist=["report_type_for"])
          .report_type_for(r"reports\selftest\manager\manager_x.md")
          == "Manager Report")
    # simulated OPERATIONAL run with no data: every category still exists
    test_day = "2026-01-01"
    ar.TODAY = test_day
    t_start = __import__("time").time()
    man_path = ar.run_allreports(data_ok=False)
    elapsed = __import__("time").time() - t_start
    check("allreports does not hang without data (fast fail)",
          elapsed < 25)
    mtxt = Path(man_path).read_text(encoding="utf-8")
    check("manifest written even when data missing",
          Path(man_path).exists() and "Generation start:" in mtxt)
    check("clear no-data error in manifest",
          "NO LIVE DATA THIS RUN" in mtxt)
    day_root = Path("reports") / test_day
    for cat, fname in (("manager", f"manager_{test_day}.md"),
                       ("tasks", f"daily_tasks_{test_day}.md"),
                       ("blockers", f"blocker_report_{test_day}.md"),
                       ("design", f"design_prompts_{test_day}.md"),
                       ("seller", f"seller_pack_{test_day}.md"),
                       ("ideas", f"ideas_{test_day}.md"),
                       ("discover", f"discover_{test_day}.md"),
                       ("listing", f"listing_nodata_{test_day}.md"),
                       ("final_qa", f"final_qa_summary_{test_day}.md"),
                       ("performance",
                        f"performance_report_{test_day}.md")):
        check(f"no-data {cat} report exists",
              (day_root / cat / fname).exists())
    nod_mgr = (day_root / "manager" / f"manager_{test_day}.md"
               ).read_text(encoding="utf-8")
    check("no-data manager uses DATA_UNAVAILABLE format",
          "DATA_UNAVAILABLE" in nod_mgr
          and "Required Team Actions" in nod_mgr)
    check("no-data manager has VI sibling",
          (day_root / "manager" / f"manager_{test_day}_VI.md").exists())
    tasks_txt = (day_root / "tasks" / f"daily_tasks_{test_day}.md"
                 ).read_text(encoding="utf-8")
    check("daily tasks covers all 9 roles + no-task fallback",
          all(r in tasks_txt for r in ("Manager", "Claude Operator",
              "Researcher", "Supplier Checker", "Designer", "Seller",
              "QA", "Performance Analyst"))
          and "No tasks today." in tasks_txt)
    blk = (day_root / "blockers" / f"blocker_report_{test_day}.md"
           ).read_text(encoding="utf-8")
    check("blocker report grouped by severity with critical no-data",
          "## Critical" in blk and "DATA_UNAVAILABLE" in blk)
    sb = day_root / "status_board"
    check("status board csv+md exist",
          (sb / "product_status_board.csv").exists()
          and (sb / "product_status_board.md").exists())
    fqa = (day_root / "final_qa" / f"final_qa_summary_{test_day}.md"
           ).read_text(encoding="utf-8")
    check("final QA says none in QA / none publish-ready",
          "No products are in FINAL_QA today." in fqa
          and "No products are publish-ready today." in fqa)
    check("listreports now points to date folder, not selftest",
          ri.latest_day_dir() is not None
          and ri.latest_day_dir().name == test_day)
    pass
    check("research report exists (combined)",
          (day_root / "research" / f"research_report_{test_day}.md"
           ).exists())
    rr = (day_root / "research" / f"research_report_{test_day}.md"
          ).read_text(encoding="utf-8")
    check("research report has 3 parts",
          "PART 1" in rr and "PART 2" in rr and "PART 3" in rr)
    pass
    check("manifest lists files generated this run",
          "| File | Report type |" in mtxt)
    # manager command does not hang without data
    pm.TODAY = "2026-01-02"
    t2 = __import__("time").time()
    pm.run_manager(data_ok=False)
    check("manager does not hang when data missing",
          __import__("time").time() - t2 < 20
          and (Path("reports/2026-01-02/manager/manager_2026-01-02.md")
               .exists()))
    pm.TODAY = "selftest"
    # commands registered + version consistency
    main_src = Path("main.py").read_text(encoding="utf-8")
    check("tasks/blockers/statusboard/finalqa/performance commands exist",
          all(f'"{c}"' in main_src for c in
              ("tasks", "blockers", "statusboard", "finalqa",
               "performance")))
    check("README version matches src/version.py",
          VERSION in Path("README.md").read_text(encoding="utf-8"))
    # V20 deploy-readiness checks
    check("requirements.txt exists with core deps",
          Path("requirements.txt").exists() and all(
              d in Path("requirements.txt").read_text()
              for d in ("requests", "python-dotenv")))
    check("live-API commands have hang guard in main",
          "LIVE_API_CMDS" in main_src and "probe" in main_src)
    check("bare command guards missing pytrends",
          "pip install pytrends" in main_src)
    check("user guide exists",
          Path("USER_GUIDE.md").exists())
    pass
    # cleanup simulated operational runs (never the real reports/latest)
    for d in ("2026-01-01", "2026-01-02"):
        _sh.rmtree(Path("reports") / d, ignore_errors=True)
    Path("reports/adhoc").exists() and _sh.rmtree("reports/adhoc",
                                              ignore_errors=True)

    def _snapshot(p):
        """Names+mtimes of files under a folder (recursive), or None."""
        p = Path(p)
        if not p.exists():
            return None
        return sorted((str(f.relative_to(p)), f.stat().st_mtime_ns)
                      for f in p.rglob("*") if f.is_file())
    _real_latest_before = _snapshot("reports/latest")

    # ---- V20.1-FINAL: clean 5-report daily system ----
    import io as _io
    import contextlib as _ctx
    import src.daily as dl
    ar.TODAY = "2026-01-03"
    run_dir = dl.run_daily(data_ok=False,
                           runs_root="reports/selftest_runs",
                           latest_dir="reports/selftest_latest")
    five = [run_dir / f"{n}.md" for n in dl.MAIN_FILES]
    check("daily creates exactly 5 md in a run folder",
          all(f.exists() for f in five))
    check("run folder name has date+time+version",
          "2026-" in run_dir.name and VERSION in run_dir.name
          and len(run_dir.name.split("_")[1]) == 6)
    check("detailed reports archived inside run folder",
          (run_dir / "archive_debug_reports" / "2026-01-03").exists())
    sh_txt = (run_dir / "00_START_HERE.md").read_text(encoding="utf-8")
    check("START_HERE has command order",
          "# Command Order" in sh_txt and "selftest" in sh_txt
          and "python main.py daily" in sh_txt)
    check("START_HERE has report reading order with ranks",
          "# Report Reading Order" in sh_txt
          and "| 1 | 01_MANAGER_ACTION_REPORT" in sh_txt
          and "| 4 | 04_DESIGNER_BRIEF_REPORT" in sh_txt)
    check("START_HERE has status summary + top 5 actions + safety",
          "Today's Status Summary" in sh_txt
          and "Today's Top 5 Actions" in sh_txt
          and "PUBLISH_READY = true" in sh_txt)
    for n, rank in (("01_MANAGER_ACTION_REPORT", "1"),
                    ("02_MARKET_KEYWORD_OPPORTUNITY_REPORT", "2"),
                    ("03_SELLER_EXECUTION_REPORT", "3"),
                    ("04_DESIGNER_BRIEF_REPORT", "4")):
        txt = (run_dir / f"{n}.md").read_text(encoding="utf-8")
        check(f"{n[:2]} report is rank {rank} with timestamp",
              f"Report rank: {rank} of 4" in txt
              and txt.startswith("Generated on: "))
    check("no-data daily still generated all 5 with DATA_UNAVAILABLE",
          all("DATA_UNAVAILABLE" in (run_dir / f"{n}.md"
              ).read_text(encoding="utf-8")
              for n in dl.MAIN_FILES))
    check("latest mirror has the 5 reports + run info",
          all((Path("reports/selftest_latest") / f"{n}.md").exists()
              for n in dl.MAIN_FILES)
          and (Path("reports/selftest_latest") / "_run_info.txt").exists())
    check("selftest did NOT touch real reports/latest",
          _snapshot("reports/latest") == _real_latest_before)
    # data-mode composition checks from the fixture manager json
    mgr_fix = json.loads(rp("manager", "manager_selftest.json"
                            ).read_text(encoding="utf-8"))
    mk = "\n".join(dl.build_market(mgr_fix, True, "selftest"))
    check("market report ranks keywords 1,2,3",
          "| 1 | " in mk and "| 2 | " in mk and "| 3 | " in mk)
    check("market report separates flagged keywords",
          "Keywords Requiring Verification" in mk
          and "weird data bag" in mk)
    sl = "\n".join(dl.build_seller(mgr_fix, True, "selftest"))
    check("seller report separates draft vs publish + must-not list",
          "Draft Allowed" in sl and "Publish Allowed" in sl
          and "Do not publish unless" in sl)
    fake_blocked = {"listing_package": [{"product_name": "Bad Product",
                    "status": "NEEDS_FIX", "final_status": "BLOCKED",
                    "listing_status": "BLOCKED", "blocked_by": ["trademark_clear"],
                    "publish_gates": {}, "publish_status": "NOT_PUBLISH_READY"}],
                    "product_ideas": []}
    dz = "\n".join(dl.build_designer(fake_blocked, True, "selftest"))
    check("designer gives NO tasks for blocked products",
          "| Bad Product | NO | BLOCKED - do not design" in dz
          and "No design prompts issued" in dz)
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        ri.list_reports(latest_dir="reports/selftest_latest")
    lr = buf.getvalue()
    check("listreports is simple (5 files, no debug flood)",
          "READ FIRST" in lr and "01_MANAGER_ACTION_REPORT" in lr
          and "Blocker Report" not in lr and "Status Board" not in lr)
    main_src2 = Path("main.py").read_text(encoding="utf-8")
    check("daily + rawreports commands exist",
          '"daily"' in main_src2 and '"rawreports"' in main_src2)
    _sh.rmtree("reports/selftest_runs", ignore_errors=True)
    _sh.rmtree("reports/selftest_latest", ignore_errors=True)

    # ---- V20.3: supplier data integration ----
    import csv as _csv
    cat = Path("data/supplier_catalog.csv")
    n_sup = 0
    if cat.exists():
        with open(cat, newline="", encoding="utf-8") as f:
            n_sup = sum(1 for _ in _csv.DictReader(f))
    check("supplier catalog registry exists (7+ suppliers)", n_sup >= 7)

    shine = Path("data/shineon_products.csv")
    shine_ok = False
    if shine.exists():
        with open(shine, newline="", encoding="utf-8") as f:
            sr = list(_csv.DictReader(f))
        shine_ok = len(sr) >= 900 and any(
            (r.get("base_cost_usd") or "").strip() for r in sr)
    check("ShineOn products imported with base costs (900+)", shine_ok)

    emb = Path("data/embroidery_supplier_prices.csv")
    emb_txt = emb.read_text(encoding="utf-8") if emb.exists() else ""
    check("embroidery supplier prices imported (shipping INCLUDED)",
          "INCLUDED" in emb_txt and "TSHIRT" in emb_txt.upper())

    from src.team_packs import EMB_SPEC
    check("design prompts carry real embroidery areas",
          "250mm" in EMB_SPEC and "120mm" in EMB_SPEC and "56-58cm" in EMB_SPEC)

    # ---- V20.4: live YTrends MCP + Market Pulse + cross-check (offline) ----
    from src import ytrends_mcp as _mcp
    check("YTrends MCP client wired (required tools + typed helpers)",
          {"ytrends_find_trending_keywords", "ytrends_find_hidden_gems"}
          <= _mcp.REQUIRED_TOOLS
          and callable(_mcp.trending_keywords)
          and callable(_mcp.market_snapshot))

    from src import crosscheck as _cc
    check("cross-check sources present (Google Trends + Pinterest + X)",
          set(_cc.status()) == {"Google Trends", "Pinterest", "X / Twitter"}
          and callable(_cc.confirm))

    from src import market_pulse as _mp
    check("Market Pulse builder is mode-aware (POD + Embroidery)",
          callable(_mp.build_market_pulse)
          and _mp.MODE_LABEL.get("pod") == "Print on Demand"
          and _mp.MODE_LABEL.get("embroidery") == "Embroidery")

    _daily_src = Path("src/daily.py").read_text(encoding="utf-8")
    _web_src = Path("src/web.py").read_text(encoding="utf-8")
    check("Market Pulse wired into daily build + team portal",
          "build_market_pulse" in _daily_src
          and '"market_pulse"' in _daily_src
          and "market_pulse.md" in _web_src)

    _env_ex = Path(".env.example").read_text(encoding="utf-8")
    check("cross-check tokens documented in .env.example",
          "PINTEREST_ACCESS_TOKEN" in _env_ex and "X_BEARER_TOKEN" in _env_ex)

    # ---- V20.5: MCP keyword harvester feeds the reports ----
    from src import harvest as _hv
    _main_src = Path("main.py").read_text(encoding="utf-8")
    check("keyword harvester wired (writes keyword_data.csv + harvest command)",
          callable(_hv.harvest) and callable(_hv.write_keyword_data)
          and "keyword" in _hv.KDATA_FIELDS and '"harvest"' in _main_src)

    from src.idea_report import DEMAND_FLOOR
    _idea_src = Path("src/idea_report.py").read_text(encoding="utf-8")
    check("ideas report reads harvested pool + niche demand floor",
          "keyword_data.csv" in _idea_src
          and bool(DEMAND_FLOOR.get("embroidery")))

    print("\nSELF-TEST RESULTS")
    for name, cond in results:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    print(f"\n{'ALL CHECKS PASSED - install is healthy' if ok else 'SOME CHECKS FAILED - paste this output into Claude Code to fix'}")
    return ok
