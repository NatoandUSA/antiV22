"""Sales Feedback Loop — post-launch tracking + Day-3/7 recommendations.

After a listing is MANUALLY published, the team logs its real performance here.
The tool reads the numbers and recommends KEEP / CHANGE / KILL / SCALE. This
private performance data is the team's edge over other sellers.
"""
import json
from datetime import date
from pathlib import Path

STORE = Path("data/feedback.json")

FIELDS = ["listing_url", "publish_date", "product_mode", "supplier", "price",
          "title", "impressions", "views", "favorites", "carts", "orders",
          "revenue", "profit", "notes"]


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def load():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return []


def _save(rows):
    STORE.parent.mkdir(exist_ok=True)
    STORE.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def recommend(m):
    """(action, reason) from the metrics — same ladder the ops report uses."""
    views, favs = _i(m.get("views")), _i(m.get("favorites"))
    carts, orders = _i(m.get("carts")), _i(m.get("orders"))
    if orders >= 1:
        return "SCALE PRODUCT LINE", "sale confirmed — make variants + expand the line"
    if carts >= 1:
        return "RAISE/LOWER PRICE + CHANGE PHOTO", "cart but no sale — check price vs rivals + main photo"
    if favs >= 3:
        return "MAKE VARIANTS", "favorites building — add variants + a bundle"
    if favs >= 1:
        return "CHANGE PHOTO", "favorites but no cart — improve the first image / offer"
    if views >= 30:
        return "CHANGE TITLE / TAGS", "views but no favorites — thumbnail + title weak"
    if views == 0:
        return "KILL LISTING", "0 views — retire or rewrite title + tags + photo"
    return "KEEP", "too little data yet — recheck at day 7"


def add(d):
    rows = load()
    d["id"] = max([r.get("id", 0) for r in rows], default=0) + 1
    d["added_at"] = str(date.today())
    action, reason = recommend(d)
    d["recommendation"], d["rec_reason"] = action, reason
    rows.append(d)
    _save(rows)
    return d


def delete(fid):
    _save([r for r in load() if r.get("id") != fid])
