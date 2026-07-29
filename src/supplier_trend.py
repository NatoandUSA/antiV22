"""Supplier Trend -> Demand (the REVERSE signal).

Factories and wholesalers (Alibaba / AliExpress / 1688) only mass-list and restock
what already sells downstream, so a surging supplier is a LEADING demand signal:
if many suppliers make the same product, and it sells + gets reordered, buyers (and
other sellers) are chasing that keyword. This module turns a manually exported
supplier product table into ranked KEYWORD LEADS with a Supplier-Demand score.

HONESTY (baked in):
- Supplier heat is a demand *lead*, not proof of Etsy demand. Leads must still be
  validated against Etsy competition (the view does a best-effort cross-check;
  the Launch Kit pulls the real Etsy read).
- Keyword extraction from messy, brand-stuffed titles is rough. Every lead carries
  a confidence flag; we never pretend a noisy title produced a clean keyword.
- A missing metric is scored as an honest null, never a default.

No network, no scraping. Pure parsing of a file YOU exported by hand.
"""
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

from src import product_fit as pf
from src.ytx_import import parse_number

DIRS = {"supplier": Path("data/imports/supplier"),
        "pinterest": Path("data/imports/pinterest"),
        "etsy": Path("data/imports/etsy_spy"),
        # Etsy SEARCH RESULTS (the listings currently ranking for a keyword).
        # Its own dir on purpose: Pattern Miner reads it as 'winners', but the
        # FROZEN proof/opportunity engines read ONLY etsy_spy, so search-result
        # candidates never leak into the ranking math (they are explicitly
        # SEARCH_RESULT_CANDIDATE_NOT_PROOF).
        "etsy_search": Path("data/imports/etsy_search")}
SUPPLIER_DIR = DIRS["supplier"]   # back-compat alias

ALL_NOUNS = pf.POD_NOUNS | pf.JEWELRY_NOUNS | pf.ACRYLIC_NOUNS

# Common design / motif words that ARE the niche (not brand noise) — lets us keep
# "dragon", "floral", "western" etc. as the meaningful modifier before the product.
THEME = {
    "dragon", "cat", "dog", "bear", "bee", "butterfly", "floral", "flower", "rose",
    "skull", "wave", "sun", "moon", "star", "heart", "cherry", "mushroom", "frog",
    "snake", "tiger", "wolf", "horse", "cow", "chicken", "fish", "angel", "cross",
    "western", "cowboy", "cowgirl", "celestial", "ghost", "pumpkin", "snowman",
    "reindeer", "santa", "name", "initial", "letter", "alphabet", "varsity",
    "college", "vintage", "retro", "checkered", "smiley", "daisy", "sunflower",
    "leopard", "cheetah", "camo", "tie", "dye", "coquette", "boho", "aesthetic",
}
# The modifiers worth keeping in a keyword (a real signal, not marketing filler).
MEANINGFUL = pf.EMB_SIGNS | pf.BUYER_INTENT_SIGNS | pf.VAGUE_MODIFIERS | THEME

# Words to drop: marketing / sourcing / material / size / color noise that carries
# no buyer meaning. Product nouns + MEANINGFUL words survive this.
STOP = {
    # sourcing / marketing
    "custom", "customized", "customize", "oem", "odm", "wholesale", "factory",
    "supplier", "manufacturer", "moq", "hot", "sale", "sales", "new", "high",
    "quality", "premium", "luxury", "fashion", "fashionable", "trendy", "trending",
    "cheap", "price", "priced", "drop", "dropshipping", "dropship", "bulk", "lot",
    "pcs", "piece", "pieces", "set", "sets", "pack", "logo", "print", "printed",
    "printing", "diy", "design", "designs", "styles", "style", "standard", "basic",
    "classic", "brand", "branded", "wholesales", "in", "stock", "ready", "free",
    "shipping", "ship", "fast", "delivery", "certified", "guaranteed",
    # audience / fit (kept out of the keyword; buyer-intent words survive via MEANINGFUL)
    "men", "mens", "man", "women", "womens", "woman", "unisex", "kids", "kid",
    "boys", "boy", "girls", "girl", "adult", "adults", "ladies", "lady",
    "oversized", "loose", "slim", "regular", "plus", "size", "sizes",
    # material / color
    "cotton", "polyester", "poly", "fleece", "wool", "blend", "acrylic", "nylon",
    "spandex", "linen", "denim", "leather", "pu", "heavyweight", "lightweight",
    "thick", "soft", "warm", "black", "white", "grey", "gray", "blue", "red",
    "green", "pink", "beige", "brown", "navy", "cream", "solid", "washed",
    # filler
    "and", "with", "the", "for", "of", "your", "you", "a", "an", "to",
    "women's", "men's", "girl's", "boy's",
}

_STAMP_ISO = "%Y-%m-%d %H:%M"


# --------------------------- keyword extraction ----------------------------
# Canonicalise decoration-technique variants so "embroidered / embroidery" (and
# "monogrammed / monogram") group into ONE keyword instead of splitting the signal.
_CANON = {"embroider": "embroidery", "embroidered": "embroidery",
          "embroidery": "embroidery", "monogrammed": "monogram", "monogram": "monogram"}


def _singular(w):
    w = _CANON.get(w, w)
    return w[:-1] if (w.endswith("s") and w[:-1] in ALL_NOUNS) else w


def extract_keyword(title, mode=None):
    """A messy supplier title -> {keyword, confidence, product_type}.

    Strategy: strip sourcing/material/color noise, find the product noun, keep the
    meaningful modifiers (embroidery / occasion / theme). confidence is HIGH when we
    found BOTH a real product noun and a meaningful modifier, MED with just a noun,
    LOW when neither is clear (brand-stuffed or generic)."""
    t = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    toks = [_singular(w) for w in t.split()
            if w and not w.isdigit() and len(w) > 1 and w not in STOP]
    if not toks:
        return {"keyword": "", "confidence": "low", "product_type": ""}
    noun = None
    for w in reversed(toks):            # last product noun = the head product
        if w in ALL_NOUNS:
            noun = w
            break
    signals = []
    for w in toks:
        if w in MEANINGFUL and w != noun and w not in signals:
            signals.append(w)
    if noun:
        words = signals[:2] + [noun]
        conf = "high" if signals else "med"
    else:
        words = signals[:2] or toks[:3]     # no product noun -> take content words
        conf = "med" if signals else "low"
    # de-dupe preserving order, cap length
    seen, kw_words = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            kw_words.append(w)
    return {"keyword": " ".join(kw_words[:4]).strip(), "confidence": conf,
            "product_type": noun or ""}


# --------------------------- column mapping --------------------------------
def _col(headers, *needles, exclude=()):
    for i, h in enumerate(headers):
        hl = str(h).lower()
        if any(n in hl for n in needles) and not any(x in hl for x in exclude):
            return i
    return None


def _map(headers):
    return {
        # "listing" = YTrends Spy's title column (LISTING); exclude listing_id
        "title": _col(headers, "title", "product", "name", "description",
                      "listing", exclude=("id",)),
        # Pinterest "saves"/"repins" are the same kind of traction signal as
        # supplier "sold", so they feed the same slot.
        "sold": _col(headers, "sold", "orders", "save", "repin", "sale"),
        "reorder": _col(headers, "reorder", "repeat", "re-order"),
        "price": _col(headers, "price", "cost"),
        "suppliers": _col(headers, "supplier count", "num suppliers", "results"),
        "url": _col(headers, "url", "link", "href"),
    }


def _pct(v):
    """A reorder-rate cell -> 0-100. Accepts '40%', '40', '0.4'."""
    n = parse_number(v)
    if n is None:
        return None
    if n <= 1.0:            # a fraction like 0.40
        n *= 100.0
    return max(0.0, min(100.0, n))


# --------------------------- demand scoring --------------------------------
def _median(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _demand(sold_med, reorder_max, n_suppliers):
    """Supplier-Demand 0-100 from the signals present (honest-null over what's
    missing). sold + reorder are the trustworthy signals; supplier-count is real
    but double-edged (also means more resellers), so it's the smallest weight."""
    parts = []
    if sold_med is not None:
        parts.append((min(100.0, 33.0 * math.log10(max(1.0, sold_med))), 0.35))
    if reorder_max is not None:
        parts.append((reorder_max, 0.35))
    if n_suppliers:
        parts.append((min(100.0, 40.0 * math.log10(1.0 + n_suppliers)), 0.30))
    if not parts:
        return None
    tw = sum(w for _, w in parts)
    return round(sum(v * w for v, w in parts) / tw, 1)


def analyze(payload, mode=None, limit=40):
    """Supplier product table -> ranked keyword leads. Each lead:
    {keyword, supplier_demand, supplier_count, sold_median, reorder_pct,
     confidence, product_type, example_title}. Rows that don't reduce to a
     launchable product keyword are dropped (same product-fit filter the rest of
     the pipeline uses)."""
    headers = payload.get("headers") or []
    rows = payload.get("rows") or []
    idx = _map(headers)
    if idx["title"] is None:            # nothing to extract keywords from
        return []

    def cell(r, key):
        i = idx[key]
        return r[i] if (i is not None and i < len(r)) else None

    groups = {}
    for r in rows:
        title = str(cell(r, "title") or "").strip()
        if not title:
            continue
        ext = extract_keyword(title, mode)
        kw = ext["keyword"]
        if not kw or len(kw) < 3:
            continue
        fit = pf.classify(kw, mode)
        if not fit["launchable"] and fit["status"] not in pf.LAUNCHABLE:
            continue
        g = groups.get(kw)
        if not g:
            g = groups[kw] = {"keyword": kw, "n": 0, "sold": [], "reorder": [],
                              "conf": ext["confidence"], "pt": ext["product_type"],
                              "example": title}
        g["n"] += 1
        s = parse_number(cell(r, "sold"))
        if s is not None:
            g["sold"].append(s)
        rp = _pct(cell(r, "reorder"))
        if rp is not None:
            g["reorder"].append(rp)
        # keep the strongest confidence seen for this keyword
        if ext["confidence"] == "high":
            g["conf"] = "high"

    leads = []
    for kw, g in groups.items():
        sold_med = _median(g["sold"])
        reorder_max = max(g["reorder"]) if g["reorder"] else None
        score = _demand(sold_med, reorder_max, g["n"])
        # data confidence: how many independent signals backed the score
        signals = sum(x is not None for x in (sold_med, reorder_max)) + (1 if g["n"] >= 3 else 0)
        data_conf = "high" if signals >= 2 else "med" if signals == 1 else "low"
        conf = min(g["conf"], data_conf, key=_CONF_RANK.get)
        leads.append({
            "keyword": kw, "supplier_demand": score, "supplier_count": g["n"],
            "sold_median": sold_med, "reorder_pct": reorder_max,
            "confidence": conf, "product_type": g["pt"], "example_title": g["example"],
        })
    leads.sort(key=lambda l: (-(l["supplier_demand"] or 0), -l["supplier_count"]))
    return leads[:limit]


_CONF_RANK = {"low": 0, "med": 1, "high": 2}


# --------------------------- store + detect --------------------------------
def looks_like_supplier(headers):
    """True if the columns look like a supplier/wholesale export (Alibaba /
    AliExpress / 1688) rather than an Etsy/YTrends keyword table."""
    blob = " ".join(str(h).lower() for h in (headers or []))
    hits = ("reorder", "min order", "min. order", "moq", "supplier", "factory",
            "1688", "alibaba", "aliexpress", "wholesale", "verified", "pieces")
    return sum(1 for h in hits if h in blob) >= 1


def _hdr_blob(headers):
    return " ".join(str(h).lower() for h in (headers or []))


def looks_like_pinterest(headers):
    """True if the columns look like a Pinterest pin export — saves/board/pinner,
    OR the minimal spy shape (pin_id + title_or_desc)."""
    blob = _hdr_blob(headers)
    hits = ("save", "repin", "board", "pinner", "pin url", "pin_url", "pinterest",
            "pin_id", "pin id", "title_or_desc")
    return sum(1 for h in hits if h in blob) >= 1


def has_keyword_col(headers):
    """True ONLY for a real KEYWORD TABLE (YTrends/Amazon), where a whole column
    IS the keyword/phrase.

    Critical fix: an Etsy SERP listing export carries per-listing metadata columns
    named 'keyword_context' / 'keyword_match_type' — those contain the substring
    'keyword' but are NOT a keyword table. Counting them here made the router dump
    ~72 ranking LISTINGS into the keyword base instead of the Pattern Miner pool
    (the "my search never shows up" bug). Match the column NAME exactly, so
    metadata tags no longer masquerade as a keyword table."""
    for h in (headers or []):
        hl = str(h).lower().strip()
        if hl in ("keyword", "keywords", "phrase", "phrases", "query",
                  "search term", "search_term", "search phrase", "search_phrase"):
            return True
    return False


def looks_like_etsy_listings(headers):
    """True for an Etsy LISTINGS / spy export (title-based, no keyword column) —
    it carries a title plus listing-level signals (sold / views / tags / shop /
    listing id), so it becomes keyword LEADS rather than a keyword table."""
    blob = _hdr_blob(headers)
    if has_keyword_col(headers):
        return False
    # title-ish: "title", or a bare "listing" TEXT column (YTrends Spy calls its
    # title column LISTING) - a listing_id column alone doesn't count
    _noid = blob.replace("listing_id", "").replace("listing id", "")
    has_title = "title" in blob or "listing" in _noid
    signals = ("he_sold", "he_views", "he_tags", "sold", "listing_id", "listing id",
               "shop", "favorite", "revenue", "conversion")
    return has_title and any(s in blob for s in signals)


def looks_like_etsy_search_results(headers):
    """Etsy SEARCH-RESULTS export from the extension (v3.6.x): the listings
    currently ranking for a keyword — title + listing signals + rank_position +
    the keyword_context/match columns.

    These are pure GOLD for the Pattern Miner ('how the winners win'), but the
    'keyword_context' column makes has_keyword_col() true, which otherwise sends
    the whole batch to the keyword ingester instead of the listings pool. Detect
    it explicitly so it lands in its own etsy_search lane (Pattern Miner only —
    never the frozen proof/ranking pool)."""
    blob = _hdr_blob(headers)
    has_title = "title" in blob
    has_rank = "rank_position" in blob or "keyword_match_type" in blob
    listingish = "listing_id" in blob or "he_sold" in blob or "he_tags" in blob
    return has_title and has_rank and listingish


def _dir(source):
    return DIRS.get(source, SUPPLIER_DIR)


def save_payload(payload, source="supplier"):
    """Persist a lead import under its OWN dir (supplier / pinterest) so the Etsy
    Winner Finder never mistakes these rows for Etsy keywords. Returns the path."""
    d = _dir(source)
    d.mkdir(parents=True, exist_ok=True)
    view = re.sub(r"[^a-z0-9]+", "-", str(payload.get("view") or source).lower()).strip("-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    p = d / f"{view or source}_{stamp}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def load_latest(source="supplier"):
    d = _dir(source)
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
    return None


def latest_info(source="supplier"):
    """{rows, view, age_seconds} for the newest import of `source`, or None."""
    import time
    d = _dir(source)
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    f = files[0]
    try:
        payload = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    try:
        age = max(0, int(time.time() - f.stat().st_mtime))
    except Exception:  # noqa: BLE001
        age = None
    return {"rows": len(payload.get("rows") or []),
            "view": str(payload.get("view") or ""), "age_seconds": age}


def analyze_latest(mode=None, limit=40, source="supplier"):
    payload = load_latest(source)
    if not payload:
        return {"ok": False, "leads": [], "error": f"no {source} import yet"}
    return {"ok": True, "view": payload.get("view"),
            "rows_in_import": len(payload.get("rows") or []),
            "leads": analyze(payload, mode=mode, limit=limit)}
