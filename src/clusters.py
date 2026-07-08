"""Group related keywords into product clusters — one product idea from many
similar keywords (e.g. summer pouch + travel pouch + bridesmaid pouch -> "pouch",
or chenille name bag + bridesmaid bag + transparent bag -> "bag").

Lightweight, no ML dependency. We key each keyword on the *product noun* it shares
with others (a bag, a mug, a shirt) so a cluster is "one product, many keywords".
When no product noun is shared, we fall back to the strongest shared theme token
(e.g. a "raccoon" design line). Keywords that share nothing stay individual.
"""
import re
from collections import Counter, defaultdict

# Modifiers / occasions / audiences — never a product on their own, so they must
# not become a cluster key (else "name necklace" + "name bag" wrongly merge).
STOP = {"a", "an", "the", "for", "with", "and", "of", "to", "in", "on", "your",
        "my", "custom", "customized", "personalized", "personalised", "gift",
        "gifts", "cute", "best", "new", "trendy", "unique", "handmade", "him",
        "her", "kids", "kid", "women", "womens", "men", "mens", "baby", "name",
        "monogram", "monogrammed", "matching", "family", "funny", "vintage",
        "retro", "cool", "little", "big", "set", "pack", "day", "birthday"}

# Real products we sell on (POD / embroidery / jewelry / acrylic). A shared token
# from this set always wins the cluster key — that is the "one product idea".
PRODUCT_NOUNS = {
    "shirt", "tshirt", "tee", "hoodie", "sweatshirt", "sweater", "tank", "jacket",
    "onesie", "bodysuit", "romper", "bib", "dress", "legging", "leggings", "pajama",
    "bag", "tote", "pouch", "backpack", "purse", "clutch", "wallet", "cosmetic",
    "mug", "tumbler", "cup", "bottle", "flask", "glass", "coaster", "koozie",
    "blanket", "pillow", "cushion", "towel", "apron", "mat", "rug", "doormat",
    "flag", "banner", "sign", "poster", "print", "canvas", "frame", "tapestry",
    "decal", "sticker", "ornament", "candle", "magnet", "keychain", "keyring",
    "necklace", "bracelet", "earring", "ring", "charm", "pendant", "pin", "brooch",
    "hat", "cap", "beanie", "sock", "bandana", "scarf", "glove", "mitten",
    "patch", "notebook", "journal", "planner", "card", "invitation", "board",
    "sweatpant", "short", "robe", "slipper", "spatula", "cuttingboard",
}


def _sing(w):
    """Crude singular: drop a trailing 's' so decals->decal, mugs->mug."""
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


def _tokens(kw):
    return [w for w in re.findall(r"[a-z0-9]+", (kw or "").lower())
            if w not in STOP and len(w) > 2]


def _key_for(toks, freq):
    """Pick the cluster key for one keyword: a shared product noun if it has one,
    else the strongest shared theme token. None if it shares nothing."""
    shared = [t for t in toks if freq[_sing(t)] >= 2]
    if not shared:
        return None
    products = [t for t in shared if _sing(t) in PRODUCT_NOUNS]
    pool = products or shared
    # highest cross-keyword frequency wins; tie-break on the longer, more specific word
    return _sing(max(pool, key=lambda t: (freq[_sing(t)], len(t))))


def cluster(keywords, min_size=2):
    """Return (clusters, singles). Each cluster: {name, primary, members, size}.

    `name` is the shared product noun/theme (the product idea); `primary` is the
    shortest member, a good base title to model the single listing on.
    """
    kws = sorted({(k or "").strip().lower() for k in keywords if (k or "").strip()})
    freq = Counter()
    for k in kws:
        freq.update({_sing(t) for t in _tokens(k)})
    groups, singles = defaultdict(list), []
    for k in kws:
        key = _key_for(_tokens(k), freq)
        if key:
            groups[key].append(k)
        else:
            singles.append(k)
    clusters = []
    for key, members in groups.items():
        if len(members) >= min_size:
            clusters.append({"name": key, "primary": min(members, key=len),
                             "members": sorted(members), "size": len(members)})
        else:
            singles.extend(members)
    clusters.sort(key=lambda c: -c["size"])
    return clusters, sorted(set(singles))
