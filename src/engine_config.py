"""Engine tunables (V30.1) - reviewer-requested: magic numbers out of code.

Reads config/engine.json once (cached); every value has a safe default so the
file is optional. Edit config/engine.json on the server to tune without a deploy.
"""
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "config" / "engine.json"

DEFAULTS = {
    # FX: VND per USD for price-band normalisation (refresh quarterly).
    "vnd_per_usd": 25000.0,
    # Owner's long-tail rule: heuristic BUILD_NOW needs at least this many words
    # ("more than 3 words"); 3-word terms are borderline -> CONFIRM_FIRST.
    "long_tail_min_words": 4,
    # Short-tail hard cap: <= this many words always routes via Pattern Miner.
    "short_tail_max_words": 2,
    # Etsy-proof verdict thresholds.
    "proven_sold": 50,
    "strong_seller_sold": 20,
    "proven_min_shops": 2,
    # Fuzzy proof match: Jaccard >= high_conf allows the PROVEN -> BUILD override;
    # matches in [min_conf, high_conf) are "medium" and cap at CONFIRM_FIRST.
    "proof_match_min_conf": 0.34,
    "proof_match_high_conf": 0.50,
    # Young-winner definition (months).
    "young_winner_months": 12,
}

_cache = None


def get(key):
    global _cache
    if _cache is None:
        _cache = dict(DEFAULTS)
        try:
            _cache.update(json.loads(_PATH.read_text(encoding="utf-8")) or {})
        except Exception:  # noqa: BLE001 - config optional
            pass
    return _cache.get(key, DEFAULTS.get(key))
