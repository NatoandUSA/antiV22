"""Early feasibility gate — workflow steps 2 (Pinterest) and 3 (Supplier).

WHY THIS EXISTS
Supplier feasibility used to be checked at the PUBLISH gate
(`product_manager.gates["supplier_confirmed"]`), which is the most expensive
possible moment: by then someone has already written the title, 13 tags, the
description, the design brief and the photo plan for a product the shop cannot
manufacture. In the owner's real workflow supplier feasibility is step 3 — it
runs BEFORE Pattern Miner, so nobody spends time on an unmakeable product.

Pinterest was in the same position but is a DIFFERENT kind of signal: it is a
separate marketplace, so it corroborates confidence and must never veto a
keyword that Etsy's own data says is good. It is advisory, displayed only.

FROZEN-FILE RULE
`ranking_engine.py` and `opportunity_score.py` are frozen. This module does not
import, patch or modify either. It reuses the SAME idea as the L0 gate/cap
pattern, but as a separate post-ranking overlay applied by the (non-frozen)
opportunity_inbox. The ranking math is untouched: a blocked row keeps the score
the engine gave it, and only its ACTION and build permission change.

HONEST-NULLS
An empty supplier library means UNKNOWN, never NOT_MAKEABLE. With no supplier
records the gate stays dormant and reports "Supplier not checked" — it must not
block all 1,523 keywords just because nobody has imported a supplier CSV yet.

REVIVABLE
A block is never permanent. It is recomputed from the live supplier library on
every read, so importing a supplier later revives the keyword automatically.
Nothing is written to the master to record a block.
"""

MAKEABLE, UNKNOWN, NOT_MAKEABLE = "MAKEABLE", "UNKNOWN", "NOT_MAKEABLE"
RISING, FLAT, NONE_, PIN_UNKNOWN = "RISING", "FLAT", "NONE", "UNKNOWN"

# Reason code carried on a blocked row (owner-specified contract).
BLOCK_REASON = "no_supplier_can_make_this"
# ranking_engine has no SUPPLIER_BLOCKED action and is frozen, so a blocked row
# takes the existing SKIP action and is labelled distinctly for the view.
BLOCK_ACTION = "SKIP"
BLOCK_LABEL = "Supplier blocked"

# Action priorities, DUPLICATED here on purpose. This module must add ZERO new
# references to the frozen ranking files, so it does not import
# ranking_engine._PRI even read-only: an import is a dependency, and the freeze
# means "nothing new points at these files". The values mirror
# ranking_engine._PRI; if they ever diverge, the frozen file is authoritative and
# test_no_frozen_imports will not catch it, so keep this list short and stable.
_PRIORITY = {"BLOCKED": 0, "SKIP": 1, "WATCH": 2, "REVIEW": 3,
             "CONFIRM_FIRST": 4, "BUILD_NOW": 5}

# Product-TYPE vocabulary. The gate deliberately does NOT use
# supplier_ops.match(): that scores token overlap between a keyword and a
# supplier product NAME, and the real library holds four blank types
# ("TSHIRT", "SWEATSHIRT", "HOODIE", "WASH CAP"). Measured on the live master,
# every threshold blocked ~100% of keywords -- "custom crew t-shirt" does not
# even token-match "TSHIRT". The right question is not "does this keyword look
# like a supplier row" but "is the product this keyword implies one my suppliers
# can make", so both sides are normalised to the same small vocabulary.
_TYPES = {
    "tshirt": ("tshirt", "t shirt", "tee", "tees", "shirt"),
    "sweatshirt": ("sweatshirt", "crewneck", "crew neck", "jumper"),
    "hoodie": ("hoodie", "hoody", "hooded"),
    "cap": ("cap", "hat", "beanie", "trucker", "snapback"),
    "tote": ("tote", "totebag", "handbag", "purse", "pouch", "bag"),
    "blanket": ("blanket", "throw"),
    "pillow": ("pillow", "cushion"),
    "towel": ("towel", "robe"),
    "mug": ("mug", "tumbler", "cup", "can cooler", "cozie", "cozies", "koozie"),
    "sticker": ("sticker", "decal"),
    "print": ("print", "poster", "wall art", "canvas"),
    "jewelry": ("necklace", "bracelet", "earring", "keychain", "charm"),
    "apron": ("apron",),
    "bib": ("bib",),
    "sock": ("sock", "socks"),
}


def _type_of(text):
    """The product type a phrase implies, or None when it names no product.

    None is the common case for a keyword like "40th birthday cozies" that names
    an occasion rather than a product, and None must stay UNKNOWN -- we only
    block when we can positively identify a product the library does not cover.
    """
    t = " " + " ".join(str(text or "").lower().replace("-", " ").split()) + " "
    for key, words in _TYPES.items():
        for w in words:
            if f" {w} " in t or t.endswith(f" {w} "):
                return key
    return None


def has_supplier_library(path=None):
    """True when ANY supplier product exists. Gate stays dormant when false."""
    try:
        from src import supplier_ops as so
        rows = so.load_products(path or so.DEFAULT_OUT)
        return bool(rows)
    except Exception:  # noqa: BLE001 - unreadable library == unknown, never a block
        return False


def supplier_fit(keyword, mode=None, path=None):
    """MAKEABLE / UNKNOWN / NOT_MAKEABLE for one keyword. Never raises.

    UNKNOWN whenever we genuinely cannot tell: no library, unreadable library,
    or no keyword. Only a populated, readable library with no adequate
    mode-correct match returns NOT_MAKEABLE.
    """
    kw = (keyword or "").strip()
    if not kw or not has_supplier_library(path):
        return UNKNOWN, None
    want = _type_of(kw)
    if want is None:
        # The keyword names no product we recognise (an occasion, a theme, a
        # phrase). We cannot claim it is unmakeable, so it stays dormant.
        return UNKNOWN, {"why": "keyword names no recognisable product type"}
    try:
        from src import supplier_ops as so
        rows = so.load_products(path or so.DEFAULT_OUT) or []
    except Exception:  # noqa: BLE001
        return UNKNOWN, None
    covered, sample = set(), {}
    for r in rows:
        pm = (r.get("production_mode") or "").upper()
        if mode and str(mode).upper() == "EMBROIDERY" and "EMBROIDERY" not in pm \
                and "CHENILLE" not in pm:
            continue                     # mode-correct: POD row can't embroider
        t = _type_of(r.get("product_name"))
        if t:
            covered.add(t)
            sample.setdefault(t, r.get("product_name"))
    if not covered:
        # A library we cannot interpret is UNKNOWN, never a block.
        return UNKNOWN, {"why": "no supplier product type could be read"}
    if want in covered:
        return MAKEABLE, {"product_type": want, "supplier_product": sample[want]}
    return NOT_MAKEABLE, {"product_type": want,
                          "covered": sorted(covered)}


def build_allowed(keyword, mode=None, path=None):
    """The ONE predicate every build-ish surface asks before letting work start:
    Pattern Miner, Build Queue, Launch Kit, Photo Plan, Team Ops build tasks.

    Returns (allowed: bool, info: dict). Advisory Pinterest is never consulted
    here — it cannot block anything by design.
    """
    fit, detail = supplier_fit(keyword, mode, path)
    if fit == NOT_MAKEABLE:
        return False, {"fit": fit, "reason": BLOCK_REASON, "revivable": True,
                       "label": BLOCK_LABEL, "detail": detail,
                       "message": ("No supplier in your library can make this. "
                                   "Import or add a supplier, then it comes back "
                                   "automatically.")}
    return True, {"fit": fit, "reason": None, "revivable": True,
                  "label": ("Makeable" if fit == MAKEABLE
                            else "Supplier not checked"),
                  "detail": detail}


def pinterest_label(keyword):
    """RISING / FLAT / NONE / UNKNOWN — ADVISORY ONLY.

    Pinterest is a different marketplace: a keyword can sell well on Etsy with no
    Pinterest presence at all, so this never gates anything. Any failure (no API
    key, network down, no cache) is UNKNOWN, not NONE — 'we did not check' and
    'we checked and found nothing' must stay distinguishable.
    """
    kw = (keyword or "").strip()
    if not kw:
        return PIN_UNKNOWN, None
    try:
        from src import crosscheck
        sig = crosscheck.pinterest_signal(kw)
    except Exception:  # noqa: BLE001
        return PIN_UNKNOWN, None
    if not sig or not isinstance(sig, dict):
        return PIN_UNKNOWN, None
    if sig.get("unavailable") or sig.get("error"):
        return PIN_UNKNOWN, sig
    growth = sig.get("growth") or sig.get("direction") or ""
    found = sig.get("found")
    if found is False:
        return NONE_, sig
    g = str(growth).lower()
    if "grow" in g or "rising" in g or "up" in g:
        return RISING, sig
    if found or sig.get("volume") or sig.get("interest") is not None:
        return FLAT, sig
    return PIN_UNKNOWN, sig


def apply_to_row(row, mode=None, path=None):
    """Overlay the gate on ONE ranked inbox row, in place. Returns the row.

    The engine's score is left exactly as it was — only the action and the build
    permission change, so this can never be mistaken for a ranking-math edit.
    A row the engine already BLOCKED (trademark) or SKIPped stays as it is.
    """
    kw = (row or {}).get("keyword")
    if not kw:
        return row
    allowed, info = build_allowed(kw, mode, path)
    row["supplier_fit"] = info["fit"]
    row["supplier_label"] = info["label"]
    row["build_allowed"] = allowed
    if not allowed and row.get("action") not in ("BLOCKED",):
        row["action"] = BLOCK_ACTION
        row["route"] = "skip"
        row["supplier_blocked"] = True
        row["revivable"] = True
        row["reason"] = BLOCK_REASON
        row["reason_text"] = info["message"]
        row["priority"] = _PRIORITY.get(BLOCK_ACTION, 1)
    return row


def summary(rows):
    """Counts for the workflow spine (step 3)."""
    out = {MAKEABLE: 0, UNKNOWN: 0, NOT_MAKEABLE: 0}
    for r in rows or []:
        out[r.get("supplier_fit") or UNKNOWN] = \
            out.get(r.get("supplier_fit") or UNKNOWN, 0) + 1
    return out
