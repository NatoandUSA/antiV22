"""Deep links OUT to the research engines (YTuong / HeyEtsy) and Etsy.

The dashboard is the EXECUTION engine; YTuong/HeyEtsy is the RESEARCH engine. So
instead of cloning their trending/hot/shop pages, we link out to them and pull the
result back in via the Import Center. One place to build every "Open in …" link.
"""
from urllib.parse import quote

YTUONG = "https://trends.ytuong.ai/en"
HEYETSY = "https://ytuong.me"
ETSY = "https://www.etsy.com"


def for_keyword(kw):
    """[(label, url)] research links for a keyword."""
    q = quote((kw or "").strip())
    return [("Open in YTuong", f"{YTUONG}/spy?q={q}"),
            ("YTuong Trending", f"{YTUONG}/trending"),
            ("Open in HeyEtsy", f"{HEYETSY}/trending"),
            ("Search on Etsy", f"{ETSY}/search?q={q}")]


def for_listing(url):
    out = []
    if (url or "").strip().startswith("http"):
        out.append(("Open Etsy listing", url.strip()))
    out.append(("YTuong Spy", f"{YTUONG}/spy"))
    out.append(("HeyEtsy Hot", f"{HEYETSY}/hot"))
    return out


def for_shop(url_or_name):
    s = (url_or_name or "").strip()
    out = []
    if s.startswith("http"):
        out.append(("Open shop", s))
    elif s:
        out.append(("Open shop", f"{ETSY}/shop/{quote(s)}"))
    out.append(("Shop inspirations", f"{HEYETSY}/shop-inspirations?filterTotalSold=shuffle"))
    return out


def render(links):
    """Render [(label,url)] as small external link buttons (opens in a new tab)."""
    import html as _h
    return "".join(
        f'<a class="dlbtn" href="{_h.escape(u)}" target="_blank" rel="noopener">'
        f'{_h.escape(lbl)} ↗</a>' for lbl, u in links)
