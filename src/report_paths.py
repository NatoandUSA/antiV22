"""Central report folder structure.

reports/YYYY-MM-DD/{manager,design,seller,discover,ideas,listing,tasks,
final_qa,performance,index}/  plus reports/latest/ mirrors and
reports/latest_report_manifest.md.
"""
from pathlib import Path

CATEGORIES = ("manager", "design", "seller", "discover", "ideas", "listing",
              "tasks", "blockers", "status_board", "final_qa", "research",
              "performance", "index")


def rdir(day, category):
    p = Path("reports") / str(day) / category
    p.mkdir(parents=True, exist_ok=True)
    return p
