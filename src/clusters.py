"""Group related keywords into product clusters — one product idea from many
similar keywords (e.g. summer pouch + travel pouch + bridesmaid pouch -> "pouch",
or chenille name bag + bridesmaid bag + transparent bag -> "bag").

Lightweight, no ML dependency. We key each keyword on the *product noun* it shares
with others (a bag, a mug, a shirt) so a cluster is "one product, many keywords".
When no product noun is shared, we fall back to the strongest shared theme token
(e.g. a "raccoon" design line). Keywords that share nothing stay individual.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

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


# ---- V28: enrich a raw cluster into a sellable "opportunity cluster" ----------
# Descriptive vocab used only to LABEL a cluster (occasion / style / audience /
# personalization). It never affects grouping — that stays product-noun based.
OCCASIONS = {"summer", "winter", "spring", "fall", "autumn", "christmas", "xmas",
             "halloween", "thanksgiving", "easter", "valentine", "valentines",
             "birthday", "wedding", "bridal", "bridesmaid", "anniversary",
             "graduation", "retirement", "baby", "shower", "vacation", "travel",
             "holiday", "gameday", "school", "reunion"}
AUDIENCES = {"mom", "dad", "mama", "papa", "grandma", "grandpa", "nana", "nurse",
             "teacher", "sister", "brother", "wife", "husband", "daughter", "son",
             "bride", "groom", "coworker", "boss", "friend", "women", "men",
             "kids", "toddler", "dog", "cat", "golfer", "gamer"}
STYLES = {"retro", "vintage", "boho", "minimalist", "coastal", "western",
          "cottagecore", "aesthetic", "funny", "cute", "floral", "abstract",
          "modern", "classic", "groovy", "y2k"}
PERSONALIZATION = {"name", "monogram", "monogrammed", "custom", "customized",
                   "personalized", "personalised", "initial", "initials", "photo",
                   "date"}

DISCOVERY_FILE = Path("data/discovery/opportunity_clusters.json")


def _desc_tokens(members):
    toks = []
    for m in members:
        toks += re.findall(r"[a-z0-9]+", (m or "").lower())
    return toks


def _first_in(tokens, vocab):
    return next((t for t in tokens if t in vocab), "")


def enrich_cluster(c, mode=None):
    """Turn a raw {name, primary, members, size} cluster into a sellable opportunity
    cluster: readable name, product mode/type, descriptive fields, and a next action.

    Market/profit SCORES are deliberately left null (status 'pending'). They are
    filled by the live market + supplier + private-learning pipeline — this function
    never fabricates a demand/competition/profit number it hasn't actually measured.
    """
    from src import product_fit as pf
    members = c.get("members", [])
    toks = _desc_tokens(members)
    product = _sing(c.get("name", ""))
    fit = pf.classify(c.get("primary") or product, mode)
    pm = mode if mode in ("pod", "embroidery") else (
        "embroidery" if fit.get("product_type") == "embroidery" else "pod")
    occasion = _first_in(toks, OCCASIONS)
    style = _first_in(toks, STYLES)
    audience = _first_in(toks, AUDIENCES)
    personalization = "yes" if set(toks) & PERSONALIZATION else "optional"
    # human, sellable name: "Personalized [Occasion] [Style] <Product>"
    parts = ["Personalized"] + [w.title() for w in (occasion, style) if w] + \
            [product.title()]
    cluster_name = " ".join(dict.fromkeys(p for p in parts if p))
    slug_seed = "-".join(x for x in (product, occasion or style,
                                     members[0] if members else "") if x)
    cid = "cl_" + (re.sub(r"[^a-z0-9]+", "-", slug_seed.lower()).strip("-") or "cluster")
    return {
        "cluster_id": cid,
        "cluster_name": cluster_name,
        "primary_keyword": c.get("primary", ""),
        "related_keywords": members,
        "product_mode": pm,
        "product_type": product,
        "target_customer": audience or "everyday & gift buyers",
        "occasion": occasion,
        "style": style,
        "personalization_fit": personalization,
        "supplier_match": "",
        "supplier_status": "PENDING_SUPPLIER_CHECK",
        "avg_price": None,
        "estimated_profit": None,
        # Market scores come from the live pipeline; never faked here.
        "demand_score": None, "competition_score": None, "trend_score": None,
        "profit_score": None, "can_we_win_score": None,
        "launch_readiness_score": None, "private_learning_score": None,
        "scores_status": "pending — run market + supplier research to fill",
        "verdict": "NEEDS_RESEARCH",
        "next_action": "Assign supplier check + competitor audit",
        "reason_shown": f"{c.get('size', len(members))} related keywords share the "
                        f"product '{product}' — one listing can capture them all.",
        "size": c.get("size", len(members)),
    }


def build_opportunity_clusters(keywords, mode=None, min_size=2):
    """(enriched_clusters, singles) — sellable clusters first, loose keywords second."""
    raw, singles = cluster(keywords, min_size=min_size)
    return [enrich_cluster(c, mode) for c in raw], singles


def save_clusters(clusters, path=DISCOVERY_FILE):
    """Persist enriched clusters to data/discovery/opportunity_clusters.json."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "count": len(clusters), "clusters": clusters}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
