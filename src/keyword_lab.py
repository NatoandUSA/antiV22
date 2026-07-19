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
    """Best single 'subject' token to expand on: the first seed word that isn't a
    product noun or a modifier, else fall back to the keyword's first strong word."""
    for w in seed_words:
        if w not in _PRODUCTS and w not in _MODIFIERS and len(w) > 2:
            return w
    toks = [w for w in re.findall(r"[a-z0-9]+", (keyword or "").lower())
            if w not in _PRODUCTS and len(w) > 2]
    return toks[0] if toks else None


def _product(seed_words, keyword):
    for w in list(seed_words) + re.findall(r"[a-z0-9]+", (keyword or "").lower()):
        if w in _PRODUCTS:
            return "sweatshirt" if w in ("quarter", "zip") else w
    return "sweatshirt"


def generate(keyword=None, limit=14):
    """Mine the pattern, then return {pattern, subject, product, candidates}.
    candidates = [{keyword, angle}] - fresh long-tails to push back into the Inbox."""
    pat = pm.mine(keyword)
    seed = pat.get("seed_words") or []
    subject = _subject(seed, pat.get("keyword") or keyword)
    product = _product(seed, pat.get("keyword") or keyword)
    cands, seen = [], set()

    def add(kw, angle):
        kw = re.sub(r"\s+", " ", kw).strip().lower()
        # long-tail only: 3+ words convert better with less competition (owner's
        # selling experience + eRank/seller consensus) - never emit short-tails.
        if kw and kw not in seen and len(kw.split()) >= 3:
            seen.add(kw)
            cands.append({"keyword": kw, "angle": angle})

    # (a) adjacent buyer identities in the same niche -> product
    adj = _ADJACENT.get(subject, [])
    for a in adj:
        add(f"personalized {a} embroidered {product}", f"adjacent buyer: {a}")

    # (b) recombine the mined pattern into fresh long-tails
    if subject:
        for m in _MODIFIERS:
            add(f"{m} {subject} {product}", "pattern recombination")
        for occ in _OCCASIONS[:4]:
            add(f"{subject} {product} {occ}", f"occasion: {occ}")
        # product swaps keep the winning subject, open a new format
        for alt in ("crewneck", "hoodie", "t shirt", "tote bag"):
            if alt.split()[0] != product:
                add(f"personalized {subject} embroidered {alt}", f"product swap: {alt}")

    return {"pattern": pat, "subject": subject, "product": product,
            "candidates": cands[:limit]}
