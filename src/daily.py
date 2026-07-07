"""`python main.py daily` - THE team command (V20.1-FINAL).

Generates exactly 5 clean files (md+pdf each), grouped per run:

  reports/runs/YYYY-MM-DD_HHMMSS_<VERSION>/
    00_START_HERE
    01_MANAGER_ACTION_REPORT
    02_MARKET_KEYWORD_OPPORTUNITY_REPORT
    03_SELLER_EXECUTION_REPORT
    04_DESIGNER_BRIEF_REPORT
    raw_data/               (input csv snapshots)
    archive_debug_reports/  (all detailed reports of this run)

reports/latest/ always mirrors the newest real run. Works with or
without live data (DATA_UNAVAILABLE format).
"""
import shutil
from pathlib import Path

from src.ops_reports import _pdf, _strip_stamp, load_mgr_json
from src.timestamp import get_report_timestamp, stamp_file
from src.version import VERSION

MAIN_FILES = ["00_START_HERE", "01_MANAGER_ACTION_REPORT",
              "02_MARKET_KEYWORD_OPPORTUNITY_REPORT",
              "03_SELLER_EXECUTION_REPORT", "04_DESIGNER_BRIEF_REPORT"]

# Detailed reports every `daily` run also produces (in reports/<day>/<cat>/).
# We copy the newest of each to reports/latest under a stable canonical name
# so the team portal + the sync surface them, not just the clean 5.
# (category folder, filename prefix, canonical name in reports/latest)
EXTRA_LATEST = [
    ("research", "research_report_", "research_report"),
    ("manager", "manager_", "manager_report"),
    ("ideas", "ideas_", "ideas_report"),
    ("discover", "discover_", "discover_report"),
    ("seller", "seller_pack_", "seller_pack"),
    ("design", "design_prompts_", "design_prompts"),
    ("design", "chatgpt_prompts_", "chatgpt_prompts"),
    ("listing", "listing_", "listing_pack"),
    ("tasks", "daily_tasks_", "daily_tasks"),
    ("blockers", "blocker_report_", "blocker_report"),
    ("status_board", "product_status_board", "product_status_board"),
    ("final_qa", "final_qa_summary_", "final_qa"),
    ("performance", "performance_report_", "performance_report"),
]


def _pick_report(folder, prefix):
    """Newest .md in folder starting with prefix; prefer an _EN variant,
    never a _VI (Vietnamese) one. Returns a Path or None."""
    if not folder.exists():
        return None
    cands = [p for p in folder.glob(f"{prefix}*.md")
             if not p.stem.endswith("_VI")]
    if not cands:
        return None
    english = [p for p in cands if p.stem.endswith("_EN")]
    pool = english or cands
    return max(pool, key=lambda p: p.stat().st_mtime)

NO_DATA = ("DATA_UNAVAILABLE\n\n"
           "No fresh keyword_data.csv and live API unavailable.\n"
           "No product can move forward today.\n"
           "Fix owner: Claude Operator (refresh YTRENDS_COOKIE in .env) "
           "or Researcher (provide keyword_data.csv).")


def _read(path):
    p = Path(path)
    return _strip_stamp(p.read_text(encoding="utf-8")) if p.exists() else ""


def _emit(run_dir, name, report_type, lines):
    p = run_dir / f"{name}.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    stamp_file(p, report_type)
    _pdf(p)
    return p


def _counts(mgr):
    z = {"reviewed": 0, "blocked": 0, "data_check": 0, "supplier": 0,
         "tmip": 0, "design": 0, "draft": 0, "qa": 0, "publish": 0}
    if not mgr:
        return z
    pkgs = mgr.get("listing_package", [])
    g = lambda p, k: p.get("publish_gates", {}).get(k, True)
    z["reviewed"] = len(pkgs)
    z["blocked"] = sum(1 for p in pkgs if p.get("final_status") == "BLOCKED")
    z["data_check"] = sum(1 for p in pkgs if not g(p, "no_flagged_data")
                          or not g(p, "keyword_data_verified"))
    z["supplier"] = sum(1 for p in pkgs if not g(p, "supplier_confirmed"))
    z["tmip"] = sum(1 for p in pkgs
                    if not g(p, "trademark_verified_or_approved"))
    z["design"] = sum(1 for p in pkgs
                      if p.get("status") == "DESIGN_PREP_READY")
    z["draft"] = sum(1 for p in pkgs
                     if p.get("status") == "DESIGN_PREP_READY"
                     and p.get("final_status") != "BLOCKED")
    z["qa"] = sum(1 for p in pkgs
                  if p.get("blocked_by") == ["manual_review_complete"])
    z["publish"] = sum(1 for p in pkgs
                       if p.get("publish_status") == "PUBLISH_READY")
    return z


def _status_table(c, data_ok):
    L = ["| Status | Value |", "|---|---:|",
         f"| Products reviewed | {c['reviewed']} |",
         f"| Products blocked | {c['blocked']} |",
         f"| Products needing data check | {c['data_check']} |",
         f"| Products design-prep-ready | {c['design']} |",
         f"| Products listing-draft-ready | {c['draft']} |",
         f"| Products in final QA | {c['qa']} |",
         f"| Products publish-ready | {c['publish']} |"]
    if not data_ok:
        L = ["", NO_DATA, ""] + L
    return L


# ------------------------- 00 START HERE -------------------------

def build_start_here(mgr, data_ok, run_dir):
    c = _counts(mgr)
    L = ["# START HERE - Etsy Product Manager", "",
         "# Command Order", "",
         "## First-time setup or after every update",
         "1. `python main.py selftest`",
         "Why: checks the tool, report generation, PDF export, and safety "
         "gates are healthy before the team uses it.", "",
         "## Daily report generation",
         "2. `python main.py daily`",
         "Why: generates the 4 clean operational reports and this "
         "START_HERE file for the team.", "",
         "## Find the latest reports",
         "3. `python main.py listreports`",
         "Why: shows the newest report folder and the 4 report paths.", "",
         "## Open latest report folder",
         "4. `python main.py openreports`",
         "Why: open the folder and start from `00_START_HERE`.", "",
         "## Optional advanced/debug commands",
         "`python main.py manager | market | seller | designer | "
         "rawreports`",
         "Why: only for manager/developer/debug. Normal team members do "
         "not need these.", "",
         "# Report Reading Order", "",
         "| Rank | Report | Who Reads It | Why It Matters | Read First? |",
         "|---:|---|---|---|---|",
         "| 1 | 01_MANAGER_ACTION_REPORT | Manager / Team Lead | Final "
         "decision, blockers, publish permission, today's priorities | "
         "YES |",
         "| 2 | 02_MARKET_KEYWORD_OPPORTUNITY_REPORT | Manager / "
         "Researcher | Keywords, ideas, opportunities, discover results, "
         "performance signals | YES |",
         "| 3 | 03_SELLER_EXECUTION_REPORT | Seller / Listing Operator | "
         "What drafts can be prepared, title/tags/description, listing "
         "QA | After manager approval |",
         "| 4 | 04_DESIGNER_BRIEF_REPORT | Designer | What designs to "
         "create, design restrictions, mockup requirements | After "
         "design approval |", "",
         "# What To Read First Today", "",
         "1. Read `00_START_HERE`.",
         "2. Then read `01_MANAGER_ACTION_REPORT`.",
         "3. If manager approves research direction, read "
         "`02_MARKET_KEYWORD_OPPORTUNITY_REPORT`.",
         "4. Seller reads `03_SELLER_EXECUTION_REPORT` only for products "
         "marked listing-draft-ready.",
         "5. Designer reads `04_DESIGNER_BRIEF_REPORT` only for products "
         "marked design-prep-ready.", "",
         "# Today's Status Summary", ""] + _status_table(c, data_ok) + [
         "", "# Today's Top 5 Actions", "",
         "| Rank | Owner | Action | Report To Read |", "|---:|---|---|---|",
         "| 1 | Manager | Review blockers and approve/reject movement | "
         "01_MANAGER_ACTION_REPORT |",
         "| 2 | Researcher | "
         + ("Fix missing keyword/supplier data"
            if not data_ok or c["data_check"] else
            "Verify top keyword opportunities")
         + " | 02_MARKET_KEYWORD_OPPORTUNITY_REPORT |",
         "| 3 | Seller | Prepare drafts only if allowed | "
         "03_SELLER_EXECUTION_REPORT |",
         "| 4 | Designer | Create designs only if allowed | "
         "04_DESIGNER_BRIEF_REPORT |",
         "| 5 | Claude Operator | Run end-of-day daily report | "
         "00_START_HERE |", "",
         "# Safety Warning", "",
         "Seller may prepare drafts only.",
         "Seller may publish manually only when Manager Report says "
         "`PUBLISH_READY = true`.", "",
         f"Run folder: {run_dir}"]
    return L


# --------------------- 01 MANAGER ACTION ------------------------

def build_manager_action(mgr, data_ok, day):
    c = _counts(mgr)
    L = ["# Manager Action Report", "",
         "## Section 0 - Read Priority",
         "Report rank: 1 of 4",
         "Read first because: this report controls product movement, "
         "blockers, and publish permission.", ""]
    if not data_ok:
        L += ["## Operational Status", "", NO_DATA, ""]
    L += ["## Section 1 - Executive Decision Dashboard",
          "| Metric | Value |", "|---|---:|",
          f"| Products reviewed | {c['reviewed']} |",
          f"| Products blocked | {c['blocked']} |",
          f"| Products needing data check | {c['data_check']} |",
          f"| Products in supplier check | {c['supplier']} |",
          f"| Products in TM/IP check | {c['tmip']} |",
          f"| Products design-prep-ready | {c['design']} |",
          f"| Products listing-draft-ready | {c['draft']} |",
          f"| Products in final QA | {c['qa']} |",
          f"| Products publish-ready | {c['publish']} |", ""]

    pkgs = (mgr or {}).get("listing_package", [])
    from src.ops_reports import SEVERITY
    sev_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    ranked = sorted(pkgs, key=lambda p: min(
        [sev_rank.get(SEVERITY.get(b, "Medium"), 2)
         for b in p.get("blocked_by", ["-"])] or [3]))
    L += ["## Section 2 - Manager Decision Table",
          "| Rank | Product | Current Status | Main Blocker | Decision "
          "Needed | Recommended Action | Owner |",
          "|---:|---|---|---|---|---|---|"]
    if ranked:
        for i, p in enumerate(ranked, 1):
            main = p.get("blocked_by", ["-"])[0] if p.get("blocked_by") \
                else "-"
            owner = ("IP reviewer" if "trademark" in main else
                     "Supplier checker" if "supplier" in main or "url" in
                     main else "Researcher" if "flagged" in main or
                     "keyword" in main or "audit" in main else "Manager")
            L.append(f"| {i} | {p['product_name']} | "
                     f"{p.get('listing_status', '')} | {main} | "
                     f"approve fix / keep blocked | resolve '{main}' | "
                     f"{owner} |")
    else:
        L.append("| - | (no products this run) | - | "
                 + ("DATA_UNAVAILABLE" if not data_ok else "-")
                 + " | - | - | - |")
    L.append("")

    L += ["## Section 3 - Publish Permission",
          "| Product | Draft Allowed | Publish Allowed | Why / Why Not |",
          "|---|---|---|---|"]
    any_pub = False
    for p in pkgs:
        pub = p.get("publish_status") == "PUBLISH_READY"
        any_pub = any_pub or pub
        why = "all gates passed" if pub else \
            ", ".join(p.get("blocked_by", [])[:3])
        L.append(f"| {p['product_name']} | "
                 f"{'YES' if p.get('status') == 'DESIGN_PREP_READY' else 'NO'} | "
                 f"{'YES' if pub else 'NO'} | {why} |")
    if not any_pub:
        L += ["", "No products are publish-ready today."]
    L.append("")

    L += ["## Section 4 - Blockers by Priority"]
    blk = _read(Path("reports") / day / "blockers" /
                f"blocker_report_{day}.md")
    L.append(blk.split("# Blocker Report", 1)[-1].split("\n", 1)[-1]
             if blk else "No blocker data this run.")
    L.append("")

    L += ["## Section 5 - Team Tasks Today"]
    tasks = _read(Path("reports") / day / "tasks" / f"daily_tasks_{day}.md")
    L.append(tasks.split("\n", 2)[-1] if tasks else "No task data this run.")
    L.append("")

    L += ["## Section 6 - Final QA"]
    fqa = _read(Path("reports") / day / "final_qa" /
                f"final_qa_summary_{day}.md")
    L.append(fqa.split("\n", 2)[-1] if fqa else "No final QA data.")
    L.append("")

    design_ok = [p["product_name"] for p in pkgs
                 if p.get("status") == "DESIGN_PREP_READY"
                 and p.get("final_status") != "BLOCKED"]
    blocked = [p["product_name"] for p in pkgs
               if p.get("final_status") == "BLOCKED"]
    pub_ready = [p["product_name"] for p in pkgs
                 if p.get("publish_status") == "PUBLISH_READY"]
    untouch = blocked + ([] if data_ok else ["ALL (DATA_UNAVAILABLE)"])
    L += ["## Section 7 - Manager Must Decide",
          f"1. Approve / reject design-prep movement for: "
          f"{', '.join(design_ok) or 'none'}",
          f"2. Approve / reject seller draft movement for: "
          f"{', '.join(design_ok) or 'none'}",
          f"3. Keep blocked: {', '.join(blocked) or 'none'}",
          f"4. Publish-ready today: {', '.join(pub_ready) or 'NONE'}",
          f"5. Do not touch today: {', '.join(untouch) or 'none'}"]
    return L


# ------------------- 02 MARKET / KEYWORDS -----------------------

def build_market(mgr, data_ok, day):
    L = ["# Market Keyword Opportunity Report", "",
         "## Section 0 - Read Priority",
         "Report rank: 2 of 4",
         "Read after Manager Report because this explains keyword and "
         "opportunity logic.", ""]
    if not data_ok:
        L += ["## Operational Status", "", NO_DATA, ""]
    kws = (mgr or {}).get("keywords", [])
    clean = [k for k in kws if not k.get("data_check")]
    flagged = [k for k in kws if k.get("data_check")]

    def score(k):
        return round((k.get("views_24h") or 0)
                     * (k.get("conversion_rate") or 0.01)
                     * (k.get("avg_price") or 10)
                     / ((k.get("etsy_listings") or 0) + 50), 1)
    clean.sort(key=score, reverse=True)
    L += ["## Section 1 - Keyword Importance Ranking",
          "| Rank | Keyword | Importance Score | Views/day | Listings | "
          "Conversion | Recommended Action |",
          "|---:|---|---:|---:|---:|---|---|"]
    if clean:
        for i, k in enumerate(clean[:10], 1):
            act = "DESIGN_PREP candidate" if i <= 3 else \
                "SUPPLIER_CHECK" if i <= 6 else "WATCHLIST"
            L.append(f"| {i} | {k['keyword']} | {score(k)} | "
                     f"{k.get('views_24h', 0)} | "
                     f"{k.get('etsy_listings', 0)} | "
                     f"{(k.get('conversion_rate') or 0)*100:.1f}% | {act} |")
    else:
        L.append("| - | (no verified keywords this run) | - | - | - | - | "
                 + ("fix data first" if not data_ok else "-") + " |")
    L.append("")
    L += ["## Keywords Requiring Verification"]
    if flagged:
        for k in flagged:
            L.append(f"- {k['keyword']} (flagged DATA_CHECK_REQUIRED - "
                     "researcher must verify before any use)")
    else:
        L.append("None.")
    L.append("")

    L += ["## Section 2 - Opportunity Summary",
          "| Rank | Opportunity | Why It Matters | Next Step |",
          "|---:|---|---|---|"]
    if clean:
        for i, k in enumerate(clean[:3], 1):
            L.append(f"| {i} | {k['keyword']} | "
                     f"{k.get('views_24h', 0)} views/day vs "
                     f"{k.get('etsy_listings', 0)} listings | supplier + "
                     "TM check, then design prep |")
    else:
        L.append("| - | none this run | - | restore data |")
    L.append("")

    L += ["## Section 3 - Discover Results (new ideas + winner listing "
          "ages)"]
    disc = _read(Path("reports") / day / "discover" /
                 f"discover_{day}_EN.md") or \
        _read(Path("reports") / day / "discover" / f"discover_{day}.md")
    L.append(disc.split("\n", 2)[-1] if disc else "Not generated this run.")
    L.append("")

    audit = (mgr or {}).get("competitor_audit", [])
    L += ["## Section 4 - Competitor Relevance",
          f"Relevant competitors found: {len(audit)} (irrelevant ones are "
          "auto-rejected). Fill manual fields in competitor_audit.csv "
          "for full COMPETITOR_AUDIT_OK.", ""]

    L += ["## Section 5 - Performance Signals"]
    perf = _read(Path("reports") / day / "performance" /
                 f"performance_report_{day}.md")
    L.append(perf.split("\n", 2)[-1] if perf
             else "No shop performance data available yet.")
    L.append("")

    L += ["## Section 6 - Researcher Tasks",
          "| Rank | Task | Product / Keyword | Evidence Needed |",
          "|---:|---|---|---|"]
    rank = 1
    for k in flagged[:5]:
        L.append(f"| {rank} | verify flagged data | {k['keyword']} | "
                 "re-pull or cross-check views/conversion |")
        rank += 1
    if not data_ok:
        L.append(f"| {rank} | restore data source | ALL | fresh "
                 "keyword_data.csv or valid YTrends cookie |")
    if rank == 1 and data_ok:
        L.append("| 1 | fill social_signals.csv + competitor manual "
                 "fields | top 3 keywords | Pinterest/X check, audit "
                 "fields |")
    return L


# --------------------- 03 SELLER EXECUTION ----------------------

def build_seller(mgr, data_ok, day):
    L = ["# Seller Execution Report", "",
         "## Section 0 - Read Priority",
         "Report rank: 3 of 4",
         "Read only after Manager Report confirms seller draft is "
         "allowed.", ""]
    if not data_ok:
        L += ["## Operational Status", "", NO_DATA, ""]
    pkgs = (mgr or {}).get("listing_package", [])
    L += ["## Section 1 - Seller Permission Dashboard",
          "| Product | Draft Allowed | Publish Allowed | Reason |",
          "|---|---|---|---|"]
    for p in pkgs:
        L.append(f"| {p['product_name']} | "
                 f"{'YES' if p.get('status') == 'DESIGN_PREP_READY' else 'NO'} | "
                 f"{'YES' if p.get('publish_status') == 'PUBLISH_READY' else 'NO'} | "
                 f"{', '.join(p.get('blocked_by', ['all gates passed'])[:3])} |")
    if not pkgs:
        L.append("| (none this run) | NO | NO | "
                 + ("DATA_UNAVAILABLE" if not data_ok else "-") + " |")
    L.append("")
    L += ["## Section 2 - Seller Task Ranking",
          "| Rank | Product | Task | Why Important | Status |",
          "|---:|---|---|---|---|"]
    r = 1
    for p in pkgs:
        if p.get("status") == "DESIGN_PREP_READY":
            L.append(f"| {r} | {p['product_name']} | prepare Etsy DRAFT "
                     "from Section 3 | first mover on validated keyword | "
                     f"{p.get('listing_status', '')} |")
            r += 1
    if r == 1:
        L.append("| 1 | - | complete supplier fields in "
                 "supplier_products.csv | unblocks drafting | waiting |")
    L.append("")
    L += ["## Section 3 - Listing Drafts (paste order)"]
    sp = _read(Path("reports") / day / "seller" / f"seller_pack_{day}.md")
    L.append(sp.split("\n", 2)[-1] if sp else "Not generated this run.")
    L.append("")
    L += ["## Section 4 - Seller QA Checklist",
          "| Check | Pass/Fail | Notes |", "|---|---|---|",
          "| No placeholder text | | |",
          "| Title natural and not stuffed | | |",
          "| 13 tags valid | | |",
          "| Production partner handled | | |",
          "| No IP-risk terms | | |",
          "| No publish without manager approval | | |", "",
          "## Section 5 - What Seller Must Not Do",
          "- Do not publish unless Manager Action Report says "
          "`Publish Allowed = YES`.",
          "- Do not paste customer-facing copy if copy is blocked.",
          "- Do not use placeholder text.",
          "- Do not use brand, celebrity, franchise, or sports terms."]
    return L


# --------------------- 04 DESIGNER BRIEF ------------------------

def build_designer(mgr, data_ok, day):
    L = ["# Designer Brief Report", "",
         "## Section 0 - Read Priority",
         "Report rank: 4 of 4",
         "Read only for products marked design-prep-ready or "
         "design-approved.", ""]
    if not data_ok:
        L += ["## Operational Status", "", NO_DATA, ""]
    pkgs = (mgr or {}).get("listing_package", [])
    ideas = (mgr or {}).get("product_ideas", [])
    L += ["## Section 1 - Design Permission Dashboard",
          "| Product | Design Allowed | Reason | Status |",
          "|---|---|---|---|"]
    allowed_any = False
    for p in pkgs:
        ok = (p.get("status") == "DESIGN_PREP_READY"
              and p.get("final_status") != "BLOCKED")
        allowed_any = allowed_any or ok
        reason = "DESIGN_PREP_READY" if ok else \
            ("BLOCKED - do not design" if p.get("final_status") ==
             "BLOCKED" else "not design-prep-ready")
        L.append(f"| {p['product_name']} | {'YES' if ok else 'NO'} | "
                 f"{reason} | {p.get('listing_status', '')} |")
    if not pkgs:
        L.append("| (none this run) | NO | "
                 + ("DATA_UNAVAILABLE" if not data_ok else "no products")
                 + " | - |")
    L.append("")
    L += ["## Section 2 - Designer Task Ranking",
          "| Rank | Product | Design Task | Output Required |",
          "|---:|---|---|---|"]
    if allowed_any and ideas:
        for i, b in enumerate(ideas[:5], 1):
            L.append(f"| {i} | {b.get('product', '')} | "
                     f"{b.get('designer_task', 'concepts + mockups')} | "
                     "3 typography + 2 icon variations |")
    else:
        L.append("| - | none allowed today | wait for manager approval | "
                 "- |")
    L.append("")
    L += ["## Section 3 - Design Briefs (copy-paste prompts for Claude)"]
    if allowed_any:
        dp = _read(Path("reports") / day / "design" /
                   f"design_prompts_{day}.md")
        L.append(dp.split("\n", 2)[-1] if dp else "Not generated this run.")
    else:
        L.append("No design prompts issued: no product is design-allowed "
                 "this run. Blocked or flagged products never receive "
                 "design tasks.")
    L.append("")
    L += ["## Section 3b - Design Briefs (copy-paste prompts for ChatGPT image "
          "generator)"]
    if allowed_any:
        cg = _read(Path("reports") / day / "design" /
                   f"chatgpt_prompts_{day}.md")
        L.append(cg.split("\n", 2)[-1] if cg else "Not generated this run.")
    else:
        L.append("No design prompts issued: no product is design-allowed "
                 "this run. Blocked or flagged products never receive "
                 "design tasks.")
    L.append("")
    L += ["## Section 4 - Originality / IP Warning",
          "Use market demand as inspiration only.",
          "Do not copy competitor artwork, layouts, logos, slogans, "
          "characters, brand names, celebrity names, sports teams, or "
          "distinctive product presentation.", "",
          "## Section 5 - Designer Self-Check",
          "| Check | Yes/No | Notes |", "|---|---|---|",
          "| Original design | | |",
          "| No protected IP | | |",
          "| Follows supplier constraints | | |",
          "| Main image readable | | |",
          "| Personalization clear | | |"]
    return L


# --------------------------- runner -----------------------------

def run_daily(mode=None, data_ok=None,
              runs_root="reports/runs", latest_dir="reports/latest",
              update_latest=True):
    ts = get_report_timestamp()
    import src.allreports as ar
    day = ar.TODAY
    print(f"Daily report run {VERSION} - {ts['display']}")
    # 1) generate the detailed layer (never hangs; no-data safe)
    ar.run_allreports(mode, data_ok=data_ok)
    if data_ok is None:
        data_ok, _ = ar.data_available()
    mgr = load_mgr_json(day)

    # 2) run folder
    run_name = f"{ts['date']}_{ts['time'].replace(':', '')}_{VERSION}"
    run_dir = Path(runs_root) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # 3) compose the 5 clean reports
    _emit(run_dir, "01_MANAGER_ACTION_REPORT", "Manager Action Report",
          build_manager_action(mgr, data_ok, day))
    _emit(run_dir, "02_MARKET_KEYWORD_OPPORTUNITY_REPORT",
          "Market Keyword Opportunity Report",
          build_market(mgr, data_ok, day))
    _emit(run_dir, "03_SELLER_EXECUTION_REPORT", "Seller Execution Report",
          build_seller(mgr, data_ok, day))
    _emit(run_dir, "04_DESIGNER_BRIEF_REPORT", "Designer Brief Report",
          build_designer(mgr, data_ok, day))
    _emit(run_dir, "00_START_HERE", "START HERE",
          build_start_here(mgr, data_ok, run_dir))

    # 4) raw data snapshot + archive the detailed reports of this run
    raw = run_dir / "raw_data"
    raw.mkdir(exist_ok=True)
    for f in ("keyword_data.csv", "supplier_products.csv",
              "social_signals.csv", "shop_performance.csv"):
        if Path(f).exists():
            shutil.copy(f, raw / f)
    arch = run_dir / "archive_debug_reports"
    arch.mkdir(exist_ok=True)
    day_dir = Path("reports") / day
    if day_dir.exists():
        shutil.move(str(day_dir), str(arch / day))

    # 5) mirror latest. POD / Embroidery land in reports/latest/<mode>/ so both
    # sets coexist; a plain `daily` (no mode) uses the reports/latest root.
    latest = Path(latest_dir)
    mtarget = latest / mode if mode in ("pod", "embroidery") else latest
    # Guard: on a no-data run, keep the last good reports instead of
    # overwriting them with DATA_UNAVAILABLE placeholders (e.g. a server that
    # can't fetch live data, or a stale-data day between syncs).
    keep_existing = (update_latest and not data_ok
                     and (mtarget / "01_MANAGER_ACTION_REPORT.md").exists())
    if keep_existing:
        print(f"Data unavailable - kept the last good reports in {mtarget} "
              "(not overwritten).")
    if update_latest and not keep_existing:
        mtarget.mkdir(parents=True, exist_ok=True)
        for old in mtarget.glob("*"):
            if old.is_file():
                old.unlink()
        # 1) the 5 clean daily reports
        for name in MAIN_FILES:
            for ext in (".md", ".pdf"):
                src = run_dir / f"{name}{ext}"
                if src.exists():
                    shutil.copy(src, mtarget / f"{name}{ext}")
        # 2) every detailed report this run produced (newest of each type),
        #    under canonical names so the team portal + sync can show them.
        daydir = arch / day
        for cat, prefix, canon in EXTRA_LATEST:
            md = _pick_report(daydir / cat, prefix)
            if not md:
                continue
            shutil.copy(md, mtarget / f"{canon}.md")
            pdf = md.with_suffix(".pdf")
            if pdf.exists():
                shutil.copy(pdf, mtarget / f"{canon}.pdf")
        # 3) chatgpt prompt DATA (date-named json) for the `images` command
        cj = daydir / "design" / f"chatgpt_prompts_{day}.json"
        if cj.exists():
            shutil.copy(cj, mtarget / cj.name)
        (mtarget / "_run_info.txt").write_text(
            f"{run_dir}\n{ts['display']}\n", encoding="utf-8")

    # 6) print summary (spec format)
    print("\nDAILY REPORTS GENERATED\n")
    print("Read first:")
    print(f"{latest_dir}/00_START_HERE.md\n")
    print("Report order:")
    print(f"1. {latest_dir}/01_MANAGER_ACTION_REPORT.md")
    print(f"2. {latest_dir}/02_MARKET_KEYWORD_OPPORTUNITY_REPORT.md")
    print(f"3. {latest_dir}/03_SELLER_EXECUTION_REPORT.md")
    print(f"4. {latest_dir}/04_DESIGNER_BRIEF_REPORT.md\n")
    print(f"Run folder:\n{run_dir}")
    if not data_ok:
        print("\nNOTE: DATA_UNAVAILABLE run - reports explain the fix; "
              "no product moves forward today.")
    return run_dir
