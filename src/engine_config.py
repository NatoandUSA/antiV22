"""Engine tunables (V30.1) - reviewer-requested: magic numbers out of code.

Reads config/engine.json (mtime-aware cache); every value has a safe default so
the file is optional. Edit config/engine.json on the server to tune WITHOUT a
restart - the cache reloads when the file's mtime changes (audit fix: the old
once-only cache silently ignored live edits until the service restarted).
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
    # Etsy-proof verdict thresholds - LIFETIME sold counts (Alura/EverBee).
    "proven_sold": 50,
    "strong_seller_sold": 20,
    "proven_min_shops": 2,
    # 24-HOUR sold bar (captures). V33 CEO consensus: noisy one-day estimates
    # can reach STRONG_SELLER at most - only LIFETIME sold mints PROVEN.
    "strong_seller_sold_24h": 8,
    # Monopoly cap: when ONE shop holds more than this share of the group's
    # listings, PROVEN/STRONG is capped at SELLING. (Raw HHI was reviewed and
    # rejected: a fair 2-shop split scores HHI 0.5 and would false-positive.)
    "monopoly_top_share": 0.7,
    # Fuzzy proof match: Jaccard >= high_conf allows the PROVEN -> BUILD override;
    # matches in [min_conf, high_conf) are "medium": they RAISE weak actions to
    # CONFIRM_FIRST and annotate (never overwrite) a merit-earned BUILD_NOW.
    "proof_match_min_conf": 0.34,
    "proof_match_high_conf": 0.50,
    # Young-winner definition (months).
    "young_winner_months": 12,
    # V37.5 Exact-Proof Loop (Phase B). Loop-verified EXACT-keyword listing
    # evidence may mint proof ONLY when this flag is on (default OFF -> ships dark,
    # zero ranking effect until the owner flips it; crosses the Evidence-Router/L4
    # separation, handoff §7.4). Bars mirror the Phase A capture lane.
    "exact_loop_proof_enabled": False,
    "exact_proof_min_shops": 2,       # distinct shops for exact multi-shop proof
    "exact_proof_min_listings": 3,    # exact-matching, selling, organic listings
    "exact_proof_min_sample": 5,      # listings pulled before the bar is evaluated
    "exact_proof_expire_days": 45,    # re-verify window; older -> capped to SELLING
    # WATCH lifecycle (V32): a WATCH row with no proof and no data refresh for
    # this many days is archived out of the main list (still reachable).
    "watch_expire_days": 30,
}

_cache = None
_cache_mtime = None


def get(key):
    global _cache, _cache_mtime
    try:
        mt = _PATH.stat().st_mtime
    except OSError:
        mt = None
    if _cache is None or mt != _cache_mtime:
        _cache = dict(DEFAULTS)
        _cache_mtime = mt
        try:
            _cache.update(json.loads(_PATH.read_text(encoding="utf-8")) or {})
        except Exception:  # noqa: BLE001 - config optional
            pass
    return _cache.get(key, DEFAULTS.get(key))
