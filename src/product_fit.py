"""Product-fit / quality filter for keyword ideas.

Stops junk from showing up as launch opportunities: shop handles
(e.g. "haticemediumstudio"), policy/niche terms (spells, psychic), digital-only
terms, trademark/brand terms, and things that aren't a makeable POD/embroidery/
jewelry product. Everything is classified with a reason so nothing is hidden
silently — the dashboard can still show "risky / review" items on a toggle.
"""
import re

from src.discover import matches_mode
from src.trademark import check as tm_check

# --- vocab ---
POD_NOUNS = {"shirt", "tshirt", "tee", "hoodie", "sweatshirt", "sweater",
             "mug", "tumbler", "cup", "tote", "bag", "pouch", "poster", "print",
             "blanket", "pillow", "hat", "cap", "beanie", "sticker", "decal",
             "sign", "towel", "apron", "flag", "banner", "case", "mousepad"}
EMB_SIGNS = {"embroider", "embroidered", "embroidery", "chenille", "monogram",
             "monogrammed", "applique", "patch", "stitch", "stitched"}
JEWELRY_NOUNS = {"necklace", "bracelet", "ring", "pendant", "earring", "earrings",
                 "keychain", "charm", "bangle", "anklet", "locket"}
ACRYLIC_NOUNS = {"acrylic", "ornament", "plaque", "keepsake", "nightlight"}
DIGITAL_SIGNS = {"svg", "png", "clipart", "clip art", "sublimation", "printable",
                 "digital", "download", "cricut", "cut file", "vector", "dxf", "pdf"}
POLICY_SIGNS = {"spell", "spells", "psychic", "reading", "tarot", "witchcraft",
                "hex", "curse", "manifest", "manifestation", "voodoo", "ritual",
                "coven", "clairvoyant", "fortune telling"}
SHOP_SUFFIXES = ("studio", "studios", "shop", "store", "co", "designs", "design",
                 "prints", "boutique", "atelier", "creations", "crafts", "arts")
GENERIC = {"gift", "gifts", "custom", "personalized", "cute", "trendy", "new",
           "best", "popular", "handmade", "unique", "shirt", "mug", "bag", "art",
           "design", "for", "her", "him", "mom", "dad"}

# Final statuses.
POD_FIT, EMBROIDERY_FIT, JEWELRY_FIT, ACRYLIC_FIT = \
    "POD_FIT", "EMBROIDERY_FIT", "JEWELRY_FIT", "ACRYLIC_FIT"
DIGITAL_FIT, SHOP_NAME_LIKELY, POLICY_RISK, TRADEMARK_RISK = \
    "DIGITAL_FIT", "SHOP_NAME_LIKELY", "POLICY_RISK", "TRADEMARK_RISK"
BROAD_SEED_ONLY, NON_PRODUCT, NEEDS_REVIEW = \
    "BROAD_SEED_ONLY", "NON_PRODUCT", "NEEDS_REVIEW"

LAUNCHABLE = {POD_FIT, EMBROIDERY_FIT, JEWELRY_FIT, ACRYLIC_FIT}


def _looks_like_shop(kw):
    t = kw.strip().lower()
    words = t.split()
    # one long run-on token with no spaces (a handle), e.g. haticemediumstudio
    if len(words) == 1 and len(t) >= 13 and t.isalpha():
        return True
    # ends with a shop-like suffix and reads like a brand (<= 3 words)
    if len(words) <= 3 and words and words[-1] in SHOP_SUFFIXES:
        return True
    return False


def classify(keyword, mode=None):
    """Return {status, launchable, product_type, reason} for one keyword."""
    kw = (keyword or "").strip().lower()
    words = set(re.findall(r"[a-z0-9]+", kw))
    # plural-aware: also match the singular of each word (decals -> decal)
    words |= {w[:-1] for w in list(words) if w.endswith("s") and len(w) > 3}
    if not kw:
        return {"status": NON_PRODUCT, "launchable": False,
                "product_type": "", "reason": "empty"}

    # 1. trademark / brand (HIGH only — CAUTION stays launchable but flagged)
    risk, why = tm_check(kw)
    if risk == "HIGH":
        return {"status": TRADEMARK_RISK, "launchable": False,
                "product_type": "", "reason": f"trademark/brand: {why}"}

    # 2. policy / spiritual niche
    if words & POLICY_SIGNS:
        return {"status": POLICY_RISK, "launchable": False, "product_type": "",
                "reason": "spiritual/spell niche — Etsy policy review"}

    # 3. shop handle / brand name
    if _looks_like_shop(kw):
        return {"status": SHOP_NAME_LIKELY, "launchable": False,
                "product_type": "", "reason": "looks like a shop/brand name, not a product"}

    # 4. digital-only (not our physical POD/embroidery business)
    if words & {w for s in DIGITAL_SIGNS for w in s.split()}:
        return {"status": DIGITAL_FIT, "launchable": False, "product_type": "digital",
                "reason": "digital/printable — not a supplier-made physical product"}

    # 5. product-mode fit
    if words & EMB_SIGNS or matches_mode(kw, "embroidery"):
        st, pt = EMBROIDERY_FIT, "embroidery"
    elif words & JEWELRY_NOUNS:
        st, pt = JEWELRY_FIT, "jewelry"
    elif words & ACRYLIC_NOUNS:
        st, pt = ACRYLIC_FIT, "acrylic"
    elif words & POD_NOUNS:
        st, pt = POD_FIT, "pod"
    else:
        # no product noun at all
        if words and words <= GENERIC:
            return {"status": BROAD_SEED_ONLY, "launchable": False,
                    "product_type": "", "reason": "too broad — a seed, not a specific product"}
        return {"status": NEEDS_REVIEW, "launchable": False, "product_type": "",
                "reason": "no clear product type — review + add a product angle"}

    # broad seed even with a noun? (e.g. just "shirt" / "gift mug")
    if len(words) <= 2 and words <= GENERIC | POD_NOUNS | JEWELRY_NOUNS:
        return {"status": BROAD_SEED_ONLY, "launchable": False, "product_type": pt,
                "reason": "too broad — narrow to a niche/occasion angle"}

    # requested mode mismatch -> not a launch opportunity for THIS mode
    if mode in ("pod", "embroidery") and not matches_mode(kw, mode):
        return {"status": st, "launchable": False, "product_type": pt,
                "reason": f"fits {pt}, not the selected {mode} mode"}

    reason = "makeable product; verify trademark" if risk == "CAUTION" else "makeable product"
    return {"status": st, "launchable": True, "product_type": pt, "reason": reason}


def annotate(rows, key="tag", mode=None):
    """Attach a 'fit' dict to each row (rows are dicts with a keyword under `key`)."""
    for r in rows:
        r["fit"] = classify(r.get(key) or r.get("keyword") or "", mode)
    return rows
