"""Pattern Miner (V29) - the engine that explains WHY winning listings win.

Give it a keyword; it pulls the top Etsy listings for that keyword (from the latest
Etsy Spy import, or the accumulated etsy_listings.csv grouped by the search term) and
mines the shared winning pattern:

  - title vocabulary + leading (first-40-char) words the winners front-load
  - title STRUCTURE (personalization + product + gift/occasion)
  - repeated multi-word phrases
  - price band (auto-detects VND vs USD)
  - shop spread + concentration
  - ad / star-seller / free-ship norms
  - personalization rate
  - exploitable competitor GAPS (where the field is weak)
  - a keyword-expansion SEED for the Keyword Lab

Honest limits: Etsy Spy exports carry title / price / shop / star-seller / ad /
free-ship - NOT per-listing units-sold, reviews, tags, or listing age (those come
through as blanks). So the miner reads the signals that ARE present and says so;
it never fabricates sold counts or tag banks it doesn't have.
"""
import csv
import re
import statistics as _stats
from collections import Counter
from pathlib import Path

from src import supplier_trend as st
from src.product_fit import POD_NOUNS, JEWELRY_NOUNS, ACRYLIC_NOUNS, EMB_SIGNS

MASTER = Path("etsy_listings.csv")
_PRODUCT_NOUNS = POD_NOUNS | JEWELRY_NOUNS | ACRYLIC_NOUNS | EMB_SIGNS
_PERS = {"personalized", "personalised", "custom", "customized", "monogram",
         "monogrammed", "name", "named", "initial", "initials", "customizable"}
_GIFT = {"gift", "gifts", "gift-for", "present"}
_STOP = {"the", "a", "an", "for", "with", "of", "and", "to", "your", "you", "in",
         "on", "or", "by", "from", "&", "|", "-", "s", "is", "it", "this", "that",
         "her", "him", "his", "my", "our", "are", "be", "de"}
def _vnd_rate():
    from src.engine_config import get as _cfg
    return float(_cfg("vnd_per_usd"))   # configurable in config/engine.json


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _flag(v):
    return str(v).strip() in ("1", "true", "True", "yes", "Y")


# --------------------------- load the listing batch ------------------------
def _from_import():
    """(keyword_hint, [listings]) from the latest Etsy Spy import, or (None, [])."""
    try:
        from src import supplier_trend as st
        payload = st.load_latest("etsy")
    except Exception:  # noqa: BLE001
        payload = None
    if not payload:
        return None, []
    H = [str(h).lower() for h in (payload.get("headers") or [])]

    def col(*names, exclude=()):
        for i, h in enumerate(H):
            if any(n in h for n in names) and not any(x in h for x in exclude):
                return i
        return None
    ti = col("title", "product", "name")
    if ti is None:
        return None, []
    pi = col("price", exclude=("was", "compare"))
    shi = col("shop", "seller", exclude=("id",))
    sti = col("star")
    adi = col("ad", "promoted", exclude=("add",))
    fsi = col("free", "ship")
    si = col("search", "query", "keyword")
    out = []
    hint = None
    for row in (payload.get("rows") or []):
        def c(i):
            return row[i] if (i is not None and i < len(row)) else None
        title = str(c(ti) or "").strip()
        if not title:
            continue
        if hint is None and si is not None:
            hint = str(c(si) or "").strip() or None
        out.append({"title": title, "price": _num(c(pi)), "shop": c(shi),
                    "star": _flag(c(sti)), "ad": _flag(c(adi)),
                    "freeship": _flag(c(fsi))})
    return hint, out


def _from_master(keyword=None):
    """(keyword, [listings]) from etsy_listings.csv, filtered to the search group
    that best matches `keyword` (or the largest group if none given)."""
    if not MASTER.is_file():
        return keyword, []
    try:
        rows = list(csv.DictReader(MASTER.open(encoding="utf-8-sig")))
    except Exception:  # noqa: BLE001
        return keyword, []
    groups = {}
    for r in rows:
        groups.setdefault((r.get("search") or "").strip(), []).append(r)
    if not groups:
        return keyword, []
    key = None
    if keyword:
        kl = keyword.lower()
        for g in groups:
            if g and (kl in g.lower() or g.lower() in kl):
                key = g
                break
    if key is None:
        key = max(groups, key=lambda g: len(groups[g]))
    batch = [{"title": (r.get("title") or "").strip(),
              "price": _num(r.get("price_num") or r.get("price")),
              "shop": r.get("shop"), "star": _flag(r.get("star_seller")),
              "ad": _flag(r.get("ad")), "freeship": _flag(r.get("free_shipping"))}
             for r in groups[key] if (r.get("title") or "").strip()]
    return (key or keyword), batch


def load_batch(keyword=None):
    """Best listings batch for a keyword: prefer a fresh Spy import, else the CSV."""
    hint, batch = _from_import()
    if batch:
        return (keyword or hint), batch
    return _from_master(keyword)


# --------------------------- the mining ------------------------------------
def _tokens(title):
    # Singularise so plural product words ("sweatshirts", "mugs") collapse to their
    # singular and match the singular-only product-noun sets — otherwise the miner
    # under-counts "names a product" and the Keyword Lab picks "sweatshirts" as a
    # subject and emits nonsense long-tails.
    return [st._singular(w) for w in re.findall(r"[a-z0-9]+", (title or "").lower())
            if w not in _STOP and len(w) > 1]


def _price_band(prices):
    vals = [p for p in prices if isinstance(p, (int, float)) and p > 0]
    if not vals:
        return None
    # Decide VND vs USD from the DISTRIBUTION (median), not per-price - otherwise a
    # single premium USD listing ($1,299) gets divided by 25,000 and mislabels the
    # whole band as VND.
    is_vnd = _stats.median(vals) > 2000
    usd = sorted((p / _vnd_rate()) if is_vnd else p for p in vals)
    n = len(usd)
    lo_i = n // 5 if n >= 5 else 0
    hi_i = min(n - 1, (n * 4) // 5) if n >= 5 else n - 1   # symmetric ~P80
    return {"median": round(_stats.median(usd), 2),
            "low": round(usd[lo_i], 2), "high": round(usd[hi_i], 2),
            "note": (f"converted from VND @ {int(_vnd_rate()):,}/USD"
                     if is_vnd else "USD")}


def mine(keyword=None):
    """Mine the winning pattern for a keyword. Returns a structured dict (always,
    even for an empty batch, so the view can explain what's missing)."""
    kw, batch = load_batch(keyword)
    n = len(batch)
    res = {"keyword": kw, "n": n, "n_shops": 0, "top_words": [], "leading": [],
           "phrases": [], "structure": {}, "price": None, "signals": {},
           "gaps": [], "seed_words": [], "have": False}
    if not n:
        return res
    res["have"] = True
    titles = [b["title"] for b in batch]
    shops = {(b["shop"] or "").strip().lower() for b in batch if b.get("shop")}
    res["n_shops"] = len(shops)

    # 1. word frequency (share of listings that use each word)
    docword = [set(_tokens(t)) for t in titles]
    wc = Counter()
    for s in docword:
        wc.update(s)
    content = [(w, round(100 * c / n)) for w, c in wc.most_common(40)
               if w not in _PERS and w not in _GIFT]
    res["top_words"] = content[:12]

    # 2. leading words (first ~40 chars = what Etsy weights most)
    lead = Counter()
    for t in titles:
        for w in set(_tokens(t[:40])):
            lead[w] += 1
    res["leading"] = [(w, round(100 * c / n)) for w, c in lead.most_common(8)]

    # 3. repeated 2-word phrases
    ph = Counter()
    for t in titles:
        toks = _tokens(t)
        for a, b in zip(toks, toks[1:]):
            ph[f"{a} {b}"] += 1
    res["phrases"] = [(p, c) for p, c in ph.most_common(8) if c >= max(2, n // 6)]

    # 4. structure rates
    def rate(pred):
        return round(100 * sum(1 for t in titles if pred(t)) / n)
    tw = [set(_tokens(t)) for t in titles]
    res["structure"] = {
        "personalization": round(100 * sum(1 for s in tw if s & _PERS) / n),
        "has_product": round(100 * sum(1 for s in tw if s & _PRODUCT_NOUNS) / n),
        "gift": round(100 * sum(1 for s in tw if s & _GIFT) / n),
        "avg_words": round(_stats.mean(len(_tokens(t)) for t in titles), 1),
        "avg_chars": round(_stats.mean(len(t) for t in titles)),
    }

    # 5. price + 6. shop spread
    res["price"] = _price_band([b["price"] for b in batch])
    top_shop = Counter((b["shop"] or "").strip().lower()
                       for b in batch if b.get("shop")).most_common(1)
    res["shop_concentration"] = (round(100 * top_shop[0][1] / n) if top_shop else 0)

    # 7. marketplace signals
    res["signals"] = {
        "ad": round(100 * sum(1 for b in batch if b["ad"]) / n),
        "star": round(100 * sum(1 for b in batch if b["star"]) / n),
        "freeship": round(100 * sum(1 for b in batch if b["freeship"]) / n),
        "personalization": res["structure"]["personalization"],
    }

    # 8. exploitable gaps (where the field is weak -> your opening)
    g = []
    s = res["structure"]
    sig = res["signals"]
    if s["personalization"] < 60:
        g.append(f"Only {s['personalization']}% personalize the title - add a "
                 "\"Custom Name\" angle to stand out.")
    if s["gift"] < 40:
        g.append(f"Only {s['gift']}% frame it as a GIFT - lead with gift intent "
                 "(occasion + recipient).")
    if sig["freeship"] < 60:
        g.append(f"Only {sig['freeship']}% offer free shipping - free ship helps "
                 "US visibility.")
    if s["avg_words"] < 10:
        g.append(f"Titles average {s['avg_words']} words - you can pack more "
                 "long-tail keywords (aim ~13-14 words).")
    if res.get("shop_concentration", 0) >= 40:
        g.append(f"One shop holds ~{res['shop_concentration']}% of the top slots "
                 "- entrenched; differentiate hard or pick a sub-niche.")
    if not g:
        g.append("Field is well-optimised - win on photo quality, review velocity, "
                 "and a sharper personalization offer.")
    res["gaps"] = g

    # 9. keyword-expansion seed = the strongest content subject words
    res["seed_words"] = [w for w, pct in content if pct >= 25][:8] or \
                        [w for w, _ in content[:6]]
    return res
