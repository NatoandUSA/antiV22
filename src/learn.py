"""Shop learning loop: reads shop_performance.csv (exported/maintained by
the team) and recommends actions per listing. Optional - runs only when
the file exists with data.

Columns: listing_id,date_published,keyword,title_version,image_version,
views,visits,favorites,carts,orders,revenue,profit
"""
import csv
from pathlib import Path

CSV = Path("shop_performance.csv")


def recommendations():
    if not CSV.exists():
        return []
    recs = []
    with CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            def n(k):
                try:
                    return float(r.get(k) or 0)
                except ValueError:
                    return 0
            lid = r.get("listing_id") or "?"
            kw = r.get("keyword") or ""
            views, favs = n("views"), n("favorites")
            carts, orders = n("carts"), n("orders")
            if orders >= 1:
                recs.append((lid, kw, "SCALE: make 5 variants; consider a "
                             "bundle offer of this design"))
            elif carts >= 1:
                recs.append((lid, kw, "FIX OFFER: cart but no sale - check "
                             "price vs competitors, shipping cost, delivery "
                             "date clarity"))
            elif favs >= 1:
                recs.append((lid, kw, "IMPROVE CONVERSION: favorites but no "
                             "cart - test price -10% or add gift-ready photo"))
            elif views >= 30:
                recs.append((lid, kw, "IMPROVE FIRST IMAGE: views but no "
                             "favorites - CTR ok, thumbnail appeal weak"))
            elif views == 0:
                recs.append((lid, kw, "REWRITE SEO: 0 views - replace title "
                             "front + 3 weakest tags from latest grow run"))
            else:
                recs.append((lid, kw, "WAIT: low data - recheck at day 7"))
    return recs
