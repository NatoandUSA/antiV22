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
teacher 52%, school 38%, back 33%, appreciation 24%. The tokens that carry the
niche — halloween — were never required.

THE RULE
Split the query into three kinds of token:

    modifier  personalized / custom / gift  — says nothing about the niche
    product   shirt, sweatshirt, tote, mug  — says WHAT it is
    theme     halloween, teacher, bride     — says WHICH niche it is

A listing belongs to the niche when it shares enough tokens overall AND, when
the query names a theme, it shares at least one THEME token. "Personalized" and
"shirt" can no longer carry a match on their own.

WHEN THERE IS NO THEME
A query like "tote bag" is all product nouns and has no theme to require, so the
old overall-overlap rule stands alone and nothing regresses.

HONEST-NULL
An empty query matches everything (the miner's overview mode); it does not
silently match nothing.
"""
import re

_STOP = {"the", "a", "an", "for", "with", "of", "and", "to", "your", "you", "in",
         "on", "by", "or", "at", "is", "it", "my", "our", "this", "that", "from"}

# Personalisation / gift words. Present in almost every POD title, so they can
# never be the reason two listings are "the same niche".
MODIFIERS = {"personalized", "personalised", "custom", "customized", "customised",
             "monogram", "monogrammed", "name", "names", "initial", "initials",
             "gift", "gifts", "present", "unique", "handmade", "cute", "funny",
             "best", "new", "sale", "shop", "etsy"}


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


def _products():
    from src import pattern_miner as pm
    return pm._PRODUCT_NOUNS


def split_query(query):
    """(all, products, themes) for a query. Themes are what make it a niche."""
    toks = []
    for t in tokens(query):
        if t not in toks:
            toks.append(t)
    prods = _products()
    products = [t for t in toks if t in prods]
    themes = [t for t in toks if t not in prods and t not in MODIFIERS]
    return toks, products, themes


def match(text, query, need=None):
    """True when `text` belongs to `query`'s niche.

    need : overall token overlap required. Defaults to the historical
           min(2, len(query tokens)) so existing behaviour is the floor, not a
           new stricter rule — the theme requirement is what does the work.
    """
    qtoks, _products_, themes = split_query(query)
    if not qtoks:
        return True                       # no query == overview mode
    tt = set(tokens(text))
    hits = sum(1 for t in qtoks if t in tt)
    if hits < (need if need is not None else min(2, len(qtoks))):
        return False
    if themes and not any(t in tt for t in themes):
        # Shares only modifiers and/or a product noun. "Personalized Teacher
        # Shirt" is not a Halloween listing.
        return False
    return True


def why(text, query):
    """Explain a match/miss — what the evidence table's match-type column reads.

    Returns (matched: bool, kind: str, shared: list). Kinds:
      exact      every query token present
      theme      a theme token plus enough overlap  (a real niche match)
      product    product noun only, no theme        (rejected)
      modifier   personalisation words only         (rejected)
      none       nothing shared
    """
    qtoks, products, themes = split_query(query)
    tt = set(tokens(text))
    shared = [t for t in qtoks if t in tt]
    if not qtoks:
        return True, "exact", shared
    if not shared:
        return False, "none", shared
    if len(shared) == len(qtoks):
        return True, "exact", shared
    matched = match(text, query)
    if matched:
        return True, "theme", shared
    if any(t in products for t in shared):
        return False, "product", shared
    return False, "modifier", shared
