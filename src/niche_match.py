"""Does this listing belong to the queried NICHE? One rule, shared.

THE BUG THIS FIXES
Pattern Miner matched a listing when it shared >=2 query tokens
(`hits >= min(2, len(qtoks))` — a fixed floor of 2 whatever the query length).
For the real query "personalized embroidery halloween shirt" that let the two
GENERIC tokens carry the match:

    "Personalized Teacher Shirt, Comfort Colors Back to School Tee"
        shares {personalized, shirt} -> 2 -> MATCHED

so a Halloween query mined TEACHER back-to-school shirts. Measured on the
owner's own run: 385 "matching" listings whose winning words came back
teacher 52%, school 38%, back 33%, appreciation 24%.

FOUR BUCKETS
Every query token is classified, and the bucket decides what it can prove:

    modifier   personalized, custom, name, monogram, gift   says nothing
    style      crew, v-neck, oversized, unisex, comfort     says nothing
    technique  embroidery, embroidered, printed, engraved   HOW it is made
    product    shirt, hoodie, tote, cap, mug, blanket       WHAT it is
    theme      halloween, teacher, nurse, bride, graduation WHICH niche

`embroidery` is a TECHNIQUE, not a product — product_fit lumps it into its noun
set, which made "embroidered" look like the thing being sold. `crew` and
`handbag` are style and product respectively; classified as themes they would be
wrongly *required*, breaking "custom crew t-shirt" and "custom name tote
handbag".

THE RULE
    query has themes    -> at least one THEME token must match
    else has products   -> at least one PRODUCT token must match (family-aware,
                           so tee/t-shirt/shirt count as one another)
    else                -> overall overlap only

Either way the historical overall-overlap floor still applies, so the new rule
is strictly NARROWER than the old one and can only ever remove matches.

HONEST-NULL
An empty query matches everything (the miner's overview mode); it does not
silently match nothing.
"""
import re

# Bump when the matching RULE changes. Anything that cached or indexed rows under
# an older version is stale and must be rebuilt before its counts can be trusted.
#   1  the original shared-token rule: hits >= min(2, len(qtoks))
#   2  four buckets; a theme (or product, when no theme) must match
MATCHER_VERSION = 2

_STOP = {"the", "a", "an", "for", "with", "of", "and", "to", "your", "you", "in",
         "on", "by", "or", "at", "is", "it", "my", "our", "this", "that", "from"}

# Personalisation / gift / marketing words. Present in most POD titles, so they
# can never be the reason two listings are the same niche.
MODIFIERS = {"personalized", "personalised", "custom", "customized", "customised",
             "monogram", "monogrammed", "name", "names", "initial", "initials",
             "gift", "gifts", "present", "unique", "handmade", "cute", "funny",
             "best", "new", "sale", "shop", "etsy", "matching", "set", "idea",
             "ideas"}

# Cut / fit / fabric. Describes the garment, never the niche. Without this,
# "custom crew t-shirt" would REQUIRE the word "crew" and miss plain tees.
STYLE = {"crew", "crewneck", "neck", "vneck", "v", "sleeve", "sleeved", "long",
         "short", "oversized", "unisex", "fitted", "relaxed", "heavyweight",
         "lightweight", "comfort", "color", "colors", "colour", "colours",
         "cotton", "fleece", "knit", "soft", "premium", "quality", "size",
         "sizes", "small", "medium", "large", "adult", "youth"}

# HOW it is decorated — not WHAT is being sold.
TECHNIQUES = {"embroidery", "embroidered", "embroider", "embroidering",
              "printed", "print", "printing", "engraved", "engraving", "etched",
              "vinyl", "sublimation", "sublimated", "screenprint", "screenprinted",
              "applique", "appliqued", "chenille", "tufted", "stitched", "stitch",
              "puff", "dtf", "dtg", "htv", "laser"}


def _singular(word):
    from src import supplier_trend as st
    try:
        return st._singular(word)
    except Exception:  # noqa: BLE001
        return word


def tokens(text):
    """Singularised content tokens. The one tokenizer both sides use."""
    return [_singular(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(w) > 1 and w not in _STOP]


def _product_nouns():
    from src import pattern_miner as pm
    # TECHNIQUES first: product_fit's noun set contains "embroidery"/"embroidered",
    # which are how a product is decorated, not the product.
    return pm._PRODUCT_NOUNS - TECHNIQUES


def bucket(token):
    """modifier | style | technique | product | theme — in precedence order."""
    t = _singular(token)
    if t in MODIFIERS:
        return "modifier"
    if t in STYLE:
        return "style"
    if t in TECHNIQUES:
        return "technique"
    if t in _product_nouns():
        return "product"
    # product_fit's noun set is not exhaustive — "handbag" is missing from it,
    # and classified as a theme it would be REQUIRED, so "custom name tote
    # handbag" would reject a plain "Name Tote Bag". supplier_ops already owns a
    # tested product vocabulary; ask it before falling through to theme.
    if _family(t):
        return "product"
    return "theme"


def classify(query):
    """{bucket: [tokens]} for a query, order-preserving and de-duplicated."""
    out = {"modifier": [], "style": [], "technique": [], "product": [],
           "theme": []}
    seen = set()
    for t in tokens(query):
        if t in seen:
            continue
        seen.add(t)
        out[bucket(t)].append(t)
    return out


def split_query(query):
    """(all, products, themes) — kept for the callers that only need these."""
    c = classify(query)
    allt = c["modifier"] + c["style"] + c["technique"] + c["product"] + c["theme"]
    ordered = [t for t in tokens(query) if t in set(allt)]
    seen, uniq = set(), []
    for t in ordered:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq, c["product"], c["theme"]


def _family(token):
    """Product family (tee/t-shirt/shirt -> one family). None when unknown."""
    try:
        from src.supplier_ops import product_family
        return product_family(token)
    except Exception:  # noqa: BLE001
        return None


def _product_hit(qproducts, ttoks):
    """(hit, via_synonym). Direct token match first, then same product family, so
    'custom crew t-shirt' still matches a listing titled 'Custom Tee'."""
    for p in qproducts:
        if p in ttoks:
            return True, False
    fams = {f for f in (_family(p) for p in qproducts) if f}
    if fams:
        for t in ttoks:
            if _family(t) in fams:
                return True, True
    return False, False


def match(text, query, need=None):
    """True when `text` belongs to `query`'s niche."""
    return why(text, query, need)[0]


def why(text, query, need=None):
    """(matched, reason, shared_tokens) — the evidence table's match-type column.

    Reasons:
      exact                     every query token present
      theme                     a theme token matched (a real niche match)
      synonym                   product matched through its family (tee ~ shirt)
      product_only              product matched, query named no theme
      modifier_only             shares only modifier/style words
      rejected_missing_theme    query names a theme; the listing has none
      rejected_product_mismatch query names a product; the listing has none
      none                      nothing shared
    """
    qtoks, products, themes = split_query(query)
    tt = set(tokens(text))
    shared = [t for t in qtoks if t in tt]
    if not qtoks:
        return True, "exact", shared

    floor = need if need is not None else min(2, len(qtoks))
    p_hit, via_syn = _product_hit(products, tt)

    if not shared and not p_hit:
        return False, "none", shared
    if len(shared) == len(qtoks):
        return True, "exact", shared

    # --- the niche requirement -----------------------------------------------
    if themes:
        if not any(t in tt for t in themes):
            # THE headline case: shares {personalized, shirt} but no halloween.
            return False, "rejected_missing_theme", shared
    elif products:
        if not p_hit:
            return False, "rejected_product_mismatch", shared

    if len(shared) < floor and not p_hit:
        return False, ("rejected_product_mismatch" if products
                       else "rejected_missing_theme"), shared

    if themes and any(t in tt for t in themes):
        return True, "theme", shared
    if via_syn:
        return True, "synonym", shared
    if p_hit:
        return True, "product_only", shared
    return True, "modifier_only", shared
