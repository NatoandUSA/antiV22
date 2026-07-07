"""Keyword Run Workspace — the one-keyword-to-everything page.

A team member types one keyword and gets a single interactive page: a verdict,
9 opportunity scores, the market/keyword read, niche angles, an automatic
listing draft, an internal (non-Etsy-branded) product preview, design prompts,
and seller/designer action lists — all live from the YTrends MCP.

This composes existing pieces (src/interactive, src/idea_report cost model,
src/ytrends_mcp) into HTML. It NEVER auto-publishes and always flags trademark
risk + labels estimated scores as estimates.
"""
import html as _html
import math

from src import ytrends_mcp as mcp
from src.discover import matches_mode
from src.trademark import check as tm_check
from src.interactive import _money, _int, _pct, _g, _rel_rows  # reuse formatters


# --------------------------- scoring ---------------------------------------

def _clamp(v):
    try:
        return max(0, min(100, int(round(v))))
    except (TypeError, ValueError):
        return 0


def _label(s):
    return ("Excellent" if s >= 90 else "Strong" if s >= 75 else
            "Good, needs work" if s >= 60 else "Weak" if s >= 40 else
            "Avoid / rethink")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute_scores(kw, stats, comp, mo, mode):
    """Return a list of {name, score, why, improve, estimate} (0-100)."""
    views = _f(stats.get("avg_views_24h")) * _f(stats.get("listing_count"))
    conv = _f(stats.get("avg_conversion_rate"))
    listings = _f(stats.get("total_listings"))
    sat = (comp.get("saturation") or "").lower()
    ner = _f(comp.get("new_entrant_rate"))
    ms = mo.get("momentum_score")
    opp = mo.get("opportunity_score")
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
    design = 78 if mode != "embroidery" else 70          # estimate
    production = 80 if mode == "pod" else 68 if mode == "embroidery" else 88
    overall = _clamp(demand * .2 + competition * .15 + opportunity * .2
                     + conversion * .15 + seo * .1 + trend * .1
                     + design * .05 + production * .05)

    def s(name, sc, why, improve, est=False):
        return {"name": name, "score": sc, "label": _label(sc),
                "why": why, "improve": improve, "estimate": est}

    return [
        s("Overall Product", overall,
          "Weighted blend of every signal below.",
          "Lift the weakest scores first."),
        s("Demand", demand,
          f"~{_int(views)} market views/day across {_int(listings)} listings.",
          "Higher demand = more buyers searching. Add high-intent long-tails."),
        s("Competition", competition,
          f"Market saturation is {sat or 'unknown'} "
          f"({_int(comp.get('sellers'))} sellers).",
          "Higher = easier to rank. Narrow to a less crowded sub-niche."),
        s("Opportunity", opportunity,
          "Low competition + real demand = opportunity.",
          "Chase high-opportunity, low-competition angles."),
        s("SEO", seo,
          f"'{kw}' is {words}-word "
          f"({'good long-tail' if 2 <= words <= 4 else 'broad' if words == 1 else 'very narrow'}).",
          "Use 2-4 word buyer phrases in the title + all 13 tags.", est=True),
        s("Conversion", conversion,
          f"Niche converts at ~{_pct(conv)}.",
          "Improve photos + offer + personalization to lift conversion."),
        s("Design Potential", design,
          "How much a distinctive design can differentiate here.",
          "Aim for an original angle, not a copy.", est=True),
        s("Production Feasibility", production,
          f"How easily this ships as {mode or 'a product'}.",
          "Embroidery: keep shapes bold, few colors.", est=True),
        s("Trend / Seasonality", trend,
          "Momentum + rank movement over the last week.",
          "Ride rising terms; time seasonal ones 4-6 weeks early.", est=True),
    ]


# --------------------------- verdict ---------------------------------------

def compute_verdict(kw, scores, comp, risk, opts):
    by = {s["name"]: s["score"] for s in scores}
    overall = by.get("Overall Product", 0)
    if risk == "HIGH":
        v, cls, reason = ("AVOID DUE TO RISK", "avoid",
                          "the trademark risk on this exact phrase is HIGH")
    elif overall >= 72 and by.get("Competition", 0) >= 50:
        v, cls, reason = ("DESIGN NOW", "design",
                          "strong demand and room to compete")
    elif overall >= 58:
        v, cls, reason = ("VALIDATE FIRST", "validate",
                          "promising, but test with 2 listings before a big batch")
    elif overall >= 47:
        v, cls, reason = ("WATCH / SAVE FOR LATER", "watch",
                          "mixed signals — save and revisit")
    else:
        v, cls, reason = ("SKIP", "skip", "the numbers don't support it right now")
    angle = opts.get("niche") or opts.get("occasion") or "personalized / gift angle"
    customer = opts.get("target_customer") or "gift buyers searching this term"
    action = {"design": "Send to the designer + build the listing below.",
              "validate": "Publish 2 test listings from the draft below.",
              "watch": "Save this run; recheck in 2-4 weeks.",
              "skip": "Try a nearby, lower-competition keyword.",
              "avoid": "Change the wording to a non-trademarked phrase."}[cls]
    main_risk = ("Trademark — verify on USPTO" if risk in ("HIGH", "CAUTION")
                 else "Crowded market" if by.get("Competition", 100) < 45
                 else "Standing out on design + photos")
    return {"verdict": v, "cls": cls, "reason": reason, "angle": angle,
            "customer": customer, "risk": main_risk, "action": action}


# --------------------------- HTML rendering --------------------------------

def _esc(t):
    return _html.escape(str(t or ""))


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
            f'</div>')
    return '<div class="scoregrid">' + "".join(cells) + "</div>"


def _copy_btn(target_id, label="Copy"):
    return (f'<button class="cbtn" data-copy="{target_id}" type="button">'
            f'{label}</button>')


def _listing_data(kw, opts, stats, related, mode):
    """Structured listing draft (title, tags, description, price…)."""
    title_kw = kw.title()
    style = opts.get("style", "")
    pers = opts.get("personalization", "")
    occ = opts.get("occasion", "")
    cust = opts.get("target_customer", "")
    parts = [title_kw]
    if pers:
        parts.append(f"Personalized {pers.title()}")
    else:
        parts.append("Personalized Gift")
    if occ:
        parts.append(f"{occ.title()} Gift")
    if cust:
        parts.append(f"Gift for {cust.title()}")
    if style:
        parts.append(style.title())
    title = ", ".join(dict.fromkeys(parts))[:140]

    tags, seen = [], set()
    for cand in [kw] + [opts.get("niche"), opts.get("occasion")] + \
                [_g(r, "tag", "keyword", "title") for r in (related or [])]:
        c = (cand or "").strip().lower()
        if c and c not in seen and 3 <= len(c) <= 20:
            r2, _ = tm_check(c)
            if r2 != "HIGH":
                seen.add(c)
                tags.append(c)
        if len(tags) >= 13:
            break

    lo, hi = stats.get("price_p25"), stats.get("price_p75")
    mid = stats.get("median_price") or stats.get("avg_price")
    cost_line, margin_line, rec_price = "", "", None
    try:
        from src.idea_report import cluster_of, load_costs, margin_at
        cluster = cluster_of(kw.lower())
        costs = load_costs(mode=mode)
        c = costs.get(cluster) if cluster else None
        if c:
            cost_line = (f"Supplier: {c[2]} — cost {_money(c[0] + c[1])} "
                         f"({cluster})")
            p = 5.0
            while p < 200:
                if (margin_at(p, cluster, costs) or -1) >= 8:
                    rec_price = p
                    break
                p += 1
            at_mid = margin_at(mid, cluster, costs) if mid else None
            if at_mid is not None:
                margin_line = (f"At {_money(mid)} you'd make {_money(at_mid)}/sale"
                               + (f"; price ≥ {_money(rec_price)} for ~$8 profit"
                                  if rec_price else ""))
    except Exception:  # noqa: BLE001
        pass

    desc = (f"{title_kw} — made just for you.\n\n"
            f"★ Personalized: {pers or '[what the buyer customizes]'}\n"
            "★ Material / size: [fill in]\n"
            "★ Ships in [X] business days\n\n"
            "How to order:\n1. Add to cart\n"
            "2. Leave your personalization in the note to seller\n"
            "3. We make it and ship\n\n"
            f"A thoughtful gift for {cust or occ or '[occasion / recipient]'}.")
    return {"title": title, "tags": tags[:13], "desc": desc,
            "price_lo": lo, "price_hi": hi, "price_mid": mid,
            "rec_price": rec_price, "cost_line": cost_line,
            "margin_line": margin_line}


def _listing_html(L):
    tags_str = ", ".join(L["tags"])
    price = _money(L["rec_price"] or L["price_mid"])
    return (
        '<div class="lb">'
        '<div class="lbrow"><b>Title</b>' + _copy_btn("ws-title") + '</div>'
        f'<div class="lbval" id="ws-title">{_esc(L["title"])}</div>'
        '<div class="lbrow"><b>13 Tags</b>' + _copy_btn("ws-tags") + '</div>'
        f'<div class="lbval" id="ws-tags">{_esc(tags_str)}</div>'
        + (f'<p class="note">Only {len(L["tags"])}/13 clean tags — add '
           f'{13 - len(L["tags"])} of your own.</p>' if len(L["tags"]) < 13 else "")
        + '<div class="lbrow"><b>Description</b>' + _copy_btn("ws-desc") + '</div>'
        f'<pre class="lbval" id="ws-desc">{_esc(L["desc"])}</pre>'
        '<div class="lbrow"><b>Price &amp; margin</b></div>'
        f'<div class="lbval">Market {_money(L["price_lo"])}–{_money(L["price_hi"])} '
        f'(mid {_money(L["price_mid"])}). {_esc(L["cost_line"])}. '
        f'{_esc(L["margin_line"])}</div>'
        '<p class="note">Draft only — never auto-published. Review, personalize, '
        'add your own photos, and verify the trademark before publishing.</p>'
        '</div>')


def _preview_html(L, shop="YourShopName"):
    """Internal marketplace-style preview — NOT Etsy, no branding."""
    price = _money(L["rec_price"] or L["price_mid"])
    tags = "".join(f'<span>{_esc(t)}</span>' for t in L["tags"][:8])
    return (
        '<div class="pv">'
        '<div class="pvgal"><div class="pvmain">product image</div>'
        '<div class="pvthumbs"><i></i><i></i><i></i><i></i></div></div>'
        '<div class="pvinfo">'
        f'<div class="pvshop">{_esc(shop)} · ★★★★★ <small>(reviews)</small></div>'
        f'<div class="pvtitle">{_esc(L["title"])}</div>'
        f'<div class="pvprice">{price} <small>Local taxes included</small></div>'
        '<label class="pvpers">Personalization<textarea '
        'placeholder="e.g. Name: ____"></textarea></label>'
        '<div class="pvqty">Qty <select><option>1</option><option>2</option>'
        '<option>3</option></select></div>'
        '<button class="pvcart" type="button">Add to cart</button>'
        '<details class="pvacc"><summary>Item details</summary>'
        f'<p>{_esc(L["desc"][:180])}…</p></details>'
        '<details class="pvacc"><summary>Shipping &amp; returns</summary>'
        '<p>Made to order · ships in a few business days.</p></details>'
        f'<div class="pvtags">Internal SEO tags: {tags}</div>'
        '</div></div>'
        '<p class="note">Internal preview only — not a real marketplace page, '
        'no external branding. Shows roughly how the listing reads to a buyer.</p>')


def _design_prompts(kw, opts, mode):
    style = opts.get("style") or "clean, modern, giftable"
    pers = opts.get("personalization") or "name / date"
    pod = (f"Design a print-on-demand graphic for an Etsy product about "
           f"\"{kw}\".\nStyle: {style}. Audience: "
           f"{opts.get('target_customer') or 'gift buyers'}.\n"
           "Deliver a bold, original, centered composition that reads at a "
           "glance on a shirt/tote/mug. Transparent background, high contrast, "
           "no photographic elements.\n"
           f"Include a tasteful spot for personalization ({pers}).\n"
           "Avoid: trademarks, brand logos, copyrighted characters, tiny "
           "unreadable text, clip-art look.")
    emb = (f"Design an EMBROIDERY motif for \"{kw}\".\n"
           "Rules for stitchability: bold clean shapes, minimal fine detail, "
           "max 6 thread colors, flat fills, no thin lines or gradients.\n"
           "Chest max 250mm wide; cap front max 120x60mm.\n"
           f"Personalization: {pers} in a bold, legible font.\n"
           "Suggest 6 thread colors. Avoid: photorealism, tiny text, "
           "gradients, trademarks.")
    return pod, emb


def build_workspace(kw, opts=None):
    """Return the full workspace HTML for a keyword. Raises on hard MCP failure."""
    opts = {k: (v or "").strip() for k, v in (opts or {}).items()}
    kw = kw.strip()
    mode = opts.get("supplier_type") or (
        "embroidery" if matches_mode(kw.lower(), "embroidery") else "pod")
    mode = mode.lower()
    if mode not in ("pod", "embroidery", "digital", "other"):
        mode = "pod"

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
    risk, reason = tm_check(kw.lower())

    scores = compute_scores(kw, stats, comp, mo, mode)
    vd = compute_verdict(kw, scores, comp, risk, opts)
    L = _listing_data(kw, opts, stats, related, mode)
    pod_prompt, emb_prompt = _design_prompts(kw, opts, mode)

    def sec(anchor, icon, title, inner):
        return (f'<section class="ws" id="{anchor}"><h2>{icon} {title}</h2>'
                f'{inner}</section>')

    # A. Verdict
    verdict_html = (
        f'<div class="verdict v-{vd["cls"]}">'
        f'<div class="vbig">{vd["verdict"]}</div>'
        f'<div class="vwhy">{_esc(vd["reason"])}.</div>'
        '<div class="vgrid">'
        f'<div><b>Best angle</b>{_esc(vd["angle"])}</div>'
        f'<div><b>Best customer</b>{_esc(vd["customer"])}</div>'
        f'<div><b>Main risk</b>{_esc(vd["risk"])}</div>'
        f'<div><b>Next action</b>{_esc(vd["action"])}</div>'
        f'<div><b>Trademark</b>{risk} — {_esc(reason or "verify on USPTO")}</div>'
        '</div></div>')

    # C. Market & keyword opportunity
    market_html = (
        '<ul class="facts">'
        f'<li><b>{_int(stats.get("total_listings"))}</b> listings · '
        f'<b>{_int(stats.get("total_sellers"))}</b> sellers</li>'
        f'<li>Avg price <b>{_money(stats.get("avg_price"))}</b> '
        f'(sweet spot {_money(stats.get("median_price"))})</li>'
        f'<li>Conversion <b>{_pct(stats.get("avg_conversion_rate"))}</b> · '
        f'demand:supply <b>{stats.get("demand_supply_ratio", "-")}</b></li>'
        f'<li>Buyer intent: <b>personalized / gift</b> (high-intent)</li>'
        '</ul><h3>Related & long-tail keywords</h3>'
        + md_table(_rel_rows(related, limit=15)))

    # D. Niches / angles
    niche_rows = ["| Angle | Try this sub-keyword | Why |", "|---|---|---|"]
    seedset = [_g(r, "tag", "keyword", "title") for r in related[:6]]
    angles = [("Gift", "gift"), ("Occasion", opts.get("occasion") or "birthday"),
              ("Humor", "funny"), ("Personalized", "custom name"),
              ("Embroidery-friendly", "embroidered"), ("POD-friendly", "comfort colors")]
    for i, (name, mod) in enumerate(angles):
        seed = seedset[i] if i < len(seedset) and seedset[i] else kw
        niche_rows.append(f"| {name} | {mod} {kw} | pairs '{mod}' intent with "
                          f"the '{seed}' demand |")
    niche_html = md_table(niche_rows)

    # G. Design prompts
    prompts_html = (
        '<div class="lbrow"><b>Print-on-Demand prompt</b>'
        + _copy_btn("ws-pod") + '</div>'
        f'<pre class="lbval" id="ws-pod">{_esc(pod_prompt)}</pre>'
        '<div class="lbrow"><b>Embroidery prompt (stitch-safe)</b>'
        + _copy_btn("ws-emb") + '</div>'
        f'<pre class="lbval" id="ws-emb">{_esc(emb_prompt)}</pre>')

    # H. Seller checklist
    seller_html = (
        '<ul class="check">'
        '<li>Verify the trademark on USPTO before using the exact phrase.</li>'
        f'<li>Publish the draft as a <b>test listing</b> at {_money(L["rec_price"] or L["price_mid"])}.</li>'
        '<li>Paste the 13 tags; front-load the keyword in the title.</li>'
        '<li>Add 5+ photos (yours) + a personalization mockup.</li>'
        '<li>Set processing time + a clear personalization note.</li>'
        '<li>Recheck views/favorites after 7 days; iterate the main photo.</li>'
        '</ul>')

    # I. Designer brief
    designer_html = (
        '<ul class="facts">'
        f'<li><b>Concept:</b> original {vd["angle"]} design for "{_esc(kw)}"</li>'
        f'<li><b>Audience:</b> {_esc(vd["customer"])}</li>'
        f'<li><b>Style:</b> {_esc(opts.get("style") or "clean, giftable, bold")}</li>'
        '<li><b>Personalization:</b> leave space for '
        f'{_esc(opts.get("personalization") or "name / date")}</li>'
        f'<li><b>Production:</b> {mode} — '
        + ("bold shapes, ≤6 thread colors" if mode == "embroidery"
           else "high-contrast, transparent background") + '</li>'
        '<li><b>Do NOT copy</b> any competitor art, photo, or title.</li>'
        '</ul>')

    # J. Export / save
    export_html = (
        '<div class="expbar">'
        f'<a class="cbtn" href="/run/save?{save_qs(kw, opts)}">💾 Save this run</a>'
        + _copy_btn("ws-title", "Copy title")
        + _copy_btn("ws-tags", "Copy tags")
        + _copy_btn("ws-desc", "Copy description")
        + _copy_btn("ws-pod", "Copy POD prompt")
        + _copy_btn("ws-emb", "Copy embroidery prompt")
        + '</div><p class="note">Saving writes a dated folder under '
        '<code>reports/latest/runs/</code> with the verdict, listing data, and '
        'prompts — exportable, never auto-published.</p>')

    return (
        sec("verdict", "🧭", "Product verdict", verdict_html)
        + sec("scores", "📊", "Opportunity scores (0–100)", _score_grid(scores))
        + sec("market", "🔑", "Market &amp; keyword opportunity", market_html)
        + sec("niches", "💡", "Niche &amp; angle discovery", niche_html)
        + sec("listing", "🛠️", "Automatic listing builder", _listing_html(L))
        + sec("preview", "👁️", "Internal product preview", _preview_html(L))
        + sec("design", "🎨", "Design prompt generator", prompts_html)
        + sec("seller", "✅", "Seller execution checklist", seller_html)
        + sec("designer", "✏️", "Designer brief", designer_html)
        + sec("export", "📤", "Save / export", export_html))


def md_table(lines):
    """Tiny markdown-table -> HTML (avoids importing markdown in this module)."""
    import markdown as _md
    return _md.markdown("\n".join(lines), extensions=["tables"])


def save_qs(kw, opts):
    from urllib.parse import urlencode
    d = {"q": kw}
    d.update({k: v for k, v in opts.items() if v})
    return urlencode(d)


def save_run(kw, opts, workspace_html):
    """Persist a run under reports/latest/runs/<date>-<slug>/ as markdown+json."""
    from datetime import date
    from pathlib import Path
    import json
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", kw.lower()).strip("-")[:40] or "run"
    folder = Path("reports/latest/runs") / f"{date.today()}-{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "00-workspace.html").write_text(workspace_html, encoding="utf-8")
    (folder / "run.json").write_text(json.dumps(
        {"keyword": kw, "options": opts, "date": str(date.today())}, indent=2),
        encoding="utf-8")
    return folder
