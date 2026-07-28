"""Keyword Lab (V29) - generate a NEW keyword batch FROM the Pattern Miner output.

Runs AFTER Pattern Miner (per the spec): instead of random AI keywords, it expands
the WINNING pattern into fresh, buyer-specific long-tail keywords by (a) swapping the
core subject for adjacent buyer identities in the same niche, and (b) recombining the
mined tokens into [modifier] + [subject] + [product] + [occasion] long-tails. Every
candidate links back to the Inbox / Should-I-sell so it is RE-RANKED through the same
layered engine (risk gate -> market signal -> final action) - closing the loop.
"""
import re

from src import pattern_miner as pm
from src.product_fit import POD_NOUNS, JEWELRY_NOUNS, ACRYLIC_NOUNS

_PRODUCTS = POD_NOUNS | JEWELRY_NOUNS | ACRYLIC_NOUNS | {"crewneck", "quarter", "zip"}

# Adjacent buyer identities within a niche - the highest-value expansion, because a
# proven niche's neighbours usually convert too. Fallback is pure recombination.
_ADJACENT = {
    "nurse": ["er nurse", "icu nurse", "nicu nurse", "nurse practitioner",
              "nursing student", "labor and delivery nurse", "oncology nurse",
              "pediatric nurse", "rn graduation", "future nurse"],
    "teacher": ["kindergarten teacher", "special ed teacher", "science teacher",
                "math teacher", "preschool teacher", "reading teacher",
                "teacher appreciation", "future teacher"],
    "dog": ["dog mom", "dog dad", "rescue dog mom", "golden retriever mom",
            "french bulldog mom", "dog grandma"],
    "cat": ["cat mom", "cat dad", "crazy cat lady", "cat grandma"],
    "mom": ["dog mom", "cat mom", "boy mom", "girl mom", "new mom", "bonus mom",
            "soccer mom", "plant mom"],
    "dad": ["dog dad", "girl dad", "boy dad", "new dad", "fishing dad", "golf dad"],
    "golf": ["golf dad", "golf grandpa", "disc golf", "golf lover", "retired golfer"],
    "coach": ["baseball coach", "soccer coach", "football coach", "cheer coach"],
}
_OCCASIONS = ["gift", "birthday gift", "graduation gift", "christmas gift",
              "appreciation gift", "retirement gift"]
_MODIFIERS = ["personalized", "custom", "embroidered"]


def _subject(seed_words, keyword):
    """Subject PHRASE to expand on: up to the first TWO seed words that aren't
    product nouns or modifiers ('patchwork usa', not just 'usa') - a two-word
    niche keeps the generated long-tails specific instead of generic."""
    subs = []
    for w in seed_words:
        if w not in _PRODUCTS and w not in _MODIFIERS and len(w) > 2:
            subs.append(w)
        if len(subs) == 2:
            break
    if not subs:
        # V37.4 bug-fix: exclude _MODIFIERS here too (the seed path already does).
        # Without it, a modifier ("personalized"/"custom") leaked into the subject
        # and produced doubled-modifier junk like "personalized personalized name tote".
        toks = [w for w in re.findall(r"[a-z0-9]+", (keyword or "").lower())
                if w not in _PRODUCTS and w not in _MODIFIERS and len(w) > 2]
        subs = toks[:2]
    # keep the words in the order they appear in the original keyword when possible
    kw_order = re.findall(r"[a-z0-9]+", (keyword or "").lower())
    subs.sort(key=lambda w: kw_order.index(w) if w in kw_order else 99)
    return " ".join(subs) if subs else None


def _product(seed_words, keyword):
    # The keyword's OWN product noun wins over a pattern-derived one, so a search
    # for "nurse sweatshirt" builds sweatshirt candidates (crewneck / hoodie / tee /
    # tote are still offered separately as product swaps). Falling back to the
    # pattern's product only when the keyword names no product.
    for w in re.findall(r"[a-z0-9]+", (keyword or "").lower()) + list(seed_words):
        if w in _PRODUCTS:
            return "sweatshirt" if w in ("quarter", "zip") else w
    return "sweatshirt"


def generate(keyword=None, limit=14, mode=None):
    """Mine the pattern, then return {pattern, subject, product, candidates}.
    candidates = [{keyword, angle}] - fresh long-tails to push back into the Inbox.

    mode selects the material word: 'embroidered' for embroidery, nothing for POD
    (V37.4 fix — the old code forced 'embroidered' onto every candidate, which was
    wrong for a print-on-demand keyword)."""
    material = "embroidered " if (mode or "").lower().startswith("emb") else ""
    pat = pm.mine(keyword)
    seed = pat.get("seed_words") or []
    # A THIN pattern (fewer than 3 matched listings) is noise, not signal — one
    # stray listing must never steer the expansion into the wrong niche. Fall
    # back to the typed keyword itself as the subject/product source.
    if keyword and (pat.get("matched") or 0) < 3:
        seed = []
    subject = _subject(seed, pat.get("keyword") or keyword)
    product = _product(seed, pat.get("keyword") or keyword)
    cands, seen = [], set()

    def add(kw, angle):
        kw = re.sub(r"\s+", " ", kw).strip().lower()
        # long-tail only: 3+ words convert better with less competition (owner's
        # selling experience + eRank/seller consensus) - never emit short-tails.
        if kw and kw not in seen and len(kw.split()) >= 3:
            seen.add(kw)
            # bucket per the long-tail rule (CEO review): 4+ words with a real
            # angle can graduate to BUILD; 3-word terms are research/confirm.
            tag = ("\U0001F680 build-ready" if len(kw.split()) >= 4
                   else "\U0001F52C research (3 words - confirm first)")
            cands.append({"keyword": kw, "angle": f"{angle} · {tag}",
                          "bucket": "build" if len(kw.split()) >= 4 else "research"})

    # (a) adjacent buyer identities in the same niche -> product
    # (the phrase, else each word of it: 'nurse' inside 'er nurse' etc.)
    adj = _ADJACENT.get(subject, [])
    if not adj and subject:
        for w in subject.split():
            adj = _ADJACENT.get(w, [])
            if adj:
                break
    for a in adj:
        add(f"personalized {a} {material}{product}".replace("  ", " "),
            f"adjacent buyer: {a}")

    # (a1) V37.4 review-derived buyer-language long-tails from the Evidence Router.
    # Real buyer/recipient nouns (granddaughter, niece...) mined from Etsy reviews
    # of matching listings. Per CF006 these are CONFIRM_FIRST candidates: they
    # re-rank through the full engine like any other and never auto-build, even at
    # 4+ words. bucket forced to "research" so they are NOT pre-checked.
    ev = pat.get("review_evidence") or {}
    for rk in (ev.get("review_derived_keywords") or []):
        rk = re.sub(r"\s+", " ", str(rk)).strip().lower()
        if rk and rk not in seen and len(rk.split()) >= 3:
            seen.add(rk)
            cands.append({
                "keyword": rk, "bucket": "research",
                "angle": "review buyer language · \U0001F52C confirm first (review-derived)"})

    # (a2) competitor TAGS from the capture (HeyEtsy overlay): the winners'
    # actual Etsy tags, 3+ words only - real buyer language, not guesses
    for t, n_uses in (pat.get("top_tags") or [])[:10]:
        add(t, f"competitor tag ({n_uses} winning listings use it)")

    # (b) recombine the mined pattern into fresh long-tails. The leading modifier
    # is mode-aware: "embroidered" is only offered for an embroidery keyword, never
    # for POD (V37.4 fix — POD used to get a stray "embroidered <niche> <product>").
    gen_modifiers = ["personalized", "custom"] + (["embroidered"] if material else [])
    if subject:
        for m in gen_modifiers:
            add(f"{m} {subject} {product}", "pattern recombination")
        for occ in _OCCASIONS[:4]:
            add(f"{subject} {product} {occ}", f"occasion: {occ}")
        # product swaps keep the winning subject, open a new format
        for alt in ("crewneck", "hoodie", "t shirt", "tote bag"):
            if alt.split()[0] != product:
                add(f"personalized {subject} {material}{alt}".replace("  ", " "),
                    f"product swap: {alt}")

    # V37.4 safety screen: never SUGGEST a trademark-infringing long-tail. A
    # trademarked seed ("disney princess shirt") otherwise emits build-ready
    # infringing candidates (they'd be BLOCKED on re-rank, but must not be shown
    # as build-ready in the first place). Drop HIGH-trademark candidates here.
    tm_dropped = 0
    try:
        from src.trademark import check as _tmck
        kept = []
        for c in cands:
            if _tmck((c.get("keyword") or "").lower())[0] == "HIGH":
                tm_dropped += 1
                continue
            kept.append(c)
        cands = kept
    except Exception:  # noqa: BLE001 - screen is best-effort, never blocks the Lab
        pass
    return {"pattern": pat, "subject": subject, "product": product,
            "candidates": cands[:limit], "tm_dropped": tm_dropped}


# --------- close the loop: SAVE candidates into the master so the Inbox -----
# actually re-ranks them (before this, "re-rank" changed nothing because the
# generated keywords were never persisted anywhere).
def save_candidates(kws, mode=None, enrich=True, limit=14, source="keyword-lab"):
    """Append new keywords to keyword_data.csv (the master the Inbox ranks),
    tagged source=keyword-lab. Best-effort: fills market fields from the live
    YTrends MCP per keyword (skipped silently when the MCP is unreachable -
    honest nulls rank as WATCH until data arrives). Returns (added, enriched)."""
    import csv as _csv
    from datetime import date as _date
    from pathlib import Path as _Path
    path = _Path("keyword_data.csv")
    default_headers = ["keyword", "etsy_listings", "seller_count", "views_24h",
                       "avg_price", "avg_revenue", "conversion_rate", "momentum",
                       "tm_risk", "source", "collected_at"]
    headers, existing = default_headers, set()
    if path.is_file():
        try:
            with path.open(encoding="utf-8-sig") as fh:
                rd = _csv.reader(fh)
                headers = next(rd, default_headers) or default_headers
                ki = 0
                for i, h in enumerate(headers):
                    if "keyword" in str(h).lower():
                        ki = i
                        break
                for row in rd:
                    if len(row) > ki and row[ki]:
                        existing.add(row[ki].strip().lower())
        except Exception:  # noqa: BLE001
            pass
    added = enriched = 0
    new_rows = []
    # MCP enrich with a HARD per-keyword timeout + circuit breaker: one hung
    # network call must never freeze the save (audited: it did - 2min+ hang).
    from concurrent.futures import ThreadPoolExecutor
    _pool = ThreadPoolExecutor(max_workers=1) if enrich else None
    _fails = 0

    def _try_enrich(d):
        nonlocal _fails
        if _fails >= 2:                 # MCP unreachable - stop trying
            return False
        try:
            from src import shortlister_integration as si
            fut = _pool.submit(si._enrich_row, d, mode)
            ok = bool(fut.result(timeout=6))
            if not ok:
                _fails += 1
            else:
                _fails = 0
            return ok
        except Exception:  # noqa: BLE001 - timeout / network / import error
            _fails += 1
            return False

    for kw in (kws or [])[:limit]:
        kw = re.sub(r"\s+", " ", str(kw)).strip().lower()
        if not kw or kw in existing:
            continue
        existing.add(kw)
        d = {"tag": kw}
        if enrich and _try_enrich(d):
            enriched += 1
        vals = {
            "keyword": kw,
            "etsy_listings": d.get("listing_count", ""),
            "seller_count": d.get("seller_count", ""),
            "views_24h": d.get("views_24h", ""),
            "avg_price": d.get("avg_price", ""),
            "avg_revenue": d.get("revenue", ""),
            "conversion_rate": d.get("avg_conversion_rate", ""),
            "momentum": d.get("momentum_score", ""),
            "tm_risk": "",
            "source": source,
            "collected_at": _date.today().isoformat(),
        }
        new_rows.append([vals.get(str(h).strip().lower(), "") for h in headers])
        added += 1
    if new_rows:
        write_header = not path.is_file()
        with path.open("a", encoding="utf-8", newline="") as fh:
            w = _csv.writer(fh)
            if write_header:
                w.writerow(headers)
            w.writerows(new_rows)
    return added, enriched
