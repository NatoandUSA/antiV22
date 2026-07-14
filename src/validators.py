"""Title and tag validators (Etsy best-practice enforcement).

Titles: clear, buyer-readable, front-loaded product noun, no keyword
stuffing, no brand/celebrity terms, no unsupported material claims.
Tags: exactly 13, <=20 chars, no duplicates or near-duplicates, no
low-quality generic tags, no IP-risk terms.
"""
import re
from collections import Counter

from src.trademark import check as tm_check

PRODUCT_NOUNS = {"bag", "pouch", "tote", "purse", "organizer", "kit",
                 "shirt", "hoodie", "sweatshirt", "tee", "mug", "tumbler",
                 "necklace", "bracelet", "ring", "print", "poster", "sign",
                 "blanket", "pillow", "towel", "hat", "sticker", "ornament"}

MATERIAL_CLAIMS = {"leather", "organic", "waterproof", "14k", "gold",
                   "silver", "silk", "cashmere", "linen", "bamboo",
                   "recycled", "eco friendly", "sterling"}

GENERIC_TAGS = {"gift", "gifts", "cute", "trendy", "new", "best seller",
                "handmade", "custom", "personalized", "unique", "popular"}

STOP = {"a", "an", "the", "for", "with", "and", "of", "to", "in", "on"}

# Occasion / buyer-intent tokens: >=2 tags should target one (Etsy buyers search
# by occasion, event, use-case, or recipient). Broad but high-signal.
OCC_BUYER = (
    # gifting occasions / holidays
    "birthday", "wedding", "christmas", "anniversary", "graduation",
    "valentine", "halloween", "thanksgiving", "baby shower", "bridal",
    "bridesmaid", "engagement", "retirement", "housewarming", "mother",
    "father", "holiday",
    # events / use-cases (also buyer intent)
    "concert", "festival", "game day", "stadium", "travel", "vacation",
    "party", "gym", "beach", "work", "school", "everyday", "event",
    # recipient / audience
    "for her", "for him", "for mom", "for dad", "for wife", "for husband",
    "for daughter", "for son", "for grandma", "for grandpa", "for teacher",
    "for nurse", "for friend", "for couples", "for women", "for men",
    "for kids", "teacher", "nurse")


def _singular(w):
    """Crude singularizer so 'bag'/'bags' and 'gift'/'gifts' collapse together."""
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _sing_words(t):
    return frozenset(_singular(w) for w in t.split())


def is_occ_buyer(tag):
    return any(k in tag.lower() for k in OCC_BUYER)


def validate_title(title, confirmed_material="", primary_keyword=""):
    """Return (passed, issues). Buyer-friendly title rules."""
    issues = []
    words = [w.strip(",").lower() for w in title.split() if w.strip(",")]
    if len(title) > 140:
        issues.append(f"over Etsy's 140 chars ({len(title)})")
    # Relevancy is Etsy's #1 signal and mobile shows only ~40 chars, so the
    # main keyword must appear in the first 40 characters of the title.
    pk = (primary_keyword or "").strip().lower()
    if pk and pk not in title[:40].lower():
        issues.append(f"main keyword '{primary_keyword}' not in first 40 "
                      "chars (mobile cuts off ~40; Etsy weights the front)")
    if len(words) > 15:
        issues.append(f"too long for buyers ({len(words)} words; keep <=15)")
    if title.count(",") > 3:
        issues.append(f"{title.count(',')} commas - reads as keyword "
                      "chain, not a title")
    counts = Counter(w for w in words if w not in STOP)
    stuffed = [w for w, n in counts.items() if n > 2]
    if stuffed:
        issues.append(f"keyword stuffing: {', '.join(stuffed)} repeated 3+x")
    first5 = set(words[:5])
    if not first5 & PRODUCT_NOUNS:
        issues.append("no product noun in the first 5 words")
    risk, why = tm_check(title)
    if risk == "HIGH":
        issues.append(f"trademark/brand term: {why}")
    material = (confirmed_material or "").lower()
    unsupported = [m for m in MATERIAL_CLAIMS
                   if re.search(rf"\b{m}\b", title.lower())
                   and m not in material]
    if unsupported:
        issues.append(f"unsupported material claim (no supplier evidence): "
                      f"{', '.join(unsupported)}")
    return (not issues), issues


def validate_tags(tags, confirmed_material="", title=""):
    """Return (passed, issues). Exactly 13 quality, safe, distinct tags.

    When `title` is given, also require >=3 tags to echo the title's keywords."""
    issues = []
    if len(tags) != 13:
        issues.append(f"must be exactly 13 tags (got {len(tags)})")
    norm = [t.strip().lower() for t in tags]
    over = [t for t in norm if len(t) > 20]
    if over:
        issues.append(f"over 20 chars: {', '.join(over)}")
    dupes = [t for t, n in Counter(norm).items() if n > 1]
    if dupes:
        issues.append(f"duplicate tags: {', '.join(dupes)}")
    # near-duplicate = same words after singular/plural + reorder collapse (Etsy
    # treats 'name bag' and 'name bags' as the same tag -> a wasted slot).
    wordsets = Counter(_sing_words(t) for t in norm)
    near = [next(t for t in norm if _sing_words(t) == wsk)
            for wsk, n in wordsets.items() if n > 1]
    if near:
        issues.append("near-duplicate tags (same words / singular-plural): "
                      + ", ".join(near))
    generic = [t for t in norm if t in GENERIC_TAGS]
    if generic:
        issues.append(f"low-quality generic single tags: "
                      f"{', '.join(generic)} - make them long-tail")
    for t in norm:
        if tm_check(t)[0] == "HIGH":
            issues.append(f"trademark-risk tag: {t}")
    material = (confirmed_material or "").lower()
    claims = [t for t in norm for m in MATERIAL_CLAIMS
              if re.search(rf"\b{m}\b", t) and m not in material]
    if claims:
        issues.append(f"tags claim unverified materials: "
                      f"{', '.join(sorted(set(claims)))}")
    # coverage: buyer-intent variety
    multiword = sum(1 for t in norm if " " in t)
    if multiword < 8:
        issues.append(f"only {multiword}/13 multi-word tags - add long-tail "
                      "buyer-intent phrases (occasion, audience, use case)")
    # >=2 tags should target an occasion or a buyer (how gift shoppers search)
    occ = sum(1 for t in norm if is_occ_buyer(t))
    if occ < 2:
        issues.append(f"only {occ} occasion/buyer tag(s) - add >=2 "
                      "(e.g. birthday, for her, wedding, for mom)")
    # >=3 tags should echo the title so its keywords are reinforced (relevancy)
    tl = (title or "").lower()
    if tl:
        tw = {_singular(w) for w in re.findall(r"[a-z]+", tl)
              if w not in STOP and len(w) > 2}
        echo = sum(1 for t in norm
                   if tw & {_singular(w) for w in t.split() if w not in STOP})
        if echo < 3:
            issues.append(f"only {echo} tag(s) echo the title - >=3 should "
                          "reinforce the title keywords")
    return (not issues), issues
