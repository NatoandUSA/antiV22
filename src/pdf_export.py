"""Convert our .md reports to styled PDFs (Vietnamese-safe fonts).

Called automatically after each report. Requires:  pip install reportlab
"""
import re
from pathlib import Path

FONT_CANDIDATES = [
    ("VN", r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("VN", r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    ("VN", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _register_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for name, reg, bold in FONT_CANDIDATES:
        if Path(reg).exists():
            pdfmetrics.registerFont(TTFont("Body", reg))
            pdfmetrics.registerFont(
                TTFont("BodyBold", bold if Path(bold).exists() else reg))
            return True
    return False  # fall back to Helvetica (Vietnamese marks may not render)


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text):
    """Markdown inline -> reportlab mini-HTML (bold, links)."""
    text = _esc(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  r'<a href="\2" color="#1155cc"><u>\1</u></a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


_REPORTLAB_WARNED = False


def _reportlab_help():
    global _REPORTLAB_WARNED
    if not _REPORTLAB_WARNED:
        import sys
        print("=" * 60)
        print("PDF EXPORT DISABLED: reportlab is not installed for THIS "
              "Python:")
        print(f"  {sys.executable}")
        print("Fix (run exactly this):")
        print(f"  \"{sys.executable}\" -m pip install reportlab")
        print("Then rerun your command. Markdown files are still saved.")
        print("=" * 60)
        _REPORTLAB_WARNED = True


def md_to_pdf(md_path):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                        Table, TableStyle)
    except ImportError:
        print("  (PDF skipped: run  pip install reportlab  to enable)")
        return None

    has_font = _register_fonts()
    body_font = "Body" if has_font else "Helvetica"
    bold_font = "BodyBold" if has_font else "Helvetica-Bold"

    S = {
        "h1": ParagraphStyle("h1", fontName=bold_font, fontSize=16, leading=20,
                             spaceAfter=6, textColor=colors.HexColor("#1a1a1a")),
        "h2": ParagraphStyle("h2", fontName=bold_font, fontSize=13, leading=17,
                             spaceBefore=10, spaceAfter=4,
                             textColor=colors.HexColor("#b45309")),
        "h3": ParagraphStyle("h3", fontName=bold_font, fontSize=11, leading=14,
                             spaceBefore=6, spaceAfter=3),
        "p": ParagraphStyle("p", fontName=body_font, fontSize=9.5, leading=13),
        "li": ParagraphStyle("li", fontName=body_font, fontSize=9.5, leading=13,
                             leftIndent=6 * mm, bulletIndent=2 * mm),
        "cell": ParagraphStyle("cell", fontName=body_font, fontSize=8, leading=10),
        "cellh": ParagraphStyle("cellh", fontName=bold_font, fontSize=8,
                                leading=10, textColor=colors.white),
    }

    md_path = Path(md_path)
    pdf_path = md_path.with_suffix(".pdf")
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )

    story, table_buf = [], []

    def flush_table():
        if not table_buf:
            return
        header, rows = table_buf[0], table_buf[1:]
        ncols = len(header)

        def _fit(row):
            # reportlab requires rectangular data; pad short rows and drop
            # overflow so a ragged markdown table can't crash doc.build().
            row = list(row)
            return (row + [""] * (ncols - len(row)))[:ncols]

        data = [[Paragraph(_inline(c), S["cellh"]) for c in header]]
        data += [[Paragraph(_inline(c), S["cell"]) for c in _fit(r)]
                 for r in rows]
        t = Table(data, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b45309")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#faf5ec")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9c9a8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 4 * mm))
        table_buf.clear()

    in_code = False
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            if line:
                story.append(Paragraph(_esc(line), S["cell"]))
                story.append(Spacer(1, 0.8 * mm))
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            table_buf.append(cells)
            continue
        flush_table()
        if not line or line.startswith("<"):
            continue
        if line.startswith("### "):
            story.append(Paragraph(_inline(line[4:]), S["h3"]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline(line[3:]), S["h2"]))
        elif line.startswith("# "):
            story.append(Paragraph(_inline(line[2:]), S["h1"]))
        elif re.match(r"^(\d+)\.\s", line):
            story.append(Paragraph(_inline(line), S["li"]))
        elif line.startswith("- "):
            story.append(Paragraph("\u2022 " + _inline(line[2:]), S["li"]))
        elif line.startswith("_") and line.endswith("_"):
            story.append(Paragraph("<i>%s</i>" % _inline(line.strip("_")), S["p"]))
        else:
            story.append(Paragraph(_inline(line), S["p"]))
        story.append(Spacer(1, 1.2 * mm))
    flush_table()

    doc.build(story)
    if not has_font:
        print("  (PDF note: no Vietnamese font found; diacritics may not render)")
    return pdf_path
