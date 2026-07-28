"""Etsy Proof layer (V30, spec layer L1) - rank by REAL Etsy sales evidence.

The strongest signal a niche will sell isn't modelled search volume - it's listings
that are ALREADY selling on Etsy. This lane ingests a product-research CSV exported
from Alura (Product Research) or EverBee (Product Analytics / Shop Analyzer) - real
per-listing units sold, revenue, price, listing AGE, and reviews - aggregates it by
keyword, and produces an Etsy-Proof verdict that sits ABOVE the market-signal score:

    etsy_proof_score = sold_rank*0.45 + revenue_rank*0.25
                     + shop_spread_rank*0.20 + young_winner_rank*0.10   (spec formula)

    PROVEN_WINNER : real sales, spread across 2+ shops (winnable, not monopolised)
    SELLING       : real sales but thin spread (check monopoly)
    YOUNG_WINNER   flag: newer listings (< ~12 months) already selling = beatable market

Honest limits: this needs the paid product-export (Alura Professional / EverBee);
until one is dropped in, the lane is simply empty and the engine falls back to the
market-signal layer. Nothing here is faked - no export, no proof.
"""
import csv
import json
import re
import statistics as _stats
from pathlib import Path

from src import supplier_trend as st
from src.engine_config import get as _cfg

PROOF_DIR = Path("data/imports/etsy_proof")


def _proven_sold():
    return float(_cfg("proven_sold"))


def _strong_sold():
    return float(_cfg("strong_seller_sold"))


def _strong_sold24():
    return float(_cfg("strong_seller_sold_24h"))


def _min_shops():
    return int(_cfg("proven_min_shops"))


def _young_months():
    return int(_cfg("young_winner_months"))


def _cfg_bool(key):
    return str(_cfg(key)).strip().lower() in ("1", "true", "yes", "on")


def _merge_loop_proof(out, mode=None):
    """V37.5 Phase B: merge loop-verified EXACT-keyword proof into the proof map,
    ONLY when exact_loop_proof_enabled is on. Default-off => returns out unchanged,
    so build_proof() behaves exactly as before. Called on BOTH build_proof return
    paths (including the no-export early return), so loop proof works even for a
    shop with no Alura/EverBee export yet."""
    try:
        if not _cfg_bool("exact_loop_proof_enabled"):
            return out
        from src import feed_evidence_router as _fer
        for ev in _fer.all_focus_evidence():
            rec = exact_proof_from_loop(ev, mode)
            if not rec:
                continue
            c = _canon(rec["keyword"])
            if not c:
                continue
            cur = out.get(c)
            if cur is None or (_VERDICT_RANK.get(rec["verdict"], 0)
                               >= _VERDICT_RANK.get(cur.get("verdict"), 0)):
                out[c] = rec           # exact loop proof wins ties (it's exact)
    except Exception:  # noqa: BLE001 - loop proof is additive, never breaks build_proof
        pass
    return out


def _num(v):
    if v is None:
        return None
    s = str(v).strip().lower().replace(",", "").replace("$", "").replace("€", "")
    if not s or s in ("-", "n/a", "lock", "locked"):
        return None
    mult = 1.0
    if s.endswith("k"):
        mult, s = 1000.0, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000.0, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _age_months(v):
    """'3y 4m' / '140 Mo.' / '7y 0m' / '18 months' -> total months, or None."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    yrs = re.search(r"(\d+)\s*y", s)
    mos = re.search(r"(\d+)\s*m", s)
    total = 0
    got = False
    if yrs:
        total += int(yrs.group(1)) * 12
        got = True
    if mos:
        total += int(mos.group(1))
        got = True
    if not got:
        n = re.search(r"(\d+)", s)
        if n:
            total = int(n.group(1))         # bare number of months (EverBee '140 Mo.')
            got = True
    return total if got else None


def _ci(headers, *needles, exclude=()):
    for i, h in enumerate(headers):
        hl = str(h).lower()
        if any(n in hl for n in needles) and not any(x in hl for x in exclude):
            return i
    return None


def _read_csv(path):
    try:
        rows = list(csv.reader(Path(path).open(encoding="utf-8-sig")))
    except Exception:  # noqa: BLE001
        return [], []
    if not rows:
        return [], []
    return rows[0], rows[1:]


def rows_from_export(headers, data, mode=None):
    """Map an Alura/EverBee product-export table to per-listing proof rows:
    {keyword, title, shop, sold, revenue, price, age_months, reviews}."""
    H = [str(h).lower() for h in headers]
    ti = _ci(H, "title", "product", "name", "listing", exclude=("shop", "seller"))
    if ti is None:
        return []
    # LIFETIME sold first (he_sold from overlay captures) - the generic 'sold'
    # needle used to grab sold_24h by column order and shrink proof 100x.
    si = _ci(H, "he_sold", "total sales", "sales", "sold", "orders",
             exclude=("revenue", "$", "24h", "24 h", "shop_daily"))
    ri = _ci(H, "he_revenue", "revenue", exclude=())
    pi = _ci(H, "price", exclude=("was",))
    shi = _ci(H, "shop", "seller", exclude=("id",))
    ai = _ci(H, "age_days", "age (days)", "age")
    revi = _ci(H, "review", "rating", exclude=())
    out = []
    for r in data:
        def c(i):
            return r[i] if (i is not None and i < len(r)) else None
        title = str(c(ti) or "").strip()
        if not title:
            continue
        kw = st.extract_keyword(title, mode).get("keyword")
        if not kw:
            continue
        out.append({
            "keyword": kw, "title": title, "shop": (c(shi) or "").strip(),
            "sold": _num(c(si)), "revenue": _num(c(ri)), "price": _num(c(pi)),
            "age_months": _age_months(c(ai)), "reviews": _num(c(revi)),
        })
    return out


def save_export(headers, data, mode=None, source="alura"):
    """Persist a product export as proof rows for the ranker. Returns count saved."""
    rows = rows_from_export(headers, data, mode)
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"source": source, "count": len(rows), "rows": rows}
    (PROOF_DIR / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def save_export_file(path, mode=None, source="alura"):
    headers, data = _read_csv(path)
    return save_export(headers, data, mode, source)


def _latest_rows():
    p = PROOF_DIR / "latest.json"
    if not p.is_file():
        return []
    try:
        return (json.loads(p.read_text(encoding="utf-8")) or {}).get("rows") or []
    except Exception:  # noqa: BLE001
        return []


# --------- proof from FREE captures (extension -> data/imports/etsy_spy) -----
# Etsy-search captures (HeyEtsy overlay he_sold / he_revenue), ytuong.me Hot
# cards (sold_24h) and YTrends Spy tables (SOLD 24H + CONVERSION + AGE (DAYS))
# all carry REAL per-listing sales evidence - so they light the proof tier too,
# not just the paid Alura/EverBee export. Sold figures here are RECENT sales
# (24h / overlay window), labelled as such; age comes from AGE (DAYS) when the
# capture has it (the young-winner signal).
CAPTURE_DIR = Path("data/imports/etsy_spy")
_CAPTURE_MAX_FILES = 12


def _capture_rows(mode=None):
    """Fresh window: newest <= 12 capture files (Pattern-Miner freshness)."""
    d = CAPTURE_DIR
    if not d.is_dir():
        return []
    files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime,
                   reverse=True)[:_CAPTURE_MAX_FILES]
    return _rows_from_files(files, mode)


def _rows_from_files(files, mode=None):
    seen = {}
    for f in files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        H = [str(h).lower() for h in (payload.get("headers") or [])]
        ti = _ci(H, "title", "product", "name")
        if ti is None:
            ti = _ci(H, "listing", exclude=("id",))
        if ti is None:
            continue
        shi = _ci(H, "shop", "seller", exclude=("id",))
        # sold: overlay lifetime-ish (he_sold) or recent 24h (sold_24h / SOLD 24H)
        si = _ci(H, "he_sold")
        s24 = _ci(H, "sold_24h", "sold 24h")
        ri = _ci(H, "he_revenue", "revenue", exclude=("id",))
        agi = _ci(H, "age (days)", "age_days")
        ui = _ci(H, "url", "link")
        idi = _ci(H, "listing_id", "listing id")
        for row in (payload.get("rows") or []):
            def c(i):
                return row[i] if (i is not None and i < len(row)) else None
            title = str(c(ti) or "").strip()
            if not title:
                continue
            kw = st.extract_keyword(title, mode).get("keyword")
            if not kw:
                continue
            sold = _num(c(si))
            recent = False                     # True = the figure is a 24h count
            if sold in (None, 0):
                s2 = _num(c(s24))
                if s2 is not None:
                    sold, recent = s2, True
            age_days = _num(c(agi))
            key = str(c(idi) or c(ui) or title.lower())
            rec = {
                "key": key,
                "keyword": kw, "title": title, "shop": (str(c(shi) or "")).strip(),
                "sold": sold, "recent": recent, "revenue": _num(c(ri)),
                "price": None,
                # audit fix: age 0 days (listed TODAY) is real data, not missing -
                # `if age_days` dropped the strongest young-winner signal
                "age_months": (age_days / 30.0) if age_days is not None else None,
                "reviews": None,
            }
            old = seen.get(key)
            if old is None or (rec["sold"] or 0) > (old["sold"] or 0):
                seen[key] = rec
    return list(seen.values())


def _ledger_paths():
    return (CAPTURE_DIR / "_proof_ledger.jsonl",
            CAPTURE_DIR / "_ledger_seen.jsonl")


def _ledger_update():
    """Append normalized proof rows from capture files not yet ingested.
    Durable L1: once a capture carried sales evidence, it stays in the proof
    base even after the file rotates out of the newest-12 fresh window."""
    if not CAPTURE_DIR.is_dir():
        return
    lp, sp = _ledger_paths()
    try:
        seen = set(json.loads(sp.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        seen = set()
    new_files = [f for f in sorted(CAPTURE_DIR.glob("*.json"))
                 if f.name not in seen]
    if not new_files:
        return
    from datetime import date as _d
    rows = _rows_from_files(new_files)
    try:
        with lp.open("a", encoding="utf-8") as fh:
            for r in rows:
                if not (r.get("sold") or r.get("revenue")):
                    continue                    # ledger keeps SALES evidence only
                r2 = dict(r)
                r2["captured_at"] = _d.today().isoformat()
                fh.write(json.dumps(r2, ensure_ascii=False) + "\n")
        seen.update(f.name for f in new_files)
        sp.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except OSError:
        pass


def _ledger_rows(mode=None):
    """All-time proof rows from the ledger, deduped by listing key (latest
    snapshot wins). Keyword re-extracted per mode at read time."""
    lp, _ = _ledger_paths()
    if not lp.is_file():
        return []
    best = {}
    try:
        with lp.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                k = str(r.get("key") or "").lower() or (r.get("title") or "").lower()
                if k:
                    best[k] = r                 # later lines = newer snapshots
    except OSError:
        return []
    out = []
    for r in best.values():
        kw = st.extract_keyword(r.get("title") or "", mode).get("keyword")
        if kw:
            r["keyword"] = kw
            out.append(r)
    return out


def _canon(kw):
    return " ".join(sorted(set(
        st._singular(w) for w in re.findall(r"[a-z0-9]+", (kw or "").lower())
        if len(w) > 1)))


def _pct(vals):
    """Midrank percentile (audit fix): ties get the tie's MIDDLE rank, not its
    maximum - so an all-zero column scores 50 everywhere instead of handing
    every zero-sales row a perfect 100."""
    s = sorted(v for v in vals if v is not None)
    if not s:
        return lambda x: None

    def f(x):
        if x is None:
            return None
        less = sum(1 for v in s if v < x)
        eq = sum(1 for v in s if v == x)
        return 100.0 * (less + 0.5 * eq) / len(s)
    return f


def build_proof(mode=None):
    """Aggregate the latest product export into a {canon_keyword: proof} map.

    proof = {keyword, sold, revenue, shops, listings, young, score, verdict,
    evidence}. Empty dict when no export is present (engine then uses market signal)."""
    # Cross-SOURCE dedup (audit fix): the same listing present in BOTH the
    # Alura/EverBee export and an extension capture used to be summed twice -
    # 30 sold became 60 and crossed the PROVEN bar on one listing's evidence.
    # Key on normalized title + shop; first source wins (export loads first).
    _ledger_update()
    _seen_x, _seen_key = set(), set()
    rows = []
    # priority: latest export > fresh captures > durable ledger history - the
    # ledger keeps proof ALIVE when old captures rotate out of the fresh window
    # (V33 CEO fix: a PROVEN niche must never vanish because 13 newer spy files
    # arrived). Primary dedup key = listing id/url; fallback title+shop.
    _all_rows = _latest_rows() + _capture_rows(mode) + _ledger_rows(mode)
    for r in _all_rows:
        k1 = str(r.get("key") or "").strip().lower()
        xk = (_canon(r.get("title") or r.get("keyword")),
              (r.get("shop") or "").strip().lower())
        if k1:
            # keyed rows (listing id/url): dedup by KEY, plus against any
            # earlier keyless row of the same title+shop (the same listing seen
            # via an export). Distinct keys never collapse - one shop's title
            # variants are separate listings (CEO review #10 refinement).
            if k1 in _seen_key or xk in _seen_x:
                continue
            _seen_key.add(k1)
        else:
            if xk in _seen_x:
                continue
            _seen_x.add(xk)
        rows.append(r)
    if not rows:
        return _merge_loop_proof({}, mode)   # loop proof still applies w/o exports
    agg = {}
    for r in rows:
        c = _canon(r["keyword"])
        if not c:
            continue
        a = agg.setdefault(c, {"keyword": r["keyword"], "sold": 0.0, "sold24": 0.0,
                               "revenue": 0.0, "shops": {}, "listings": 0,
                               "young": 0})
        if len(r["keyword"]) < len(a["keyword"]):
            a["keyword"] = r["keyword"]
        # UNIT SPLIT (audit fix): 24-hour sold counts and lifetime sold counts
        # are different units - never sum them into one figure judged by one bar.
        if r.get("recent"):
            a["sold24"] += r["sold"] or 0
        else:
            a["sold"] += r["sold"] or 0
        a["revenue"] += r["revenue"] or 0
        a["listings"] += 1
        if r["shop"]:
            sh = r["shop"].lower()
            a["shops"][sh] = a["shops"].get(sh, 0) + 1
        if (r["age_months"] is not None and r["age_months"] <= _young_months()
                and (r["sold"] or 0) > 0):
            a["young"] += 1

    recs = list(agg.values())
    # spread = distinct shops when shop data exists; when the export has NO shop
    # column we only know listing count, which is NOT a monopoly signal - so we
    # track shops_known and never award PROVEN on listing-count alone.
    #
    # HONEST-NULLS on the score too (CPA fix): a component whose source column is
    # entirely absent must be EXCLUDED and the remaining weights renormalised -
    # otherwise pr_spread over all-zero shops pays a uniform +20 to every niche
    # (inflated absolute scores, e.g. 95/100 on a two-column export).
    has_shop_data = any(r.get("shop") for r in rows)
    has_age_data = any(r.get("age_months") is not None for r in rows)
    pr_sold = _pct([a["sold"] + a["sold24"] for a in recs])
    pr_rev = _pct([a["revenue"] for a in recs])
    pr_spread = _pct([len(a["shops"]) for a in recs])
    pr_young = _pct([a["young"] for a in recs])
    weights = [("sold", 0.45), ("rev", 0.25)]
    if has_shop_data:
        weights.append(("spread", 0.20))
    if has_age_data:
        weights.append(("young", 0.10))
    wtot = sum(w for _, w in weights)
    out = {}
    for c, a in agg.items():
        shops = len(a["shops"])
        shops_known = shops > 0
        comp = {"sold": pr_sold(a["sold"] + a["sold24"]) or 0,
                "rev": pr_rev(a["revenue"]) or 0,
                "spread": pr_spread(shops) or 0,
                "young": pr_young(a["young"]) or 0}
        score = round(sum(comp[k] * w for k, w in weights) / wtot, 1)
        # Separate bars per unit: lifetime sold vs 24-hour sold. A niche moving
        # 20+ units in a single day is proven demand even with zero lifetime data.
        s_life, s_24 = a["sold"], a["sold24"]
        spread_ok = shops_known and shops >= _min_shops()
        # V33 CEO consensus: noisy 24h estimates NEVER mint PROVEN - lifetime
        # sold is the only PROVEN signal; a 24h spike reaches STRONG_SELLER max.
        if s_life >= _proven_sold() and spread_ok:
            verdict = "PROVEN_WINNER"          # real sales AND spread across shops
        elif (s_life >= _strong_sold() or s_24 >= _strong_sold24()) and spread_ok:
            verdict = "STRONG_SELLER"          # solid sales + spread, below PROVEN bar
        elif s_life + s_24 > 0:
            verdict = "SELLING"                # sells, but spread unknown/monopolised
        else:
            verdict = "LISTED"
        # Monopoly cap: if ONE shop holds most of the group's listings, spread
        # is an illusion - cap PROVEN/STRONG down to SELLING. (Top-share test,
        # not raw HHI: an even 2-shop split is competition, not monopoly.)
        if shops_known and verdict in ("PROVEN_WINNER", "STRONG_SELLER"):
            tot_l = sum(a["shops"].values()) or 1
            if max(a["shops"].values()) / tot_l > float(_cfg("monopoly_top_share")):
                verdict = "SELLING"
        out[c] = {
            "keyword": a["keyword"], "sold": s_life, "sold_24h": s_24,
            "revenue": a["revenue"],
            "shops": shops, "shops_known": shops_known, "listings": a["listings"],
            "young": a["young"], "score": score, "verdict": verdict,
            "young_winner": a["young"] >= 2,
            "evidence": _evidence(s_life, a["revenue"], shops, shops_known,
                                  a["listings"], a["young"], sold24=s_24),
        }
    return _merge_loop_proof(out, mode)


def _short(n):
    n = float(n or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return f"{n:.0f}"


def _evidence(sold, revenue, shops, shops_known, listings, young, sold24=0):
    bits = []
    if sold:
        bits.append(f"{int(sold)} sold")
    if sold24:
        bits.append(f"{int(sold24)} sold/24h")
    if revenue:
        bits.append(f"${_short(revenue)}")
    if shops_known and shops:
        bits.append(f"{int(shops)} shop(s)")
    elif listings:
        bits.append(f"{int(listings)} listing(s)")   # shop data absent - not spread
    if young:
        bits.append(f"{int(young)} young winner(s)")
    return " · ".join(bits) or "listed, no sales data"


_PROOF_PRODUCT = {"sweatshirt", "crewneck", "hoodie", "tshirt", "tee", "shirt",
                  "necklace", "bracelet", "ring", "mug", "tumbler", "tote", "bag",
                  "hat", "cap", "blanket", "pillow", "sign", "decal", "sticker"}
# Words that describe HOW/WHAT-KIND, not WHICH niche - a match can't rest on these.
_PROOF_GENERIC = {"personalized", "personalised", "custom", "customized", "embroidered",
                  "embroidery", "monogram", "monogrammed", "gift", "name", "custom",
                  "cute", "cozy", "matching", "set"}


def proof_for(keyword, proof_map):
    """Look up proof for a keyword, tolerating phrasing differences between the
    inbox keyword ('personalized nurse sweatshirt') and the extracted proof keyword
    ('nurse embroidery sweatshirt'). Requires a shared SUBJECT token (a niche word
    that isn't just a product noun or a generic modifier) so a broad term like
    'embroidered sweatshirt' can't hijack a specific niche's proof."""
    if not proof_map:
        return None
    c = _canon(keyword)
    kt = set(c.split())
    if len(kt) < 2:
        return None
    if c in proof_map:
        # exact canonical match -> full confidence (the PROVEN override may fire)
        return dict(proof_map[c], match="exact", match_confidence=1.0)
    best, best_score = None, 0.0
    for pc, p in proof_map.items():
        pt = set(pc.split())
        ov = kt & pt
        if len(ov) < 2:
            continue
        # the overlap must include a real SUBJECT word (not just product/modifier),
        # and share a product noun or be a subset relationship
        subject = ov - _PROOF_PRODUCT - _PROOF_GENERIC
        if not subject:
            continue
        if not (ov & _PROOF_PRODUCT or kt <= pt or pt <= kt):
            continue
        j = len(ov) / len(kt | pt)
        if j > best_score:
            best, best_score = p, j
    if best_score >= float(_cfg("proof_match_min_conf")):
        # fuzzy match -> carry the confidence; decide() only allows the PROVEN ->
        # BUILD override at high confidence, medium caps at CONFIRM_FIRST.
        return dict(best, match="fuzzy", match_confidence=round(best_score, 2))
    return None


_VERDICT_RANK = {"PROVEN_WINNER": 3, "STRONG_SELLER": 2, "SELLING": 1, "LISTED": 0}


def niche_proof(keyword, proof_map):
    """NICHE-LEVEL roll-up (V35). For a long-tail phrase with no confident
    exact-canonical proof group of its own, aggregate ALL sibling proof groups
    that share a SUBJECT token with the keyword (same subject-word rule as
    proof_for, so a generic 'embroidered sweatshirt' can never absorb a niche).

    Returns an aggregate dict with match='niche' plus the member groups (best
    first), or None. The numbers are the SUM across real sibling groups - they
    are NICHE-level evidence, clearly labelled, never presented as exact-phrase
    data. The verdict is the best MEMBER verdict (each member already earned it
    honestly per-group); the roll-up itself never mints a higher tier."""
    if not proof_map:
        return None
    kt = set(_canon(keyword).split())
    subj = kt - _PROOF_PRODUCT - _PROOF_GENERIC
    if not subj:
        return None                     # no niche identity to roll up on
    kw_products = kt & _PROOF_PRODUCT
    members = []
    for pc, p in proof_map.items():
        pt = set(pc.split())
        if not (subj & pt):
            continue                    # must share a real subject word
        # If the keyword names a product, the sibling must name a COMPATIBLE
        # product (or none at all): 'teacher mug' proof must not prop up a
        # 'teacher shirt' launch. Product-less groups (pure niche phrases)
        # still count - they are the niche itself.
        p_products = pt & _PROOF_PRODUCT
        if kw_products and p_products and not (kw_products & p_products):
            continue
        members.append(p)
    if not members:
        return None
    members.sort(key=lambda m: -((m.get("sold") or 0) + (m.get("sold_24h") or 0)))
    sold = sum(m.get("sold") or 0 for m in members)
    sold24 = sum(m.get("sold_24h") or 0 for m in members)
    revenue = sum(m.get("revenue") or 0 for m in members)
    shops_known = any(m.get("shops_known") for m in members)
    # shop counts can overlap across groups -> this is an UPPER bound, say so
    shops = sum(m.get("shops") or 0 for m in members if m.get("shops_known"))
    listings = sum(m.get("listings") or 0 for m in members)
    young = sum(m.get("young") or 0 for m in members)
    best = max(members, key=lambda m: _VERDICT_RANK.get(m.get("verdict"), 0))
    return {
        "keyword": keyword,
        "sold": sold, "sold_24h": sold24, "revenue": revenue,
        "shops": shops, "shops_known": shops_known, "listings": listings,
        "young": young,
        "score": best.get("score"),
        "verdict": best.get("verdict", "LISTED"),
        "evidence": _evidence(sold, revenue, shops, shops_known, listings,
                              young, sold24=sold24),
        "match": "niche", "match_confidence": None,
        "groups": len(members),
        "members": [{"keyword": m.get("keyword"), "verdict": m.get("verdict"),
                     "evidence": m.get("evidence")} for m in members[:5]],
    }


def exact_proof_from_loop(ev, mode=None):
    """Build a loop-verified EXACT-keyword proof record from one Phase-A lane
    payload (feed_evidence_router.record_focus_evidence), or None.

    match='exact' + source='loop'. Verdict follows the SAME tiers as export proof:
    PROVEN needs lifetime sold >= proven_sold AND spread across >= exact_proof_min_shops
    distinct shops; a single-shop or thin pull caps at SELLING (-> CONFIRM_FIRST in
    decide()). Ads and non-selling listings are excluded; stale pulls cap to SELLING."""
    if not ev:
        return None
    focus = (ev.get("focus_keyword") or "").strip()
    listings = ev.get("listings") or []
    if not focus or not listings:
        return None
    q = [l for l in listings
         if l.get("exact_match") and l.get("selling") and not l.get("is_ad")]
    if (len(listings) < int(_cfg("exact_proof_min_sample"))
            or len(q) < int(_cfg("exact_proof_min_listings"))):
        return None
    shops = {}
    s_life = s_24 = rev = 0.0
    for l in q:
        sh = (l.get("shop") or "").strip().lower()
        if sh:
            shops[sh] = shops.get(sh, 0) + 1
        s_life += l.get("sold") or 0
        s_24 += l.get("sold_24h") or 0
        rev += l.get("revenue_usd") or 0
    n_shops = len(shops)
    spread_ok = n_shops >= int(_cfg("exact_proof_min_shops"))
    if s_life >= _proven_sold() and spread_ok:
        verdict = "PROVEN_WINNER"
    elif (s_life >= _strong_sold() or s_24 >= _strong_sold24()) and spread_ok:
        verdict = "STRONG_SELLER"
    elif s_life + s_24 > 0:
        verdict = "SELLING"
    else:
        return None
    # monopoly cap — same rule as export proof.
    if verdict in ("PROVEN_WINNER", "STRONG_SELLER") and shops:
        tot = sum(shops.values()) or 1
        if max(shops.values()) / tot > float(_cfg("monopoly_top_share")):
            verdict = "SELLING"
    # freshness — a stale pull can no longer hold Build; cap to SELLING.
    stale = False
    exp = int(_cfg("exact_proof_expire_days"))
    coll = ev.get("collected_at")
    if exp > 0 and coll:
        try:
            from datetime import date as _date
            y, m, d = (int(x) for x in str(coll)[:10].split("-"))
            if (_date.today() - _date(y, m, d)).days > exp:
                stale = True
                if _VERDICT_RANK.get(verdict, 0) > _VERDICT_RANK["SELLING"]:
                    verdict = "SELLING"
        except Exception:  # noqa: BLE001
            pass
    ev_str = _evidence(s_life, rev, n_shops, True, len(q), 0, sold24=s_24)
    ev_str += " · loop-verified"
    if coll:
        ev_str += f" {str(coll)[:10]}"
    if stale:
        ev_str += " (stale — re-verify)"
    return {
        "keyword": focus, "sold": s_life, "sold_24h": s_24, "revenue": rev,
        "shops": n_shops, "shops_known": True, "listings": len(q),
        "young": 0, "score": None, "verdict": verdict, "young_winner": False,
        "evidence": ev_str, "match": "exact", "match_confidence": 1.0,
        "source": "loop",
        "proof_scope": "EXACT_MULTISHOP" if spread_ok else "EXACT_SINGLE_SHOP",
        "verified_at": coll, "stale": stale,
        "listing_ids": [l.get("listing_id") for l in q],
    }


def latest_info():
    """{count, source} for the newest proof export, or None."""
    p = PROOF_DIR / "latest.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8")) or {}
        return {"count": d.get("count", 0), "source": d.get("source", "")}
    except Exception:  # noqa: BLE001
        return None
