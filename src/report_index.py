"""Central report index: find, list, and open the latest reports."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Reading order: the 4 CORE reports every role needs, then extras.
CORE_LABELS = [
    ("1", "Manager Report EN", "manager", "manager_*[!I].md",
     "READ FIRST - decisions, dashboard, publish permission"),
    ("2", "Research Report", "research", "research_report_*.md",
     "all keywords: ideas + analysis + opportunities + discover + "
     "performance"),
    ("3", "Seller Pack", "seller", "seller_pack_*[!I].md",
     "everything the seller pastes into Etsy (drafts only)"),
    ("4", "Design Prompts", "design", "design_prompts_*[!I].md",
     "copy-paste prompts for the designer"),
]
EXTRA_LABELS = [
    ("Manager Report VI", "manager", "manager_*_VI.md"),
    ("Daily Tasks", "tasks", "daily_tasks_*.md"),
    ("Blocker Report", "blockers", "blocker_report_*.md"),
    ("Product Status Board", "status_board", "product_status_board.md"),
    ("Final QA", "final_qa", "final_qa_summary_*.md"),
    ("Performance", "performance", "performance_report_*.md"),
    ("Ideas Report", "ideas", "ideas_*[!I].md"),
    ("Discover Report", "discover", "discover_*[!I].md"),
    ("Listing Pack", "listing", "listing_*[!I].md"),
    ("Manifest", "index", "manifest_*.md"),
]
LABELS = [(lbl, cat, pat) for _, lbl, cat, pat, _ in CORE_LABELS] + \
    EXTRA_LABELS

LATEST_CANONICAL = {
    "Manager Report EN": "1_manager_report_EN",
    "Research Report": "2_research_report",
    "Seller Pack": "3_seller_pack",
    "Design Prompts": "4_design_prompts",
    "Manager Report VI": "1_manager_report_VI",
    "Daily Tasks": "daily_tasks",
    "Blocker Report": "blocker_report",
    "Product Status Board": "product_status_board",
    "Final QA": "final_qa_summary",
    "Performance": "performance_report",
    "Manifest": "manifest",
}


import re as _re

_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


def latest_day_dir(include_selftest=False):
    """Newest OPERATIONAL day folder (YYYY-MM-DD only). selftest is never
    the operational latest; with include_selftest it is used only when no
    date folder exists."""
    root = Path("reports")
    if not root.exists():
        return None
    days = sorted([d for d in root.iterdir()
                   if d.is_dir() and _DATE_RE.match(d.name)],
                  key=lambda d: d.name)
    if days:
        return days[-1]
    if include_selftest and (root / "selftest").is_dir():
        return root / "selftest"
    return None


def scan_latest(include_selftest=False):
    """{label: {"md": path|None}} for the newest day."""
    day = latest_day_dir(include_selftest)
    out = {}
    if not day:
        return out
    for label, cat, pattern in LABELS:
        folder = day / cat
        if not folder.exists():
            continue
        hits = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime)
        if not hits:
            continue
        out[label] = {"md": hits[-1]}
    return out


def list_reports(include_selftest=False, latest_dir="reports/latest"):
    """Simple team view: START_HERE + the 4 main reports."""
    from pathlib import Path as _P
    latest = _P(latest_dir)
    start = latest / "00_START_HERE.md"
    if start.exists():
        print("\nREAD FIRST:")
        print(f"{start}")
        print("\nMAIN REPORTS:")
        for i, name in enumerate(
                ("01_MANAGER_ACTION_REPORT",
                 "02_MARKET_KEYWORD_OPPORTUNITY_REPORT",
                 "03_SELLER_EXECUTION_REPORT",
                 "04_DESIGNER_BRIEF_REPORT"), 1):
            md = latest / f"{name}.md"
            print(f"{i}. {md}")
        info = latest / "_run_info.txt"
        if info.exists():
            lines = info.read_text(encoding="utf-8").splitlines()
            print(f"\nRun folder: {lines[0]}")
            if len(lines) > 1:
                print(f"Generated:  {lines[1]}")
        print("\nAdvanced/debug detail: python main.py listreports --all")
        print()
        return {"start_here": start}
    print("No reports found yet.")
    print("Run: python main.py daily")
    return {}


def list_reports_detailed(include_selftest=False):
    from src.version import VERSION
    day = latest_day_dir(include_selftest)
    if not day:
        print("No operational reports found yet.")
        print("Run: python main.py allreports")
        return {}
    found = scan_latest(include_selftest)
    print("\nLATEST OPERATIONAL REPORTS")
    print(f"\nReport date: {day.name}   |   Tool version: {VERSION}")
    print("Simple view: open the folder  reports/latest/  - files are "
          "numbered 1-4 in reading order.")
    print("\n================ READ IN THIS ORDER ================")
    for rank, label, cat, pat, why in CORE_LABELS:
        paths = found.get(label)
        print(f"\n[{rank}] {label} - {why}")
        if not paths:
            print("     (not generated this run - see manifest)")
            continue
        print(f"     MD:  {paths['md']}")
    print("\n================ EXTRA DETAIL REPORTS ==============")
    for label, cat, pat in EXTRA_LABELS:
        paths = found.get(label)
        if not paths:
            continue
        line = f"  {label}: {paths['md']}"
        if label == "Product Status Board":
            csvp = paths["md"].with_suffix(".csv")
            if csvp.exists():
                line += f"  (+ {csvp.name})"
        print(line)
    lm = Path("reports/latest_report_manifest.md")
    print("\nManifest: "
          f"{lm if lm.exists() else 'not generated yet'}")
    print("\n================ COMMAND ORDER =====================")
    print("First time on a PC:  python main.py selftest   (verify install)")
    print("Generate everything: python main.py allreports (end of day)")
    print("Find the files:      python main.py listreports (any time)")
    print()
    return found


def open_reports(really_open=True):
    latest = Path("reports/latest")
    target = (latest if (latest / "00_START_HERE.md").exists()
              else (latest_day_dir() or Path("reports"))).resolve()
    claimed = False
    if really_open:
        try:
            if sys.platform.startswith("win"):
                os.startfile(target)  # type: ignore[attr-defined]
                claimed = True
            elif sys.platform == "darwin" and shutil.which("open"):
                r = subprocess.run(["open", str(target)], timeout=10,
                                   capture_output=True)
                claimed = r.returncode == 0
            elif shutil.which("xdg-open"):
                r = subprocess.run(["xdg-open", str(target)], timeout=10,
                                   capture_output=True)
                claimed = r.returncode == 0
        except Exception:
            claimed = False
    print("Latest report folder:")
    print(f"{target}")
    print()
    if claimed:
        print("Your file explorer should have opened. If it did not, "
              "open this path manually.")
    else:
        print("If your file explorer did not open, open this path "
              "manually.")
    return {"path": target, "claimed_open": claimed}


def update_latest(_manifest_path=None):
    """Rebuild reports/latest/ + latest_report_manifest.md from the newest
    OPERATIONAL (date-named) folder. selftest never lands here."""
    day = latest_day_dir()
    if day is None:
        return None
    found = scan_latest()
    latest = Path("reports/latest")
    latest.mkdir(parents=True, exist_ok=True)
    for old in latest.glob("*"):
        old.unlink()
    for label, paths in found.items():
        canon = LATEST_CANONICAL.get(label)
        p = paths.get("md")
        if p:
            name = (canon + ".md") if canon else p.name
            shutil.copy(p, latest / name)
        if label == "Product Status Board":
            csvp = paths["md"].with_suffix(".csv")
            if csvp.exists():
                shutil.copy(csvp, latest / "product_status_board.csv")
    man = found.get("Manifest", {})
    if man.get("md"):
        shutil.copy(man["md"], "reports/latest_report_manifest.md")
    return day
