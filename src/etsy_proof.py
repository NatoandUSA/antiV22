"""Etsy Proof layer (V30, spec layer L1) - rank by REAL Etsy sales evidence.

The strongest signal a niche will sell isn't modelled search volume - it's listings
that are ALREADY selling on Etsy. This lane ingests a product-research CSV exported
from Alura (Product Research) or EverBee (Product Analytics / Shop Analyzer) - real
per-listing units sold, revenue, price, listing AGE, and reviews - aggregates it by
keyword, and produces an Etsy-Proof verdict that sits ABOVE the market-signal score:

    etsy_proof_score = sold_rank*0.45 + revenue_rank*0.25
                     + shop_spread_rank*0.20 + young_winner_rank*0.10   (spec formula)

    PROVEN_WINNER : real sales, spread across 2+ shops (winnable, not monopolised)
    SELLING       : real sales but thin spread (check monopoly)
    YOUNG_WINNER   flag: newer listings (< ~12 months) already selling = beatable market

Honest limits: this needs the paid product-export (Alura Professional / EverBee);
until one is dropped in, the lane is simply empty and the engine falls back to the
market-signal layer. Nothing here is faked - no export, no proof.
"""
import csv
import json
import re
import statistics as _stats
from pathlib import Path

from src import supplier_trend as st
from src.engine_config import get as _cfg

PROOF_DIR = Path("data/imports/etsy_proof")


def _proven_sold():
    return float(_cfg("proven_sold"))


def _strong_sold():
    return float(_cfg("strong_seller_sold"))


def _min_shops():
    return int(_cfg("proven_min_shops"))


def _young_months():
    return int(_cfg("young_winner_months"))


def _num(v):
    if v is None:
        return None
    s = str(v).strip().lower().replace(",", "").replace("$", "").replace("€", "")
    if not s or s in ("-", "n/a", "lock", "locked"):
        return None
    mult = 1.0
    if s.endswith("k"):
        mult, s = 1000.0, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000.0, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _age_months(v):
    """'3y 4m' / '140 Mo.' / '7y 0m' / '18 months' -> total months, or None."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    yrs = re.search(r"(\d+)\s*y", s)
    mos = re.search(r"(\d+)\s*m", s)
    total = 0
    got = False
    if yrs:
        total += int(yrs.group(1)) * 12
        got = True
    if mos:
        total += int(mos.group(1))
        got = True
    if not got:
        n = re.search(r"(\d+)", s)
        if n:
            total = int(n.group(1))         # bare number of months (EverBee '140 Mo.')
            got = True
    return total if got else None


def _ci(headers, *needles, exclude=()):
    for i, h in enumerate(headers):
        hl = str(h).lower()
        if any(n in hl for n in needles) and not any(x in hl for x in exclude):
            return i
    return None


def _read_csv(path):
    try:
        rows = list(csv.reader(Path(path).open(encoding="utf-8-sig")))
    except Exception:  # noqa: BLE001
        return [], []
    if not rows:
        return [], []
    return rows[0], rows[1:]


def rows_from_export(headers, data, mode=None):
    """Map an Alura/EverBee product-export table to per-listing proof rows:
    {keyword, title, shop, sold, revenue, price, age_months, reviews}."""
    H = [str(h).lower() for h in headers]
    ti = _ci(H, "title", "product", "name", "listing", exclude=("shop", "seller"))
    if ti is None:
        return []
    # 'sales' / 'total sales' / 'mo. sales' -> units sold
    si = _ci(H, "sales", "sold", "orders", exclude=("revenue", "$"))
    ri = _ci(H, "revenue", exclude=())
    pi = _ci(H, "price", exclude=("was",))
    shi = _ci(H, "shop", "seller", exclude=("id",))
    ai = _ci(H, "age")
    revi = _ci(H, "review", "rating", exclude=())
    out = []
    for r in data:
        def c(i):
            return r[i] if (i is not None and i < len(r)) else None
        title = str(c(ti) or "").strip()
        if not title:
            continue
        kw = st.extract_keyword(title, mode).get("keyword")
        if not kw:
            continue
        out.append({
            "keyword": kw, "title": title, "shop": (c(shi) or "").strip(),
            "sold": _num(c(si)), "revenue": _num(c(ri)), "price": _num(c(pi)),
            "age_months": _age_months(c(ai)), "reviews": _num(c(revi)),
        })
    return out


def save_export(headers, data, mode=None, source="alura"):
    """Persist a product export as proof rows for the ranker. Returns count saved."""
    rows = rows_from_export(headers, data, mode)
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"source": source, "count": len(rows), "rows": rows}
    (PROOF_DIR / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def save_export_file(path, mode=None, source="alura"):
    headers, data = _read_csv(path)
    return save_export(headers, data, mode, source)


def _latest_rows():
    p = PROOF_DIR / "latest.json"
    if not p.is_file():
        return []
    try:
        return (json.loads(p.read_text(encoding="utf-8")) or {}).get("rows") or []
    except Exception:  # noqa: BLE001
        return []


def _canon(kw):
    return " ".join(sorted(set(
        st._singular(w) for w in re.findall(r"[a-z0-9]+", (kw or "").lower())
        if len(w) > 1)))


def _pct(vals):
    s = sorted(v for v in vals if v is not None)
    if not s:
        return lambda x: None
    return lambda x: (100.0 * sum(1 for v in s if v <= x) / len(s)
                      if x is not None else None)


def build_proof(mode=None):
    """Aggregate the latest product export into a {canon_keyword: proof} map.

    proof = {keyword, sold, revenue, shops, listings, young, score, verdict,
    evidence}. Empty dict when no export is present (engine then uses market signal)."""
    rows = _latest_rows()
    if not rows:
        return {}
    agg = {}
    for r in rows:
        c = _canon(r["keyword"])
        if not c:
            continue
        a = agg.setdefault(c, {"keyword": r["keyword"], "sold": 0.0, "revenue": 0.0,
                               "shops": set(), "listings": 0, "young": 0})
        if len(r["keyword"]) < len(a["keyword"]):
            a["keyword"] = r["keyword"]
        a["sold"] += r["sold"] or 0
        a["revenue"] += r["revenue"] or 0
        a["listings"] += 1
        if r["shop"]:
            a["shops"].add(r["shop"].lower())
        if (r["age_months"] is not None and r["age_months"] <= _young_months()
                and (r["sold"] or 0) > 0):
            a["young"] += 1

    recs = list(agg.values())
    # spread = distinct shops when shop data exists; when the export has NO shop
    # column we only know listing count, which is NOT a monopoly signal - so we
    # track shops_known and never award PROVEN on listing-count alone.
    #
    # HONEST-NULLS on the score too (CPA fix): a component whose source column is
    # entirely absent must be EXCLUDED and the remaining weights renormalised -
    # otherwise pr_spread over all-zero shops pays a uniform +20 to every niche
    # (inflated absolute scores, e.g. 95/100 on a two-column export).
    has_shop_data = any(r.get("shop") for r in rows)
    has_age_data = any(r.get("age_months") is not None for r in rows)
    pr_sold = _pct([a["sold"] for a in recs])
    pr_rev = _pct([a["revenue"] for a in recs])
    pr_spread = _pct([len(a["shops"]) for a in recs])
    pr_young = _pct([a["young"] for a in recs])
    weights = [("sold", 0.45), ("rev", 0.25)]
    if has_shop_data:
        weights.append(("spread", 0.20))
    if has_age_data:
        weights.append(("young", 0.10))
    wtot = sum(w for _, w in weights)
    out = {}
    for c, a in agg.items():
        shops = len(a["shops"])
        shops_known = shops > 0
        comp = {"sold": pr_sold(a["sold"]) or 0,
                "rev": pr_rev(a["revenue"]) or 0,
                "spread": pr_spread(shops) or 0,
                "young": pr_young(a["young"]) or 0}
        score = round(sum(comp[k] * w for k, w in weights) / wtot, 1)
        if a["sold"] >= _proven_sold() and shops_known and shops >= _min_shops():
            verdict = "PROVEN_WINNER"          # real sales AND spread across shops
        elif a["sold"] >= _strong_sold() and shops_known and shops >= _min_shops():
            verdict = "STRONG_SELLER"          # solid sales + spread, below PROVEN bar
        elif a["sold"] > 0:
            verdict = "SELLING"                # sells, but spread unknown/monopolised
        else:
            verdict = "LISTED"
        out[c] = {
            "keyword": a["keyword"], "sold": a["sold"], "revenue": a["revenue"],
            "shops": shops, "shops_known": shops_known, "listings": a["listings"],
            "young": a["young"], "score": score, "verdict": verdict,
            "young_winner": a["young"] >= 2,
            "evidence": _evidence(a["sold"], a["revenue"], shops, shops_known,
                                  a["listings"], a["young"]),
        }
    return out


def _short(n):
    n = float(n or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return f"{n:.0f}"


def _evidence(sold, revenue, shops, shops_known, listings, young):
    bits = []
    if sold:
        bits.append(f"{int(sold)} sold")
    if revenue:
        bits.append(f"${_short(revenue)}")
    if shops_known and shops:
        bits.append(f"{int(shops)} shop(s)")
    elif listings:
        bits.append(f"{int(listings)} listing(s)")   # shop data absent - not spread
    if young:
        bits.append(f"{int(young)} young winner(s)")
    return " · ".join(bits) or "listed, no sales data"


_PROOF_PRODUCT = {"sweatshirt", "crewneck", "hoodie", "tshirt", "tee", "shirt",
                  "necklace", "bracelet", "ring", "mug", "tumbler", "tote", "bag",
                  "hat", "cap", "blanket", "pillow", "sign", "decal", "sticker"}
# Words that describe HOW/WHAT-KIND, not WHICH niche - a match can't rest on these.
_PROOF_GENERIC = {"personalized", "personalised", "custom", "customized", "embroidered",
                  "embroidery", "monogram", "monogrammed", "gift", "name", "custom",
                  "cute", "cozy", "matching", "set"}


def proof_for(keyword, proof_map):
    """Look up proof for a keyword, tolerating phrasing differences between the
    inbox keyword ('personalized nurse sweatshirt') and the extracted proof keyword
    ('nurse embroidery sweatshirt'). Requires a shared SUBJECT token (a niche word
    that isn't just a product noun or a generic modifier) so a broad term like
    'embroidered sweatshirt' can't hijack a specific niche's proof."""
    if not proof_map:
        return None
    c = _canon(keyword)
    kt = set(c.split())
    if len(kt) < 2:
        return None
    if c in proof_map:
        # exact canonical match -> full confidence (the PROVEN override may fire)
        return dict(proof_map[c], match="exact", match_confidence=1.0)
    best, best_score = None, 0.0
    for pc, p in proof_map.items():
        pt = set(pc.split())
        ov = kt & pt
        if len(ov) < 2:
            continue
        # the overlap must include a real SUBJECT word (not just product/modifier),
        # and share a product noun or be a subset relationship
        subject = ov - _PROOF_PRODUCT - _PROOF_GENERIC
        if not subject:
            continue
        if not (ov & _PROOF_PRODUCT or kt <= pt or pt <= kt):
            continue
        j = len(ov) / len(kt | pt)
        if j > best_score:
            best, best_score = p, j
    if best_score >= float(_cfg("proof_match_min_conf")):
        # fuzzy match -> carry the confidence; decide() only allows the PROVEN ->
        # BUILD override at high confidence, medium caps at CONFIRM_FIRST.
        return dict(best, match="fuzzy", match_confidence=round(best_score, 2))
    return None


def latest_info():
    """{count, source} for the newest proof export, or None."""
    p = PROOF_DIR / "latest.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8")) or {}
        return {"count": d.get("count", 0), "source": d.get("source", "")}
    except Exception:  # noqa: BLE001
        return None
