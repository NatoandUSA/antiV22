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
# F3 (V35.6): apparel / drinkware / accessory nouns added so real POD keywords
# (denim jacket, leggings, joggers, water bottle, koozie, wallet ...) are no
# longer mis-classified as "no product noun" -> THEME_FIT_NEEDS_PRODUCT and
# silently dropped from launch opportunities.
POD_NOUNS = {"shirt", "tshirt", "tee", "hoodie", "sweatshirt", "sweater",
             "mug", "tumbler", "cup", "tote", "bag", "pouch", "poster", "print",
             "blanket", "pillow", "hat", "cap", "beanie", "sticker", "decal",
             "sign", "towel", "apron", "flag", "banner", "case", "mousepad",
             # apparel
             "jacket", "coat", "vest", "cardigan", "joggers", "jogger",
             "sweatpants", "leggings", "legging", "shorts", "romper", "jumpsuit",
             "bodysuit", "onesie", "dress", "skirt", "jersey", "tank", "poncho",
             "robe", "pajamas", "pajama", "overalls", "scarf", "gloves",
             "mittens", "socks", "sock", "tights", "bandana", "headband",
             "visor", "crewneck",
             # drinkware / accessories / home
             "bottle", "flask", "koozie", "coozie", "cooler", "wallet",
             "backpack", "lanyard", "coaster", "magnet", "keytag", "doormat",
             "placemat", "jar", "wristband", "hoodie"}
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
# Occasion / holiday / gift-recipient signals: a theme carrying these has clear
# buyer intent and converts on an obvious default product -> launch-ready as-is.
BUYER_INTENT_SIGNS = {"christmas", "xmas", "halloween", "thanksgiving", "easter",
                      "valentine", "valentines", "birthday", "wedding", "bridal",
                      "bridesmaid", "anniversary", "graduation", "retirement",
                      "baby", "newborn", "nursery", "engagement", "reunion",
                      "celebration", "celebrations", "memorial", "appreciation",
                      "mothers", "fathers", "teacher", "nurse", "coworker",
                      "wife", "husband"}
# Curiosity / informational phrases: people browse, they don't buy.
CURIOSITY_SIGNS = {"facts", "fact", "trivia", "quiz", "meaning", "definition",
                   "history", "wiki", "statistics", "stats", "tutorial", "guide"}
# Lone modifiers that are meaningless without a concrete subject.
VAGUE_MODIFIERS = {"funny", "retro", "vintage", "aesthetic", "boho", "spooky",
                   "sassy", "cozy", "groovy", "minimalist", "cottagecore"}

# Final statuses.
POD_FIT, EMBROIDERY_FIT, JEWELRY_FIT, ACRYLIC_FIT = \
    "POD_FIT", "EMBROIDERY_FIT", "JEWELRY_FIT", "ACRYLIC_FIT"
DIGITAL_FIT, SHOP_NAME_LIKELY, POLICY_RISK, TRADEMARK_RISK = \
    "DIGITAL_FIT", "SHOP_NAME_LIKELY", "POLICY_RISK", "TRADEMARK_RISK"
BROAD_SEED_ONLY, NON_PRODUCT, NEEDS_REVIEW = \
    "BROAD_SEED_ONLY", "NON_PRODUCT", "NEEDS_REVIEW"

# A design theme has no literal product noun. We split it by how launch-ready it is:
#   THEME_FIT_READY         - clear theme WITH buyer intent + no risk -> launch as-is
#   THEME_FIT_NEEDS_PRODUCT - good theme but no product noun -> choose a product first
#   AMBIGUOUS_PHRASE        - meaning/intent unclear
#   LOW_BUYER_INTENT        - curiosity/vague -> unlikely to convert
THEME_FIT_READY, THEME_FIT_NEEDS_PRODUCT, AMBIGUOUS_PHRASE, LOW_BUYER_INTENT = \
    "THEME_FIT_READY", "THEME_FIT_NEEDS_PRODUCT", "AMBIGUOUS_PHRASE", "LOW_BUYER_INTENT"

# Only these are shown as normal launch opportunities.
LAUNCHABLE = {POD_FIT, EMBROIDERY_FIT, JEWELRY_FIT, ACRYLIC_FIT, THEME_FIT_READY}


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
        # No literal product noun. Decide among: too-broad seed, a launch-ready
        # theme (clear buyer intent), a theme that still needs a product chosen,
        # or a low-value phrase (curiosity / ambiguous — unlikely to convert).
        non_generic = words - GENERIC
        if not non_generic:
            return {"status": BROAD_SEED_ONLY, "launchable": False,
                    "product_type": "", "reason": "too broad — a seed, not a specific product"}
        if words & CURIOSITY_SIGNS:
            return {"status": LOW_BUYER_INTENT, "launchable": False,
                    "product_type": "theme",
                    "reason": "curiosity/informational phrase — unlikely to convert"}
        has_intent = bool(words & BUYER_INTENT_SIGNS)
        lone = next(iter(non_generic)) if len(non_generic) == 1 else None
        if lone and not has_intent and (len(lone) <= 3 or lone in VAGUE_MODIFIERS):
            return {"status": AMBIGUOUS_PHRASE, "launchable": False,
                    "product_type": "theme",
                    "reason": "meaning/intent unclear — needs a clearer angle"}
        if has_intent and risk != "CAUTION":
            return {"status": THEME_FIT_READY, "launchable": True,
                    "product_type": "theme",
                    "reason": "clear design theme with buyer intent — launch on a "
                    "default product (shirt / mug / tote)"}
        return {"status": THEME_FIT_NEEDS_PRODUCT, "launchable": False,
                "product_type": "theme",
                "reason": "good design theme but no product — pair with a shirt, "
                "sweatshirt, mug, tote, or pouch"
                + ("; verify trademark" if risk == "CAUTION" else "")}

    # broad seed even with a noun? (e.g. just "shirt" / "gift mug")
    if len(words) <= 2 and words <= GENERIC | POD_NOUNS | JEWELRY_NOUNS:
        return {"status": BROAD_SEED_ONLY, "launchable": False, "product_type": pt,
                "reason": "too broad — narrow to a niche/occasion angle"}

    # requested mode mismatch -> not a launch opportunity for THIS mode
    if mode in ("pod", "embroidery") and not matches_mode(kw, mode):
        return {"status": st, "launchable": False, "product_type": pt,
                "reason": f"fits {pt}, not the selected {mode} mode"}

    reason = "makeable product; verify trademark" if risk == "CAUTION" else "makeable product"
    # F1 (V35.6): expose the trademark risk so ranking_engine can cap a CAUTION
    # (ambiguous brand / slogan) term at CONFIRM_FIRST instead of BUILD_NOW.
    return {"status": st, "launchable": True, "product_type": pt, "reason": reason,
            "tm_risk": risk}


# --- embroidery stitch producibility (used by opportunity_score._feasibility) ---
# We only have the keyword TEXT here (no image), so this reads the design CONCEPT:
# which ideas are known to stitch cleanly vs which fight the medium.
HARD_TO_STITCH = {"watercolor", "gradient", "ombre", "galaxy", "nebula", "cosmos",
                  "cosmic", "photorealistic", "photo", "photograph", "realistic",
                  "portrait", "3d", "shading", "sketch", "pencil", "charcoal",
                  "detailed", "intricate", "filigree", "lace", "mandala", "tiny",
                  "miniature", "landscape", "scenery", "sunset", "fur", "feathers",
                  "smoke", "splash", "splatter", "distressed", "grunge", "airbrush",
                  "hologram", "holographic", "iridescent"}
FINE_TEXT = {"handwriting", "handwritten", "cursive", "script", "calligraphy",
             "signature", "paragraph", "quote", "poem", "verse", "lyrics"}
STITCH_SAFE = {"monogram", "monogrammed", "initial", "initials", "name", "names",
               "letter", "letters", "number", "bold", "block", "simple", "clean",
               "outline", "silhouette", "logo", "badge", "crest", "emblem",
               "minimalist", "text", "typography", "applique", "patch"}


def producibility(keyword, mode=""):
    """Embroidery stitch-producibility read from the design CONCEPT (keyword text).

    Returns {"score": 0-100, "label", "reasons"}. For print/POD (or any non-
    embroidery context) returns label 'PRINTS_FINE' + score 100 - print reproduces
    almost any art, so callers skip the penalty. For embroidery/chenille it scores
    how cleanly the idea is likely to stitch: gradients, photo-realism, fine detail
    and tiny/handwritten text drag it down; bold shapes, monograms and short text
    lift it. This is a concept heuristic, NOT a substitute for a real sew-out."""
    kw = (keyword or "").lower()
    m = (mode or "").strip().lower()
    words = set(re.findall(r"[a-z0-9]+", kw))
    emb_ctx = (m in ("embroidery", "chenille")
               or (m not in ("pod", "print", "jewelry", "acrylic", "digital")
                   and bool(words & EMB_SIGNS)))
    if not emb_ctx:
        return {"score": 100, "label": "PRINTS_FINE",
                "reasons": ["print reproduces fine art / gradients / photos"]}
    score, reasons = 72, []
    hard = words & HARD_TO_STITCH
    if hard:
        score -= 12 * len(hard)
        reasons.append("hard to stitch cleanly: " + ", ".join(sorted(hard)))
    fine = words & FINE_TEXT
    if fine:
        score -= 10 * len(fine)
        reasons.append("fine/handwritten text won't stitch small: "
                       + ", ".join(sorted(fine)))
    safe = words & STITCH_SAFE
    if safe:
        score += 8 * len(safe)
        reasons.append("stitch-friendly: " + ", ".join(sorted(safe)))
    score = max(0, min(100, score))
    label = ("STITCH_SAFE" if score >= 75 else
             "STITCH_OK" if score >= 50 else "STITCH_RISK")
    if not reasons:
        reasons.append("no obvious stitch red flags in the concept")
    return {"score": score, "label": label, "reasons": reasons}


def annotate(rows, key="tag", mode=None):
    """Attach a 'fit' dict to each row (rows are dicts with a keyword under `key`)."""
    for r in rows:
        r["fit"] = classify(r.get(key) or r.get("keyword") or "", mode)
    return rows
