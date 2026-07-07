"""Sales Feedback Loop — post-launch tracking + Day-3/7 recommendations.

After a listing is MANUALLY published, the team logs its real performance here.
The tool reads the numbers and recommends ONE next action. This private
performance data is the team's edge over other sellers using the same public
keyword data — it also feeds src/learning.py so future runs score smarter.

Saves to data/performance/listing_feedback.json (+ .csv) and mirrors a
feedback_tracking.json into the matching saved-run folder. Never publishes.
"""
import csv
import json
import re
from datetime import date
from pathlib import Path

PERF_DIR = Path("data/performance")
STORE = PERF_DIR / "listing_feedback.json"
CSV_STORE = PERF_DIR / "listing_feedback.csv"
LEGACY = Path("data/feedback.json")   # pre-V23 location, still read if present

# Full tracked schema (what the team can log). Kept practical: the recommender
# only needs the metric fields; the rest are context for the learning system.
FIELDS = [
    "listing_url", "publish_date", "keyword", "product_mode", "supplier",
    "product_cost", "shipping_cost", "price", "title", "tags",
    "main_image_version", "mockup_style", "personalization_offer", "bundle_offer",
    "day_1_impressions", "day_3_views", "day_7_views", "favorites", "carts",
    "orders", "revenue", "profit", "refund_or_issue", "notes",
]

# The exact action set the recommender may return.
ACTIONS = ["KEEP", "CHANGE_MAIN_PHOTO", "CHANGE_TITLE", "CHANGE_TAGS",
           "RAISE_PRICE", "LOWER_PRICE", "MAKE_VARIANTS", "KILL_LISTING",
           "SCALE_PRODUCT_LINE"]


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def recommend(m, day=7):
    """(action, reason) from the real metrics. One action from ACTIONS.

    Priority ladder, strongest signal first: orders > carts > favorites >
    views > impressions. `day` picks which view count to read (3 or 7)."""
    imp = _i(m.get("day_1_impressions") or m.get("impressions"))
    v3 = _i(m.get("day_3_views"))
    v7 = _i(m.get("day_7_views") or m.get("views"))
    views = v7 if (day >= 7 or v7) else v3
    favs = _i(m.get("favorites"))
    carts = _i(m.get("carts"))
    orders = _i(m.get("orders"))
    price, cost = _f(m.get("price")), _f(m.get("product_cost")) + _f(m.get("shipping_cost"))
    margin = (price - cost) / price if price else 0.0

    if orders >= 1:
        if margin and margin < 0.35:
            return "RAISE_PRICE", ("selling, but margin is thin ("
                                   f"{margin*100:.0f}%) — raise price, then scale")
        return "SCALE_PRODUCT_LINE", "sales confirmed — make variants + expand the line"
    if carts >= 2:
        return "LOWER_PRICE", "repeated carts, no checkout — price/shipping is the friction"
    if carts >= 1:
        return "CHANGE_MAIN_PHOTO", "cart but no sale — strengthen the hero image + trust signals"
    if favs >= 5:
        return "MAKE_VARIANTS", "strong saves, no cart — add variants + a bundle/gift option"
    if favs >= 1:
        return "CHANGE_MAIN_PHOTO", "a few saves, no cart — first image/offer isn't closing"
    if views >= 50:
        return "CHANGE_TITLE", "traffic but no saves — the title promise + thumbnail are weak"
    if imp >= 100 and views < 10:
        return "CHANGE_TITLE", "shown a lot but few clicks — title/thumbnail CTR is low"
    if views >= 10:
        return "CHANGE_TAGS", "some views, no traction — tighten long-tail tags/SEO"
    if day >= 7 and views == 0:
        return "KILL_LISTING", "no traffic after 7 days — retire or fully rewrite title+tags+photo"
    return "KEEP", "too little data yet — recheck at day 7"


def load():
    for p in (STORE, LEGACY):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return []
    return []


def _write(rows):
    PERF_DIR.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    cols = ["id", "added_at"] + FIELDS + ["day3_action", "day3_reason",
                                          "day7_action", "day7_reason"]
    with CSV_STORE.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow(r)


def _slug(kw):
    return re.sub(r"[^a-z0-9]+", "-", (kw or "").lower()).strip("-")[:40]


def _mirror_to_run(d):
    """Best-effort: drop feedback_tracking.json into the matching saved run."""
    slug = _slug(d.get("keyword"))
    if not slug:
        return
    base = Path("reports/latest/runs")
    if not base.exists():
        return
    hits = sorted(base.glob(f"*_{slug}"))
    if not hits:
        return
    payload = {
        "keyword": d.get("keyword"), "listing_url": d.get("listing_url"),
        "publish_date": d.get("publish_date"), "product_mode": d.get("product_mode"),
        "day_3": {"logged": bool(d.get("day_3_views")),
                  "views": d.get("day_3_views"), "action": d.get("day3_action"),
                  "reason": d.get("day3_reason")},
        "day_7": {"logged": bool(d.get("day_7_views")),
                  "views": d.get("day_7_views"), "favorites": d.get("favorites"),
                  "carts": d.get("carts"), "orders": d.get("orders"),
                  "action": d.get("day7_action"), "reason": d.get("day7_reason")},
        "recommendation": d.get("day7_action") or d.get("day3_action"),
    }
    (hits[-1] / "feedback_tracking.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")


def add(d):
    rows = load()
    d["id"] = max([r.get("id", 0) for r in rows], default=0) + 1
    d["added_at"] = str(date.today())
    a3, r3 = recommend(d, day=3)
    a7, r7 = recommend(d, day=7)
    d["day3_action"], d["day3_reason"] = a3, r3
    d["day7_action"], d["day7_reason"] = a7, r7
    # keep old keys some callers/tests read
    d["recommendation"], d["rec_reason"] = a7, r7
    rows.append(d)
    _write(rows)
    _mirror_to_run(d)
    try:
        from src import learning
        learning.record_feedback(d)
    except Exception:  # noqa: BLE001 - learning must never break logging
        pass
    return d


def delete(fid):
    _write([r for r in load() if r.get("id") != fid])
