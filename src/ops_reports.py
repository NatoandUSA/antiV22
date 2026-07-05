"""Operational reports engine.

Every report category exists EVERY run. When data is unavailable, reports
say DATA_UNAVAILABLE with reason, owner, required fix, and severity -
they never pretend and they are never skipped. All writers stamp headers
and attempt PDF export, reporting failures loudly.
"""
import csv
import json
from pathlib import Path

from src.report_paths import rdir
from src.timestamp import stamp_file
from src.version import VERSION

NO_DATA_TEXT = ("DATA_UNAVAILABLE\n\n"
                "No fresh keyword_data.csv and live API unavailable.\n"
                "Action required: update keyword_data.csv or refresh "
                "YTrends credentials.")

ROLES = ["Manager", "Claude Operator", "Researcher", "Supplier Checker",
         "TM/IP/Policy Reviewer", "Designer", "Seller", "QA",
         "Performance Analyst"]


def _pdf(path):
    try:
        from src.pdf_export import md_to_pdf
        out = md_to_pdf(path)
        if not out:
            print(f"  PDF FAILED for {path} (reportlab missing?) - "
                  "Markdown kept")
            return None
        return out
    except Exception as exc:
        print(f"  PDF FAILED for {path}: {exc} - Markdown kept")
        return None


def _write(day, category, filename, report_type, lines):
    p = rdir(day, category) / filename
    p.write_text("\n".join(lines), encoding="utf-8")
    stamp_file(p, report_type)
    _pdf(p)
    return p


def load_mgr_json(day):
    p = rdir(day, "manager") / f"manager_{day}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ---------------- no-data manager (EN + VI + PDFs) ----------------

def write_nodata_manager(day, reason):
    p = rdir(day, "manager") / f"manager_{day}.md"
    L = ["# Manager Report", "",
         "## Operational Status", "",
         "DATA_UNAVAILABLE", "",
         f"Reason:", f"{reason}", "",
         "Manager decision:",
         "No product can move to design, listing, final QA, or "
         "publish-ready today.", "",
         "## Required Team Actions", "",
         "| Owner | Task | Expected Output |", "|---|---|---|",
         "| Claude Operator | Fix data input or credentials | Fresh "
         "keyword_data.csv or valid YTrends token |",
         "| Researcher | Provide verified keyword data | "
         "keyword_data.csv |",
         "| Manager | Do not approve publish | No publish-ready products "
         "today |", "",
         "**No products are publish-ready today.**"]
    p.write_text("\n".join(L), encoding="utf-8")
    from src.lang import finalize_manager
    finalize_manager(p)
    return p


# ---------------- daily tasks (9 roles) ----------------

def write_daily_tasks(day, mgr=None, reason=""):
    tasks = {r: [] for r in ROLES}
    if mgr is None:
        tasks["Claude Operator"].append(
            "Fix data input or credentials -> fresh keyword_data.csv or "
            "valid YTrends cookie/token")
        tasks["Researcher"].append(
            "Provide verified keyword data -> keyword_data.csv")
        tasks["Manager"].append(
            "Do not approve publish (DATA_UNAVAILABLE)")
    else:
        for p in mgr.get("listing_package", []):
            name = p["product_name"]
            for b in p.get("blocked_by", []):
                if "supplier" in b or "product_url" in b:
                    tasks["Supplier Checker"].append(
                        f"{name}: resolve gate '{b}' in "
                        "supplier_products.csv")
                elif "trademark" in b or "policy" in b:
                    tasks["TM/IP/Policy Reviewer"].append(
                        f"{name}: resolve '{b}' (USPTO check / approval "
                        "log in tm_verified.csv)")
                elif "flagged" in b or "keyword" in b:
                    tasks["Researcher"].append(
                        f"{name}: clear '{b}' (verify flagged keyword "
                        "rows)")
                elif "audit" in b:
                    tasks["Researcher"].append(
                        f"{name}: complete competitor audit manual fields")
                elif "manual_review" in b:
                    tasks["QA"].append(
                        f"{name}: run Final QA form; manager records "
                        "manual_review=yes")
                elif "title" in b or "tag" in b:
                    tasks["Seller"].append(
                        f"{name}: fix '{b}' per validator reasons")
        if mgr.get("product_ideas"):
            tasks["Designer"].append(
                "Execute design prompts (design folder) - one prompt at a "
                "time in Claude")
            tasks["Seller"].append(
                "Prepare Etsy DRAFTS from seller pack (no publishing)")
        tasks["Manager"].append(
            "Review Publish Gate Dashboard; approve/reject moves")
        tasks["Claude Operator"].append(
            "Run end-of-day allreports; send latest manifest path to "
            "manager")
        if Path("shop_performance.csv").exists():
            tasks["Performance Analyst"].append(
                "Update shop_performance.csv from Etsy Stats; review "
                "performance report decisions")
    L = [f"# Daily Team Tasks - {day}", ""]
    if mgr is None:
        L += ["## Operational Status", "", NO_DATA_TEXT, ""]
    for role in ROLES:
        L.append(f"## {role}")
        if tasks[role]:
            L += [f"- [ ] {t}" for t in sorted(set(tasks[role]))]
        else:
            L.append("No tasks today.")
        L.append("")
    return _write(day, "tasks", f"daily_tasks_{day}.md",
                  "Daily Tasks Report", L)


# ---------------- blocker report ----------------

SEVERITY = {"trademark_clear": "Critical", "copyright_policy_clear":
            "Critical", "supplier_confirmed": "High",
            "seller_original_design_confirmed": "High",
            "production_partner_disclosed": "High",
            "no_flagged_data": "High", "keyword_data_verified": "High",
            "product_url_recorded": "Medium",
            "competitor_audit_complete": "Medium",
            "profitability_verified": "Medium",
            "manual_review_complete": "Medium",
            "supplier_last_verified": "Low",
            "trademark_verified_or_approved": "High"}


def write_blockers(day, mgr=None, reason=""):
    L = [f"# Blocker Report - {day}", ""]
    groups = {"Critical": [], "High": [], "Medium": [], "Low": [],
              "Cleared today": []}
    if mgr is None:
        groups["Critical"].append(
            ("ALL PRODUCTS", "DATA_UNAVAILABLE", "Claude Operator / "
             "Researcher", "provide fresh keyword_data.csv or working API "
             "credentials"))
        L += ["## Operational Status", "", NO_DATA_TEXT, ""]
    else:
        for p in mgr.get("listing_package", []):
            for b in p.get("blocked_by", []):
                sev = SEVERITY.get(b, "Medium")
                owner = ("IP reviewer" if "trademark" in b or "policy" in b
                         else "Supplier checker" if "supplier" in b
                         or "url" in b or "partner" in b
                         else "Researcher" if "flagged" in b
                         or "keyword" in b or "audit" in b
                         else "Manager")
                groups[sev].append((p["product_name"], b, owner,
                                    p["gate_detail"].get(b, {})
                                    .get("reason", "")[:70]))
            passed = [k for k, v in p.get("gate_detail", {}).items()
                      if v.get("passed")]
            for k in passed[:3]:
                groups["Cleared today"].append(
                    (p["product_name"], k, "-", "passed"))
    for sev in ("Critical", "High", "Medium", "Low", "Cleared today"):
        L.append(f"## {sev}")
        if groups[sev]:
            L.append("| Product | Blocker | Owner | Required fix / note |")
            L.append("|---|---|---|---|")
            for row in groups[sev]:
                L.append("| " + " | ".join(str(x) for x in row) + " |")
        else:
            L.append("None.")
        L.append("")
    return _write(day, "blockers", f"blocker_report_{day}.md",
                  "Blocker Report", L)


# ---------------- product status board (csv + md + pdf) ----------------

BOARD_FIELDS = ["date", "product", "primary_keyword", "current_status",
                "data_quality", "supplier_status", "tm_ip_status",
                "design_status", "listing_status", "final_status",
                "draft_allowed", "publish_allowed", "main_blocker",
                "owner", "next_action", "due_date"]


def _board_rows(day, mgr):
    rows = []
    if not mgr:
        rows.append({f: "" for f in BOARD_FIELDS} | {
            "date": day, "product": "(no products - DATA_UNAVAILABLE)",
            "current_status": "DATA_UNAVAILABLE",
            "main_blocker": "no fresh keyword data / API unreachable",
            "owner": "Claude Operator / Researcher",
            "next_action": "provide keyword_data.csv or fix credentials"})
        return rows
    flagged = {k["keyword"] for k in mgr.get("keywords", [])
               if k.get("data_check")}
    for p in mgr.get("listing_package", []):
        g = p.get("publish_gates", {})
        if p.get("final_status") == "BLOCKED":
            cur, nxt = "BLOCKED", "do not use; see blocker report"
        elif p.get("publish_status") == "PUBLISH_READY":
            cur, nxt = "PUBLISH_READY", "manager sign-off then manual publish"
        elif not g.get("supplier_confirmed"):
            cur, nxt = "SUPPLIER_CHECK", "verify supplier_products.csv fields"
        elif not g.get("trademark_verified_or_approved", True):
            cur, nxt = "TM_IP_CHECK", "USPTO check or approval log"
        elif not g.get("competitor_audit_complete"):
            cur, nxt = ("LISTING_DRAFT_READY",
                        "seller drafts; researcher completes audit")
        elif not g.get("manual_review_complete"):
            cur, nxt = "FINAL_QA", "manager records manual_review=yes"
        else:
            cur, nxt = "NEEDS_REVIEW", "resolve remaining gates"
        main = p.get("blocked_by", ["-"])[0] if p.get("blocked_by") else "-"
        rows.append({
            "date": day, "product": p["product_name"],
            "primary_keyword": p.get("primary_keyword", ""),
            "current_status": cur,
            "data_quality": ("flagged rows in cluster" if flagged
                             else "clean"),
            "supplier_status": p.get("supplier_status", ""),
            "tm_ip_status": ("OK_VERIFIED" if g.get(
                "trademark_verified_or_approved") else
                "HEURISTIC_OK_NOT_VERIFIED" if g.get("trademark_clear")
                else "BLOCKED/CAUTION"),
            "design_status": p.get("status", ""),
            "listing_status": p.get("listing_status", ""),
            "final_status": p.get("final_status", ""),
            "draft_allowed": "yes" if p.get("status") ==
                             "DESIGN_PREP_READY" else "no",
            "publish_allowed": "yes" if p.get("publish_status") ==
                               "PUBLISH_READY" else "no",
            "main_blocker": main,
            "owner": ("IP reviewer" if "trademark" in main else
                      "Supplier checker" if "supplier" in main else
                      "Researcher" if "flagged" in main or "audit" in main
                      else "Manager"),
            "next_action": nxt, "due_date": ""})
    return rows


def write_statusboard(day, mgr=None):
    rows = _board_rows(day, mgr)
    folder = rdir(day, "status_board")
    csv_p = folder / "product_status_board.csv"
    with csv_p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BOARD_FIELDS)
        w.writeheader()
        w.writerows(rows)
    L = [f"# Product Status Board - {day}", ""]
    if not mgr:
        L += ["## Operational Status", "", NO_DATA_TEXT, ""]
    L.append("| " + " | ".join(BOARD_FIELDS) + " |")
    L.append("|" + "---|" * len(BOARD_FIELDS))
    for r in rows:
        L.append("| " + " | ".join(str(r[f]) for f in BOARD_FIELDS) + " |")
    md = _write(day, "status_board", "product_status_board.md",
                "Product Status Board", L)
    return csv_p, md


# ---------------- final QA summary ----------------

def write_finalqa(day, mgr=None, reason=""):
    L = [f"# Final QA Summary - {day}", ""]
    if mgr is None:
        L += ["## Operational Status", "", NO_DATA_TEXT, "",
              "No products are in FINAL_QA today.",
              "No products are publish-ready today."]
    else:
        in_qa = [p for p in mgr.get("listing_package", [])
                 if p.get("blocked_by") == ["manual_review_complete"]
                 or (p.get("final_status") == "NEEDS_REVIEW"
                     and "manual_review_complete" in p.get("blocked_by", []))]
        ready = [p for p in mgr.get("listing_package", [])
                 if p.get("publish_status") == "PUBLISH_READY"]
        if in_qa:
            L.append("| Product | Missing gates | Manager decision needed |")
            L.append("|---|---|---|")
            for p in in_qa:
                L.append(f"| {p['product_name']} | "
                         f"{', '.join(p['blocked_by'])} | record "
                         "manual_review=yes or reject |")
        else:
            L.append("No products are in FINAL_QA today.")
        L.append("")
        if ready:
            L.append("Publish-ready: "
                     + ", ".join(p["product_name"] for p in ready)
                     + " (manual publish after manager sign-off only)")
        else:
            L.append("No products are publish-ready today.")
        L += ["", "Per-product Final QA form: team_workflow/"
              "forms_final_qa.md"]
    return _write(day, "final_qa", f"final_qa_summary_{day}.md",
                  "Final QA Summary", L)


# ---------------- performance report ----------------

def _decision(views, favs, carts, orders, days_live):
    if orders >= 1:
        return "SCALE", "sale confirmed - make 5 variants + bundle offer"
    if carts >= 1:
        return "REVISE_PRICE_SHIPPING", ("cart but no sale - check price "
                                         "vs competitors + shipping clarity")
    if favs >= 1:
        return "REVISE_MAIN_IMAGE", ("favorites but no cart - improve "
                                     "offer photos / gift-ready image")
    if views >= 30:
        return "REVISE_MAIN_IMAGE", ("views but no favorites - thumbnail "
                                     "appeal weak")
    if views == 0 and days_live >= 14:
        return "KILL", "0 views after 14+ days - retire or full rewrite"
    if views == 0 and days_live >= 4:
        return "REVISE_TITLE_TAGS", ("0 views - replace title front + 3 "
                                     "weakest tags")
    return "WATCH", "low data - recheck at day 7"


def write_performance(day, reason=""):
    src = Path("shop_performance.csv")
    L = [f"# Performance Report - {day}", ""]
    if not src.exists():
        L += ["shop_performance.csv not found.",
              "No live listing performance can be analyzed today.", "",
              "Owner: Performance Analyst - export Etsy Stats into "
              "shop_performance.csv (see team_workflow/"
              "forms_performance.md)."]
    else:
        rows = list(csv.DictReader(src.open(newline="", encoding="utf-8")))
        if not rows:
            L.append("No performance data available.")
        else:
            L.append("| Listing | Keyword | Days | Views | Favs | Carts | "
                     "Orders | Decision | Action |")
            L.append("|---|---|---|---|---|---|---|---|---|")
            from datetime import date as _d
            for r in rows:
                def n(k):
                    try:
                        return float(r.get(k) or 0)
                    except ValueError:
                        return 0
                try:
                    days_live = (_d.fromisoformat(day) - _d.fromisoformat(
                        r.get("date_published", day))).days
                except Exception:
                    days_live = 0
                dec, act = _decision(n("views"), n("favorites"),
                                     n("carts"), n("orders"), days_live)
                L.append(f"| {r.get('listing_id', '?')} | "
                         f"{r.get('keyword', '')} | {days_live} | "
                         f"{int(n('views'))} | {int(n('favorites'))} | "
                         f"{int(n('carts'))} | {int(n('orders'))} | "
                         f"**{dec}** | {act} |")
    return _write(day, "performance", f"performance_report_{day}.md",
                  "Performance Report", L)


# ---------------- generic no-data reports for research categories ------

def write_nodata_generic(day, category, filename, title, report_type,
                         reason):
    L = [f"# {title} - {day}", "", "## Operational Status", "",
         NO_DATA_TEXT, "", f"Reason detail: {reason}", "",
         "| Owner | Required fix | Severity |", "|---|---|---|",
         "| Claude Operator | refresh YTrends cookie/token in .env | "
         "Critical |",
         "| Researcher | or provide fresh keyword_data.csv | Critical |",
         "", "No recommendations are made without verified data."]
    return _write(day, category, filename, report_type, L)


# ---------------- consolidated research report (report #2) ----------

def _strip_stamp(text):
    """Remove the timestamp header block from an already-stamped report."""
    if text.startswith("Generated on: "):
        parts = text.split("\n\n", 1)
        return parts[1] if len(parts) > 1 else text
    return text


def write_research_report(day):
    """ONE research document: keyword ideas + analysis + opportunities +
    discover (listing ages) + performance. Composed from the individual
    reports of the same run."""
    sections = [
        ("PART 1 - PRODUCT IDEAS, ANALYSIS & OPPORTUNITIES",
         rdir(day, "ideas") / f"ideas_{day}_EN.md",
         rdir(day, "ideas") / f"ideas_{day}.md"),
        ("PART 2 - DISCOVER: FOCUS KEYWORDS + WINNER LISTING AGES",
         rdir(day, "discover") / f"discover_{day}_EN.md",
         rdir(day, "discover") / f"discover_{day}.md"),
        ("PART 3 - SHOP PERFORMANCE DECISIONS",
         rdir(day, "performance") / f"performance_report_{day}.md", None),
    ]
    L = [f"# Research Report - {day}",
         "",
         "_One document for keyword research: ideas, analysis, "
         "opportunities, discovery, and live performance._", ""]
    for title, primary, fallback in sections:
        L += [f"# {title}", ""]
        src = primary if primary.exists() else             (fallback if fallback and fallback.exists() else None)
        if src:
            L.append(_strip_stamp(src.read_text(encoding="utf-8")))
        else:
            L.append("_Not generated this run (see manifest for reason)._")
        L.append("")
    return _write(day, "research", f"research_report_{day}.md",
                  "Research Report", L)
