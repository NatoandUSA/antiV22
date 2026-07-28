"""Feed Center Evidence Router (V37.4).

Normalizes and validates the two NEW granular exports from the 22Etsy Evidence
Exporter v3.4.0 BEFORE they are allowed to touch Rank / Pattern / Re-rank:

  - HeyEtsy_*_Detail.csv  -> per-listing third-party estimate evidence
  - Etsy_*_Reviews.csv    -> buyer voice-of-customer (per-review rows + one summary)

Why a router (CEO review, v37.3 -> v37.4): the earlier plan routed raw Detail CSVs
straight into the L1 proof lane and Review CSVs into the competitor-spy lane. That is
unsafe. Raw detail rows are not proof-ready, reviews are not competitor listings, and a
single winning listing is NOT a winnable keyword market. This module instead lands the
data in four clean, validated lanes and hands the Rank layer only *capped* evidence:

    data/imports/etsy_listing_detail/{listing_id}.json    (normalized listing evidence)
    data/imports/etsy_listing_reviews/{listing_id}.json   (one review per row)
    data/imports/etsy_review_summary/{listing_id}.json    (ONE summary per listing)
    data/imports/listing_keyword_map/{listing_id}.json    (keyword candidates + confidence)

Hard rules baked in (do not weaken without an owner decision):
  * HeyEtsy estimated sold/revenue is THIRD-PARTY listing evidence, never "real proof".
  * Single-listing evidence caps at CONFIRM_FIRST; PROVEN needs shop_spread >= 2.
  * Reviews feed Pattern Miner / Keyword Lab / Photo Studio only -- NEVER L2 market math.
    (This module never writes to keyword_data.csv.)
  * variation_json yields "top mentioned/reviewed variants", never "highest-converting"
    unless true variant-level conversion data exists.
  * Honest nulls: a missing field stays None; a missing variation_json skips extraction.
  * conversion_pct=4 is normalized to conversion_rate=0.04 (never read as 400%).
  * Listing-level review summaries are stored ONCE per listing, never summed per row.

Pure stdlib (csv/json/re/html/hashlib/pathlib). No network. No publish. No marketplace
automation. It does not import or alter the frozen L0-L4 ranking math.
"""
import csv
import hashlib
import html
import json
import re
from datetime import date
from pathlib import Path

IMPORTS = Path("data/imports")
DETAIL_DIR = IMPORTS / "etsy_listing_detail"
REVIEWS_DIR = IMPORTS / "etsy_listing_reviews"
SUMMARY_DIR = IMPORTS / "etsy_review_summary"
MAP_DIR = IMPORTS / "listing_keyword_map"

# Evidence provenance label -- deliberately NOT "real Etsy sales".
DETAIL_EVIDENCE_TYPE = "heyetsy_estimated_listing_evidence"

# ----------------------------------------------------------------------------
# Small vocab (kept local so this module stays stdlib-only + independently
# testable). Mirrors product_fit / pattern_miner intent without importing them.
# ----------------------------------------------------------------------------
PRODUCT_NOUNS = {
    "sweatshirt", "crewneck", "hoodie", "tshirt", "tee", "shirt", "necklace",
    "bracelet", "ring", "earring", "earrings", "mug", "tumbler", "tote", "bag",
    "handbag", "backpack", "hat", "cap", "blanket", "pillow", "sign", "decal",
    "sticker", "towel", "apron", "keychain", "ornament", "shirt", "sweater",
}
GENERIC_MODIFIERS = {
    "personalized", "personalised", "custom", "customized", "customised",
    "customize", "embroidered", "embroidery", "monogram", "monogrammed",
    "name", "cute", "cozy", "matching", "set", "gift", "gifts", "present",
}
# Broad umbrella tags that must be MODIFIERS ONLY, never standalone Build keywords.
BROAD_TAGS = {
    "baby gifts", "baby gift", "nursery gifts", "gift for kids", "gifts for kids",
    "christmas gifts", "christmas gift", "customize gift", "custom gift",
    "customized gift", "mothers day gift", "mother's day gift", "fathers day gift",
    "school gifts", "school gift", "birthday gift", "birthday gifts", "gift",
    "gifts", "gift ideas", "holiday gifts", "unique gifts", "personalized gifts",
}
# Buyer / recipient nouns mined from review text -> long-tail buyer language.
RECIPIENT_NOUNS = {
    "granddaughter", "grandson", "grandkid", "grandkids", "grandchild",
    "daughter", "son", "niece", "nephew", "toddler", "kid", "kids", "child",
    "children", "baby", "boy", "girl", "mom", "mum", "mother", "dad", "father",
    "grandma", "grandmother", "grandpa", "grandfather", "wife", "husband",
    "sister", "brother", "friend", "teacher", "nurse", "coworker", "bride",
    "flower", "graduate",
}
OCCASION_NOUNS = {
    "birthday", "christmas", "graduation", "wedding", "anniversary", "baptism",
    "communion", "shower", "retirement", "valentine", "easter", "halloween",
    "thanksgiving", "back-to-school", "backtoschool", "holiday",
}
_STOP = {"the", "a", "an", "for", "with", "of", "and", "to", "your", "you", "in",
         "on", "or", "by", "from", "s", "is", "it", "this", "that", "her", "him",
         "his", "my", "our", "are", "be", "so", "as", "at", "we", "i", "was",
         "they", "them", "she", "he"}


# ----------------------------------------------------------------------------
# Number / unit helpers (BUG-002 conversion, BUG-005 K/M, BUG-006 html entities)
# ----------------------------------------------------------------------------
def parse_market_number(s):
    """Robust numeric parse for HeyEtsy/Etsy cells.

    Handles '52.6K', '2.5K', '$35,236.00', '15.36 USD', '4%', '(1,200)', blanks,
    '-', 'n/a', and stray html entities. Returns float or None. Never raises.
    """
    if s is None:
        return None
    t = html.unescape(str(s)).strip()
    if not t or t.lower() in ("-", "—", "n/a", "na", "none", "null", "lock",
                              "locked"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    mult = 1.0
    m = re.search(r"([kmb])\b", t, re.I)
    if m and re.search(r"\d", t):
        mult = {"k": 1e3, "m": 1e6, "b": 1e9}[m.group(1).lower()]
    t = re.sub(r"[^0-9.\-]", "", t.replace(",", ""))
    if t in ("", "-", ".", "--", "-."):
        return None
    try:
        v = float(t) * mult
    except ValueError:
        return None
    return -v if neg else v


def normalize_conversion(v):
    """(raw_pct, rate) for a conversion cell (BUG-002 / CF010 / CF009).

    HeyEtsy gives conversion_pct=4 meaning 4% -> rate 0.04. Rule:
      * value is None            -> (None, None)   (honest null)
      * 0 < value <= 1           -> already a fraction: raw = value*100, rate = value
      * 1 < value <= 100         -> a percent: raw = value, rate = value/100
      * value > 100              -> implausible: keep raw, rate = None (flag upstream)
    """
    n = parse_market_number(v)
    if n is None:
        return None, None
    if 0 < n <= 1:
        return round(n * 100.0, 4), round(n, 6)
    if 1 < n <= 100:
        return round(n, 4), round(n / 100.0, 6)
    if n == 0:
        return 0.0, 0.0
    return round(n, 4), None  # >100 -> implausible, do not invent a rate


def clean_text(s):
    """html.unescape + whitespace-collapse (BUG-006). '' -> None."""
    if s is None:
        return None
    t = re.sub(r"\s+", " ", html.unescape(str(s))).strip()
    return t or None


def _months_from_days(days):
    return round(days / 30.0, 1) if isinstance(days, (int, float)) else None


def _ci(headers, *needles, exclude=()):
    """First header index whose lowercased name contains any needle (and no
    excluded token). Underscores and spaces both match."""
    for i, h in enumerate(headers):
        hl = re.sub(r"[\s_]+", " ", str(h).lower())
        hlj = str(h).lower()
        if any(n in hl or n in hlj for n in needles) \
                and not any(x in hl or x in hlj for x in exclude):
            return i
    return None


def _row_get(row, idx):
    return row[idx] if (idx is not None and idx < len(row)) else None


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 1 and w not in _STOP]


def _singular(w):
    """Cheap singularizer so 'bags'/'handbags' match the singular product set."""
    if len(w) > 3 and w.endswith("es") and w[:-2] in PRODUCT_NOUNS:
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


# ----------------------------------------------------------------------------
# Detection -- run these BEFORE the generic etsy-listings/keyword detectors.
# ----------------------------------------------------------------------------
def looks_like_heyetsy_detail(headers):
    """HeyEtsy Detail export: per-listing estimates. Signature = an estimated
    sold/revenue column + a listing id, and NO per-review text column."""
    if not headers:
        return False
    has_estimate = (_ci(headers, "estimated_sold", "estimated sold",
                        "estimated_revenue", "estimated revenue", "he_sold") is not None)
    has_listing = (_ci(headers, "listing_id", "listing id", "heyetsy") is not None)
    has_reviews = (_ci(headers, "review_text", "review text", "review_id",
                       "review id") is not None)
    return has_estimate and has_listing and not has_reviews


def looks_like_etsy_reviews(headers):
    """Etsy Reviews export: one row per review. Signature = a review text/id
    column tied to a listing id (or a variation_json review column)."""
    if not headers:
        return False
    has_review = (_ci(headers, "review_text", "review text", "review_id",
                      "review id") is not None)
    has_listing = (_ci(headers, "listing_id", "listing id") is not None)
    has_variation = (_ci(headers, "variation_json", "variation") is not None)
    return has_review and (has_listing or has_variation)


# ----------------------------------------------------------------------------
# Detail lane
# ----------------------------------------------------------------------------
def normalize_detail(headers, rows, source_hint=None):
    """Map a HeyEtsy Detail table to a normalized listing-evidence dict.

    Returns a dict (or None if no listing_id/title can be found). Honest nulls
    throughout; conversion normalized; K/M parsed; title html-unescaped.
    """
    if not rows:
        return None
    idx = {
        "listing_id": _ci(headers, "listing_id", "listing id"),
        "title": _ci(headers, "title", "product title", "name",
                     exclude=("shop", "seller")),
        "shop": _ci(headers, "shop", "seller", exclude=("id", "sales", "review")),
        "price": _ci(headers, "price", exclude=("was", "compare")),
        "sold": _ci(headers, "estimated_sold", "estimated sold", "he_sold",
                    exclude=("revenue", "24")),
        "revenue": _ci(headers, "estimated_revenue", "estimated revenue",
                       "he_revenue"),
        "views": _ci(headers, "views", exclude=("average", "avg", "rate", "vel")),
        "views_avg": _ci(headers, "views_average", "views average", "avg views"),
        "favorites": _ci(headers, "favorite", "favourites", exclude=("rate",)),
        "fav_rate": _ci(headers, "favorite_rate", "favourite rate", "favorite rate"),
        "conv": _ci(headers, "conversion"),
        "age_days": _ci(headers, "listing_age_days", "age_days", "age (days)",
                        "listing age"),
        "shop_sales": _ci(headers, "shop_sales", "shop sales"),
        "shop_reviews": _ci(headers, "shop_reviews", "shop review", "shop_review_count"),
        "listing_reviews": _ci(headers, "listing_review_count", "listing reviews",
                               "review_count", exclude=("shop",)),
        "tags": _ci(headers, "tags", exclude=("count", "categor")),
        "tags_count": _ci(headers, "tags_count", "tag count"),
        "image_count": _ci(headers, "image_count", "images", "image count"),
        "url": _ci(headers, "url", "link", "heyetsy"),
    }
    row = rows[0]  # a Detail export is one listing per file
    listing_id = clean_text(_row_get(row, idx["listing_id"]))
    title = clean_text(_row_get(row, idx["title"]))
    if not listing_id:
        # fall back to a stem from the filename (HeyEtsy_4412078408_Detail.csv)
        m = re.search(r"(\d{6,})", str(source_hint or ""))
        listing_id = m.group(1) if m else None
    if not listing_id or not title:
        return None

    conv_raw, conv_rate = normalize_conversion(_row_get(row, idx["conv"]))
    age_days = parse_market_number(_row_get(row, idx["age_days"]))
    raw_tags = clean_text(_row_get(row, idx["tags"])) or ""
    tags = [t.strip() for t in re.split(r"[;|,]", raw_tags) if t.strip()]
    shop_reviews = parse_market_number(_row_get(row, idx["shop_reviews"]))
    # BUG-004: a 0 from the detail export is UNKNOWN, not authoritative -- a
    # reviews file may carry the real positive count. Store 0 as None here.
    if shop_reviews == 0:
        shop_reviews = None

    return {
        "listing_id": listing_id,
        "title": title,
        "shop": clean_text(_row_get(row, idx["shop"])),
        "price_usd": parse_market_number(_row_get(row, idx["price"])),
        "estimated_sold": parse_market_number(_row_get(row, idx["sold"])),
        "estimated_revenue_usd": parse_market_number(_row_get(row, idx["revenue"])),
        "views": parse_market_number(_row_get(row, idx["views"])),
        "views_average": parse_market_number(_row_get(row, idx["views_avg"])),
        "favorites": parse_market_number(_row_get(row, idx["favorites"])),
        "favorite_rate_pct": parse_market_number(_row_get(row, idx["fav_rate"])),
        "conversion_pct_raw": conv_raw,
        "conversion_rate": conv_rate,
        "listing_age_days": age_days,
        "listing_age_months": _months_from_days(age_days),
        "shop_sales": parse_market_number(_row_get(row, idx["shop_sales"])),
        "shop_reviews": shop_reviews,
        "listing_review_count": parse_market_number(_row_get(row, idx["listing_reviews"])),
        "tags": tags,
        "tags_count": int(parse_market_number(_row_get(row, idx["tags_count"])) or len(tags)),
        "image_count": parse_market_number(_row_get(row, idx["image_count"])),
        "heyetsy_url": clean_text(_row_get(row, idx["url"])),
        "evidence_type": DETAIL_EVIDENCE_TYPE,
        "shop_spread": 1,   # a single detail file = one shop/listing. Never proof.
        "collected_at": date.today().isoformat(),
        "source": source_hint or "heyetsy-detail",
    }


def save_detail(headers, rows, source_hint=None):
    """Normalize + persist one HeyEtsy Detail file. Also (re)builds the keyword
    map for the listing. Returns the detail dict, or None if unusable."""
    detail = normalize_detail(headers, rows, source_hint)
    if not detail:
        return None
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    (DETAIL_DIR / f"{detail['listing_id']}.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        build_keyword_map(detail["listing_id"])
    except Exception:  # noqa: BLE001 -- map is best-effort, never blocks ingest
        pass
    return detail


def load_detail(listing_id):
    p = DETAIL_DIR / f"{listing_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------
# Review lanes (rows lane + ONE summary lane, deduped)  BUG-001 / CF008 / CF009
# ----------------------------------------------------------------------------
# Listing-level columns that repeat identically on every review row. These are
# stored ONCE per listing (summary lane) and must never be summed per row.
_SUMMARY_NEEDLES = (
    "feature_tags", "categorical_tags", "buyers_recommend", "buyer_recommend",
    "item_quality_rating", "shipping_rating", "customer_service_rating",
    "listing_review_count", "shop_review_count", "rating_distribution",
    "rating_breakdown",
)


def _has_review_photo(image_id, photo_url):
    """BUG-010: an image_id is NOT a usable URL. has_review_photo is a boolean
    derived from either signal; the raw url is kept separately."""
    if clean_text(photo_url):
        return True
    return bool(clean_text(image_id))


def _parse_variation(v):
    """variation_json -> list of {label,value} mentions. Honest null on missing
    (CF-missing_variation): returns [] and the caller records nothing invented."""
    t = clean_text(v)
    if not t:
        return []
    out = []
    try:
        data = json.loads(t)
        if isinstance(data, dict):
            for k, val in data.items():
                out.append({"label": str(k), "value": clean_text(val) or str(val)})
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    for k, val in item.items():
                        out.append({"label": str(k), "value": clean_text(val) or str(val)})
                else:
                    out.append({"label": "variation", "value": clean_text(item)})
        return out
    except (ValueError, TypeError):
        # not JSON -> treat as a plain "Color: Pink" style string
        for part in re.split(r"[;|]", t):
            if ":" in part:
                k, val = part.split(":", 1)
                out.append({"label": k.strip(), "value": val.strip()})
            elif part.strip():
                out.append({"label": "variation", "value": part.strip()})
        return out


def normalize_reviews(headers, rows, source_hint=None):
    """Return (listing_id, review_rows, summary). review_rows = one dict per
    review; summary = the listing-level block captured ONCE (deduped)."""
    if not rows:
        return None, [], None
    idx = {
        "listing_id": _ci(headers, "listing_id", "listing id"),
        "review_id": _ci(headers, "review_id", "review id"),
        "text": _ci(headers, "review_text", "review text", "comment", "message"),
        "rating": _ci(headers, "rating", "stars", exclude=("item", "shipping",
                      "service", "distribution", "breakdown", "average", "avg")),
        "variation": _ci(headers, "variation_json", "variation"),
        "date": _ci(headers, "review_date", "date", "created"),
        "buyer": _ci(headers, "buyer", "reviewer", "author"),
        "image_id": _ci(headers, "review_image_id", "image_id", "image id"),
        "photo_url": _ci(headers, "review_photo_url", "photo_url", "photo url"),
    }
    summary_cols = {}
    for need in _SUMMARY_NEEDLES:
        j = _ci(headers, need)
        if j is not None:
            summary_cols[str(headers[j])] = j   # key by REAL header, not the needle

    listing_id = None
    review_rows = []
    for row in rows:
        lid = clean_text(_row_get(row, idx["listing_id"]))
        if lid and not listing_id:
            listing_id = lid
        variants = _parse_variation(_row_get(row, idx["variation"]))
        review_rows.append({
            "review_id": clean_text(_row_get(row, idx["review_id"])),
            "listing_id": lid,
            "rating": parse_market_number(_row_get(row, idx["rating"])),
            "text": clean_text(_row_get(row, idx["text"])),
            "review_date": clean_text(_row_get(row, idx["date"])),
            "buyer": clean_text(_row_get(row, idx["buyer"])),
            "variation_mentions": variants,       # honest null -> [] (nothing invented)
            "variation_evidence_type": "mentioned" if variants else None,
            "has_review_photo": _has_review_photo(
                _row_get(row, idx["image_id"]), _row_get(row, idx["photo_url"])),
            "review_photo_url": clean_text(_row_get(row, idx["photo_url"])),
        })
    if not listing_id:
        m = re.search(r"(\d{6,})", str(source_hint or ""))
        listing_id = m.group(1) if m else None
    if not listing_id:
        return None, [], None

    # Build the ONE-per-listing summary from the FIRST row only (BUG-001: these
    # columns repeat identically on every row -- never sum them).
    summary = None
    if summary_cols:
        first = rows[0]
        blob = {}
        for name, j in summary_cols.items():
            blob[name] = clean_text(_row_get(first, j))
        checksum = hashlib.sha1(
            json.dumps(blob, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:12]
        summary = {
            "listing_id": listing_id,
            "fields": blob,
            "review_rows_in_file": len(review_rows),
            "summary_checksum": checksum,
            "collected_at": date.today().isoformat(),
            "note": "listing-level summary; stored once per listing, not per review row.",
        }
    return listing_id, review_rows, summary


def save_reviews(headers, rows, source_hint=None):
    """Normalize + persist an Etsy Reviews file into the review-rows lane and the
    dedup'd summary lane. Returns a small dict of counts, or None if unusable."""
    listing_id, review_rows, summary = normalize_reviews(headers, rows, source_hint)
    if not listing_id:
        return None
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / f"{listing_id}.json").write_text(
        json.dumps({"listing_id": listing_id, "reviews": review_rows,
                    "collected_at": date.today().isoformat()},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    wrote_summary = False
    if summary:
        SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
        sp = SUMMARY_DIR / f"{listing_id}.json"
        # Dedup: identical summary (same checksum) is written once, not re-counted.
        if sp.is_file():
            try:
                prev = json.loads(sp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                prev = {}
            if prev.get("summary_checksum") != summary["summary_checksum"]:
                sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                              encoding="utf-8")
                wrote_summary = True
        else:
            sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                          encoding="utf-8")
            wrote_summary = True
    try:
        build_keyword_map(listing_id)
    except Exception:  # noqa: BLE001
        pass
    return {"listing_id": listing_id, "reviews": len(review_rows),
            "summary_written": wrote_summary}


def load_reviews(listing_id):
    p = REVIEWS_DIR / f"{listing_id}.json"
    if not p.is_file():
        return []
    try:
        return (json.loads(p.read_text(encoding="utf-8")) or {}).get("reviews") or []
    except Exception:  # noqa: BLE001
        return []


# ----------------------------------------------------------------------------
# Review intelligence -> feeds Pattern Miner / Keyword Lab (NOT L2 market math)
# ----------------------------------------------------------------------------
_COMPLAINT_SIGNS = {
    "thin": "material", "thinner": "material", "flimsy": "material",
    "cheap": "material", "quality": "material", "small": "size",
    "smaller": "size", "tiny": "size", "large": "size", "big": "size",
    "late": "shipping", "slow": "shipping", "delay": "shipping",
    "delayed": "shipping", "damaged": "shipping", "wrong": "accuracy",
    "misspelled": "personalization", "spelling": "personalization",
}


def review_intel(listing_id=None, reviews=None):
    """Extract buyer-intent signals from review rows. Pure qualitative output for
    Pattern Miner / Keyword Lab / Photo Studio -- it NEVER returns a demand score
    and callers must not route it into L2. Honest: only reflects text present.
    """
    if reviews is None:
        reviews = load_reviews(listing_id) if listing_id else []
    recip, occ, variants = {}, {}, {}
    complaints = {"material": 0, "size": 0, "shipping": 0, "accuracy": 0,
                  "personalization": 0}
    personalization_mentions = 0
    photo_expectation = 0
    n_text = 0
    for r in reviews:
        for m in r.get("variation_mentions") or []:
            val = (m.get("value") or "").strip().lower()
            if val:
                variants[val] = variants.get(val, 0) + 1
        if r.get("has_review_photo"):
            photo_expectation += 1
        text = (r.get("text") or "")
        if not text:
            continue
        n_text += 1
        toks = set(_tokens(text))
        for t in toks:
            if t in RECIPIENT_NOUNS:
                recip[t] = recip.get(t, 0) + 1
            if t in OCCASION_NOUNS:
                occ[t] = occ.get(t, 0) + 1
            if t in ("personalized", "personalised", "custom", "name", "monogram"):
                personalization_mentions += 1
        for w, cat in _COMPLAINT_SIGNS.items():
            if re.search(r"\b" + re.escape(w) + r"\b", text.lower()):
                complaints[cat] = complaints.get(cat, 0) + 1

    def _rank(d):
        return sorted(({"value": k, "count": v} for k, v in d.items()),
                      key=lambda x: -x["count"])

    return {
        "listing_id": listing_id,
        "reviews_scanned": len(reviews),
        "reviews_with_text": n_text,
        "recipient_nouns": _rank(recip),
        "occasion_nouns": _rank(occ),
        # labelled MENTIONED/REVIEWED -- never "highest-converting" (CF005)
        "top_mentioned_variants": _rank(variants),
        "variant_evidence_type": "mentioned_or_reviewed",
        "personalization_mentions": personalization_mentions,
        "complaints": {k: v for k, v in complaints.items() if v},
        "photo_expectation_signals": photo_expectation,
        "feeds": ["pattern_miner", "keyword_lab", "photo_studio", "offer_gap",
                  "can_we_win"],
        "affects_l2_market_signal": False,
    }


# ----------------------------------------------------------------------------
# Listing -> keyword match map (CF004 / CF007)  + broad-tag classification (CF011)
# ----------------------------------------------------------------------------
def classify_keyword_role(phrase):
    """primary_candidate | modifier | weak_broad for a tag/phrase (CF011).

    A phrase is a real candidate only if it names a product noun AND has >= 3
    words (or carries a clear subject). Broad umbrella gift tags are modifiers.
    """
    p = re.sub(r"\s+", " ", (phrase or "").strip().lower())
    if not p:
        return "weak_broad"
    if p in BROAD_TAGS:
        return "modifier"
    toks = _tokens(p)
    sing = [_singular(t) for t in toks]
    has_product = any(t in PRODUCT_NOUNS for t in sing)
    subject = [t for t, s in zip(toks, sing)
               if s not in PRODUCT_NOUNS and t not in GENERIC_MODIFIERS]
    # A product-bearing phrase that is specific enough (>= 3 words, e.g.
    # "personalized name tote bag") OR that carries a real subject word
    # ("toddler tote bag") is a real launch candidate. Everything else -- bare
    # umbrella gift tags, 2-word generics -- is a modifier, never a standalone.
    if has_product and (len(toks) >= 3 or subject):
        return "primary_candidate"
    return "modifier" if (len(toks) <= 2 or not subject) else "weak_broad"


def _title_head_keyword(title):
    """The first clause of an Etsy title = its strongest phrase."""
    if not title:
        return None
    head = re.split(r"[:,\-|]", title, maxsplit=1)[0].strip().lower()
    head = re.sub(r"\s+", " ", head)
    return head or None


def build_keyword_map(listing_id, detail=None, intel=None):
    """Build listing_keyword_map/{listing_id}.json: candidate keywords with
    match_type, match_confidence, keyword_role, and an action_cap.

    action_cap enforces the safety rails:
      * single-listing evidence never exceeds CONFIRM_FIRST (CF001/CF007)
      * broad modifiers are 'modifier_only' (cannot be a standalone Build)
      * review-derived long-tails are CONFIRM_FIRST candidates for Re-rank (CF006)
    Nothing here is auto-built; Re-rank + gates decide the final action.
    """
    detail = detail or load_detail(listing_id)
    if not detail:
        return None
    intel = intel or review_intel(listing_id)
    title = detail.get("title") or ""
    shop_spread = detail.get("shop_spread", 1)
    single = shop_spread < 2
    base_cap = "CONFIRM_FIRST" if single else "PROVEN_CANDIDATE"

    candidates = []
    seen = set()

    def add(kw, match_type, confidence, role, cap):
        kw = re.sub(r"\s+", " ", (kw or "").strip().lower())
        if not kw or kw in seen:
            return
        seen.add(kw)
        candidates.append({
            "keyword": kw, "match_type": match_type,
            "match_confidence": round(float(confidence), 2),
            "keyword_role": role, "action_cap": cap,
            "words": len(kw.split()),
        })

    # 1. title head phrase -> strongest, product-specific
    head = _title_head_keyword(title)
    if head:
        add(head, "title_exact_phrase", 0.95, classify_keyword_role(head), base_cap)

    # 2. tags -> primary candidates or modifiers only (broad tags never standalone)
    for tag in detail.get("tags") or []:
        role = classify_keyword_role(tag)
        if role == "primary_candidate":
            add(tag.lower(), "tag_exact", 0.8, role, base_cap)
        else:
            add(tag.lower(), "tag_modifier_only", 0.4, role, "modifier_only")

    # 3. review-derived long-tails: buyer noun + product (CF006 -> Re-rank, not build)
    product = None
    for t in _tokens(title):
        if t in PRODUCT_NOUNS:
            product = t
            break
    if product:
        for rec in (intel.get("recipient_nouns") or [])[:4]:
            noun = rec["value"]
            kw = f"personalized {product} for {noun}"
            # confidence scales a little with how often buyers said it, capped mid
            conf = min(0.6, 0.35 + 0.05 * rec["count"])
            add(kw, "review_derived", conf, "primary_candidate", "CONFIRM_FIRST")

    MAP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "listing_id": listing_id,
        "shop_spread": shop_spread,
        "single_listing_evidence": single,
        "evidence_type": detail.get("evidence_type"),
        "max_action_without_multishop": "CONFIRM_FIRST" if single else "REVIEW",
        "candidates": candidates,
        "note": ("HeyEtsy estimate is third-party listing evidence. Single-listing "
                 "evidence caps at CONFIRM_FIRST; BUILD_NOW/PROVEN needs shop_spread "
                 ">= 2 or manager override. Review-derived keywords must pass "
                 "Re-rank (L0/L1/L2/L3) and all gates -- never auto-build."),
        "collected_at": date.today().isoformat(),
    }
    (MAP_DIR / f"{listing_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_keyword_map(listing_id):
    p = MAP_DIR / f"{listing_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def candidates_for_rerank(listing_id):
    """Plain candidate keywords to push back through the Inbox/Re-rank. Every one
    carries an action_cap; NONE are BUILD_NOW. Keyword Lab / Re-rank decide."""
    m = load_keyword_map(listing_id)
    if not m:
        return []
    return [c for c in m.get("candidates", [])
            if c.get("keyword_role") == "primary_candidate"]


# ----------------------------------------------------------------------------
# Recent evidence (read-only card for the Feed / Import Center)
# ----------------------------------------------------------------------------
def recent_evidence(limit=12):
    """Newest-first list of per-listing evidence cards for the /imports page.

    Read-only join of the detail + reviews + summary lanes. Each row is capped
    (single-listing = CONFIRM_FIRST) and carries a buyer snippet. Never raises;
    returns [] when no detail lane exists.
    """
    if not DETAIL_DIR.is_dir():
        return []
    files = sorted(DETAIL_DIR.glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:max(0, limit)]
    out = []
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        lid = d.get("listing_id") or p.stem
        reviews = load_reviews(lid)
        intel = review_intel(lid, reviews)
        act = listing_evidence_action(d)
        recip = intel.get("recipient_nouns") or []
        variants = intel.get("top_mentioned_variants") or []
        out.append({
            "listing_id": lid,
            "title": d.get("title"),
            "shop": d.get("shop"),
            "price_usd": d.get("price_usd"),
            "estimated_sold": d.get("estimated_sold"),
            "estimated_revenue_usd": d.get("estimated_revenue_usd"),
            "conversion_rate": d.get("conversion_rate"),
            "evidence_type": d.get("evidence_type"),
            "review_count": len(reviews),
            "has_summary": (SUMMARY_DIR / f"{lid}.json").is_file(),
            "top_recipient": recip[0]["value"] if recip else None,
            "top_variant": variants[0]["value"] if variants else None,
            "complaints": intel.get("complaints") or {},
            "photo_expectation_signals": intel.get("photo_expectation_signals", 0),
            "max_action": act["max_action"],
            "collected_at": d.get("collected_at"),
        })
    return out


# ----------------------------------------------------------------------------
# keyword -> listing-evidence JOIN (feeds Pattern Miner + Keyword Lab)
# ----------------------------------------------------------------------------
def _product_from(text):
    for t in (_singular(w) for w in _tokens(text)):
        if t in PRODUCT_NOUNS:
            return t
    return None


def _all_map_listing_ids():
    if not MAP_DIR.is_dir():
        return []
    ids = []
    for p in sorted(MAP_DIR.glob("*.json")):
        ids.append(p.stem)
    return ids


def evidence_for_keyword(keyword, max_listings=6):
    """Join a mined keyword to the listing evidence that belongs to it.

    Scans listing_keyword_map + detail titles; a listing is attached only when it
    shares >= 2 subject-bearing tokens with the keyword (or an explicit map
    candidate overlaps) -- this is the CF007 guard so evidence never attaches to
    the wrong keyword. Returns a compact, HONEST dict (empty when no lanes):

        {keyword, has_evidence, listings[], recipient_nouns[], occasion_nouns[],
         top_mentioned_variants[], complaints{}, photo_expectation_signals,
         review_derived_keywords[], note}

    Purely qualitative + capped-action. It NEVER returns a market/demand score and
    must not be routed into L2. Reviews here inform Pattern/Keyword Lab only.
    """
    empty = {"keyword": keyword, "has_evidence": False, "listings": [],
             "recipient_nouns": [], "occasion_nouns": [],
             "top_mentioned_variants": [], "complaints": {},
             "photo_expectation_signals": 0, "review_derived_keywords": [],
             "affects_l2_market_signal": False,
             "note": "listing evidence is capped; single-listing = CONFIRM_FIRST max."}
    kw_toks = set(_singular(t) for t in _tokens(keyword))
    if not kw_toks:
        return empty
    # Generic words carry NO niche identity: a bridge built only on "custom"/"name"
    # must never attach a listing to an unrelated keyword (CF007). The discriminators
    # are SUBJECT tokens (niche words) and the PRODUCT noun.
    _mods = {_singular(m) for m in GENERIC_MODIFIERS}
    kw_products = kw_toks & PRODUCT_NOUNS

    def _valid_bridge(shared, other_toks):
        """A token overlap is a valid keyword<->evidence bridge only when it shares
        a SUBJECT word or the SAME PRODUCT noun — never generic modifiers alone
        ("custom"/"name"), and never across conflicting products (a necklace keyword
        must not borrow a tote handbag listing's evidence)."""
        if len(shared) < 2:
            return False
        beyond_generic = shared - _mods                 # a subject OR a product noun
        other_products = other_toks & PRODUCT_NOUNS
        conflict = bool(kw_products and other_products
                        and not (kw_products & other_products))
        return bool(beyond_generic) and not conflict

    matched = []
    for lid in _all_map_listing_ids():
        detail = load_detail(lid)
        if not detail:
            continue
        title_toks = set(_singular(t) for t in _tokens(detail.get("title")))
        overlap = kw_toks & title_toks
        title_ok = _valid_bridge(overlap, title_toks)
        conf = 0.0
        mp = load_keyword_map(lid) or {}
        for c in mp.get("candidates", []):
            ct = set(_singular(t) for t in _tokens(c.get("keyword")))
            if _valid_bridge(kw_toks & ct, ct):
                j = len(kw_toks & ct) / max(1, len(kw_toks | ct))
                conf = max(conf, round(j * float(c.get("match_confidence") or 0.5), 2))
        if title_ok or conf >= 0.4:
            score = conf if conf else round(len(overlap) / max(1, len(kw_toks | title_toks)), 2)
            matched.append((score, lid, detail))
    if not matched:
        return empty
    matched.sort(key=lambda x: -x[0])
    matched = matched[:max_listings]

    listings, recip, occ, variants = [], {}, {}, {}
    complaints, photo = {}, 0
    single_only = True
    for score, lid, detail in matched:
        intel = review_intel(lid)
        if detail.get("shop_spread", 1) >= 2:
            single_only = False
        act = listing_evidence_action(detail)
        listings.append({
            "listing_id": lid,
            "title": detail.get("title"),
            "shop": detail.get("shop"),
            "evidence_type": detail.get("evidence_type"),
            "estimated_sold": detail.get("estimated_sold"),
            "estimated_revenue_usd": detail.get("estimated_revenue_usd"),
            "conversion_rate": detail.get("conversion_rate"),
            "match_confidence": score,
            "max_action": act["max_action"],
        })
        for r in intel.get("recipient_nouns", []):
            recip[r["value"]] = recip.get(r["value"], 0) + r["count"]
        for o in intel.get("occasion_nouns", []):
            occ[o["value"]] = occ.get(o["value"], 0) + o["count"]
        for v in intel.get("top_mentioned_variants", []):
            variants[v["value"]] = variants.get(v["value"], 0) + v["count"]
        for k, n in (intel.get("complaints") or {}).items():
            complaints[k] = complaints.get(k, 0) + n
        photo += intel.get("photo_expectation_signals", 0)

    def _rank(d):
        return sorted(({"value": k, "count": v} for k, v in d.items()),
                      key=lambda x: -x["count"])

    # review-derived long-tails: buyer noun + product (CONFIRM_FIRST, re-rank only)
    product = _product_from(keyword) or _product_from(matched[0][2].get("title") or "")
    review_kws = []
    if product:
        for r in _rank(recip)[:5]:
            review_kws.append(f"personalized {product} for {r['value']}")

    return {
        "keyword": keyword,
        "has_evidence": True,
        "single_listing_only": single_only,
        "listings": listings,
        "recipient_nouns": _rank(recip),
        "occasion_nouns": _rank(occ),
        "top_mentioned_variants": _rank(variants),
        "variant_evidence_type": "mentioned_or_reviewed",
        "complaints": complaints,
        "photo_expectation_signals": photo,
        "review_derived_keywords": review_kws,
        "affects_l2_market_signal": False,
        "note": ("Third-party listing evidence. Single-listing evidence caps at "
                 "CONFIRM_FIRST; review-derived keywords must pass Re-rank + gates."),
    }


# ----------------------------------------------------------------------------
# Rank-facing safety helper (does NOT change L0-L4 math; advisory cap only)
# ----------------------------------------------------------------------------
def listing_evidence_action(detail, extra_shop_spread=0):
    """Max action a piece of listing evidence may justify on its own.

    single shop  -> CONFIRM_FIRST (route to Pattern Miner)
    >= 2 shops   -> REVIEW (may support PROVEN if keyword match confidence is high)
    Never returns BUILD_NOW: BUILD_NOW requires multi-shop proof + supplier/profit/
    trademark/photo gates + manager sign-off, decided elsewhere.
    """
    if not detail:
        return {"max_action": "WATCH", "reason": "no listing evidence"}
    spread = max(detail.get("shop_spread", 1), 1) + max(extra_shop_spread, 0)
    if spread >= 2:
        return {"max_action": "REVIEW", "shop_spread": spread,
                "reason": "multi-shop listing evidence; can support PROVEN only if "
                          "keyword match confidence is high and gates pass."}
    return {"max_action": "CONFIRM_FIRST", "shop_spread": spread,
            "reason": "single-listing third-party evidence; strong competitor proof, "
                      "not keyword-market proof. Route to Pattern Miner."}
