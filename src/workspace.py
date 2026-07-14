"""Keyword Run Workspace — the one-keyword ACTION CENTER for a POD + Embroidery
Etsy team. One keyword (+ product mode) → verdict, scores, source confidence,
how-we-beat-competitors, competitor audit, market/keyword, niches, sales
forecast, supplier recommendation, a strict-QA listing builder (exactly 13 tags,
typo + trademark flags), internal product preview, mode-aware design prompts,
seller checklist, designer brief, product-line expansion, and save/export.

Rules baked in: never auto-publish; the verdict gates the UI (WATCH/SKIP/BLOCKED
never say "publish"); the button says "Save Draft" unless PUBLISH_READY; estimates
are labelled; embroidery vs POD rules are mode-specific.
"""
import html as _html
import math
import re

from src import ytrends_mcp as mcp
from src.discover import matches_mode
from src.trademark import check as tm_check
from src.interactive import _money, _int, _pct, _g, _rel_rows

MODES = ("pod", "embroidery", "both")


# --------------------------- small helpers ---------------------------------

def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _clamp(v):
    try:
        return max(0, min(100, int(round(v))))
    except (TypeError, ValueError):
        return 0


def _label(s):
    return ("Excellent" if s >= 90 else "Strong" if s >= 75 else
            "Good, needs work" if s >= 60 else "Weak" if s >= 40 else
            "Avoid / rethink")


def _esc(t):
    return _html.escape(str(t or ""))


def _urlquote(s):
    from urllib.parse import quote
    return quote(str(s or ""), safe="")


def md_table(lines):
    import markdown as _md
    # Wrap in .tw so the table gets real border/striping styling (the base
    # table CSS is scoped to .md pages) and can scroll horizontally on mobile
    # without pushing the whole page sideways.
    return ('<div class="tw">'
            + _md.markdown("\n".join(lines), extensions=["tables"])
            + '</div>')


# --------------------------- data-quality checks ---------------------------

def data_check(stats, kw):
    """Return a list of DATA_CHECK_REQUIRED reasons (suspicious data)."""
    flags = []
    conv = _f(stats.get("avg_conversion_rate"))
    if conv > 0.15:
        flags.append(f"conversion looks too high ({_pct(conv)}) — verify")
    price = _f(stats.get("avg_price"))
    if price and price < 3:
        flags.append(f"avg price {_money(price)} may be below supplier cost")
    listings = _f(stats.get("total_listings"))
    views = _f(stats.get("avg_views_24h")) * listings
    if listings and views and views / max(listings, 1) > 500:
        flags.append("views very high vs listings — verify demand")
    if re.search(r"(.)\1\1", kw) or _looks_typo(kw)[1]:
        flags.append(f"keyword may contain a typo ('{kw}')")
    if not stats:
        flags.append("no keyword stats returned (SOURCE_NOT_AVAILABLE)")
    return flags


def source_confidence(stats, data_flags):
    """Which sources fed this run + confidence + freshness."""
    from src import crosscheck
    cc = crosscheck.status()
    ytr = "live (pulled today)" if stats else "SOURCE_NOT_AVAILABLE"
    google = "live" if cc.get("Google Trends") == "live" else "off"
    rows = [
        ("YTrends (Etsy index)", ytr, "High" if stats else "—"),
        ("Google Trends", google, "Medium" if google == "live" else "—"),
        ("Pinterest", "off (add token)" if "off" in cc.get("Pinterest", "")
         else "live", "—"),
        ("Reddit", "off" if "off" in cc.get("Reddit", "") else "live (free)",
         "Low"),
        ("X / Twitter", "off (add token)" if "off" in cc.get("X / Twitter", "")
         else "live", "—"),
        ("Supplier catalog", "on file (supplier_costs.csv)", "High"),
    ]
    overall = ("LOW — verify before acting" if data_flags else
               "MEDIUM" if google != "live" else "MEDIUM-HIGH")
    return rows, overall


# --------------------------- scoring ---------------------------------------

def compute_scores(kw, stats, comp, mo, mode):
    views = _f(stats.get("avg_views_24h")) * _f(stats.get("total_listings"))
    conv = _f(stats.get("avg_conversion_rate"))
    listings = _f(stats.get("total_listings"))
    sat = (comp.get("saturation") or "").lower()
    ner = _f(comp.get("new_entrant_rate"))
    ms, opp = mo.get("momentum_score"), mo.get("opportunity_score")
    words = len(kw.split())

    demand = _clamp((math.log10(views + 1) - 1.5) / 3.5 * 100) if views else 35
    # Competition = how easy to break in. Use the CONTINUOUS seller-concentration
    # index (a niche with FEW sellers can still be hard if a handful dominate it)
    # instead of the coarse 3-bucket saturation, so it discriminates keyword to
    # keyword. Low concentration (well spread) -> high score (easy); high -> low.
    conc = _f(comp.get("seller_concentration_index"))
    if conc > 0:
        competition = _clamp(176 - 38 * math.log10(conc + 1) + (6 if ner > 0.01 else 0))
    else:
        competition = _clamp({"low": 82, "medium": 55, "high": 30}.get(sat, 52)
                             + (8 if ner > 0.01 else 0))
    conversion = _clamp(conv * 100 * 16 + 10)
    opportunity = _clamp(opp if opp is not None else (demand + competition) / 2)
    # SEO: 3-word buyer phrases are the sweet spot; 1-word is too broad, 5+ too niche
    seo = _clamp({1: 45, 2: 72, 3: 85, 4: 78}.get(words, 60) + (8 if len(mo) else 0))
    trend = _clamp(ms if ms is not None else
                   (72 if _f(stats.get("rank_change_7d")) < 0 else 48))
    # Design room grows where it's easier to break in (a less-dominated niche).
    design = _clamp((78 if mode != "embroidery" else 70) + (competition - 55) * 0.28)
    production = 80 if mode == "pod" else 66 if mode == "embroidery" else 88
    overall = _clamp(demand * .2 + competition * .15 + opportunity * .2
                     + conversion * .15 + seo * .1 + trend * .1
                     + design * .05 + production * .05)

    def s(name, sc, why, improve, src, est=False):
        return {"name": name, "score": sc, "label": _label(sc), "why": why,
                "improve": improve, "sources": src, "estimate": est}

    return [
        s("Overall Product", overall, "Weighted blend of all signals below.",
          "Lift the weakest scores first.", "all"),
        s("Demand", demand,
          f"~{_int(views)} market views/day across {_int(listings)} listings.",
          "More buyers searching = better. Add high-intent long-tails.",
          "YTrends, Etsy"),
        s("Competition", competition,
          f"{_int(comp.get('sellers'))} sellers, "
          + ("a few dominate" if conc > 3000 else "well spread" if conc < 1200
             else "moderately concentrated") + ".",
          "Higher score = easier to rank. Narrow the sub-niche.", "YTrends"),
        s("Opportunity", opportunity, "Low competition + real demand.",
          "Chase high-opportunity, low-competition angles.", "YTrends"),
        s("SEO", seo, f"'{kw}' is {words}-word.",
          "Use 2-4 word buyer phrases in title + all 13 tags.", "heuristic", True),
        s("Conversion", conversion, f"Niche converts ~{_pct(conv)}.",
          "Better photos + offer + personalization lift conversion.", "Etsy"),
        s("Design Potential", design, "Room for a distinctive design to win.",
          "Aim original, not a copy.", "heuristic", True),
        s("Production Feasibility", production,
          f"How easily this ships as {mode}.",
          "Embroidery: bold shapes, few colors.", "supplier + heuristic", True),
        s("Trend / Seasonality", trend, "Momentum + weekly rank movement.",
          "Ride rising terms; time seasonal 4-6 weeks early.",
          "YTrends, Google", True),
    ]


# --------------------------- strict verdict --------------------------------

def strict_verdict(kw, scores, comp, risk, data_flags, cww=0, lr=0, fib=0, offer=0):
    by = {s["name"]: s["score"] for s in scores}
    overall, competition = by.get("Overall Product", 0), by.get("Competition", 0)
    if risk == "HIGH":
        v, cls = "BLOCKED", "avoid"
        reason = "trademark risk on this exact phrase is HIGH"
    elif (overall >= 75 and competition >= 55 and not data_flags
          and cww >= 70 and lr >= 85 and fib >= 75 and offer >= 70):
        v, cls = "SELL NOW", "design"
        reason = "strong demand, we can win, and it's launch-ready"
    elif overall >= 58:
        v, cls = "VALIDATE FIRST", "validate"
        reason = "promising — test with 2 listings before a big batch"
    elif overall >= 47:
        v, cls = "WATCH / SAVE FOR LATER", "watch"
        reason = "mixed signals — save and recheck in 2-4 weeks"
    else:
        v, cls = "SKIP", "skip"
        reason = "the numbers don't support it right now"
    gates = {
        "build_listing": cls in ("design", "validate"),  # draft only
        "design": cls in ("design", "validate", "watch"),
        "publish": False,   # ALWAYS false here; only the QA gate can pass it
        "watch": cls == "watch", "skip": cls == "skip", "blocked": cls == "avoid",
    }
    return {"verdict": v, "cls": cls, "reason": reason, "gates": gates,
            "confidence": "LOW" if data_flags else "MEDIUM"}


# --------------------------- tag builder (exactly 13) ----------------------

_TYPO = {"racoon": "raccoon", "shiirt": "shirt", "tshit": "tshirt",
         "personlized": "personalized", "personalised": "personalized",
         "bday": "birthday", "xmas": "christmas", "sweatshit": "sweatshirt"}
_BROAD = {"shirt", "gift", "custom", "tshirt", "hat", "bag", "art", "design"}


def _looks_typo(tag):
    words = tag.split()
    out, changed = [], False
    for w in words:
        if w in _TYPO:
            out.append(_TYPO[w]); changed = True
        else:
            w2 = re.sub(r"(.)\1{2,}", r"\1", w)   # 3+ repeated letters
            out.append(w2); changed = changed or (w2 != w)
    return " ".join(out), changed


def _tag_type(tag, kw):
    t = tag.lower()
    if t == kw.lower():
        return "primary"
    if any(o in t for o in ("christmas", "valentine", "halloween", "4th",
                            "july", "mother", "father", "birthday")):
        return "occasion"
    if any(a in t for a in ("men", "women", "kids", "mom", "dad", "her", "him",
                            "teacher", "nurse")):
        return "audience"
    if any(p in t for p in ("custom", "personalized", "monogram", "name")):
        return "personalization"
    if any(s in t for s in ("funny", "retro", "vintage", "cute", "aesthetic",
                            "minimalist", "boho")):
        return "style"
    if any(pr in t for pr in ("shirt", "hoodie", "tote", "hat", "mug", "bag",
                              "sweatshirt", "cap", "blanket")):
        return "product"
    if "gift" in t:
        return "gift"
    if len(t.split()) >= 3:
        return "long-tail"
    return "seasonal"


def build_tags(kw, related, opts, mode):
    """Return exactly 13 tag dicts {tag,type,status,reason,publish_safe}.
    Plural-deduped, and guaranteed >=2 occasion/buyer tags so the output always
    clears the tag validators."""
    from src.validators import _sing_words, is_occ_buyer
    cands = [kw]
    for k in ("niche", "occasion", "personalization", "style"):
        if opts.get(k):
            cands.append(opts[k])
    cands += [_g(r, "tag", "keyword", "title") for r in (related or [])]
    # mode-appropriate fallbacks (all <=20 chars, clean) so we ALWAYS hit 13
    base = "embroidered" if mode == "embroidery" else "custom"
    cands += [f"{base} gift", "custom gift", "personalized gift", "gift for her",
              "gift for him", "gift for mom", "gift for dad", "unique gift idea",
              "birthday gift", "handmade gift", "custom present", "name gift",
              "custom name", "gift idea", "matching gift", "family gift",
              "cute gift idea", "trendy gift", "personalized present"]

    def _tagdict(tag, was_typo, src):
        risk, _ = tm_check(tag)
        if risk == "HIGH":
            st, safe, rs = "BLOCKED_TM", False, "trademark risk HIGH"
        elif risk == "CAUTION":
            st, safe, rs = "NEED_TM_CHECK", False, "verify trademark first"
        elif was_typo:
            st, safe, rs = "TYPO_FIXED", True, f"corrected from '{src}'"
        elif tag in _BROAD:
            st, safe, rs = "TOO_BROAD", True, "broad — pair with specifics"
        else:
            st, safe, rs = "OK", True, ""
        return {"tag": tag, "type": _tag_type(tag, kw), "status": st,
                "reason": rs, "publish_safe": safe}

    out, seen, seen_sing = [], set(), set()
    for raw in cands:
        c = (raw or "").strip().lower()
        if not c or c in seen or not (3 <= len(c) <= 20):
            continue
        tag, was_typo = _looks_typo(c)
        sk = _sing_words(tag)                       # plural/reorder-safe key
        if tag in seen or sk in seen_sing:
            continue
        seen.add(tag)
        seen_sing.add(sk)
        out.append(_tagdict(tag, was_typo, c))
        if len(out) >= 13:
            break
    out = out[:13]

    # guarantee >=2 occasion/buyer tags: swap trailing non-occasion tags for
    # occasion/buyer fallbacks (only bites when opts + related carry none).
    occ_fb = ["gift for her", "gift for him", "gift for mom", "birthday gift",
              "gift for dad", "wedding gift"]
    have = sum(1 for t in out if is_occ_buyer(t["tag"]))
    for i in range(len(out) - 1, -1, -1):
        if have >= 2:
            break
        if is_occ_buyer(out[i]["tag"]):
            continue
        present = {t["tag"] for t in out}
        present_sing = {_sing_words(t["tag"]) for t in out}
        for ft in occ_fb:
            if ft in present or _sing_words(ft) in present_sing:
                continue
            out[i] = _tagdict(ft, False, ft)
            have += 1
            break
    return out[:13]


# --------------------------- publish-ready QA gate -------------------------

# The manual checks a MANAGER must confirm (the tool cannot verify these itself).
# PUBLISH_READY can only become true when every one is explicitly confirmed — so
# the tool never declares a listing publish-ready on its own. HIGH trademark is a
# HARD block that no confirmation can clear.
MANAGER_CHECKS = [
    ("supplier", "supplier confirmed (product URL + base/shipping cost + material)"),
    ("competitor_audit", "competitor audit complete"),
    ("material", "material / size / processing time verified"),
    ("image", "image / mockup checklist complete"),
    ("trademark", "trademark verified or manager-approved"),
]


def publish_gate(kw, tags, supplier_ok, risk, data_flags, verdict_cls,
                 lr=0, fib=0, offer=0, confirms=None):
    """Strict gate. Returns (ready, failed_checks[]).

    `confirms` is a dict of manager sign-offs (supplier/competitor_audit/material/
    image/trademark). PUBLISH_READY is true only when all automated checks pass AND
    every manual item is manager-confirmed. Never auto-publishes."""
    confirms = confirms or {}
    failed = []
    # ---- automated checks ----
    if lr < 85:
        failed.append(f"launch readiness {lr}/100 (need ≥ 85)")
    if fib and fib < 75:
        failed.append(f"first-image score {fib}/100 (need ≥ 75)")
    if offer and offer < 70:
        failed.append(f"offer strength {offer}/100 (need ≥ 70)")
    clean_safe = [t for t in tags if t["publish_safe"]]
    if verdict_cls in ("watch", "skip", "avoid"):
        failed.append(f"verdict is {verdict_cls.upper()} — not for publishing")
    if len(tags) != 13:
        failed.append(f"need exactly 13 tags (have {len(tags)})")
    if len(clean_safe) != 13:
        failed.append(f"{13 - len(clean_safe)} tag(s) need typo/trademark review")
    if any(t["status"].startswith("BLOCKED") for t in tags):
        failed.append("a tag has HIGH trademark risk")
    if data_flags:
        failed.append("DATA_CHECK_REQUIRED on source data")
    # ---- trademark: HIGH is a HARD block; CAUTION needs manager approval ----
    if risk == "HIGH":
        failed.append("primary keyword is a known trademark/brand — cannot publish")
    elif risk == "CAUTION" and not confirms.get("trademark"):
        failed.append("primary keyword trademark not verified/approved (manager)")
    # ---- manual manager sign-offs ----
    if not (supplier_ok or confirms.get("supplier")):
        failed.append("supplier + product URL + costs not confirmed (manager)")
    if not confirms.get("competitor_audit"):
        failed.append("competitor audit not confirmed complete (manager)")
    if not confirms.get("material"):
        failed.append("material / size / processing time not verified (manager)")
    if not confirms.get("image"):
        failed.append("image / mockup checklist not confirmed complete (manager)")
    return (len(failed) == 0), failed


# --------------------------- competitor audit + beat -----------------------

def competitor_audit(listings):
    rows = ["| Competitor listing | Price | Sold | Conv | Favs | Weakness to beat |",
            "|---|---|---|---|---|---|"]
    for r in (listings or [])[:6]:
        title = _esc(_g(r, "title"))[:52]
        pers = "name" in (_g(r, "title") or "").lower() or \
               "custom" in (_g(r, "title") or "").lower() or \
               "personal" in (_g(r, "title") or "").lower()
        weak = ("no personalization in title" if not pers else
                "generic title" if len(str(_g(r, "title") or "").split()) < 6
                else "beatable with a stronger first image")
        rows.append(f"| {title} | {_money(_g(r,'price'))} "
                    f"| {_int(_g(r,'total_sold'))} | {_pct(_g(r,'conversion_rate'))} "
                    f"| {_int(_g(r,'favorites'))} | {weak} |")
    status = ("COMPETITOR_RELEVANCE_OK_MANUAL_FIELDS_MISSING" if listings
              else "COMPETITOR_AUDIT_NOT_STARTED")
    note = ("_Structural read only — photo count, video, and personalization "
            "options need a manual check to reach COMPETITOR_AUDIT_OK. "
            f"Status: **{status}**._")
    return md_table(rows) + note, status


def beat_competitors(kw, listings, opts, mode):
    pers = opts.get("personalization") or "name / date / initials"
    lines = [
        "| Advantage | Our play |", "|---|---|",
        f"| 1. First image | Bold, high-contrast main image that reads at a "
        f"glance — most rivals use flat mockups |",
        f"| 2. Mockup | Lifestyle + gift-in-use shots, not just a blank product |",
        f"| 3. Personalization | Offer {pers} (many rivals sell generic) |",
        f"| 4. SEO | Specific long-tails vs their broad '{kw}' titles |",
        f"| 5. Niche angle | Narrow to an emotional/gift/occasion angle |",
        f"| 6. Bundle | Set of 2 / family set / gift box option |",
        f"| 7. Price/value | Price higher on better personalization + bundle |",
        f"| 8. Trust | Size chart, care guide, clear personalization + shipping |",
        f"| 9. Originality | Original art — never copy clip-art or rival designs |",
        f"| 10. Speed | State a clear, fast processing/ship time |",
    ]
    summary = [
        "**How we beat competitors**",
        "- **Biggest competitor weakness:** generic art + weak first image, "
        "little/no personalization.",
        f"- **Our winning angle:** original {opts.get('niche') or 'gift'} design "
        f"for \"{kw}\" with a strong first image and "
        f"{'stitch-safe embroidery' if mode == 'embroidery' else 'bold print'}.",
        "- **Main image strategy:** one clear hero image, big readable subject, "
        "gift context.",
        f"- **Personalization strategy:** {pers}.",
        "- **SEO strategy:** 13 specific long-tail tags, keyword front-loaded.",
        "- **Bundle strategy:** offer a set / gift-box upsell.",
        "- **Pricing strategy:** price for margin + personalization premium.",
        "- **Trust strategy:** size/care/shipping clarity + personalization note.",
        "- **Design originality rule:** original only — study structure, copy nothing.",
        "- **Final edge:** better first image + real personalization + tighter SEO.",
    ]
    return md_table(lines) + "\n".join(f"<p>{_esc(x)}</p>" if not x.startswith("**")
                                       else f"<p><b>{_esc(x.strip('*'))}</b></p>"
                                       for x in summary)


# --------------------------- can we win / launch readiness -----------------

CWW_FACTORS = [
    ("First image", "beat their flat mockups with a bold hero image"),
    ("Mockup", "lifestyle + gift-in-use shots"),
    ("Personalization", "offer name / date / monogram many rivals lack"),
    ("SEO", "specific long-tails vs broad titles"),
    ("Niche angle", "narrow to an emotional / gift / occasion angle"),
    ("Bundle", "set / gift-box option most don't offer"),
    ("Price/value", "premium on better personalization + bundle"),
    ("Trust", "size chart, care, clear personalization + shipping"),
    ("Design originality", "original art vs clip-art copies"),
    ("Speed", "clear, fast processing / ship time"),
    ("Supplier", "a confirmed, cost-fit supplier"),
    ("Product-line", "expandable into a whole line"),
]


def can_we_win(kw, comp, listings, opts, mode, supplier_ok):
    """Per-niche win potential MEASURED from the actual top rivals, not constants.
    A factor scores higher where the rivals are measurably weak = a real gap to
    exploit. Returns (overall, scores, gaps): `gaps` is the ranked list of the
    biggest MEASURED weaknesses (name, score, evidence), strongest first."""
    ls = [r for r in (listings or []) if _g(r, "title")]
    n = len(ls)
    titles = [str(_g(r, "title") or "").lower() for r in ls]
    prices = sorted(p for p in (_f(_g(r, "price")) for r in ls) if p > 0)
    solds = sorted(_f(_g(r, "total_sold")) for r in ls)
    sat = (comp.get("saturation") or "").lower()
    damp = {"high": -10, "medium": -3, "low": 5}.get(sat, 0)

    def cnt(words):
        return sum(1 for t in titles if any(w in t for w in words))

    PERS = ("name", "custom", "personal", "monogram", "initial", "personalised",
            "personalized")
    CLIP = ("clipart", "clip art", "svg", "png", "sublimation", "digital",
            "printable", "vector")

    measured = {}   # name -> (score, evidence) -- only where we have real data
    if n:
        no_pers = n - cnt(PERS)
        measured["Personalization"] = (
            _clamp(42 + 56 * (no_pers / n)),
            f"{no_pers}/{n} top rivals show no personalization in the title")
        broad = sum(1 for t in titles if len(t.split()) <= 4)
        measured["SEO"] = (
            _clamp(40 + 52 * (broad / n)),
            f"{broad}/{n} rivals use short/broad titles -- beat them with specific "
            "long-tails")
        clip = cnt(CLIP)
        measured["Design originality"] = (
            _clamp(48 + 48 * (clip / n)),
            (f"{clip}/{n} rivals look like clip-art / digital prints -- win on "
             "original stitched art" if clip else
             "rivals aren't obvious clip-art -- still win on genuinely original art"))
    if prices:
        med = prices[len(prices) // 2]
        headroom = 1.0 if med < 18 else 0.6 if med < 28 else 0.3
        measured["Price/value"] = (
            _clamp(45 + 45 * headroom),
            f"rivals cluster at ~{_money(med)} median -- room to premium on "
            "personalization + quality")
    if solds:
        med_sold = solds[len(solds) // 2]
        beat = 1.0 if med_sold < 50 else 0.6 if med_sold < 300 else 0.25
        ang = opts.get("niche") or opts.get("occasion")
        measured["Niche angle"] = (
            _clamp(44 + 46 * beat),
            f"top rivals' median ~{_int(med_sold)} sold -- niche isn't locked up"
            + (f"; sharpen a '{ang}' angle" if ang else ""))

    # Execution levers we can't read from the index (our craft, not a measured
    # rival gap) -- honest moderate defaults, dampened by saturation.
    execution = {"First image": 78, "Mockup": 76, "Bundle": 70, "Trust": 74,
                 "Speed": 70, "Product-line": 74,
                 "Supplier": 82 if supplier_ok else 52}
    scores = {k: v for k, (v, _ev) in measured.items()}
    for k, v in execution.items():
        scores[k] = _clamp(v + damp)
    for name, _play in CWW_FACTORS:          # fill any factor missing for lack of data
        scores.setdefault(name, _clamp(64 + damp))

    overall = _clamp(sum(scores.values()) / len(scores))
    gaps = sorted(((k, s, ev) for k, (s, ev) in measured.items()),
                  key=lambda x: x[1], reverse=True)
    return overall, scores, gaps


def launch_readiness(supplier_ok, tags, risk, L, opts, confirms=None):
    """0-100 + status + blocking reasons. Gates PUBLISH_READY (needs >= 85). The
    manual steps (photo/mockup, shipping, production partner) are cleared only by
    explicit manager sign-off (confirms), so readiness reflects real confirmation."""
    confirms = confirms or {}
    checks = {
        "Supplier confirmed": supplier_ok,
        # True net floor (same as the report pipeline's gate): a viable price
        # exists that clears >=$6 net profit AND >=30% net margin after all fees.
        "Profit target met": (bool(L.get("rec_price"))
                              and (L.get("rec_profit") or 0) >= 6
                              and (L.get("rec_margin_pct") or 0) >= 30),
        "13 clean tags": sum(1 for t in tags if t["publish_safe"]) == 13,
        "Photo / mockup ready": bool(confirms.get("image")),
        "Competitor advantage ready": True,   # the tool produces the beat plan
        "Trademark verified": risk == "OK" or bool(confirms.get("trademark")),
        "Description ready": True,
        "Personalization ready": True,
        "Shipping clarity ready": bool(confirms.get("material")),
        "Production partner confirmed": bool(confirms.get("supplier")),
    }
    score = _clamp(sum(bool(v) for v in checks.values()) / len(checks) * 100)
    reasons = [k for k, v in checks.items() if not v]
    return score, ("READY" if score >= 85 else "NOT READY"), reasons


def first_image_battle(listings):
    titles = " ".join(str(r.get("title") or "").lower() for r in listings)
    rivals_personalize = any(w in titles for w in ("name", "custom", "personal"))
    pattern = ["flat product mockup", "little / no personalization shown",
               "weak gift context", "small unreadable thumbnail text"]
    plan = ["clear product close-up", "personalization visible in-frame",
            "gift context / lifestyle", "clean background",
            "readable at thumbnail size", "one emotional buyer hook"]
    score = _clamp(82 if not rivals_personalize else 74)
    return score, pattern, plan


# --------------------------- sales forecast --------------------------------

def offer_builder(kw, opts, mode):
    """Don't just build a product — build a better OFFER. Returns
    (html, offer_strength_score, factor_scores)."""
    pers = opts.get("personalization") or "name / date / monogram"
    cust = opts.get("target_customer") or "gift buyers"
    occ = opts.get("occasion") or "gift-giving"
    bundles = ("embroidered sweatshirt + hat · name bag + card · family set"
               if mode == "embroidery"
               else "set of 2 · family set · gift box · matching tote + pouch")
    rows = [
        ("Base product", kw),
        ("Better offer", f"Personalized {kw} with gift-ready packaging, {pers}, "
                         "and a matching-set option"),
        ("Personalization", pers),
        ("Bundle / set", bundles),
        ("Gift angle", f"ready-to-gift for {occ}"),
        ("Premium angle", "gift box + personalization = a higher price point"),
        ("Upsell", "add a matching item or a gift note"),
        ("Trust elements", "size chart, care guide, clear personalization + shipping"),
        ("Why buyers choose us", f"original design + real personalization for {cust}"),
    ]
    # Offer Strength Score 0-100 from the 7 factors the spec lists.
    factors = {
        "Buyer emotion": 80 if (opts.get("occasion") or opts.get("target_customer")) else 66,
        "Personalization": 88 if opts.get("personalization") else 74,
        "Giftability": 84 if opts.get("occasion") else 72,
        "Bundle potential": 76,
        "Premium value": 74 if opts.get("personalization") else 66,
        "Clarity": 80,
        "Uniqueness": 82 if opts.get("niche") else 68,
    }
    score = _clamp(sum(factors.values()) / len(factors))
    frows = ["| Offer strength factor | Score |", "|---|---|"]
    frows += [f"| {k} | {v} |" for k, v in factors.items()]
    html = (
        f'<div class="gate {"g-ok" if score >= 70 else "g-no"}">Offer Strength '
        f'score: {score}/100 — '
        + ("a genuinely better offer than rivals" if score >= 70
           else "offer too weak — do not SELL NOW") + '</div>'
        + md_table(["| Element | Our offer |", "|---|---|"]
                   + [f"| {a} | {_esc(b)} |" for a, b in rows])
        + "<h3>Offer strength</h3>" + md_table(frows))
    return html, score, factors


def better_angles(kw, related, mode):
    """Weak/WATCH keyword? Suggest nearby angles with a stronger hook."""
    angles = []
    for r in (related or []):
        tag = _g(r, "tag", "keyword", "title")
        if tag and tag.lower() != kw.lower():
            angles.append((tag, _f(_g(r, "avg_conversion_rate", "conversion",
                                      "conversion_rate"))))
        if len(angles) >= 7:
            break
    if not angles:
        return "<p><em>No related angles returned this run.</em></p>"
    rows = ["_Nearby angles with a stronger gift / occasion hook — cross-check "
            "each with Analyze before committing._", "",
            "| Better angle | Conv | Why it may beat the seed |", "|---|---|---|"]
    for tag, conv in angles:
        rows.append(f"| {_esc(tag)} | {_pct(conv)} | more specific buyer intent |")
    best = max(angles, key=lambda a: a[1])[0]
    return md_table(rows) + f"<p><b>Best next angle to test:</b> {_esc(best)}</p>"


def sales_forecast(stats, price, cost, conv, data_flags):
    tier = _f(stats.get("avg_views_24h")) * _f(stats.get("total_listings"))
    vlo, vhi = (10, 40) if tier < 5000 else (20, 80) if tier < 30000 else (40, 150)
    favs = (max(0, vlo // 15), max(1, vhi // 15))
    carts = (0, max(1, vhi // 40))
    conv = conv or 0.025
    slo, shi = 0, max(1, round(vhi * conv))
    # per-sale fees ~12% = 6.5% txn + 3% payment + 2.5% USD->VND currency, + ~$0.45
    # flat (listing + payment fixed). Excludes the discretionary ad reserve.
    profit_each = max(0, (price or 0) - (cost or 0) - ((price or 0) * .12 + .45))
    return {
        "visits": f"{vlo}–{vhi}", "favorites": f"{favs[0]}–{favs[1]}",
        "carts": f"{carts[0]}–{carts[1]}", "sales": f"{slo}–{shi}",
        "breakeven": 1, "profit": f"$0–{_money(profit_each * shi)}",
        "scale": "1 sale OR 3+ favorites in 7 days",
        "kill": "0 views after 7 days",
        "confidence": "LOW" if data_flags or tier < 3000 else "MEDIUM",
    }


# --------------------------- product-line expansion ------------------------

def product_line_expansion(kw, mode):
    pod = ["shirt", "sweatshirt", "hoodie", "mug", "tote", "ornament", "poster"]
    emb = ["embroidered sweatshirt", "embroidered hoodie", "embroidered hat",
           "embroidered tote", "embroidered pouch", "embroidered patch",
           "monogram gift"]
    lst = emb if mode == "embroidery" else pod
    rows = ["| If this works, build next | Same idea, new form |", "|---|---|"]
    ideas = ["same design on other products", "same audience, new design",
             "same occasion, new product", "same product, new personalization",
             "bundle / matching set"]
    for i, base in enumerate(lst[:5]):
        rows.append(f"| {base} | {ideas[i]} |")
    return md_table(rows)


# --------------------------- design prompts + risk -------------------------

def design_prompts(kw, opts, mode):
    style = opts.get("style") or "clean, bold, giftable"
    pers = opts.get("personalization") or "name / date"
    pod = (f"Design a print-on-demand graphic for \"{kw}\".\n"
           f"Style: {style}. Audience: {opts.get('target_customer') or 'gift buyers'}.\n"
           "Full-color allowed. Transparent background, bold readable centered "
           "composition, high contrast, no photographic elements.\n"
           f"Leave a tasteful spot for personalization ({pers}).\n"
           "AVOID: trademarks, brand logos, copyrighted characters, tiny text, "
           "clip-art look, copying any competitor art.")
    emb = (f"Design a STITCH-SAFE embroidery motif for \"{kw}\".\n"
           "Rules: bold clean shapes, minimal fine detail, MAX 6 thread colors, "
           "flat fills, no thin lines, no gradients, no photorealism.\n"
           "Chest max 250mm wide; cap front max 120x60mm. Readable text only.\n"
           f"Personalization: {pers} in a bold legible font.\n"
           "Suggest 6 thread colors. AVOID: tiny detail, gradients, trademarks.")
    risks = []
    low = kw.lower()
    if mode == "embroidery":
        if any(w in low for w in ("raccoon", "cat", "dog", "fur", "animal",
                                  "portrait", "realistic", "photo")):
            risks.append("Detailed fur/photo subjects are hard to stitch — use a "
                         "simplified silhouette, bold outline, 3–5 color blocks.")
        if len(low.split()) > 4:
            risks.append("Long text embroiders poorly — keep to a short slogan.")
        risks.append("Keep to ≤6 thread colors and avoid gradients/tiny detail.")
    else:
        risks.append("Keep the main subject large and readable on the product "
                     "thumbnail; avoid clip-art.")
    return pod, emb, risks


# --------------------------- listing data ----------------------------------

def _listing_data(kw, opts, stats, related, mode, tags):
    title_kw = kw.title()
    parts = [title_kw]
    if opts.get("personalization"):
        parts.append(f"Personalized {opts['personalization'].title()}")
    else:
        parts.append("Personalized Gift")
    if opts.get("occasion"):
        parts.append(f"{opts['occasion'].title()} Gift")
    if opts.get("target_customer"):
        parts.append(f"Gift for {opts['target_customer'].title()}")
    if opts.get("style"):
        parts.append(opts["style"].title())
    title = ", ".join(dict.fromkeys(parts))[:140]

    lo, hi = stats.get("price_p25"), stats.get("price_p75")
    mid = stats.get("median_price") or stats.get("avg_price")
    cost_line, margin_line, rec_price, supplier, cost_total = "", "", None, None, None
    rec_profit, rec_margin_pct = 0.0, 0.0
    try:
        from src.idea_report import cluster_of, load_costs, margin_at
        cluster = cluster_of(kw.lower())
        assumed = ""
        if not cluster:   # slogan/phrase keyword -> assume it goes on apparel
            cluster, assumed = "apparel", " · assumed apparel (pick your product for exact cost)"
        costs = load_costs(mode=mode if mode in ("pod", "embroidery") else "pod")
        c = costs.get(cluster)
        if c:
            supplier, cost_total = c[2], c[0] + c[1]
            cost_line = f"Supplier: {c[2]} — cost {_money(cost_total)} ({cluster}{assumed})"
            p = 5.0
            while p < 200:
                if (margin_at(p, cluster, costs) or -1) >= 8:
                    rec_price = p
                    break
                p += 1
            if rec_price:   # true net profit + net margin % at the recommended price
                rec_profit = margin_at(rec_price, cluster, costs) or 0.0
                rec_margin_pct = round(rec_profit / rec_price * 100, 1) if rec_price else 0.0
            at_mid = margin_at(mid, cluster, costs) if mid else None
            if at_mid is not None:
                lowprofit = at_mid < 5
                margin_line = (f"At {_money(mid)} you'd make {_money(at_mid)}/sale"
                               + (f"; price ≥ {_money(rec_price)} for ~$8 profit"
                                  if rec_price else "")
                               + (" — margin thin: raise price, pick another "
                                  "supplier, or use a premium/personalized angle"
                                  if lowprofit else ""))
    except Exception:  # noqa: BLE001
        pass

    desc = (f"{title_kw} — made just for you.\n\n"
            f"★ Personalized: {opts.get('personalization') or '[what the buyer customizes]'}\n"
            "★ Material / size: [fill in]\n★ Ships in [X] business days\n\n"
            "How to order:\n1. Add to cart\n"
            "2. Leave your personalization in the note to seller\n3. We make + ship\n\n"
            f"A thoughtful gift for {opts.get('target_customer') or opts.get('occasion') or '[recipient / occasion]'}.")
    return {"title": title, "desc": desc, "price_lo": lo, "price_hi": hi,
            "price_mid": mid, "rec_price": rec_price, "cost_line": cost_line,
            "margin_line": margin_line, "supplier": supplier,
            "cost_total": cost_total, "rec_profit": rec_profit,
            "rec_margin_pct": rec_margin_pct}


# --------------------------- HTML bits -------------------------------------

def _copy_btn(tid, label="Copy"):
    return f'<button class="cbtn" data-copy="{tid}" type="button">{label}</button>'


def _score_grid(scores):
    cells = []
    for s in scores:
        est = ' <span class="est">est</span>' if s.get("estimate") else ""
        cells.append(
            f'<div class="score s{s["score"] // 20}">'
            f'<div class="sname">{_esc(s["name"])}{est}</div>'
            f'<div class="snum">{s["score"]}<i>/100</i></div>'
            f'<div class="sbar"><span style="width:{s["score"]}%"></span></div>'
            f'<div class="slabel">{_esc(s["label"])}</div>'
            f'<div class="swhy">{_esc(s["why"])}</div>'
            f'<div class="simp"><b>Improve:</b> {_esc(s["improve"])}</div>'
            f'<div class="simp"><b>Source:</b> {_esc(s["sources"])}</div>'
            f'</div>')
    return '<div class="scoregrid">' + "".join(cells) + "</div>"


def _tag_html(tags):
    rows = ["| # | Tag | Type | Status | Note |", "|---|---|---|---|---|"]
    for i, t in enumerate(tags, 1):
        mark = "✅" if t["publish_safe"] else "⚠️"
        rows.append(f"| {i} | {mark} {_esc(t['tag'])} | {t['type']} "
                    f"| {t['status']} | {_esc(t['reason'])} |")
    csv = ", ".join(t["tag"] for t in tags)
    n_safe = sum(1 for t in tags if t["publish_safe"])
    warn = ("" if n_safe == 13 else
            f'<p class="note">⚠️ {13 - n_safe} tag(s) flagged (typo/trademark) — '
            "fix before publishing.</p>")
    return (md_table(rows) + warn
            + '<div class="lbrow"><b>Copy all 13</b>'
            + _copy_btn("ws-tags") + '</div>'
            + f'<div class="lbval" id="ws-tags">{_esc(csv)}</div>')


def _preview_html(L, tags, verdict_cls):
    price = _money(L["rec_price"] or L["price_mid"])
    tag_html = "".join(f'<span>{_esc(t["tag"])}</span>' for t in tags[:8])
    return (
        '<div class="pv"><div><div class="pvmain">first image concept — bold, '
        'gift-ready</div><div class="pvthumbs"><i></i><i></i><i></i><i></i></div>'
        '<p class="note">Trust images needed: size chart, personalization example, '
        'lifestyle/gift shot.</p></div>'
        '<div class="pvinfo">'
        '<div class="pvshop">YourShopName · ★★★★★ <small>(reviews)</small></div>'
        f'<div class="pvtitle">{_esc(L["title"])}</div>'
        f'<div class="pvprice">{price} <small>Local taxes included</small></div>'
        '<label class="pvpers">Personalization<textarea placeholder="e.g. Name: ____">'
        '</textarea></label>'
        '<div class="pvqty">Qty <select><option>1</option><option>2</option></select></div>'
        '<button class="pvcart" type="button">Add to cart</button>'
        f'<details class="pvacc"><summary>Item details</summary><p>{_esc(L["desc"][:160])}…</p></details>'
        '<details class="pvacc"><summary>Shipping &amp; returns</summary>'
        '<p>Made to order · ships in a few business days.</p></details>'
        f'<div class="pvtags">13 SEO tags: {tag_html}…</div></div></div>'
        '<p class="note">Internal preview only — not a real marketplace page, no '
        'external branding.</p>')


def _mode_compare(kw, stats):
    """Side-by-side POD vs Embroidery for 'Both'."""
    rows = ["| | Print on Demand | Embroidery |", "|---|---|---|",
            "| Typical cost | ~$9–12 | ~$17 (incl. ship) |",
            "| Difficulty | Low | Medium (stitch limits) |",
            "| Design | Full-color print | Bold shapes, ≤6 colors |",
            "| Best for | Graphics, humor, big art | Names, monograms, premium |",
            "| Price ceiling | Lower | Higher (premium feel) |"]
    emb = matches_mode(kw.lower(), "embroidery")
    rec = ("Embroidery" if emb else "Print on Demand")
    why = ("the keyword reads embroidery/monogram — premium, higher price"
           if emb else "graphic/print intent — cheaper, faster, wider design range")
    return (md_table(rows) + f'<p><b>Recommended for "{_esc(kw)}": {rec}</b> — '
            f'{_esc(why)}. The workspace below is built for {rec}.</p>'), \
        ("embroidery" if emb else "pod")


# --------------------------- orchestration ---------------------------------

def save_qs(kw, opts):
    from urllib.parse import urlencode
    d = {"q": kw}
    d.update({k: v for k, v in opts.items() if v})
    return urlencode(d)


def suggest_fields(kw, stats, related, mode, req_mode):
    """AI-suggested value + source + confidence for each command-center field."""
    low = kw.lower()
    try:
        from src.idea_report import cluster_of
        cluster = cluster_of(low) or "apparel"
    except Exception:  # noqa: BLE001
        cluster = "apparel"
    relw = " ".join(_g(r, "tag", "keyword", "title") or "" for r in related[:8]).lower()

    def has(*ws):
        return any(w in low or w in relw for w in ws)

    cust = ("dads" if "dad" in low else "moms" if "mom" in low else
            "teachers" if "teacher" in low else "nurses" if "nurse" in low else
            "gift buyers, women 25-45")
    occ = ("4th of July" if has("usa", "4th", "july", "america", "patriot")
           else "Christmas" if has("christmas", "xmas")
           else "Valentine's" if has("valentine")
           else "birthday / gift-giving")
    style = ", ".join(w for w in ("funny", "retro", "vintage", "cute", "boho",
                                  "minimalist", "patriotic") if has(w)) \
        or "bold, giftable, personalized"
    pers = ("monogram" if "monogram" in low else "name" if "name" in low
            else "name / date")
    sup = ("Embroidery" if req_mode == "embroidery" or matches_mode(low, "embroidery")
           else "Both" if req_mode == "both" else "Print on Demand")

    def f(sug, src, conf):
        return {"suggestion": sug, "source": src, "confidence": conf}

    return {
        "product_type": f(cluster, "keyword + cluster map", "High"),
        "niche": f(_g(related[0], "tag", "keyword", "title") if related else kw,
                   "YTrends related keywords", "Medium"),
        "target_customer": f(cust, "keyword + Etsy buyer patterns", "Medium"),
        "occasion": f(occ, "keyword + seasonal calendar", "Medium"),
        "style": f(style, "competitor title words", "Medium"),
        "personalization": f(pers, "keyword intent", "Medium"),
        "supplier_type": f(sup, "keyword contains a product word", "High"),
    }


def _gather(kw, opts=None):
    """Fetch + compute one full run. Returns a dict used by the workspace render,
    the Manager/Seller/Designer reports, and save_run."""
    opts = {k: (v or "").strip() for k, v in (opts or {}).items()}
    kw = kw.strip()
    req_mode = (opts.get("supplier_type") or opts.get("mode") or "").lower()
    if req_mode not in MODES:
        req_mode = "embroidery" if matches_mode(kw.lower(), "embroidery") else "pod"

    rk = mcp.research_keyword(kw)
    stats = rk.get("stats", {}) if isinstance(rk, dict) else {}
    related = (rk.get("related_keywords") if isinstance(rk, dict) else None) or []
    listings = (rk.get("top_listings") if isinstance(rk, dict) else None) or []
    timeline = (rk.get("timeline") if isinstance(rk, dict) else None) or []
    try:
        comp = mcp.call("ytrends_analyze_competition", seed=kw, seed_type="keyword")
        comp = comp.get("data", comp) if isinstance(comp, dict) else {}
    except Exception:  # noqa: BLE001
        comp = {}
    mo = {}
    try:
        for t in mcp.trending_keywords(limit=8, search=kw):
            if (t.get("tag") or "").lower() == kw.lower():
                mo = t
                break
    except Exception:  # noqa: BLE001
        pass
    risk, tm_reason = tm_check(kw.lower())
    data_flags = data_check(stats, kw)

    compare_html, mode = "", req_mode
    if req_mode == "both":
        compare_html, mode = _mode_compare(kw, stats)

    scores = compute_scores(kw, stats, comp, mo, mode)
    src_rows, src_conf = source_confidence(stats, data_flags)
    tags = build_tags(kw, related, opts, mode)
    conv = _f(stats.get("avg_conversion_rate"))
    L = _listing_data(kw, opts, stats, related, mode, tags)
    # Manager sign-offs (checkboxes on the workspace form). PUBLISH_READY can only
    # become true when the manager explicitly confirms these; default = unconfirmed.
    confirms = {k: bool(opts.get("confirm_" + k)) for k in
                ("supplier", "competitor_audit", "material", "image", "trademark")}
    supplier_ok = confirms["supplier"]   # supplier is confirmed only by the manager
    cww_score, cww_scores, cww_gaps = can_we_win(kw, comp, listings, opts, mode,
                                                 supplier_ok)
    try:
        from src import learning
        learn_notes, learn_delta = learning.learning_note(
            kw, [t["tag"] for t in tags], L.get("supplier"))
        cww_score = _clamp(cww_score + learn_delta)
    except Exception:  # noqa: BLE001 - private learning must never break a run
        learn_notes, learn_delta = [], 0
    private_learning = {
        "private_learning_boost": max(0, learn_delta),
        "private_learning_warning": min(0, learn_delta),
        "private_learning_reason": "; ".join(learn_notes),
        "notes": learn_notes,
    }
    lr_score, lr_status, lr_reasons = launch_readiness(supplier_ok, tags, risk, L, opts, confirms)
    fib_score, fib_pattern, fib_plan = first_image_battle(listings)
    offer_html, offer_score, offer_factors = offer_builder(kw, opts, mode)
    vd = strict_verdict(kw, scores, comp, risk, data_flags, cww_score, lr_score,
                        fib_score, offer_score)
    ready, failed = publish_gate(kw, tags, supplier_ok, risk, data_flags,
                                 vd["cls"], lr_score, fib_score, offer_score, confirms)
    pod_prompt, emb_prompt, design_risks = design_prompts(kw, opts, mode)
    fc = sales_forecast(stats, L["rec_price"] or L["price_mid"], L["cost_total"],
                        conv, data_flags)
    audit_html, audit_status = competitor_audit(listings)
    return dict(
        kw=kw, opts=opts, req_mode=req_mode, mode=mode, stats=stats,
        related=related, listings=listings, comp=comp, mo=mo, risk=risk,
        tm_reason=tm_reason, data_flags=data_flags, compare_html=compare_html,
        scores=scores, vd=vd, src_rows=src_rows, src_conf=src_conf, tags=tags,
        conv=conv, L=L, ready=ready, failed=failed, pod_prompt=pod_prompt,
        emb_prompt=emb_prompt, design_risks=design_risks, fc=fc,
        audit_html=audit_html, audit_status=audit_status, timeline=timeline,
        cww_score=cww_score, cww_scores=cww_scores, cww_gaps=cww_gaps,
        lr_score=lr_score,
        lr_status=lr_status, lr_reasons=lr_reasons, fib_score=fib_score,
        fib_pattern=fib_pattern, fib_plan=fib_plan, offer_html=offer_html,
        offer_score=offer_score, offer_factors=offer_factors, supplier_ok=supplier_ok,
        learn_notes=learn_notes, confirms=confirms,
        private_learning=private_learning,
        suggestions=suggest_fields(kw, stats, related, mode, req_mode))


def build_workspace(kw, opts=None):
    G = _gather(kw, opts)
    kw, opts, req_mode, mode = G["kw"], G["opts"], G["req_mode"], G["mode"]
    stats, related, listings, comp = G["stats"], G["related"], G["listings"], G["comp"]
    risk, tm_reason, data_flags = G["risk"], G["tm_reason"], G["data_flags"]
    compare_html, scores, vd = G["compare_html"], G["scores"], G["vd"]
    src_rows, src_conf, tags, conv, L = (G["src_rows"], G["src_conf"], G["tags"],
                                         G["conv"], G["L"])
    ready, failed = G["ready"], G["failed"]
    pod_prompt, emb_prompt, design_risks = (G["pod_prompt"], G["emb_prompt"],
                                            G["design_risks"])
    fc, audit_html, audit_status = G["fc"], G["audit_html"], G["audit_status"]
    timeline = G["timeline"]
    cww_score, cww_scores = G["cww_score"], G["cww_scores"]
    cww_gaps = G["cww_gaps"]
    lr_score, lr_status, lr_reasons = G["lr_score"], G["lr_status"], G["lr_reasons"]
    fib_score, fib_pattern, fib_plan = G["fib_score"], G["fib_pattern"], G["fib_plan"]
    offer_score = G["offer_score"]
    confirms = G["confirms"]

    def sec(anchor, icon, title, inner):
        return (f'<section class="ws" id="{anchor}"><h2>{icon} {title}</h2>'
                f'{inner}</section>')

    # 1. verdict
    pub_line = ("<b>Do NOT publish.</b> Save this run and recheck in 2-4 weeks."
                if vd["cls"] == "watch" else
                "<b>Do NOT design/list.</b> Blocked — change the wording."
                if vd["cls"] == "avoid" else
                "Draft only — never auto-published." if vd["cls"] == "skip" else
                "Build the draft below (draft only until the QA gate passes).")
    verdict_html = (
        f'<div class="verdict v-{vd["cls"]}"><div class="vbig">{vd["verdict"]}</div>'
        f'<div class="vwhy">{_esc(vd["reason"])}. Confidence: {vd["confidence"]}.</div>'
        '<div class="vgrid">'
        f'<div><b>Product mode</b>{req_mode.upper()}</div>'
        f'<div><b>Best angle</b>{_esc(opts.get("niche") or "gift / occasion angle")}</div>'
        f'<div><b>Best customer</b>{_esc(opts.get("target_customer") or "gift buyers")}</div>'
        f'<div><b>Main risk</b>{"Trademark" if risk != "OK" else "Standing out on design"}</div>'
        f'<div><b>Trademark</b>{risk} — {_esc(tm_reason or "verify on USPTO")}</div>'
        f'<div><b>Next action</b>{pub_line}</div>'
        '</div></div>')
    if data_flags:
        verdict_html += ('<p class="note">⚠️ DATA_CHECK_REQUIRED: '
                         + "; ".join(_esc(f) for f in data_flags) + "</p>")

    # 3. source confidence
    sc_rows = ["| Source | Status | Confidence |", "|---|---|---|"]
    for n, st, cf in src_rows:
        sc_rows.append(f"| {n} | {st} | {cf} |")
    src_html = (md_table(sc_rows) + f'<p><b>Overall data confidence: {src_conf}.</b> '
                "Unavailable sources show SOURCE_NOT_AVAILABLE — never faked.</p>")

    # market
    from src.interactive import sparkline, trend_word
    _views = [p.get("total_views_24h") for p in timeline]
    _sp = sparkline(_views)
    spark_html = (f'<li>Demand (last ~6 mo): <code class="spark">{_sp}</code> — '
                  f'<b>{trend_word(_views)}</b></li>' if _sp else "")
    market_html = (
        '<ul class="facts">'
        f'<li><b>{_int(stats.get("total_listings"))}</b> listings · '
        f'<b>{_int(stats.get("total_sellers"))}</b> sellers · avg '
        f'<b>{_money(stats.get("avg_price"))}</b></li>'
        f'<li>Conversion <b>{_pct(conv)}</b> · demand:supply '
        f'<b>{stats.get("demand_supply_ratio","-")}</b> · buyer intent '
        f'<b>personalized / gift</b></li>'
        f'{spark_html}</ul>'
        '<h3>Related & long-tail keywords</h3>' + md_table(_rel_rows(related, 15)))

    # niches
    nrows = ["| Angle | Try this sub-keyword | Why |", "|---|---|---|"]
    seeds = [_g(r, "tag", "keyword", "title") for r in related[:6]]
    for i, (nm, mod) in enumerate([("Gift", "gift"),
                                   ("Occasion", opts.get("occasion") or "birthday"),
                                   ("Humor", "funny"), ("Personalized", "custom name"),
                                   ("Embroidery-friendly", "embroidered"),
                                   ("POD-friendly", "comfort colors")]):
        nrows.append(f"| {nm} | {mod} {kw} | pairs '{mod}' intent with real demand |")
    niche_html = md_table(nrows)

    # sales forecast
    fc_html = ('<ul class="facts">'
               f'<li>Expected visits: <b>{fc["visits"]}</b> · favorites '
               f'<b>{fc["favorites"]}</b> · carts <b>{fc["carts"]}</b> · sales '
               f'<b>{fc["sales"]}</b> (7 days)</li>'
               f'<li>Break-even: <b>{fc["breakeven"]} sale</b> · profit '
               f'<b>{fc["profit"]}</b></li>'
               f'<li>Scale trigger: {fc["scale"]} · Kill trigger: {fc["kill"]}</li>'
               f'<li>FORECAST_CONFIDENCE: <b>{fc["confidence"]}</b> — conservative '
               'estimate, not a promise</li></ul>')

    # supplier recommendation
    from src.supplier_pull import SUPPLIER_CATALOGS as _CATS
    _sup = (L["supplier"] or "").lower()
    _cat = next((u for k, u in _CATS.items() if _sup and _sup in k), None)
    _catlink = (f' · <a href="{_esc(_cat)}" target="_blank" rel="noopener">'
                'Open catalog ↗</a>' if _cat and _cat.startswith("http") else "")
    sup_html = ('<ul class="facts">'
                f'<li>Recommended: <b>{_esc(L["supplier"] or "NEED_SUPPLIER_DETAILS")}</b>'
                f' ({mode}) — {_esc(L["cost_line"] or "no cost on file")}{_catlink}</li>'
                f'<li>Status: <b>{"SUPPLIER_PARTIAL (costs on file, confirm product URL)" if L["supplier"] else "NEED_SUPPLIER_DETAILS"}</b> · product match: '
                f'<b>{"70/100" if L["supplier"] else "—"}</b></li>'
                f'<li>{_esc(L["margin_line"])}</li></ul>'
                f'<p><a class="cbtn" href="/suppliers?match={_urlquote(kw)}'
                f'&mode={req_mode}">🏭 Open Supplier panel — match / upload / '
                'confirm →</a></p>'
                '<p class="note">Confirm the exact product URL, base/shipping cost, '
                'material, size, and processing time before publish (no terminal '
                'needed — everything is on the Supplier panel).</p>')

    # listing builder + publish gate
    save_label = "Publish-ready ✅" if ready else "DRAFT ONLY — DO NOT PUBLISH"
    gate_rows = "".join(f"<li>{_esc(x)}</li>" for x in failed)
    def _ck(name, label):
        on = " checked" if confirms.get(name) else ""
        return (f'<label class="ckrow"><input type="checkbox" name="confirm_{name}" '
                f'value="1"{on}> {label}</label>')
    mgr_hidden = (f'<input type="hidden" name="q" value="{_esc(kw)}">'
                  f'<input type="hidden" name="supplier_type" value="{req_mode}">'
                  + "".join(f'<input type="hidden" name="{f}" value="{_esc(opts.get(f,""))}">'
                            for f in ("niche", "target_customer", "occasion", "style",
                                      "personalization", "product_type")))
    mgr_form = (
        '<details class="mgrsignoff"' + (" open" if not ready else "") + '>'
        '<summary>🔑 Manager sign-off — required before PUBLISH_READY</summary>'
        '<form method="get" action="/run">' + mgr_hidden
        + _ck("supplier", "Supplier confirmed (product URL + base/shipping cost + material)")
        + _ck("competitor_audit", "Competitor audit complete")
        + _ck("material", "Material / size / processing time verified")
        + _ck("image", "Image / mockup checklist complete")
        + _ck("trademark", "Trademark verified or approved "
              "(a known brand = HIGH can NEVER be cleared)")
        + '<button class="primary" type="submit">Apply manager sign-off →</button>'
        '<p class="note">This never publishes. It only recomputes PUBLISH_READY '
        'after a manager confirms each item — publishing stays a manual action you '
        'do yourself on Etsy.</p></form></details>')
    listing_html = (
        f'<div class="gate {"g-ok" if ready else "g-no"}">PUBLISH_READY: '
        f'{"true" if ready else "false"} — {save_label}</div>'
        + ("" if ready else '<div class="lbrow"><b>FAILED_PUBLISH_CHECKS</b></div>'
           f'<ul class="check">{gate_rows}</ul>')
        + mgr_form
        + '<div class="lbrow"><b>SEO title</b>' + _copy_btn("ws-title") + '</div>'
        f'<div class="lbval" id="ws-title">{_esc(L["title"])}</div>'
        + '<div class="lbrow"><b>13 tags (type + status)</b></div>' + _tag_html(tags)
        + '<div class="lbrow"><b>Description</b>' + _copy_btn("ws-desc") + '</div>'
        f'<pre class="lbval" id="ws-desc">{_esc(L["desc"])}</pre>'
        f'<p class="note">Market {_money(L["price_lo"])}–{_money(L["price_hi"])}; '
        f'{_esc(L["margin_line"])}. Draft only — never auto-published.</p>')

    # design
    risk_html = "".join(f'<li>{_esc(r)}</li>' for r in design_risks)
    design_html = (
        f'<div class="warn"><b>Design risk ({mode}):</b><ul>{risk_html}</ul></div>'
        '<div class="lbrow"><b>POD prompt</b>' + _copy_btn("ws-pod") + '</div>'
        f'<pre class="lbval" id="ws-pod">{_esc(pod_prompt)}</pre>'
        '<div class="lbrow"><b>Embroidery prompt (stitch-safe)</b>'
        + _copy_btn("ws-emb") + '</div>'
        f'<pre class="lbval" id="ws-emb">{_esc(emb_prompt)}</pre>')

    seller_html = ('<ul class="check">'
                   '<li>Verify trademark on USPTO before the exact phrase.</li>'
                   '<li>Confirm supplier product URL + costs (see above).</li>'
                   f'<li>Use the 13 tags; front-load "{_esc(kw)}" in the title.</li>'
                   '<li>Add 5+ original photos + personalization mockup + size chart.</li>'
                   '<li>Set processing time + personalization note.</li>'
                   '<li>Publish only when PUBLISH_READY = true.</li></ul>')

    designer_html = ('<ul class="facts">'
                     f'<li><b>Make:</b> original {mode} design for "{_esc(kw)}"</li>'
                     f'<li><b>Style:</b> {_esc(opts.get("style") or "clean, bold, giftable")}</li>'
                     f'<li><b>Personalization space:</b> {_esc(opts.get("personalization") or "name / date")}</li>'
                     + ("<li><b>Embroidery:</b> bold shapes, ≤6 thread colors, no tiny detail</li>"
                        if mode == "embroidery" else
                        "<li><b>POD:</b> high-contrast, transparent background, big subject</li>")
                     + '<li><b>Do NOT copy</b> any competitor art, photo, or title.</li></ul>')

    _q = save_qs(kw, opts)
    export_html = (
        '<div class="expbar">'
        f'<a class="cbtn" href="/run/save?{_q}">💾 Save run (JSON)</a>'
        f'<a class="cbtn" href="/run/export/manager?{_q}" target="_blank">'
        '🖨️ Manager PDF</a>'
        f'<a class="cbtn" href="/run/export/seller?{_q}" target="_blank">'
        '🖨️ Seller PDF</a>'
        f'<a class="cbtn" href="/run/export/designer?{_q}" target="_blank">'
        '🖨️ Designer PDF</a>'
        f'<a class="cbtn" href="/run/export/researcher?{_q}" target="_blank">'
        '🖨️ Researcher PDF</a>'
        + _copy_btn("ws-title", "Copy title") + _copy_btn("ws-tags", "Copy tags")
        + _copy_btn("ws-desc", "Copy description") + _copy_btn("ws-pod", "Copy POD")
        + _copy_btn("ws-emb", "Copy embroidery")
        + '</div><p class="note">Save writes workspace.json, listing_draft.json, '
        'design_prompts.txt, supplier_check.json, competitor_audit.json, '
        'sales_forecast.json, publish_gate.json, feedback_tracking.json under '
        '<code>reports/latest/runs/</code>. Each PDF button opens a print-ready '
        'page — use your browser\'s <b>Print → Save as PDF</b>. Never '
        'auto-published.</p>')

    # Can We Win: ONE merged table (Advantage | Score | Our play), where the play
    # is the MEASURED gap evidence for factors we could read from the rivals, and
    # the generic play otherwise. Plus a ranked "biggest gaps to exploit" list.
    _gap_play = {name: ev for name, _s, ev in cww_gaps}
    cww_rows = ["| Advantage | Score | Our play |", "|---|---|---|"]
    for _name, _play in CWW_FACTORS:
        _p = _gap_play.get(_name, _play)   # measured evidence beats the generic play
        cww_rows.append(f"| {_name} | {cww_scores.get(_name, '-')} | {_esc(_p)} |")
    learn_html = ""
    if G.get("learn_notes"):
        learn_html = ('<div class="learnbox"><b>🔒 Our private sales data</b><ul>'
                      + "".join(f"<li>{_esc(n)}</li>" for n in G["learn_notes"])
                      + '</ul></div>')
    # ranked, evidence-backed gaps measured from THIS niche's rivals
    _nl = len(listings or [])
    if cww_gaps:
        _items = "".join(
            f'<li><b>{_esc(name)}</b> ({int(sc)}/100) — {_esc(ev)}</li>'
            for name, sc, ev in cww_gaps[:3])
        gaps_html = (f'<h3>🎯 Biggest gaps to exploit (measured from {_nl} rivals)</h3>'
                     f'<ul class="facts">{_items}</ul>')
        _top, _ts, _tev = cww_gaps[0]
        edge_html = (f'<div class="edge"><b>Our biggest measured edge:</b> '
                     f'{_esc(_top)} — {_esc(_tev)}. Pair it with a strong first '
                     'image + original stitched art.</div>')
    else:
        gaps_html = ('<p class="note">No competitor listings returned — scores use '
                     'baseline defaults; re-run when rival data is available.</p>')
        edge_html = ('<div class="edge"><b>Our edge:</b> better first image + real '
                     'personalization + tighter long-tail SEO. (No rival data to '
                     'measure specific gaps this run.)</div>')
    cww_html = (
        f'<div class="gate {"g-ok" if cww_score >= 70 else "g-no"}">Can We Win '
        f'score: {cww_score}/100 — '
        + ("yes, we can differentiate" if cww_score >= 70
           else "edge is thin — do not SELL NOW") + '</div>'
        + learn_html + md_table(cww_rows) + gaps_html + edge_html)

    fib_html = (
        f'<div class="gate {"g-ok" if fib_score >= 75 else "g-no"}">First-image '
        f'score: {fib_score}/100'
        + ("" if fib_score >= 75 else " — improve the hero image before publishing")
        + '</div><h3>Top competitor image pattern</h3><ul class="facts">'
        + "".join(f'<li>{_esc(p)}</li>' for p in fib_pattern)
        + '</ul><h3>Our first-image plan</h3><ul class="facts">'
        + "".join(f'<li>{_esc(p)}</li>' for p in fib_plan) + '</ul>')

    lr_reason_html = "".join(f'<li>{_esc(r)}</li>' for r in lr_reasons)
    lr_html = (
        f'<div class="gate {"g-ok" if lr_score >= 85 else "g-no"}">Launch '
        f'Readiness: {lr_score}/100 — {lr_status}</div>'
        + ("" if lr_score >= 85 else '<b>Not ready — blockers:</b>'
           f'<ul class="check">{lr_reason_html}</ul>'))

    offer_html = G["offer_html"]
    angle_html = better_angles(kw, related, mode)

    # 0. AI-suggested, editable run inputs (re-run with edits)
    sg = G["suggestions"]

    def _fld(name, label):
        s = sg.get(name, {})
        cur = opts.get(name) or s.get("suggestion", "")
        return (f'<div class="fld"><label>{_esc(label)}</label>'
                f'<input name="{name}" value="{_esc(cur)}">'
                f'<div class="fmeta">AI: <b>{_esc(s.get("suggestion",""))}</b> · '
                f'{_esc(s.get("source",""))} · conf {_esc(s.get("confidence",""))}'
                '</div></div>')
    mode_opts = "".join(
        f'<option value="{v}"{" selected" if req_mode == v else ""}>{lbl}</option>'
        for v, lbl in (("pod", "Print on Demand"), ("embroidery", "Embroidery"),
                       ("both", "Both")))
    inputs_html = (
        '<p class="note">AI filled these from the data — edit any field and '
        're-run. Nothing is hidden; every suggestion shows its source + confidence.</p>'
        f'<form class="runedit" method="get" action="/run">'
        f'<input type="hidden" name="q" value="{_esc(kw)}">'
        '<div class="fld"><label>Product mode</label>'
        f'<select name="supplier_type">{mode_opts}</select>'
        '<div class="fmeta">AI: <b>' + _esc(sg["supplier_type"]["suggestion"])
        + '</b> · ' + _esc(sg["supplier_type"]["source"]) + ' · conf '
        + _esc(sg["supplier_type"]["confidence"]) + '</div></div>'
        + _fld("product_type", "Product type") + _fld("niche", "Niche")
        + _fld("target_customer", "Target customer") + _fld("occasion", "Occasion")
        + _fld("style", "Style") + _fld("personalization", "Personalization")
        + '<button class="primary" type="submit">Re-run with these ↻</button></form>')

    # --- assemble: collapsed inputs -> hero (verdict + at-a-glance) -> sticky
    #     nav -> 5 clearly-labelled groups. Easy to scan, easy to follow.
    overall = next((s["score"] for s in scores if s["name"] == "Overall Product"), 0)
    next_act = {"design": "Build the listing + get manager sign-off to publish.",
                "validate": "Publish 2 test listings from the draft.",
                "watch": "Save &amp; recheck in 2–4 weeks — do NOT publish.",
                "skip": "Try a better angle below, or a lower-competition keyword.",
                "avoid": "Change the wording — blocked."}[vd["cls"]]
    glance = (
        '<div class="glance">'
        f'<span class="chip">Overall <b>{overall}/100</b></span>'
        f'<span class="chip {"cg-ok" if cww_score >= 70 else "cg-no"}">Can we win '
        f'<b>{cww_score}/100</b></span>'
        f'<span class="chip {"cg-ok" if lr_score >= 85 else "cg-no"}">Launch-ready '
        f'<b>{lr_score}/100</b></span>'
        f'<span class="chip {"cg-ok" if fib_score >= 75 else "cg-no"}">First image '
        f'<b>{fib_score}/100</b></span>'
        f'<span class="chip {"cg-ok" if offer_score >= 70 else "cg-no"}">Offer '
        f'<b>{offer_score}/100</b></span>'
        f'<span class="chip">Mode <b>{req_mode.upper()}</b></span>'
        f'<span class="chip {"cg-ok" if ready else "cg-no"}">Publish-ready '
        f'<b>{"yes" if ready else "no"}</b></span>'
        f'<span class="chip">TM <b>{risk}</b></span>'
        f'<span class="chip wide">Next → <b>{next_act}</b></span></div>')
    hero = f'<section class="ws hero" id="top">{verdict_html}{glance}</section>'
    nav = ('<nav class="wsnav"><a href="#top">Verdict</a>'
           '<a href="#g1">① Decision</a><a href="#g2">🔬 Deeper</a>'
           '<a href="#g3">🚦 Listing</a><a href="#g4">🎨 Design</a>'
           '<a href="#g5">✅ Do next</a></nav>')

    def grp(gid, title):
        return f'<h2 class="wsgroup" id="{gid}">{title}</h2>'

    def dgrp(gid, title, hint, inner):
        # A collapsible group — keeps the page decision-first: the detail lives
        # one click away instead of scrolling past it every time.
        return (f'<details class="wsgrp" id="{gid}"><summary>'
                f'<span class="gt">{title}</span><span class="gh">{hint}</span>'
                f'<span class="chev">▸</span></summary>'
                f'<div class="wsgrpbody">{inner}</div></details>')

    inputs_block = ('<details class="ws inputsbox" id="inputs"><summary>📝 Run '
                    'inputs — AI-suggested &amp; editable (click to open)</summary>'
                    f'{inputs_html}</details>')

    # ① Decision — always open: the four things you actually decide on.
    out = inputs_block + hero + nav + grp("g1", "① The decision")
    if compare_html:
        out += sec("compare", "⚖️", "POD vs Embroidery — recommendation", compare_html)
    out += (
        sec("scores", "📊", "Opportunity scores (0–100)", _score_grid(scores))
        + sec("canwin", "🏆", "Can we win?", cww_html)
        + sec("market", "🔑", "Market &amp; keyword opportunity", market_html)
        + sec("sources", "🛰️", "Source confidence", src_html))
    # Everything else — one click away.
    out += dgrp(
        "g2", "🔬 Deeper analysis",
        "First image · niches · angles · offer · forecast · competitors",
        sec("firstimage", "🖼️", "First image battle", fib_html)
        + sec("niches", "💡", "Niche &amp; angle discovery", niche_html)
        + sec("angles", "🧭", "Better angle generator", angle_html)
        + sec("offer", "🎁", "Offer builder", offer_html)
        + sec("forecast", "📈", "7-day sales forecast", fc_html)
        + sec("competitors", "🔍", "Competitor audit", audit_html))
    out += dgrp(
        "g3", "🚦 Listing &amp; supplier",
        "Launch readiness · supplier · listing builder · preview",
        sec("readiness", "🚦", "Launch readiness", lr_html)
        + sec("supplier", "🏭", "Supplier recommendation", sup_html)
        + sec("listing", "🛠️", "Listing builder + publish gate", listing_html)
        + sec("preview", "👁️", "Internal product preview", _preview_html(L, tags, vd["cls"])))
    out += dgrp(
        "g4", "🎨 Design", "Design prompt · designer brief",
        sec("design", "🎨", "Design prompt generator", design_html)
        + sec("designer", "✏️", "Designer brief", designer_html))
    out += dgrp(
        "g5", "✅ Do next &amp; export",
        "Seller checklist · product-line · save / export",
        sec("seller", "✅", "Seller execution checklist", seller_html)
        + sec("expand", "🌱", "Product-line expansion", product_line_expansion(kw, mode))
        + sec("export", "📤", "Save / export", export_html))
    # Open a collapsed group when the sticky nav jumps to it.
    out += ('<script>(function(){function o(){var h=location.hash;if(!h)return;'
            'var e;try{e=document.querySelector(h);}catch(_){return;}'
            'while(e){if(e.tagName==="DETAILS")e.open=true;e=e.parentElement;}}'
            'window.addEventListener("hashchange",o);o();})();</script>')

    # stash structured data for save_run
    build_workspace._last = {
        "keyword": kw, "product_mode": req_mode, "verdict": vd,
        "publish_ready": ready, "failed_publish_checks": failed,
        "scores": [{k: s[k] for k in ("name", "score", "label", "sources")}
                   for s in scores],
        "gate_scores": {"can_we_win": cww_score, "launch_readiness": lr_score,
                        "first_image": fib_score, "offer_strength": offer_score,
                        "launch_status": lr_status},
        "manager_confirms": confirms,
        "private_learning": G["private_learning"],
        "tags": tags, "listing": {"title": L["title"], "desc": L["desc"],
                                  "supplier": L["supplier"], "cost": L["cost_total"],
                                  "rec_price": L["rec_price"]},
        "supplier_check": {"supplier_ok": G["supplier_ok"], "supplier": L["supplier"],
                           "status": ("SUPPLIER_CONFIRMED" if G["supplier_ok"]
                                      else "NEED_SUPPLIER_DETAILS"),
                           "cost_total": L["cost_total"], "mode": mode},
        "sales_forecast": fc, "competitor_audit_status": audit_status,
        "product_line_expansion": product_line_expansion(kw, mode),
        "publish_gate": {"publish_ready": ready, "failed_checks": failed},
        "source_confidence": {"overall": src_conf,
                              "sources": [dict(zip(("source", "status", "confidence"), r))
                                          for r in src_rows]},
        "data_check_required": data_flags,
        "design_prompts": {"pod": pod_prompt, "embroidery": emb_prompt,
                           "risks": design_risks},
    }
    return out


def save_run(kw, opts, workspace_html):
    from datetime import date
    from pathlib import Path
    import json
    slug = re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-")[:40] or "run"
    folder = Path("reports/latest/runs") / f"{date.today()}_{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    data = getattr(build_workspace, "_last", {"keyword": kw, "options": opts})
    data = {**data, "options": opts, "date": str(date.today())}
    (folder / "workspace.html").write_text(workspace_html, encoding="utf-8")
    (folder / "workspace.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (folder / "listing_draft.json").write_text(
        json.dumps({"listing": data.get("listing"), "tags": data.get("tags")},
                   indent=2), encoding="utf-8")
    dp = data.get("design_prompts", {})
    (folder / "design_prompts.txt").write_text(
        f"POD:\n{dp.get('pod','')}\n\nEMBROIDERY:\n{dp.get('embroidery','')}",
        encoding="utf-8")
    (folder / "competitor_audit.json").write_text(
        json.dumps({"status": data.get("competitor_audit_status")}, indent=2),
        encoding="utf-8")
    (folder / "source_confidence.json").write_text(
        json.dumps(data.get("source_confidence", {}), indent=2), encoding="utf-8")
    (folder / "supplier_check.json").write_text(
        json.dumps(data.get("supplier_check", {}), indent=2), encoding="utf-8")
    (folder / "sales_forecast.json").write_text(
        json.dumps(data.get("sales_forecast", {}), indent=2), encoding="utf-8")
    (folder / "product_line_expansion.json").write_text(
        json.dumps({"html": data.get("product_line_expansion", "")}, indent=2),
        encoding="utf-8")
    (folder / "publish_gate.json").write_text(
        json.dumps(data.get("publish_gate", {"publish_ready": False}), indent=2),
        encoding="utf-8")
    # Seed the Day-3/7 feedback tracker (empty until the team logs real numbers).
    ft = folder / "feedback_tracking.json"
    if not ft.exists():
        ft.write_text(json.dumps({
            "keyword": kw, "product_mode": data.get("product_mode"),
            "publish_ready_at_save": data.get("publish_ready", False),
            "listing_url": "", "publish_date": "",
            "day_3": {"logged": False}, "day_7": {"logged": False},
            "recommendation": "AWAITING_PUBLISH_AND_METRICS",
            "note": "Log real numbers in the Sales Feedback tool after manual publish."
        }, indent=2), encoding="utf-8")
    return folder


# --------------------------- role reports (print -> PDF) -------------------

def run_data(kw, opts=None):
    """Full structured run — used by the Manager/Seller/Designer reports."""
    return _gather(kw, opts)


def _score_table(G):
    rows = ["<table><tr><th>Score</th><th>/100</th><th>Sources</th></tr>"]
    for s in G["scores"]:
        rows.append(f"<tr><td>{_esc(s['name'])}</td><td><b>{s['score']}</b></td>"
                    f"<td>{_esc(s['sources'])}</td></tr>")
    return "".join(rows) + "</table>"


def manager_report(G):
    vd, fc, L = G["vd"], G["fc"], G["L"]
    failed = "".join(f"<li>{_esc(x)}</li>" for x in G["failed"])
    src = "".join(f"<li>{_esc(n)}: {_esc(st)} (conf {_esc(cf)})</li>"
                  for n, st, cf in G["src_rows"])
    return (
        f"<h1>Manager report — {_esc(G['kw'])}</h1>"
        f"<p class='meta'>Product mode: {G['req_mode'].upper()} · "
        f"Data confidence: {_esc(G['src_conf'])}</p>"
        f"<h2>Verdict: {vd['verdict']}</h2><p>{_esc(vd['reason'])}. "
        f"Confidence {vd['confidence']}.</p>"
        f"<p><b>Trademark:</b> {G['risk']} — {_esc(G['tm_reason'] or 'verify on USPTO')}</p>"
        "<h2>Opportunity scores</h2>" + _score_table(G)
        + f"<h2>Can We Win: {G['cww_score']}/100 · Launch Readiness: "
        f"{G['lr_score']}/100 ({G['lr_status']})</h2>"
        + (f"<p>Launch blockers: {_esc('; '.join(G['lr_reasons']))}</p>"
           if G['lr_reasons'] else "<p>Launch-ready.</p>")
        + f"<p>First-image score: {G['fib_score']}/100 · "
        f"Offer strength: {G['offer_score']}/100.</p>"
        + (("<h2>🔒 Our private sales data</h2><ul>"
            + "".join(f"<li>{_esc(n)}</li>" for n in G.get("learn_notes", []))
            + "</ul>") if G.get("learn_notes") else "")
        + "<h2>Source confidence</h2><ul>" + src + "</ul>"
        + (f"<p class='warn'>DATA_CHECK_REQUIRED: "
           f"{'; '.join(_esc(f) for f in G['data_flags'])}</p>" if G['data_flags'] else "")
        + f"<h2>Profit &amp; 7-day forecast</h2><p>{_esc(L['margin_line'] or L['cost_line'])}</p>"
        f"<ul><li>Expected sales: {fc['sales']} · profit {fc['profit']} · "
        f"break-even {fc['breakeven']}</li><li>Scale: {fc['scale']} · Kill: "
        f"{fc['kill']} · confidence {fc['confidence']}</li></ul>"
        f"<h2>Publish gate</h2><p><b>PUBLISH_READY: {'true' if G['ready'] else 'false'}</b></p>"
        + ("" if G['ready'] else f"<b>FAILED_PUBLISH_CHECKS</b><ul>{failed}</ul>")
        + "<h2>What to approve</h2><ul>"
        + ("<li>Approve design + listing build (draft).</li>"
           if vd['cls'] in ('design', 'validate')
           else f"<li>Do NOT approve publish — {_esc(vd['verdict'])}.</li>")
        + "<li>Require supplier + trademark confirmation before any publish.</li></ul>")


def seller_report(G):
    L, tags = G["L"], G["tags"]
    tag_rows = "".join(f"<tr><td>{i}</td><td>{_esc(t['tag'])}</td><td>{t['type']}</td>"
                       f"<td>{t['status']}</td></tr>" for i, t in enumerate(tags, 1))
    failed = "".join(f"<li>{_esc(x)}</li>" for x in G["failed"])
    return (
        f"<h1>Seller report — {_esc(G['kw'])}</h1>"
        f"<p class='meta'>Mode: {G['req_mode'].upper()}</p>"
        f"<h2>Listing {'(PUBLISH-READY)' if G['ready'] else '— DRAFT ONLY, DO NOT PUBLISH'}</h2>"
        f"<p><b>Title:</b> {_esc(L['title'])}</p>"
        "<h3>13 tags</h3><table><tr><th>#</th><th>Tag</th><th>Type</th>"
        f"<th>Status</th></tr>{tag_rows}</table>"
        f"<h3>Description</h3><pre>{_esc(L['desc'])}</pre>"
        f"<h2>Supplier &amp; price</h2><p>{_esc(L['cost_line'] or 'NEED_SUPPLIER_DETAILS')}. "
        f"{_esc(L['margin_line'])}</p>"
        f"<h2>Publish checklist</h2><p><b>PUBLISH_READY: {'true' if G['ready'] else 'false'}</b></p>"
        + ("" if G['ready'] else f"<ul>{failed}</ul>")
        + "<h2>Trademark checklist</h2><ul>"
        f"<li>Primary keyword: {G['risk']} — {_esc(G['tm_reason'] or 'verify USPTO')}</li>"
        "<li>Exclude any NEED_TM_CHECK / BLOCKED_TM tags from a published listing.</li>"
        "</ul>"
        f"<h2>Competitor notes</h2>{G['audit_html']}")


def designer_report(G):
    opts, mode = G["opts"], G["mode"]
    risks = "".join(f"<li>{_esc(r)}</li>" for r in G["design_risks"])
    return (
        f"<h1>Designer brief — {_esc(G['kw'])}</h1><p class='meta'>Mode: {mode}</p>"
        "<h2>Visual direction</h2><ul>"
        f"<li>Make: original {mode} design for \"{_esc(G['kw'])}\"</li>"
        f"<li>Style: {_esc(opts.get('style') or 'clean, bold, giftable')}</li>"
        f"<li>Personalization space: {_esc(opts.get('personalization') or 'name / date')}</li>"
        "<li>Do NOT copy any competitor art, photo, or title.</li></ul>"
        f"<h2>Design risk warnings</h2><ul>{risks}</ul>"
        f"<h2>First-image plan (score {G['fib_score']}/100)</h2><ul>"
        + "".join(f"<li>{_esc(p)}</li>" for p in G["fib_plan"]) + "</ul>"
        f"<h2>POD prompt</h2><pre>{_esc(G['pod_prompt'])}</pre>"
        f"<h2>Embroidery prompt (stitch-safe)</h2><pre>{_esc(G['emb_prompt'])}</pre>"
        "<h2>Mockup checklist</h2><ul><li>Hero image: bold subject, gift context.</li>"
        "<li>Lifestyle / in-use shot.</li><li>Personalization example.</li>"
        "<li>Size chart / detail shot.</li></ul>"
        "<h2>Avoid list</h2><ul><li>Trademarks, brand logos, copyrighted characters.</li>"
        "<li>Tiny text, clip-art look, copied designs.</li>"
        + ("<li>Embroidery: gradients, fine detail, more than 6 colors.</li>"
           if mode == "embroidery" else "") + "</ul>"
        "<h2>Competitor weakness to beat</h2><p>Generic art + weak first image; "
        "we win with a bold original hero image and real personalization.</p>")


def researcher_report(G):
    """Data / trademark / supplier verification checklist for the Researcher."""
    src = "".join(f"<li>{_esc(n)}: {_esc(st)} (conf {_esc(cf)})</li>"
                  for n, st, cf in G["src_rows"])
    tm_tags = [t for t in G["tags"]
               if t["status"] not in ("OK", "TYPO_FIXED")]
    tmq = ("".join(f"<li>{_esc(t['tag'])} — {t['status']}</li>" for t in tm_tags)
           or "<li>All 13 tags clear of trademark flags.</li>")
    flags = ("; ".join(_esc(f) for f in G["data_flags"]) if G["data_flags"]
             else "none — data passed the plausibility check")
    return (
        f"<h1>Researcher checklist — {_esc(G['kw'])}</h1>"
        f"<p class='meta'>Mode: {G['req_mode'].upper()} · Overall data confidence: "
        f"{_esc(G['src_conf'])}</p>"
        "<h2>Source confidence</h2><ul>" + src + "</ul>"
        f"<h2>Data check</h2><p>DATA_CHECK_REQUIRED: {flags}</p>"
        f"<h2>Trademark queue</h2><p>Primary keyword: <b>{G['risk']}</b> — "
        f"{_esc(G['tm_reason'] or 'verify on USPTO before publish')}</p>"
        f"<ul>{tmq}</ul>"
        f"<h2>Competitor audit</h2>{G['audit_html']}"
        "<h2>Supplier verification</h2><p><b>"
        + ("SUPPLIER_CONFIRMED" if G["supplier_ok"] else "NEED_SUPPLIER_DETAILS")
        + "</b> — confirm product URL, base + shipping cost, material, "
        "processing time, and (mode-specific) print area / embroidery area "
        "before PUBLISH_READY can be true.</p>"
        "<h2>Verify before publish</h2><ul>"
        "<li>Trademark cleared on USPTO or manager-approved.</li>"
        "<li>Supplier fields complete for the product mode.</li>"
        "<li>No DATA_CHECK_REQUIRED flags open.</li>"
        "<li>Competitor audit manual fields filled.</li></ul>")


ROLE_REPORTS = {"manager": manager_report, "seller": seller_report,
                "designer": designer_report, "researcher": researcher_report}
