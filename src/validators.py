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


def validate_tags(tags, confirmed_material=""):
    """Return (passed, issues). Exactly 13 quality, safe, distinct tags."""
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
    wordsets = Counter(frozenset(t.split()) for t in norm)
    near = [next(t for t in norm if frozenset(t.split()) == ws)
            for ws, n in wordsets.items() if n > 1]
    if near:
        issues.append(f"near-duplicate tags (same words reordered): "
                      f"{', '.join(near)}")
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
    # coverage guidance (warns, doesn't fail): buyer-intent variety
    multiword = sum(1 for t in norm if " " in t)
    if multiword < 8:
        issues.append(f"only {multiword}/13 multi-word tags - add long-tail "
                      "buyer-intent phrases (occasion, audience, use case)")
    return (not issues), issues
