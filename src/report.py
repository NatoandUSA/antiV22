"""Writes the weekly niche report as a Markdown file."""
from datetime import date
from pathlib import Path


def write_report(rows):
    """rows: list of dicts already sorted by opportunity (best first)."""
    from src.report_paths import rdir
    path = rdir(date.today(), "index") / f"report_{date.today()}.md"

    lines = [f"# Niche opportunity report - {date.today()}", ""]
    lines.append("| Rank | Keyword | Demand (avg) | Momentum | Competition | Opportunity |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        comp = r["competition"] if r["competition"] else "?"
        lines.append(
            f"| {i} | {r['keyword']} | {r['avg_interest']} | "
            f"{r['momentum_pct']}% | {comp} | {r['opportunity']} |"
        )
    lines += [
        "",
        "Momentum = last 3 months vs first 3 months of Google Trends interest (US).",
        "Competition = number of Etsy listings for the keyword. Until the YTrends",
        "API is wired in, fill it manually in keywords.csv (search the keyword on",
        "Etsy and copy the result count, or read it from YTrends).",
        "",
        "Rule of thumb: publish into keywords with positive momentum and",
        "competition under ~1,000. Ignore high-demand keywords with 10,000+",
        "listings -- a new shop cannot rank there yet.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    from src.timestamp import stamp_file
    stamp_file(path, "Google Trends Validation")
    try:
        from src.pdf_export import md_to_pdf
        md_to_pdf(path)
    except Exception:
        pass
    return path
