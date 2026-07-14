"""Private learning system — turns our own sales feedback into a scoring edge.

Every logged listing outcome (src/feedback.py) updates five pattern files. Future
runs read them so the tool scores smarter than a competitor using only public
keyword data:

  data/learning/winner_patterns.json     keywords/tags that produced sales
  data/learning/failed_patterns.json     keywords/listings that died (0 views/kills)
  data/learning/image_patterns.json       main-image / mockup styles that convert
  data/learning/tag_patterns.json          tags that earn impressions/favorites/orders
  data/learning/supplier_performance.json  suppliers that caused refunds/issues

Nothing here touches Etsy or publishes. It only remembers what worked for US.
"""
import json
import re
from pathlib import Path

DIR = Path("data/learning")
FILES = {
    "winner": DIR / "winner_patterns.json",
    "failed": DIR / "failed_patterns.json",
    "image": DIR / "image_patterns.json",
    "tag": DIR / "tag_patterns.json",
    "supplier": DIR / "supplier_performance.json",
}
DEFAULTS = {
    "winner": {"keywords": {}, "tags": {}},
    "failed": {"keywords": {}},
    "image": {"styles": {}},
    "tag": {"tags": {}},
    "supplier": {"suppliers": {}},
}


def _i(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _load(name):
    p = FILES[name]
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return json.loads(json.dumps(DEFAULTS[name]))   # fresh copy


def _save(name, data):
    DIR.mkdir(parents=True, exist_ok=True)
    FILES[name].write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_files():
    """Create every learning file with an empty structure if missing."""
    for name in FILES:
        if not FILES[name].exists():
            _save(name, DEFAULTS[name])


def _bump(bucket, key, **adds):
    key = (key or "").strip().lower()
    if not key:
        return
    row = bucket.setdefault(key, {"count": 0})
    row["count"] = row.get("count", 0) + 1
    for k, v in adds.items():
        row[k] = row.get(k, 0) + v


def _tags_of(d):
    t = d.get("tags")
    if isinstance(t, list):
        return [str(x) for x in t]
    return [s.strip() for s in str(t or "").replace("\n", ",").split(",") if s.strip()]


def record_feedback(d):
    """Fold one feedback row into all five pattern files."""
    kw = d.get("keyword")
    orders, carts = _i(d.get("orders")), _i(d.get("carts"))
    favs = _i(d.get("favorites"))
    views = _i(d.get("day_7_views") or d.get("views"))
    imp = _i(d.get("day_1_impressions") or d.get("impressions"))
    tags = _tags_of(d)

    if orders >= 1:
        w = _load("winner")
        _bump(w["keywords"], kw, orders=orders, favorites=favs)
        for t in tags:
            _bump(w["tags"], t, orders=orders)
        _save("winner", w)
    if views == 0 or (d.get("day7_action") == "KILL_LISTING"):
        f = _load("failed")
        _bump(f["keywords"], kw, zero_views=(1 if views == 0 else 0))
        _save("failed", f)

    img = _load("image")
    _bump(img["styles"], d.get("mockup_style") or d.get("main_image_version"),
          favorites=favs, carts=carts, orders=orders)
    _save("image", img)

    tg = _load("tag")
    for t in tags:
        _bump(tg["tags"], t, impressions=imp, favorites=favs, orders=orders)
    _save("tag", tg)

    sp = _load("supplier")
    issue = 1 if (d.get("refund_or_issue") and
                  str(d.get("refund_or_issue")).strip().lower()
                  not in ("", "no", "none", "0", "false")) else 0
    _bump(sp["suppliers"], d.get("supplier"), orders=orders, issues=issue)
    _save("supplier", sp)


# --------------------------- read side: scoring edge -----------------------
def winner_keywords():
    return set(_load("winner").get("keywords", {}))


def winner_tags():
    return set(_load("winner").get("tags", {}))


def problem_suppliers():
    out = {}
    for s, row in _load("supplier").get("suppliers", {}).items():
        if row.get("issues", 0) >= 1:
            out[s] = row["issues"]
    return out


def supplier_edge(supplier):
    """(delta:int, note) for a supplier from our OWN logged P&L + refunds.
    Profitable-for-us -> boost; refund-prone or net-negative -> warning. This is
    what makes the supplier net-profit that profit.add logs actually affect
    future scoring (it was recorded but never read)."""
    if not supplier:
        return 0, None
    row = _load("supplier").get("suppliers", {}).get(supplier.strip().lower())
    if not row:
        return 0, None
    issues = _i(row.get("issues"))
    sales = _i(row.get("sales")) or _i(row.get("orders"))
    net = _i(row.get("net_profit_cents")) / 100.0
    if issues >= 1:
        return -3, f"Supplier '{supplier}' caused {issues} refund/issue(s) in our data."
    if sales >= 2 and net > 0:
        return 2, (f"Supplier '{supplier}' has been profitable for us "
                   f"(~${net / sales:.2f}/sale over {sales} sales).")
    if sales >= 2 and net <= 0:
        return -2, (f"Supplier '{supplier}' has been net-negative for us over "
                    f"{sales} sales.")
    return 0, None


def best_image_style():
    """The mockup/image style with the most orders in our data (or None) -- reads
    the image magnitudes that were recorded but never surfaced. Returns
    (style, orders)."""
    styles = _load("image").get("styles", {})
    best = max(styles.items(), key=lambda kv: _i(kv[1].get("orders")),
               default=None)
    if not best or _i(best[1].get("orders")) < 1:
        return None
    return best[0], _i(best[1].get("orders"))


def learning_note(kw, tags=None, supplier=None):
    """A short list of private-data notes + a small can-we-win nudge (int).

    Positive when we have proof this keyword/tag converted; negative when a tag
    or supplier has a bad track record for us."""
    notes, delta = [], 0
    kwl = (kw or "").strip().lower()
    w = _load("winner")
    wk_rows, wt_rows = w.get("keywords", {}), w.get("tags", {})
    # winner keyword: weighted by how many orders it actually sold for us
    if kwl in wk_rows:
        o = _i(wk_rows[kwl].get("orders"))
        b = 4 + min(6, o)                     # 1 order -> +5 ... 6+ orders -> +10
        delta += b
        notes.append(f"Private data: '{kw}' has sold {o} order(s) for us (+{b}).")
    # proven tags: weighted by their combined orders, not mere presence
    hits = [(t, _i(wt_rows.get(str(t).strip().lower(), {}).get("orders")))
            for t in (tags or []) if str(t).strip().lower() in wt_rows]
    if hits:
        tot = sum(o for _t, o in hits)
        b = 2 + min(6, tot)
        delta += b
        top = sorted(hits, key=lambda x: -x[1])[:4]
        notes.append("Proven tags in our sales data: "
                     + ", ".join(f"{t} ({o})" for t, o in top) + f" (+{b}).")
    if kwl in _load("failed").get("keywords", {}):
        delta -= 4
        notes.append(f"Caution: '{kw}' has died for us before (low/zero traffic).")
    # supplier: real P&L + refund history (not just presence of an issue)
    s_delta, s_note = supplier_edge(supplier)
    if s_note:
        delta += s_delta
        notes.append(s_note)
    return notes, delta


def summary():
    """Counts for the dashboard / healthcheck."""
    return {
        "winning_keywords": len(_load("winner").get("keywords", {})),
        "winning_tags": len(_load("winner").get("tags", {})),
        "failed_keywords": len(_load("failed").get("keywords", {})),
        "image_styles_tracked": len(_load("image").get("styles", {})),
        "tags_tracked": len(_load("tag").get("tags", {})),
        "suppliers_tracked": len(_load("supplier").get("suppliers", {})),
        "problem_suppliers": len(problem_suppliers()),
        "best_image_style": best_image_style(),
    }
