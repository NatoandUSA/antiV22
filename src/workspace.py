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


def md_table(lines):
    import markdown as _md
    return _md.markdown("\n".join(lines), extensions=["tables"])


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
        ("X / Twitter", "off (add token)" if "off" in cc.get("X / Twitter", "")
         else "live", "—"),
        ("Supplier catalog", "on file (supplier_costs.csv)", "High"),
    ]
    overall = ("LOW — verify before acting" if data_flags else
               "MEDIUM" if google != "live" else "MEDIUM-HIGH")
    return rows, overall


# --------------------------- scoring ---------------------------------------

def compute_scores(kw, stats, comp, mo, mode):
    views = _f(stats.get("avg_views_24h")) * _f(stats.get("listing_count"))
    conv = _f(stats.get("avg_conversion_rate"))
    listings = _f(stats.get("total_listings"))
    sat = (comp.get("saturation") or "").lower()
    ner = _f(comp.get("new_entrant_rate"))
    ms, opp = mo.get("momentum_score"), mo.get("opportunity_score")
    words = len(kw.split())

    demand = _clamp((math.log10(views + 1) - 1.5) / 3.5 * 100) if views else 35
    competition = _clamp({"low": 82, "medium": 55, "high": 30}.get(sat, 52)
                         + (8 if ner > 0.01 else 0))
    conversion = _clamp(conv * 100 * 16 + 10)
    opportunity = _clamp(opp if opp is not None else (demand + competition) / 2)
    seo = _clamp((70 if 2 <= words <= 4 else 45 if words == 1 else 55)
                 + (10 if len(mo) else 0))
    trend = _clamp(ms if ms is not None else
                   (72 if _f(stats.get("rank_change_7d")) < 0 else 48))
    design = 78 if mode != "embroidery" else 70
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
          f"Saturation is {sat or 'unknown'} ({_int(comp.get('sellers'))} sellers).",
          "Higher = easier to rank. Narrow the sub-niche.", "YTrends"),
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

def strict_verdict(kw, scores, comp, risk, data_flags):
    by = {s["name"]: s["score"] for s in scores}
    overall, competition = by.get("Overall Product", 0), by.get("Competition", 0)
    if risk == "HIGH":
        v, cls = "BLOCKED", "avoid"
        reason = "trademark risk on this exact phrase is HIGH"
    elif overall >= 75 and competition >= 55 and not data_flags:
        v, cls = "SELL NOW", "design"
        reason = "strong demand, room to compete, and a clear gap"
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
    """Return exactly 13 tag dicts {tag,type,status,reason,publish_safe}."""
    cands = [kw]
    for k in ("niche", "occasion", "personalization", "style"):
        if opts.get(k):
            cands.append(opts[k])
    cands += [_g(r, "tag", "keyword", "title") for r in (related or [])]
    # mode-appropriate fallbacks so we ALWAYS reach 13 clean tags
    base = "embroidered" if mode == "embroidery" else "personalized"
    cands += [f"{base} gift", "custom gift", "gift for her", "gift for him",
              "unique gift idea", f"{kw} gift", "personalized present",
              "custom name gift", "gift for mom", "handmade style gift"]

    out, seen = [], set()
    for raw in cands:
        c = (raw or "").strip().lower()
        if not c or c in seen or not (3 <= len(c) <= 20):
            continue
        fixed, was_typo = _looks_typo(c)
        tag = fixed
        if tag in seen:
            continue
        risk, _ = tm_check(tag)
        if risk == "HIGH":
            status, safe, reason = "BLOCKED_TM", False, "trademark risk HIGH"
        elif risk == "CAUTION":
            status, safe, reason = "NEED_TM_CHECK", False, "verify trademark first"
        elif was_typo:
            status, safe, reason = "TYPO_FIXED", True, f"corrected from '{c}'"
        elif tag in _BROAD:
            status, safe, reason = "TOO_BROAD", True, "broad — pair with specifics"
        else:
            status, safe, reason = "OK", True, ""
        seen.add(tag)
        out.append({"tag": tag, "type": _tag_type(tag, kw), "status": status,
                    "reason": reason, "publish_safe": safe})
        if len(out) >= 13:
            break
    return out[:13]


# --------------------------- publish-ready QA gate -------------------------

def publish_gate(kw, tags, supplier_ok, risk, data_flags, verdict_cls):
    """Strict gate. Returns (ready, failed_checks[])."""
    failed = []
    clean_safe = [t for t in tags if t["publish_safe"]]
    if verdict_cls in ("watch", "skip", "avoid"):
        failed.append(f"verdict is {verdict_cls.upper()} — not for publishing")
    if len(tags) != 13:
        failed.append(f"need exactly 13 tags (have {len(tags)})")
    if len(clean_safe) != 13:
        failed.append(f"{13 - len(clean_safe)} tag(s) need typo/trademark review")
    if any(t["status"].startswith("BLOCKED") for t in tags):
        failed.append("a tag has HIGH trademark risk")
    if risk in ("HIGH", "CAUTION"):
        failed.append("primary keyword trademark not verified/approved")
    if not supplier_ok:
        failed.append("supplier + product URL + costs not confirmed "
                      "(NEED_SUPPLIER_DETAILS)")
    if data_flags:
        failed.append("DATA_CHECK_REQUIRED on source data")
    # always-manual gates for a brand-new draft
    failed += ["competitor audit manual fields incomplete",
               "material / size / processing time not verified",
               "image / mockup checklist not complete"]
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


# --------------------------- sales forecast --------------------------------

def sales_forecast(stats, price, cost, conv, data_flags):
    tier = _f(stats.get("avg_views_24h")) * _f(stats.get("listing_count"))
    vlo, vhi = (10, 40) if tier < 5000 else (20, 80) if tier < 30000 else (40, 150)
    favs = (max(0, vlo // 15), max(1, vhi // 15))
    carts = (0, max(1, vhi // 40))
    conv = conv or 0.025
    slo, shi = 0, max(1, round(vhi * conv))
    profit_each = max(0, (price or 0) - (cost or 0) - ((price or 0) * .095 + .45))
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
    try:
        from src.idea_report import cluster_of, load_costs, margin_at
        cluster = cluster_of(kw.lower())
        costs = load_costs(mode=mode if mode in ("pod", "embroidery") else "pod")
        c = costs.get(cluster) if cluster else None
        if c:
            supplier, cost_total = c[2], c[0] + c[1]
            cost_line = f"Supplier: {c[2]} — cost {_money(cost_total)} ({cluster})"
            p = 5.0
            while p < 200:
                if (margin_at(p, cluster, costs) or -1) >= 8:
                    rec_price = p
                    break
                p += 1
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
            "cost_total": cost_total}


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


def build_workspace(kw, opts=None):
    opts = {k: (v or "").strip() for k, v in (opts or {}).items()}
    kw = kw.strip()
    req_mode = (opts.get("supplier_type") or opts.get("mode") or "").lower()
    if req_mode not in MODES:
        req_mode = "embroidery" if matches_mode(kw.lower(), "embroidery") else "pod"

    # fetch once
    rk = mcp.research_keyword(kw)
    stats = rk.get("stats", {}) if isinstance(rk, dict) else {}
    related = (rk.get("related_keywords") if isinstance(rk, dict) else None) or []
    listings = (rk.get("top_listings") if isinstance(rk, dict) else None) or []
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

    compare_html = ""
    mode = req_mode
    if req_mode == "both":
        compare_html, mode = _mode_compare(kw, stats)

    scores = compute_scores(kw, stats, comp, mo, mode)
    vd = strict_verdict(kw, scores, comp, risk, data_flags)
    src_rows, src_conf = source_confidence(stats, data_flags)
    tags = build_tags(kw, related, opts, mode)
    conv = _f(stats.get("avg_conversion_rate"))
    L = _listing_data(kw, opts, stats, related, mode, tags)
    supplier_ok = False   # brand-new run: needs manual supplier confirmation
    ready, failed = publish_gate(kw, tags, supplier_ok, risk, data_flags, vd["cls"])
    pod_prompt, emb_prompt, design_risks = design_prompts(kw, opts, mode)
    fc = sales_forecast(stats, L["rec_price"] or L["price_mid"], L["cost_total"],
                        conv, data_flags)
    audit_html, audit_status = competitor_audit(listings)

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
    market_html = (
        '<ul class="facts">'
        f'<li><b>{_int(stats.get("total_listings"))}</b> listings · '
        f'<b>{_int(stats.get("total_sellers"))}</b> sellers · avg '
        f'<b>{_money(stats.get("avg_price"))}</b></li>'
        f'<li>Conversion <b>{_pct(conv)}</b> · demand:supply '
        f'<b>{stats.get("demand_supply_ratio","-")}</b> · buyer intent '
        f'<b>personalized / gift</b></li></ul>'
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
    sup_html = ('<ul class="facts">'
                f'<li>Recommended: <b>{_esc(L["supplier"] or "NEED_SUPPLIER_DETAILS")}</b>'
                f' ({mode}) — {_esc(L["cost_line"] or "no cost on file")}</li>'
                f'<li>Status: <b>{"SUPPLIER_PARTIAL (costs on file, confirm product URL)" if L["supplier"] else "NEED_SUPPLIER_DETAILS"}</b></li>'
                f'<li>{_esc(L["margin_line"])}</li></ul>'
                '<p class="note">Confirm the exact product URL, base/shipping cost, '
                'material, size, and processing time before publish.</p>')

    # listing builder + publish gate
    save_label = "Publish-ready ✅" if ready else "DRAFT ONLY — DO NOT PUBLISH"
    gate_rows = "".join(f"<li>{_esc(x)}</li>" for x in failed)
    listing_html = (
        f'<div class="gate {"g-ok" if ready else "g-no"}">PUBLISH_READY: '
        f'{"true" if ready else "false"} — {save_label}</div>'
        + ("" if ready else '<div class="lbrow"><b>FAILED_PUBLISH_CHECKS</b></div>'
           f'<ul class="check">{gate_rows}</ul>')
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

    export_html = (
        '<div class="expbar">'
        f'<a class="cbtn" href="/run/save?{save_qs(kw, opts)}">💾 Save run (JSON)</a>'
        + _copy_btn("ws-title", "Copy title") + _copy_btn("ws-tags", "Copy tags")
        + _copy_btn("ws-desc", "Copy description") + _copy_btn("ws-pod", "Copy POD")
        + _copy_btn("ws-emb", "Copy embroidery")
        + '</div><p class="note">Save writes workspace.json, listing_draft.json, '
        'design_prompts.txt, competitor_audit.json, source_confidence.json under '
        '<code>reports/latest/runs/</code>. Bilingual Manager/Seller/Designer PDF '
        'export is the next upgrade. Never auto-published.</p>')

    out = sec("verdict", "🧭", "Product verdict", verdict_html)
    if compare_html:
        out += sec("compare", "⚖️", "POD vs Embroidery", compare_html)
    out += (
        sec("scores", "📊", "Opportunity scores (0–100)", _score_grid(scores))
        + sec("sources", "🛰️", "Source confidence &amp; freshness", src_html)
        + sec("beat", "🥊", "How we beat competitors", beat_competitors(kw, listings, opts, mode))
        + sec("market", "🔑", "Market &amp; keyword opportunity", market_html)
        + sec("niches", "💡", "Niche &amp; angle discovery", niche_html)
        + sec("forecast", "📈", "7-day sales forecast", fc_html)
        + sec("supplier", "🏭", "Supplier recommendation", sup_html)
        + sec("listing", "🛠️", "Listing builder + publish gate", listing_html)
        + sec("preview", "👁️", "Internal product preview", _preview_html(L, tags, vd["cls"]))
        + sec("competitors", "🔍", "Competitor audit", audit_html)
        + sec("design", "🎨", "Design prompt generator", design_html)
        + sec("seller", "✅", "Seller execution checklist", seller_html)
        + sec("designer", "✏️", "Designer brief", designer_html)
        + sec("expand", "🌱", "Product-line expansion", product_line_expansion(kw, mode))
        + sec("export", "📤", "Save / export", export_html))

    # stash structured data for save_run
    build_workspace._last = {
        "keyword": kw, "product_mode": req_mode, "verdict": vd,
        "publish_ready": ready, "failed_publish_checks": failed,
        "scores": [{k: s[k] for k in ("name", "score", "label", "sources")}
                   for s in scores],
        "tags": tags, "listing": {"title": L["title"], "desc": L["desc"],
                                  "supplier": L["supplier"], "cost": L["cost_total"],
                                  "rec_price": L["rec_price"]},
        "sales_forecast": fc, "competitor_audit_status": audit_status,
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
    return folder
