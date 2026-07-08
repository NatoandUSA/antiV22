"""Group related keywords into product clusters — one product idea from many
similar keywords (e.g. summer pouch + travel pouch + bridesmaid pouch -> "pouch").

Lightweight token-based grouping, no ML dependency. A cluster is keywords that
share a dominant content token; the rest stay as individual ideas.
"""
import re
from collections import Counter, defaultdict

STOP = {"a", "an", "the", "for", "with", "and", "of", "to", "in", "on", "your",
        "my", "custom", "customized", "personalized", "personalised", "gift",
        "gifts", "cute", "best", "new", "trendy", "unique", "handmade", "him",
        "her", "kids", "women", "men"}


def _tokens(kw):
    return [w for w in re.findall(r"[a-z0-9]+", (kw or "").lower())
            if w not in STOP and len(w) > 2]


def cluster(keywords, min_size=2):
    """Return (clusters, singles). Each cluster: {name, primary, members, size}."""
    kws = sorted({(k or "").strip().lower() for k in keywords if (k or "").strip()})
    freq = Counter()
    for k in kws:
        freq.update(set(_tokens(k)))
    groups, singles = defaultdict(list), []
    for k in kws:
        shared = [(t, freq[t]) for t in _tokens(k) if freq[t] >= 2]
        if shared:
            groups[max(shared, key=lambda x: x[1])[0]].append(k)
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
