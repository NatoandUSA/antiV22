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

COVERAGE BEFORE ENFORCEMENT (owner's order, items D + F)
"No supplier matched" only means "we cannot make this" if the library is
COMPLETE. Measured on the real library: 25 product rows from ONE supplier
(TSHIRT / SWEATSHIRT / HOODIE / WASH CAP, all EMBROIDERY, all SUPPLIER_PARTIAL),
while supplier_sources.json registers eight suppliers — six POD catalogs with
zero products imported. So the library is INCOMPLETE, not embroidery-only, and a
miss there is a gap in our data, not a fact about the shop. While coverage is
partial or unknown a miss returns NEEDS_SUPPLIER_CHECK, which is a BADGE and
never a block. NOT_MAKEABLE — the only verdict that can stop work — is reachable
only once every registered supplier has confirmed products on file.
"""
from pathlib import Path

# ONE canonical matcher, shared with supplier_ops.match(). A private copy here is
# what let the two surfaces disagree about whether the shop can make a product.
from src.supplier_ops import product_family as _family

MAKEABLE, UNKNOWN, NOT_MAKEABLE = "MAKEABLE", "UNKNOWN", "NOT_MAKEABLE"
# The verdict the owner asked for: the library says no, but the library is not
# finished, so this is a question for a human — not a block.
NEEDS_SUPPLIER_CHECK = "NEEDS_SUPPLIER_CHECK"
RISING, FLAT, NONE_, PIN_UNKNOWN = "RISING", "FLAT", "NONE", "UNKNOWN"

# Library coverage (item D). Only COMPLETE unlocks enforcement (item F).
COV_COMPLETE, COV_PARTIAL, COV_NONE = "complete", "partial", "unknown"

# The four badges, exactly as the owner specified them.
LABELS = {MAKEABLE: "Makeable", UNKNOWN: "Not checked",
          NEEDS_SUPPLIER_CHECK: "Needs supplier check",
          NOT_MAKEABLE: "Supplier blocked"}

# Reason code carried on a blocked row (owner-specified contract).
BLOCK_REASON = "no_supplier_can_make_this"
# ranking_engine has no SUPPLIER_BLOCKED action and is frozen, so a blocked row
# takes the existing SKIP action and is labelled distinctly for the view.
BLOCK_ACTION = "SKIP"
BLOCK_LABEL = LABELS[NOT_MAKEABLE]      # one literal, so the two cannot drift

# Action priorities, DUPLICATED here on purpose. This module must add ZERO new
# references to the frozen ranking files, so it does not import
# ranking_engine._PRI even read-only: an import is a dependency, and the freeze
# means "nothing new points at these files". The values mirror
# ranking_engine._PRI; if they ever diverge, the frozen file is authoritative and
# test_no_frozen_imports will not catch it, so keep this list short and stable.
_PRIORITY = {"BLOCKED": 0, "SKIP": 1, "WATCH": 2, "REVIEW": 3,
             "CONFIRM_FIRST": 4, "BUILD_NOW": 5}

_SNAP = {}


def _snapshot(path=None):
    """Read the supplier library ONCE per library state. Never raises.

    The inbox overlays this gate on ~1,500 rows; loading a CSV per row would turn
    one 25-row file read into 1,500 of them.
    """
    from src import supplier_ops as so
    p = str(path or so.DEFAULT_OUT)
    try:
        st = Path(p).stat()
        key = (p, st.st_mtime, st.st_size)
    except OSError:
        key = (p, 0, 0)
    hit = _SNAP.get(key)
    if hit is None:
        _SNAP.clear()                    # only ever keep the newest state
        hit = _SNAP[key] = _read_library(p)
    return hit


def _read_library(p):
    from src import supplier_ops as so
    try:
        rows = so.load_products(p) or []
    except Exception:  # noqa: BLE001 - unreadable library == unknown, never a block
        rows = []
    by_family, confirmed, stamps = {}, 0, []
    for r in rows:
        if (r.get("supplier_status") or "") == "SUPPLIER_CONFIRMED":
            confirmed += 1
        if (r.get("last_updated") or "").strip():
            stamps.append(r["last_updated"].strip())
        fam = _family(r.get("product_name"))
        if fam:
            by_family.setdefault(fam, []).append(r)
    try:
        registered = set(so.load_sources() or {})
    except Exception:  # noqa: BLE001
        registered = set()
    with_products = {(r.get("supplier_id") or "").strip() for r in rows if r.get("supplier_id")}
    missing = sorted(registered - with_products)
    if not rows:
        status = COV_NONE
    elif not missing and confirmed == len(rows):
        status = COV_COMPLETE
    else:
        status = COV_PARTIAL
    return {
        "by_family": by_family,
        "coverage": {
            "status": status, "products": len(rows), "confirmed": confirmed,
            "registered": sorted(registered), "with_products": sorted(with_products),
            "missing_sources": missing, "families": sorted(by_family),
            "last_updated": max(stamps) if stamps else None,
        },
    }


def coverage(path=None):
    """How far the supplier library can be trusted — the switch item F turns on.

    complete : every registered supplier has products AND every row reached
               SUPPLIER_CONFIRMED. Only here may a miss mean NOT_MAKEABLE.
    partial  : products exist, but a registered supplier has none or rows are
               still SUPPLIER_PARTIAL / NEED_SUPPLIER_DETAILS.
    unknown  : no products at all — the gate stays dormant.
    """
    return dict(_snapshot(path)["coverage"])


def has_supplier_library(path=None):
    """True when ANY supplier product exists. Gate stays dormant when false."""
    return _snapshot(path)["coverage"]["status"] != COV_NONE


def supplier_fit(keyword, mode=None, path=None):
    """MAKEABLE / NEEDS_SUPPLIER_CHECK / UNKNOWN / NOT_MAKEABLE. Never raises.

    Returns (verdict, detail) where detail always carries the owner's fields:
    product_family, supplier_source, coverage_status, last_updated, confidence.

    UNKNOWN whenever we genuinely cannot tell: no library, unreadable library,
    no keyword, or a keyword naming no product. A miss on an INCOMPLETE library
    is NEEDS_SUPPLIER_CHECK. NOT_MAKEABLE needs a complete library.
    """
    snap = _snapshot(path)
    cov = snap["coverage"]
    base = {"product_family": None, "supplier_source": None,
            "coverage_status": cov["status"], "last_updated": cov["last_updated"],
            "confidence": None}
    kw = (keyword or "").strip()
    if not kw:
        return UNKNOWN, dict(base, why="no keyword")
    if cov["status"] == COV_NONE:
        return UNKNOWN, dict(base, why="no supplier products imported yet")
    if not snap["by_family"]:
        # A library we cannot interpret is UNKNOWN, never a block.
        return UNKNOWN, dict(base, why="no supplier product type could be read")
    fam = _family(kw)
    if fam is None:
        # The keyword names an occasion, a theme or a phrase — not a product. We
        # cannot claim it is unmakeable, so the gate stays dormant.
        return UNKNOWN, dict(base, why="keyword names no recognisable product type")
    base["product_family"] = fam
    from src import supplier_ops as so
    hits = [r for r in snap["by_family"].get(fam, [])
            if so.mode_allows(mode, r.get("production_mode"))]
    if hits:
        ok = [r for r in hits
              if (r.get("supplier_status") or "") == "SUPPLIER_CONFIRMED"]
        pick = (ok or hits)[0]
        return MAKEABLE, dict(
            base, supplier_source=(pick.get("supplier_id") or "").strip() or None,
            supplier_product=pick.get("product_name"),
            # A SUPPLIER_PARTIAL row proves the supplier makes the product but
            # not that we know its cost or lead time — that is medium, not high.
            confidence="high" if ok else "medium")
    covered = sorted(snap["by_family"])
    if cov["status"] == COV_COMPLETE:
        return NOT_MAKEABLE, dict(base, covered=covered, confidence="high")
    return NEEDS_SUPPLIER_CHECK, dict(
        base, covered=covered, confidence="low",
        why=("supplier library is incomplete ("
             + (f"{len(cov['missing_sources'])} registered supplier(s) have no "
                "products on file" if cov["missing_sources"]
                else f"{cov['products'] - cov['confirmed']} row(s) not confirmed")
             + "), so 'no match' is a gap in our data, not a fact about the shop"))


def build_allowed(keyword, mode=None, path=None):
    """The ONE predicate every build-ish surface asks before letting work start:
    Pattern Miner, Build Queue, Launch Kit, Photo Plan, Team Ops build tasks.

    Returns (allowed: bool, info: dict). Advisory Pinterest is never consulted
    here — it cannot block anything by design. NEEDS_SUPPLIER_CHECK is a badge,
    not a block: only a COMPLETE library can produce the one verdict that stops
    work, so this returns True for every keyword until the library is finished.
    """
    fit, detail = supplier_fit(keyword, mode, path)
    if fit == NOT_MAKEABLE:
        return False, {"fit": fit, "reason": BLOCK_REASON, "revivable": True,
                       "label": LABELS[fit], "detail": detail,
                       "message": ("No supplier in your library can make this. "
                                   "Import or add a supplier, then it comes back "
                                   "automatically.")}
    msg = None
    if fit == NEEDS_SUPPLIER_CHECK:
        msg = ("Nothing in your supplier library makes this yet, but the library "
               "is incomplete — check with a supplier before building.")
    return True, {"fit": fit, "reason": None, "revivable": True,
                  "label": LABELS.get(fit, LABELS[UNKNOWN]),
                  "detail": detail, "message": msg}


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

    BADGE ONLY (owner's item E) while the library is incomplete: the row gains
    supplier_fit / supplier_label / build_allowed and NOTHING else changes. The
    engine's score is never touched, and the action only ever changes on the
    NOT_MAKEABLE verdict, which a partial library cannot produce. A row the
    engine already BLOCKED (trademark) stays as it is.
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
        row["reason_text"] = info["message"] or BLOCK_LABEL
        row["priority"] = _PRIORITY.get(BLOCK_ACTION, 1)
    return row


def summary(rows):
    """Counts for the workflow spine (step 3) and the Inbox badge line."""
    out = {MAKEABLE: 0, NEEDS_SUPPLIER_CHECK: 0, UNKNOWN: 0, NOT_MAKEABLE: 0}
    for r in rows or []:
        k = r.get("supplier_fit") or UNKNOWN
        out[k] = out.get(k, 0) + 1
    return out
