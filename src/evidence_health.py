"""Evidence Health — what is the Pattern Miner analysis actually based on?

WHY THIS EXISTS
Pattern Miner said "Mined the 385 listings matching X (of 385 captured, across
227 shops)" and staff had no way to check any of it. Two different questions hid
behind one sentence:

  * how many listings were CAPTURED, and how many survived the niche matcher
  * how much DEEPER evidence exists — opened listing pages, HeyEtsy, reviews

The second one is where the summary was most misleading: the winners'-structure
block spoke with total confidence off SIX opened listings out of 385.

SOURCE LAYERS ARE NOT INTERCHANGEABLE
The panel separates them because they prove different things and carry different
weight:

  1 SERP capture       broad market pattern — titles, price band, ad/star rates
  2 Opened listing     deep competitor proof, but a handful of listings
  3 HeyEtsy            real tags and detail behind a listing
  4 Reviews            buyer voice; NEVER market demand
  5 Candidates         generated, not observed

Review and listing evidence NEVER change the market score. That is the rule the
frozen L0-L4 files enforce, and this panel states it out loud rather than
letting a confident paragraph imply otherwise.

HONEST-NULL
A field the capture schema does not carry is reported as "not captured", never
as 0 and never blank. A zero would read as a measurement.
"""
from datetime import datetime

# What a SERP capture row actually carries (pattern_miner._from_import reads
# exactly these). Everything the evidence-table spec asks for beyond this list is
# absent from the SERP layer and must say so instead of rendering an empty cell.
SERP_FIELDS = ("title", "price", "shop", "star", "ad", "freeship", "tags")

# Which capture columns would satisfy each field the evidence table wants.
# MEASURED against the pool, never assumed: the PC's capture dir is nearly empty
# while the VPS carries 109 distinct headers including views_24h,
# he_revenue_usd, country, reviews and age_days. A hardcoded "not captured" list
# built from the local schema tells staff a field is unavailable when the server
# has it — a false negative that stops them looking for real data.
FIELD_ALIASES = {
    "views": ("views_24h", "he_views", "he_views_avg"),
    "favorites": ("he_favorites", "favorites_24h", "he_fav_pct"),
    "conversion": ("conversion_pct", "conversion"),
    "revenue": ("he_revenue_usd",),
    "sold": ("sold_24h", "he_sold", "shop_daily_sold", "sold 24h"),
    "shop_country": ("country",),
    "review_count": ("reviews",),
    "listing_age": ("age_days", "age (days)", "freshness"),
    "listing_id": ("listing_id",),
    "listing_url": ("url",),
    "tags": ("he_tags", "tags"),
    "shop_rating": (),          # no capture column supplies it
    "image_count": (),          # opened-listing lane only
}
# Shown when no alias is present. Distinguishes "this layer cannot carry it" from
# "your pool has not captured it yet".
ABSENT_SERP = "Not captured in SERP data"
ABSENT_DEEP = "Available only from HeyEtsy / opened listing evidence"
DEEP_ONLY = {"shop_rating", "image_count"}


def field_availability(present=None):
    """{field: True | 'reason'} — measured against the real capture headers."""
    if present is None:
        try:
            from src import pattern_miner as pm
            present = pm.capture_fields()
        except Exception:  # noqa: BLE001
            present = set()
    present = {str(p).strip().lower() for p in (present or ())}
    out = {}
    for field, aliases in FIELD_ALIASES.items():
        hit = next((a for a in aliases if a in present), None)
        if hit:
            out[field] = True
        else:
            out[field] = ABSENT_DEEP if field in DEEP_ONLY else ABSENT_SERP
    return out

# Match reasons that mean "this listing is in the niche because of a real niche
# signal" versus "it only shared a product noun or a personalisation word".
STRONG_REASONS = ("exact", "theme", "serp_view")
WEAK_REASONS = ("product_only", "modifier_only", "synonym")

STRONG = "Strong broad sample"
DIRECTIONAL = "Good directional sample"
WEAK_DETAIL = "Weak detail coverage"
MIXED = "Mixed cluster warning"
LOW = "Low data confidence"

WHY_IT_MATTERS = (
    "Broad SERP data shows market pattern. Opened listing/HeyEtsy/review data "
    "gives deeper competitor proof, but does not automatically change market "
    "score.")

# Below this share of matched listings, the deep lanes are anecdotes rather than
# coverage — 6 of 385 is 1.6%.
_DETAIL_THIN = 0.10
_STRONG_MIN_LISTINGS = 40
_STRONG_MIN_SHOPS = 15


def _stamp(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _age_days(ts):
    if not ts:
        return None
    try:
        return max(0, (datetime.now() - datetime.fromtimestamp(ts)).days)
    except Exception:  # noqa: BLE001
        return None


def _deep_lanes(keyword):
    """Counts for layers 2-4. Never raises: an absent lane reports zero WITH
    has_* False, so the caller can tell 'none imported' from 'not checked'."""
    out = {"opened": 0, "heyetsy": 0, "reviews": 0, "images": None,
           "has_structure": False, "has_reviews": False, "review_note": None}
    try:
        from src import feed_evidence_router as fer
        s = fer.structure_for_keyword(keyword) or {}
        out["has_structure"] = bool(s.get("has_structure"))
        out["opened"] = int(s.get("listings") or 0)
        out["images"] = s.get("avg_image_count")
        # HeyEtsy is where a listing's REAL tags come from
        out["heyetsy"] = len(s.get("top_tags") or [])
    except Exception:  # noqa: BLE001
        pass
    try:
        from src import feed_evidence_router as fer
        e = fer.evidence_for_keyword(keyword) or {}
        out["has_reviews"] = bool(e.get("has_evidence"))
        out["reviews"] = len(e.get("listings") or [])
        out["review_note"] = e.get("note")
    except Exception:  # noqa: BLE001
        pass
    return out


def report(keyword, mode=None):
    """The Evidence Health payload. Pure data — render_html() draws it."""
    from src import pattern_miner as pm
    from src import niche_match as nm

    a = pm.audit(keyword) if keyword else {
        "source": "none", "scanned": 0, "matched": 0, "rejected": 0,
        "reasons": {}, "shops": 0, "with_price": 0, "with_tags": 0,
        "newest": None, "oldest": None, "rejects_observable": True,
        "matched_rows": []}
    reasons = a["reasons"]
    matched, scanned = a["matched"], a["scanned"]
    deep = _deep_lanes(keyword) if keyword else {
        "opened": 0, "heyetsy": 0, "reviews": 0, "images": None,
        "has_structure": False, "has_reviews": False, "review_note": None}

    strong_hits = sum(reasons.get(r, 0) for r in STRONG_REASONS)
    weak_hits = sum(reasons.get(r, 0) for r in WEAK_REASONS)
    buckets = nm.classify(keyword) if keyword else {
        "modifier": [], "style": [], "technique": [], "product": [], "theme": []}

    rep = {
        "keyword": keyword or None,
        "mode": mode or "all lines",
        "source": a["source"],
        "buckets": buckets,
        "captured": scanned,
        "matched": matched,
        "rejected": a["rejected"],
        "rejects_observable": a["rejects_observable"],
        "match_rate": (round(100 * matched / scanned) if scanned else None),
        "shops": a["shops"],
        "reasons": reasons,
        "strong_hits": strong_hits,
        "weak_hits": weak_hits,
        "opened": deep["opened"],
        "heyetsy": deep["heyetsy"],
        "reviews": deep["reviews"],
        "images": deep["images"],
        "newest": _stamp(a["newest"]),
        "oldest": _stamp(a["oldest"]),
        "age_days": _age_days(a["newest"]),
        # price confidence is only claimable from rows that carry a price
        "price_known": a["with_price"],
        "price_confidence": (round(100 * a["with_price"] / matched)
                             if matched else None),
        "tags_known": a["with_tags"],
        "fields": field_availability(),
        "why_it_matters": WHY_IT_MATTERS,
    }
    rep["index_version"] = a.get("index_version")
    rep["matcher_version"] = nm.MATCHER_VERSION
    rep["index_stale"] = (rep["source"] == "db"
                          and (a.get("index_version") or 0) < nm.MATCHER_VERSION)
    rep["warnings"] = _warnings(rep, deep)
    rep["strength"] = _strength(rep)
    return rep


def _warnings(rep, deep):
    """Only warn about things we can actually see. A warning fired from missing
    data is worse than silence — it teaches staff to ignore the panel."""
    w = []
    m = rep["matched"]
    if not m:
        w.append(("none", "No listing matched this keyword — nothing below is "
                          "based on your captures."))
        return w
    if not rep["rejects_observable"]:
        # The index selects whole SEARCHES and returns only rows it already
        # judged a match, so "0 rejected" would be a fabrication, not a finding.
        w.append(("prefiltered",
                  "DB pre-filtered source — rejected rows are not observable. "
                  "Rebuild the index after matcher changes before trusting "
                  "strict-match counts."))
    if rep.get("index_stale"):
        w.append(("stale_index",
                  "Index may be stale — rebuild required after matcher change "
                  f"(index built under matcher v{rep.get('index_version') or 0}, "
                  f"current is v{rep.get('matcher_version')})."))
    if rep["rejected"] and rep["match_rate"] is not None \
            and rep["match_rate"] < 50:
        w.append(("filtered",
                  f"{rep['rejected']} of {rep['captured']} captured listings "
                  "were rejected as off-niche. The pattern below uses only the "
                  f"{m} that matched."))
    if deep["opened"] < max(1, int(m * _DETAIL_THIN)):
        w.append(("detail",
                  f"Low detail coverage — only {deep['opened']} opened listing(s) "
                  f"behind {m} matched. Treat the winners'-structure section as "
                  "a few examples, not a measured rate."))
    if rep["weak_hits"] and rep["weak_hits"] >= rep["strong_hits"]:
        w.append(("weak",
                  f"{rep['weak_hits']} match(es) rest on a product noun or a "
                  "personalisation word rather than the niche itself — the "
                  "pattern may be broader than your keyword."))
    if len(rep["buckets"].get("theme") or []) > 1:
        w.append(("mixed",
                  "Mixed clusters possible — this keyword names more than one "
                  f"niche ({', '.join(rep['buckets']['theme'])}). Mine one at a "
                  "time if the pattern looks blended."))
    if rep["age_days"] is not None and rep["age_days"] > 30:
        w.append(("stale",
                  f"Newest capture is {rep['age_days']} days old — the SERP has "
                  "probably moved."))
    if rep["price_confidence"] is not None and rep["price_confidence"] < 60:
        w.append(("price",
                  f"Only {rep['price_confidence']}% of matched listings carry a "
                  "price — treat the price band as indicative."))
    if deep["opened"] == 1:
        w.append(("cap", "Single-listing evidence — caps at CONFIRM_FIRST. One "
                         "competitor is not keyword-market proof."))
    if deep["has_reviews"]:
        w.append(("reviews", "Review evidence is buyer voice only — it does not "
                             "change the market score."))
    return w


def _strength(rep):
    """One label staff can act on. Ordered worst-first: a real problem outranks
    a flattering headline count."""
    m = rep["matched"]
    kinds = {k for k, _t in rep["warnings"]}
    if not m:
        return LOW
    if "mixed" in kinds:
        return MIXED
    if "stale_index" in kinds:
        # Rows selected by a superseded rule cannot be a strong sample, however
        # many of them there are.
        return LOW
    if "weak" in kinds or m < 10 or rep["shops"] < 5:
        return LOW
    if "detail" in kinds and m >= _STRONG_MIN_LISTINGS:
        return WEAK_DETAIL
    if m >= _STRONG_MIN_LISTINGS and rep["shops"] >= _STRONG_MIN_SHOPS:
        return STRONG
    return DIRECTIONAL


# ------------------------------------------------------------------ rendering
_CHIP = {"none": "#99271F", "filtered": "#3B6E8F", "detail": "#B45309",
         "weak": "#B45309", "mixed": "#99271F", "stale": "#B45309",
         "price": "#6E6455", "cap": "#B45309", "reviews": "#1E6B54",
         "prefiltered": "#B45309", "stale_index": "#99271F"}
_STRENGTH_BG = {STRONG: "#1E6B54", DIRECTIONAL: "#3B6E8F",
                WEAK_DETAIL: "#B45309", MIXED: "#99271F", LOW: "#6E6455"}


def _esc(s):
    import html
    return html.escape(str(s if s is not None else ""))


def _card(label, value, note=None):
    n = f'<span class="ehnote">{_esc(note)}</span>' if note else ""
    return (f'<div class="ehcard"><span class="ehl">{_esc(label)}</span>'
            f'<b class="ehv">{_esc(value)}</b>{n}</div>')


def render_html(rep):
    """Compact cards + warning chips, above the markdown summary."""
    if not rep.get("keyword"):
        return ""
    strength = rep["strength"]
    chips = "".join(
        f'<span class="ehchip" style="background:{_CHIP.get(k, "#6E6455")}">'
        f'{_esc(t)}</span>' for k, t in rep["warnings"])
    rate = "—" if rep["match_rate"] is None else f'{rep["match_rate"]}%'

    # layer 1 — SERP
    l1 = "".join([
        _card("Captured", f'{rep["captured"]:,}'),
        _card("Matched", f'{rep["matched"]:,}',
              None if rep["rejects_observable"]
              else "source is keyword-keyed; rejects not observable"),
        _card("Rejected", f'{rep["rejected"]:,}' if rep["rejects_observable"]
              else "n/a",
              None if rep["rejects_observable"] else "not observable via index"),
        _card("Match rate", rate),
        _card("Unique shops", f'{rep["shops"]:,}'),
    ])
    # match reasons — straight from niche_match.why()
    order = ["exact", "theme", "serp_view", "synonym", "product_only",
             "modifier_only", "rejected_missing_theme",
             "rejected_product_mismatch", "none"]
    seen = [(k, rep["reasons"][k]) for k in order if rep["reasons"].get(k)]
    reasons = "".join(_card(k.replace("_", " "), v) for k, v in seen) or \
        '<p class="note">No per-row reasons — this source does not expose them.</p>'
    # layers 2-4 — deep evidence
    l2 = "".join([
        _card("Opened listings", rep["opened"]),
        _card("HeyEtsy tags", rep["heyetsy"]),
        _card("Review listings", rep["reviews"]),
        _card("Avg images", rep["images"] if rep["images"] is not None
              else "not captured"),
    ])
    dates = "".join([
        _card("Newest capture", rep["newest"] or "not captured"),
        _card("Oldest capture", rep["oldest"] or "not captured"),
        _card("Price known", f'{rep["price_known"]:,}',
              None if rep["price_confidence"] is None
              else f'{rep["price_confidence"]}% of matched'),
    ])
    fields = rep.get("fields") or {}
    have = sorted(k for k, v in fields.items() if v is True)
    lack = sorted((k, v) for k, v in fields.items() if v is not True)
    missing = "".join(
        f'<li><b>{_esc(k.replace("_", " "))}</b> — {_esc(v)}</li>'
        for k, v in lack) or '<li>Every field the table needs is captured.</li>'
    if have:
        missing = ('<li style="color:var(--ok)"><b>Captured and available:</b> '
                   + _esc(", ".join(h.replace("_", " ") for h in have))
                   + "</li>") + missing

    return (
        '<style>'
        '.eh{background:var(--surface);border:1px solid var(--line-strong);'
        'border-radius:14px;padding:16px 18px;margin:0 0 16px;box-shadow:var(--shadow)}'
        '.ehhead{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}'
        '.ehhead h2{font-size:1.05rem;margin:0}'
        '.ehstr{font-size:.72rem;font-weight:800;color:#fff;border-radius:20px;padding:3px 11px}'
        '.ehsub{font-size:.78rem;color:var(--ink-faint);margin:0 0 10px}'
        '.ehgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));'
        'gap:8px;margin:8px 0}'
        '.ehcard{background:var(--paper);border:1px solid var(--line);border-radius:9px;'
        'padding:8px 10px;display:flex;flex-direction:column;gap:1px}'
        '.ehl{font-size:.62rem;text-transform:uppercase;letter-spacing:.05em;'
        'color:var(--ink-faint);font-weight:700}'
        '.ehv{font-size:1.15rem;font-variant-numeric:tabular-nums;line-height:1.2}'
        '.ehnote{font-size:.62rem;color:var(--ink-faint)}'
        '.ehlayer{font-size:.66rem;font-weight:700;text-transform:uppercase;'
        'letter-spacing:.07em;color:var(--ink-soft);margin:12px 0 2px}'
        '.ehchips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 2px}'
        '.ehchip{font-size:.73rem;font-weight:600;color:#fff;border-radius:8px;padding:4px 10px}'
        '.ehwhy{font-size:.78rem;color:var(--ink-soft);background:var(--accent-bg);'
        'border-radius:9px;padding:9px 12px;margin:10px 0 0}'
        '.eh details{margin-top:8px}.eh summary{cursor:pointer;font-size:.78rem;'
        'font-weight:700;color:var(--accent)}'
        '.eh details ul{margin:6px 0 0;padding-left:18px;font-size:.78rem;color:var(--ink-soft)}'
        '</style>'
        '<section class="eh">'
        '<div class="ehhead"><h2>\U0001F9EA Evidence Health</h2>'
        f'<span class="ehstr" style="background:{_STRENGTH_BG.get(strength, "#6E6455")}">'
        f'{_esc(strength)}</span></div>'
        f'<p class="ehsub">Seed keyword <b>{_esc(rep["keyword"])}</b> · '
        f'mode <b>{_esc(rep["mode"])}</b> · source <b>{_esc(rep["source"])}</b>'
        + (f' · index matcher <b>v{_esc(rep.get("index_version") or 0)}</b> '
           f'(current v{_esc(rep.get("matcher_version"))})'
           if rep["source"] == "db" else "") + '</p>'
        f'{chips and f"<div class=ehchips>{chips}</div>"}'
        '<div class="ehlayer">1 · SERP capture layer</div>'
        f'<div class="ehgrid">{l1}</div>'
        '<div class="ehlayer">Why each listing matched (niche matcher)</div>'
        f'<div class="ehgrid">{reasons}</div>'
        '<div class="ehlayer">2–4 · Opened listing / HeyEtsy / review layers</div>'
        f'<div class="ehgrid">{l2}</div>'
        '<div class="ehlayer">Capture recency &amp; price confidence</div>'
        f'<div class="ehgrid">{dates}</div>'
        f'<details><summary>Field coverage — what your captures do and do not '
        f'carry</summary><ul>{missing}</ul></details>'
        f'<p class="ehwhy"><b>Why this matters:</b> {_esc(rep["why_it_matters"])}</p>'
        '</section>')
