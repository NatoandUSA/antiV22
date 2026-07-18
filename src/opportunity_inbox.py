"""Opportunity Inbox — ONE deduped, market-proof worklist across every source.

Replaces the old 'my formula ranks the winner' approach. The rule (owner's call):
- RANK BY REAL ETSY SALES EVIDENCE — actual units sold, revenue, favorites, and
  how many shops share the sales (spread = not monopolized = winnable). No
  invented composite drives the order.
- ETSY DECIDES, OTHER SOURCES CONFIRM — a keyword also seen on Supplier / Pinterest
  / Amazon gets a cross-validated CONFIDENCE badge, but supplier/pin hype never
  outranks real Etsy sales.
- DEDUP ACROSS FILES — every keyword is normalised to a canonical key (word-order
  insensitive, singularised, embroidery/tee variants folded) so the same niche
  from 4 files becomes ONE row.

Honest limits (stated, never faked):
- "Young shops are already winning it" (the strongest winnability signal) needs
  listing AGE, which the current bulk exports don't carry — shop-spread is used as
  the available proxy and age is flagged as a TODO for the extension.
- No Etsy private-algorithm or seller-community API exists; real sold/revenue from
  your HeyEtsy exports is the market's verdict and is what pros (eRank/EverBee) use.
"""
import json
import re
from pathlib import Path

from src import supplier_trend as st
from src.ytx_import import parse_number

IMPORTS = Path("data/imports")
# Where each source's newest import lives.
SRC_DIRS = {
    "etsy": IMPORTS / "etsy_spy",        # Etsy LISTINGS/spy -> real sold/revenue
    "supplier": IMPORTS / "supplier",
    "pinterest": IMPORTS / "pinterest",
    "ytrends": IMPORTS / "ytrends_ext",  # YTrends keyword tables (+ Amazon, by view)
}

# A keyword needs at least this many real units sold (across the scrape) to count
# as PROVEN demand rather than a lead.
PROVEN_SOLD = 10


# --------------------------- canonical dedup key ---------------------------
_STOP = {"the", "a", "an", "for", "with", "of", "and", "to", "your", "you",
         "in", "on", "s"}
_SYN = {"tee": "tshirt", "tees": "tshirt", "tshirts": "tshirt", "t": "tshirt"}


def _canon(kw):
    """Word-order-insensitive canonical key: normalise -> fold variants ->
    sort unique tokens. 'nurse embroidery sweatshirt' and 'embroidery nurse
    sweatshirts' collapse to the same key."""
    toks = re.sub(r"[^a-z0-9 ]", " ", (kw or "").lower()).split()
    out = []
    for t in toks:
        t = st._singular(t)          # folds plural + embroidery/monogram variants
        t = _SYN.get(t, t)
        if t and t not in _STOP and len(t) > 1:
            out.append(t)
    return " ".join(sorted(set(out)))


def _num(v):
    n = parse_number(v)
    return n if isinstance(n, (int, float)) else None


def _latest(dirpath):
    d = Path(dirpath)
    if not d.is_dir():
        return None
    for f in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return None


def _ci(headers, *needles, exclude=()):
    for i, h in enumerate(headers):
        hl = str(h).lower()
        if any(n in hl for n in needles) and not any(x in hl for x in exclude):
            return i
    return None


# --------------------------- per-source readers ----------------------------
def _emit(recs, canon, display, source, **fields):
    r = recs.get(canon)
    if not r:
        r = recs[canon] = {"display": display, "canon": canon,
                           "etsy_sold": 0.0, "etsy_rev": 0.0, "favorites": 0.0,
                           "listings": 0, "shops": set(), "views": None,
                           "competition": None, "sources": set(),
                           "supplier_demand": None, "pin_saves": None,
                           "amazon_vol": None, "conf": "high"}
    # keep the shortest clean display form (usually the cleanest keyword)
    if display and (len(display) < len(r["display"]) or not r["display"]):
        r["display"] = display
    r["sources"].add(source)
    for k, v in fields.items():
        if k == "shop":
            if v:
                r["shops"].add(str(v).strip().lower())
        elif k in ("etsy_sold", "etsy_rev", "favorites", "listings"):
            if isinstance(v, (int, float)):
                r[k] += v
        elif v is not None:
            r[k] = v


def _read_etsy(recs, mode):
    """Etsy LISTINGS / spy export -> the market proof (sold, revenue, favorites,
    shop spread), aggregated per keyword extracted from each title."""
    p = _latest(SRC_DIRS["etsy"])
    if not p:
        return
    H = p.get("headers") or []
    ti = _ci(H, "title", "product", "name")
    if ti is None:
        return
    si = _ci(H, "sold")
    ri = _ci(H, "revenue")
    fi = _ci(H, "favorite", "fav")
    shi = _ci(H, "shop", "seller", exclude=("id",))
    for row in (p.get("rows") or []):
        def c(i):
            return row[i] if (i is not None and i < len(row)) else None
        title = str(c(ti) or "").strip()
        if not title:
            continue
        kw = st.extract_keyword(title, mode)["keyword"]
        if not kw:
            continue
        _emit(recs, _canon(kw), kw, "etsy",
              etsy_sold=(_num(c(si)) or 0.0), etsy_rev=(_num(c(ri)) or 0.0),
              favorites=(_num(c(fi)) or 0.0), listings=1, shop=c(shi))


def _read_ytrends(recs):
    """YTrends keyword table (+ Amazon Xray) -> competition/views, and the Amazon
    source badge. Keyword tables carry a real keyword column."""
    p = _latest(SRC_DIRS["ytrends"])
    if not p:
        return
    H = p.get("headers") or []
    ki = _ci(H, "keyword", "phrase")
    if ki is None:
        return
    vi = _ci(H, "views", "view", "search volume", "volume")
    ci = _ci(H, "competition")
    li = _ci(H, "listing", "competing", exclude=("id", "url", "/"))
    is_amazon = "amazon" in str(p.get("view") or "").lower()
    src = "amazon" if is_amazon else "ytrends"
    for row in (p.get("rows") or []):
        def c(i):
            return row[i] if (i is not None and i < len(row)) else None
        kw = str(c(ki) or "").strip()
        if not kw:
            continue
        f = {"views": _num(c(vi)), "competition": c(ci)}
        if is_amazon:
            f["amazon_vol"] = _num(c(vi))
        _emit(recs, _canon(kw), kw, src, **f)


def _read_leads(recs, mode, source):
    """Supplier or Pinterest export -> confirmation badge + a demand hint."""
    p = _latest(SRC_DIRS[source])
    if not p:
        return
    for ld in st.analyze(p, mode=mode, limit=200):
        kw = ld.get("keyword")
        if not kw:
            continue
        f = {}
        if source == "supplier":
            f["supplier_demand"] = ld.get("supplier_demand")
        else:
            f["pin_saves"] = ld.get("sold_median")
        _emit(recs, _canon(kw), kw, source, **f)


# --------------------------- rank + verdict --------------------------------
def _verdict(r):
    """Market-proof verdict from the EVIDENCE (not a formula)."""
    try:
        from src.trademark import check as tm_check
        if tm_check((r["display"] or "").lower())[0] == "HIGH":
            return "SKIP", 9, "trademark HIGH — do not build"
    except Exception:  # noqa: BLE001
        pass
    sold = r["etsy_sold"]
    spread = len(r["shops"]) or r["listings"]
    if sold >= PROVEN_SOLD and spread >= 2:
        return "PROVEN WINNER", 0, "real Etsy sales, spread across shops = winnable"
    if sold > 0:
        return "SELLING", 1, ("sells but few shops — check if it's monopolised"
                              if spread < 2 else "early real sales")
    if len(r["sources"]) >= 2:
        return "CROSS-VALIDATED LEAD", 2, "multiple sources agree — validate on Etsy"
    return "LEAD", 3, "one source only — a demand lead, not proof"


def _evidence(r):
    bits = []
    if r["etsy_sold"]:
        bits.append(f"{int(r['etsy_sold'])} sold")
    if r["etsy_rev"]:
        bits.append(f"${_short(r['etsy_rev'])}")
    sp = len(r["shops"]) or r["listings"]
    if sp:
        bits.append(f"{sp} shop(s)" if r["shops"] else f"{sp} listing(s)")
    if not r["etsy_sold"]:
        if r["supplier_demand"]:
            bits.append(f"supplier {int(r['supplier_demand'])}")
        if r["pin_saves"]:
            bits.append(f"pins {int(r['pin_saves'])}")
        if r["amazon_vol"]:
            bits.append(f"amz vol {int(r['amazon_vol'])}")
    return " · ".join(bits) or "—"


def _short(n):
    n = float(n)
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return f"{n:.0f}"


SRC_BADGE = {"etsy": "🟢E", "ytrends": "🔎Y", "supplier": "🏭S",
             "pinterest": "📌P", "amazon": "🅰️A"}


# --------------------------- containment merge -----------------------------
# The title extractor is not perfectly consistent: the SAME niche can arrive as
# "nurse embroidery sweatshirt" from one listing and "embroidery nurse" from the
# next (product noun dropped). Word-order canon alone leaves them as 2 rows and
# splits the sales evidence. This pass folds a SHORTER keyword into the single
# more-specific keyword that already contains all its words, and ADDS the
# evidence together so the niche shows its true total sold/revenue/spread.
_MERGE_NUM = ("etsy_sold", "etsy_rev", "favorites", "listings")


def _combine(dst, src):
    """Fold src's evidence into dst (dst is the more specific / higher-proof one)."""
    for k in _MERGE_NUM:
        dst[k] = (dst.get(k) or 0) + (src.get(k) or 0)
    dst["shops"] |= src["shops"]
    dst["sources"] |= src["sources"]
    for k in ("views", "competition", "supplier_demand", "pin_saves", "amazon_vol"):
        if dst.get(k) in (None, "") and src.get(k) not in (None, ""):
            dst[k] = src[k]


def _merge_contained(recs):
    """Fold each keyword whose word-set is a strict subset of exactly one more
    specific keyword into that keyword. Ambiguous (contained by several) -> fold
    into the one with the most real Etsy sales; the market breaks the tie.
    1-word keys are left alone (too generic to safely absorb)."""
    items = [(c, set(c.split()), r) for c, r in recs.items()]
    # shortest first so a 2-word key merges before its 3-word target is itself
    # considered for merging upward
    items.sort(key=lambda t: len(t[1]))
    dead = set()
    for canon, toks, r in items:
        if canon in dead or len(toks) < 2:
            continue
        supers = [(c2, r2) for c2, t2, r2 in items
                  if c2 != canon and c2 not in dead
                  and toks < t2]  # strict subset
        if not supers:
            continue
        # market decides the target: most real sold, then most specific (longest)
        target_c, target_r = max(
            supers, key=lambda cr: (cr[1].get("etsy_sold") or 0, len(cr[0])))
        _combine(target_r, r)
        dead.add(canon)
    for c in dead:
        recs.pop(c, None)
    return recs


def build_inbox(mode=None, limit=60):
    """Merge the newest import from every source into ONE deduped, ranked list.
    Returns {counts, rows:[record...]} ordered PROVEN -> SELLING -> CROSS-VALIDATED
    -> LEAD, and inside each tier by real units sold then revenue then #sources."""
    recs = {}
    try:
        _read_etsy(recs, mode)
    except Exception:  # noqa: BLE001
        pass
    try:
        _read_ytrends(recs)
    except Exception:  # noqa: BLE001
        pass
    for s in ("supplier", "pinterest"):
        try:
            _read_leads(recs, mode, s)
        except Exception:  # noqa: BLE001
            pass
    _merge_contained(recs)

    rows = []
    for r in recs.values():
        verdict, tier, why = _verdict(r)
        r["verdict"], r["_tier"], r["why"] = verdict, tier, why
        r["evidence"] = _evidence(r)
        r["confidence"] = len(r["sources"])
        r["badges"] = " ".join(SRC_BADGE[s] for s in
                               ("etsy", "ytrends", "supplier", "pinterest", "amazon")
                               if s in r["sources"])
        rows.append(r)
    rows.sort(key=lambda r: (r["_tier"], -r["etsy_sold"], -r["etsy_rev"],
                             -r["confidence"]))
    counts = {"total": len(rows),
              "proven": sum(1 for r in rows if r["_tier"] == 0),
              "selling": sum(1 for r in rows if r["_tier"] == 1),
              "leads": sum(1 for r in rows if r["_tier"] in (2, 3))}
    return {"counts": counts, "rows": rows[:limit]}
