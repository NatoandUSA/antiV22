"""V35 Launch Kit page - the FULL copy-paste listing, laid out like a real
marketplace product page.

Everything a launch needs on one page, every field ready to copy:
scorecard (verdict / proof / gaps / P&L / publish gates) on top, then an
Etsy-style two-column preview (12-photo gallery grid left, title / price /
personalization right), then the copy-paste blocks: title, 13 tags,
description, personalization instructions, buyer how-to-order guide and
notes/policies (production, VN->US shipping, care, returns).

Fields that REQUIRE human input or correction are rendered in RED with the
.needs-human class: price (from real cost), shipping profile, real photos,
final trademark eyeball, personalization preview. Draft-only rule unchanged -
nothing here touches the Etsy account; the human publishes manually.

Honest-nulls: absent data shows as absent ("--" / a plain note), never as an
invented number. Niche fallback (kit_evidence) labels niche-level evidence.
"""
import html as _h

from src import interactive as iv
from src import photo_brief

_MONEY = iv._money


def _e(t):
    return _h.escape(str(t if t is not None else ""), quote=True)


def _copy(tid, label="📋 Copy"):
    return (f'<button class="cbtn" data-copy="{tid}" type="button">{label}'
            '</button>')


def _block(tid, heading, text, note="", red=False):
    """One labelled copy-paste block: header row + Copy button + value box."""
    cls = "lkblock needs-human" if red else "lkblock"
    n = f'<p class="note">{note}</p>' if note else ""
    return (f'<div class="{cls}"><div class="lbrow"><b>{heading}</b>'
            + _copy(tid) + '</div>'
            + f'<div class="lbval" id="{tid}">{_e(text)}</div>' + n + '</div>')


# --------------------------- listing copy ----------------------------------

def _title(kw, mode):
    base = kw.strip().title()
    prod = "Embroidered" if mode == "embroidery" else "Custom"
    parts = [base, f"Personalized {prod} Gift", "Custom Name",
             "Gift for [Recipient]"]
    return ", ".join(dict.fromkeys(parts))[:140]


def _description(kw, mode, price_note):
    t = kw.strip().title()
    made = "embroidered" if mode == "embroidery" else "printed"
    detail = ("Stitched with up to 6 thread colors in bold, clean shapes that "
              "will not crack, peel or fade" if mode == "embroidery" else
              "Printed in vibrant, long-lasting color with crisp edges")
    return f"""{t} — made just for you. 🧵

WHY YOU'LL LOVE IT
★ {made.capitalize()} to order — no two are exactly alike
★ Personalized with any name (up to 12 characters)
★ {detail}
★ A gift that feels chosen, not bought

DETAILS & MATERIALS
• Soft, premium cotton-blend garment, unisex fit
• Design {made} directly on the garment (no vinyl, no transfers)
• Made to order — ships in [X] business days [confirm your real production time]

SIZING
• Sizes S–3XL — see the size chart in the photos
• Between sizes? We recommend sizing up for a relaxed fit

HOW TO ORDER
1. Choose your size and garment color
2. Type the name EXACTLY as you want it in the Personalization box
3. Add to cart — we make it and ship it with tracking

{price_note}

Questions? Message us — we answer within 24 hours."""


def _personalization(kw):
    return """PERSONALIZATION — what to enter (copy into Etsy's personalization field settings):

Instructions shown to the buyer:
"Type the name exactly as you want it stitched (max 12 characters, letters and spaces only). Example: Ms. Johnson — Double-check spelling: we stitch exactly what you type!"

• Character limit to set in Etsy: 12
• What we accept: letters, spaces, periods, hyphens
• What we can't stitch: emojis, special symbols, extra-long text
• Buyer example 1: Ms. Johnson
• Buyer example 2: Coach Emma
• If the buyer leaves it blank: we message once, then ship the non-personalized version after 48h."""


def _how_to_order(kw):
    t = kw.strip().title()
    return f"""HOW TO ORDER YOUR {t.upper()} (buyer guide — paste in FAQ or first listing photo caption):

1. Pick your SIZE (S–3XL — size chart is in the photos) and garment COLOR.
2. In the Personalization box, type the name EXACTLY as you want it — max 12 characters. We stitch what you type!
3. (Optional) Want to see it first? Add a note "preview please" and we'll message a mockup for approval before we make it.
4. Add to cart and check out. You'll get a tracking number as soon as it ships.
5. Check your Etsy messages after ordering — if anything about the name looks off, we'll contact you there."""


def _policies(kw, mode):
    made = "embroidery" if mode == "embroidery" else "print"
    return f"""NOTES & POLICIES (paste into your listing's bottom section / shop policies):

PRODUCTION TIME
• Made to order: [X–Y] business days before shipping [set your REAL {made} production time]

SHIPPING (Vietnam → USA)
• Tracked international shipping: typically [7–14] business days after production [confirm with your carrier]
• A tracking number is added to your order the day it ships
• Need it by a date? Message us BEFORE ordering and we'll confirm honestly.

CARE
• Machine wash cold, inside out, gentle cycle
• No bleach; hang dry or tumble low
• {"Embroidery keeps its color — it will not crack or peel." if mode == "embroidery" else "Do not iron directly on the print."}

RETURNS ON PERSONALIZED ITEMS
• Personalized orders are made just for you and can't be resold, so returns/exchanges are only for damaged or defective items — send us a photo within 48h of delivery and we'll remake or refund.
• Wrong name typed by the buyer: we stitch what was entered, but message us — we'll offer a discounted remake."""


# --------------------------- scorecard -------------------------------------

def _chip(label, value, cls=""):
    return (f'<span class="chip {cls}"><b>{_e(value)}</b> {_e(label)}</span>')


def _scorecard(kw, mode, ev, price, base, ship):
    sub = ev.get("sub") or {}

    def n(k):
        v = sub.get(k)
        return round(v) if isinstance(v, (int, float)) else "—"

    verdict = ev.get("verdict") or "—"
    vcls = ("cg-ok" if verdict in ("GO", "BUILD") else
            "cg-no" if verdict == "SKIP" else "")
    gap = ev.get("gap")
    chips = [
        _chip("Verdict", verdict, vcls),
        _chip("Winner gap", gap if gap is not None else "—"),
        _chip("Score", ev.get("score") if ev.get("score") is not None else "—"),
        _chip("Demand", n("market_potential")),
        _chip("Competition", n("competition_health")),
        _chip("Trademark", ev.get("risk") or "—",
              "cg-no" if ev.get("risk") == "HIGH" else ""),
    ]
    proof = ev.get("proof")
    if proof:
        lvl = proof.get("match")
        tag = {"exact": "exact", "fuzzy":
               f"conf {proof.get('match_confidence')}",
               "niche": f"niche-level · {proof.get('groups', 1)} group(s)"}.get(lvl, "")
        chips.append(_chip(f"Etsy proof ({tag})", proof.get("evidence") or "—",
                           "cg-ok" if proof.get("verdict") in
                           ("PROVEN_WINNER", "STRONG_SELLER") else ""))
    else:
        chips.append(_chip("Etsy proof", "none on file"))
    html = ['<div class="chips">' + "".join(chips) + '</div>']

    # niche-level evidence (exact phrase unindexed = open lane, long-tail rule)
    if not ev.get("exact_indexed"):
        rows = []
        if proof and proof.get("match") == "niche":
            g = "; ".join(f"<b>{_e(m['keyword'])}</b> ({_e(m['evidence'])})"
                          for m in (proof.get("members") or [])[:3])
            rows.append(f"<li><b>Sibling proof groups:</b> "
                        f"{_e(proof.get('evidence'))} across "
                        f"{proof.get('groups', 1)} group(s) — {g}</li>")
        r = ev.get("niche_row")
        if r:
            rs = r.get("sub_scores") or {}

            def rc(k):
                v = rs.get(k)
                return round(v) if isinstance(v, (int, float)) else "—"

            rows.append(f"<li><b>Parent niche '{_e(r.get('keyword'))}':</b> "
                        f"demand {rc('market_potential')} · competition "
                        f"{rc('competition_health')} · final action "
                        f"<b>{_e(r.get('action', '—'))}</b></li>")
        p = ev.get("patterns")
        if p:
            bits = [w for w, _ in (p.get("phrases") or [])[:3]] or \
                   [w for w, _ in (p.get("top_words") or [])[:5]]
            if bits:
                rows.append("<li><b>Winning-title patterns:</b> "
                            + ", ".join(f"<code>{_e(b)}</code>" for b in bits)
                            + "</li>")
        if not rows:
            rows.append("<li><i>No sibling proof or parent market row on file "
                        "yet — capture this niche with the extension (Etsy "
                        "search → Send to agent) to light this up.</i></li>")
        html.append('<div class="lkniche">🧭 <b>Niche-level evidence</b> — the '
                    'exact phrase has <b>no index entry</b>: for a 4+ word '
                    'long-tail that is an <b>open lane</b> (✓ long-tail rule). '
                    'Below is the NICHE around it, never the exact phrase:'
                    f'<ul>{"".join(rows)}</ul></div>')

    # P&L strip (honest-null)
    cost = (base + ship) if (base is not None and ship is not None) else base
    pl = ["<b>P&amp;L:</b>"]
    pl.append(f"market price {_MONEY(price)}" if price else
              "market price — (no index data)")
    pl.append(f"supplier cost {_MONEY(cost)}" if cost is not None
              else "supplier cost — (not on file)")
    if price and cost is not None:
        try:
            from src.ads_plan import _economics
            econ = _economics(price, cost, 0.0)
        except (SystemExit, Exception):  # noqa: BLE001
            econ = None
        if econ and not econ.get("unprofitable"):
            pl.append(f"→ net ~{_MONEY(econ['net_profit'])}/sale "
                      f"({econ['margin_pct']}% margin)")
        elif econ:
            pl.append("→ ⚠️ UNPROFITABLE at market price — reprice before launch")
    html.append('<p class="lkpl needs-human">' + " · ".join(pl)
                + ' <span class="nh">SET FROM YOUR REAL COST</span></p>')

    # top measured competitor gaps
    try:
        from src import edge as edge_engine
        from src import ytrends_mcp as mcp
        listings = iv._competitor_listings(kw)
        try:
            comp = mcp.analyze_competition(kw) or {}
        except (SystemExit, Exception):  # noqa: BLE001
            comp = {}
        edges = [e for e in edge_engine.measure_edges(listings, comp)
                 if e.get("measured")][:3]
    except (SystemExit, Exception):  # noqa: BLE001
        edges = []
    if edges:
        li = "".join(f"<li><b>{_e(e['category'])}</b> ({e['magnitude']}%): "
                     f"{_e(e['action'])}</li>" for e in edges)
        html.append(f'<div class="lkgaps"><b>Beat them here:</b><ul>{li}</ul>'
                    f'<a href="/edge?q={iv._uq(kw)}">All gaps →</a></div>')

    # 4 publish gates - the human walks these before publishing
    ok_evidence = bool(proof) or (isinstance(sub.get("market_potential"),
                                             (int, float)))
    gates = [
        ("① Evidence", ok_evidence, "auto",
         "verdict + proof above (niche-level counts, honestly labelled)"),
        ("② Price &amp; margin", False, "human",
         "set the price from your REAL cost — target ≥35–40% net"),
        ("③ Real photos", False, "human",
         "hero / macro / measurements / sew-out published images must be REAL"),
        ("④ Trademark + preview", False, "human",
         "final USPTO eyeball + send one personalization preview to yourself"),
    ]
    g = "".join(
        f'<div class="gate {"g-ok" if ok else "g-no"}'
        f'{" needs-human" if who == "human" else ""}">{name}: '
        f'{"PASS" if ok else "PENDING"}'
        + (' <span class="nh">HUMAN</span>' if who == "human" else "")
        + f'<small> — {why}</small></div>'
        for name, ok, who, why in gates)
    html.append('<div class="lkgates">' + g + '</div>')
    return "".join(html)


# --------------------------- preview ---------------------------------------

def _gallery(kw, mode, product):
    """Compact left column: hero square + a thumb STRIP of the 12 slots; the
    full 12-brief plan is one click away in a collapsible."""
    slots = photo_brief.build(kw, product=product, mode=mode)
    thumbs = "".join(
        f'<i class="{"r" if s["real_photo"] else ""}" '
        f'title="{s["n"]}. {_e(s["slot"])} — {_e(s["purpose"])}">{s["n"]}</i>'
        for s in slots)
    cells = []
    for s in slots:
        badge = ('<i class="real">📸 REAL</i>' if s["real_photo"]
                 else '<i class="ai">🎨 AI</i>')
        cells.append(f'<div class="lkslot" title="{_e(s["purpose"])}">'
                     f'<b>{s["n"]}</b> {_e(s["slot"])} {badge}</div>')
    return ('<div class="pvmain">#1 hero — REAL photo</div>'
            f'<div class="lkthumbs">{thumbs}</div>'
            '<details class="pvacc"><summary>Full 12-image plan '
            '(red = must be a REAL photo)</summary>'
            '<div class="lkgal">' + "".join(cells) + '</div>'
            '<p class="note needs-human">Published 📸 shots must be REAL photos '
            '<span class="nh">HUMAN</span> — AI drafts + GPT runner in '
            f'<a href="/photo-brief?q={iv._uq(kw)}">Photo prompts →</a></p>'
            '</details>')


def _preview(kw, mode, title, tags, price, pers_limit=12):
    price_txt = _MONEY(price) if price else "$[SET PRICE]"
    chips = "".join(f"<span>{_e(t)}</span>" for t in tags[:6])
    made = "embroidered" if mode == "embroidery" else "made"
    return (
        '<div class="pvinfo">'
        '<div class="pvshop">YourShopName · <span class="pvstars">★★★★★</span> '
        '<small>(your reviews) · Star Seller</small></div>'
        f'<div class="pvtitle">{_e(title)}</div>'
        f'<div class="pvprice needs-human">{_e(price_txt)} '
        '<small>+ shipping · VAT incl.</small> <span class="nh">REAL COST</span>'
        '</div>'
        f'<div class="pvhint">Personalized · {made} to order · ships from VN '
        'with tracking</div>'
        '<label class="pvpers">Add your personalization *'
        f'<textarea placeholder="Name exactly as you want it — max '
        f'{pers_limit} characters. Example: Ms. Johnson"></textarea></label>'
        '<button class="pvcart" type="button">Add to cart</button>'
        '<div class="pvhint needs-human">Arrives by [date from your REAL '
        'shipping profile] <span class="nh">HUMAN</span></div>'
        '<details class="pvacc"><summary>Item details</summary>'
        '<p>Full description below — copy block ⑤.</p></details>'
        '<details class="pvacc"><summary>Shipping &amp; returns</summary>'
        '<p>Made to order · VN→US tracked [7–14] business days · no returns on '
        'personalized items unless defective.</p></details>'
        f'<div class="pvtags">{chips}<span>+7 tags</span></div>'
        '</div>')


_CSS = """
<style>
.lkblock{margin:14px 0}
.lkblock .lbval{white-space:pre-wrap;max-height:340px;overflow:auto}
.needs-human{border-left:4px solid #d92d20;padding-left:10px;border-radius:4px}
.needs-human .nh,.nh{background:#d92d20;color:#fff;font-size:.62rem;
font-weight:800;padding:1px 7px;border-radius:9px;letter-spacing:.06em;
vertical-align:middle}
.lkpv{max-width:680px}
.lkpv .pv{padding:12px;gap:12px;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr)}
.lkpv .pvmain{font-size:.72rem}
.lkthumbs{display:flex;gap:4px;margin-top:5px;flex-wrap:wrap}
.lkthumbs i{width:30px;height:30px;border-radius:6px;background:var(--line);
font-style:normal;font-size:.62rem;font-weight:800;display:flex;
align-items:center;justify-content:center;color:var(--ink-soft);cursor:default}
.lkthumbs i.r{border:2px solid #d92d20;color:#d92d20;background:var(--surface)}
.pvstars{color:#B45309;letter-spacing:1px}
.pvhint{font-size:.72rem;color:var(--ink-soft);margin:4px 0}
.lkpv .pvtitle{font-size:.92rem;line-height:1.3}
.lkpv .pvprice{font-size:1.2rem;margin:4px 0}
.lkpv .pvpers textarea{min-height:34px;font-size:.8rem}
.lkpv .pvcart{background:#1b1b1b;color:#fff;padding:9px;margin:6px 0}
.lkpv .pvtags{margin-top:6px}
.lkgal{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}
.lkslot{border:1px solid var(--line);border-radius:8px;padding:7px 8px;
font-size:.68rem;background:var(--surface);line-height:1.35}
.lkslot b{color:var(--accent)}
.lkslot i.real{color:#d92d20;font-style:normal;font-weight:700;display:block}
.lkslot i.ai{color:var(--ink-faint);font-style:normal;display:block}
.lkniche{background:var(--accent-bg);border:1px solid var(--line-strong);
border-radius:10px;padding:10px 14px;margin:10px 0;font-size:.85rem}
.lkniche ul{margin:6px 0 0 18px}
.lkpl{font-size:.85rem;margin:10px 0}
.lkgaps{font-size:.85rem;margin:10px 0}.lkgaps ul{margin:4px 0 4px 18px}
.lkgates{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
gap:8px;margin:10px 0}
.lkgates .gate small{display:block;font-weight:400;font-size:.7rem;
margin-top:2px}
.lknext{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
.lksent{background:var(--ok);color:#fff;border-radius:10px;padding:11px 15px;
margin:10px 0;font-weight:700}
.lksubmit textarea{width:100%;min-height:52px;padding:9px 11px;
border:1px solid var(--line-strong);border-radius:9px;background:var(--paper);
color:var(--ink);font:inherit;font-size:.88rem;resize:vertical;margin:6px 0}
.lksubmit button{padding:11px 18px;border:0;border-radius:10px;
background:var(--accent);color:var(--paper);font-weight:800;cursor:pointer;
font-size:.92rem}
</style>
"""


def summary_for_manager(kw, mode, ev, price, tags):
    """Plain-text summary attached to the review task - what the manager reads
    before List / Fix / Decline. Honest-null like everything else."""
    sub = ev.get("sub") or {}

    def n(k):
        v = sub.get(k)
        return round(v) if isinstance(v, (int, float)) else "-"

    proof = ev.get("proof")
    pline = "none on file"
    if proof:
        lvl = proof.get("match")
        pline = (proof.get("evidence") or "-") + (
            f" (niche-level, {proof.get('groups', 1)} groups)" if lvl == "niche"
            else f" (fuzzy conf {proof.get('match_confidence')})" if lvl == "fuzzy"
            else " (exact)")
    return (
        f"LISTING APPROVAL REQUEST - {kw} [{mode}]\n"
        f"Verdict: {ev.get('verdict') or '-'} | Score: "
        f"{ev.get('score') if ev.get('score') is not None else '-'} | "
        f"Winner gap: {ev.get('gap') if ev.get('gap') is not None else '-'}\n"
        f"Demand {n('market_potential')} | Competition "
        f"{n('competition_health')} | Trademark: {ev.get('risk')}\n"
        f"Etsy proof: {pline}\n"
        f"Market price: {(_MONEY(price) if price else 'no index data')} | "
        f"Tags ready: {min(len(tags), 13)}/13\n"
        f"Human gates still open: price from real cost, shipping profile, "
        f"real photos, trademark eyeball, personalization preview.\n"
        f"Full kit: /launch-kit?q={iv._uq(kw)}&mode={mode}")


def build(kw, mode=None, sent=False):
    """The full V35 Launch Kit page body (HTML). Never raises on missing data -
    absent signals render as absent, red .needs-human marks human fields."""
    kw = (kw or "").strip()
    mode = iv._mode_for(kw, mode)
    label = iv.MODE_LABEL.get(mode, mode)
    product = ("Embroidered Sweatshirt" if mode == "embroidery"
               else "Printed T-Shirt")

    ev = iv.kit_evidence(kw, mode)
    tags = iv._tags_for(kw)
    price, base, ship, _conv = iv._price_cost_for(kw, mode)

    title = _title(kw, mode)
    price_note = ("Price: [SET FROM YOUR REAL COST — target ≥35–40% net "
                  "margin after Etsy fees]")
    desc = _description(kw, mode, price_note)
    pers = _personalization(kw)
    order = _how_to_order(kw)
    policy = _policies(kw, mode)
    tags_csv = ", ".join(tags[:13])
    tag_note = ("" if len(tags) >= 13 else
                f"⚠️ only {len(tags)} clean tags found — add "
                f"{13 - len(tags)} of your own (each ≤20 chars).")

    sent_bar = ('<div class="lksent">✅ Sent to the manager — it is now in the '
                '<a href="/admin/reviews" style="color:#fff;text-decoration:'
                'underline">Review Queue</a>. Nothing publishes until it is '
                'approved AND the human gates pass.</div>' if sent else "")
    H = [_CSS,
         f'<article class="md">{sent_bar}<h1>🚀 Launch Kit — {_e(kw)}</h1>'
         f'<p><i>{_e(label)} · <b>draft only</b> — copy each block into Etsy '
         'yourself; nothing here touches your account. Red blocks need YOUR '
         'input before publish.</i></p></article>',
         # scorecard
         '<article class="md"><h2>① Scorecard</h2>'
         + _scorecard(kw, mode, ev, price, base, ship) + '</article>',
         # compact marketplace preview
         '<article class="md"><h2>② Listing preview</h2>'
         '<div class="lkpv"><div class="pv"><div>'
         + _gallery(kw, mode, product) + '</div>'
         + _preview(kw, mode, title, tags, price) + '</div></div>'
         '<p class="note">Compact internal preview — how the buyer roughly '
         'sees it. Not a real marketplace page.</p></article>']

    # copy-paste blocks
    blocks = [
        _block("lk-title", "③ Title (keyword in first 40 chars)", title,
               note="Etsy cuts titles around 140 chars; the first ~40 carry "
               "the ranking weight."),
        ('<div class="lkblock"><div class="lbrow"><b>④ 13 tags (each ≤20 '
         'chars)</b>' + _copy("lk-tags", "📋 Copy all 13") + '</div>'
         '<div class="chips">'
         + "".join(f'<span class="chip">{_e(t)}</span>' for t in tags[:13])
         + '</div>'
         + f'<div class="lbval" id="lk-tags">{_e(tags_csv)}</div>'
         + (f'<p class="note">{_e(tag_note)}</p>' if tag_note else "")
         + '</div>'),
        _block("lk-desc", "⑤ Description (hook · details · sizing · order "
               "steps)", desc),
        _block("lk-pers", "⑥ Personalization instructions", pers, red=True,
               note="Send ONE preview to yourself before the first real order "
               "— that's publish gate ④."),
        _block("lk-order", "⑦ Buyer how-to-order guide", order),
        _block("lk-policy", "⑧ Notes & policies (production · VN→US shipping "
               "· care · returns)", policy, red=True,
               note="Replace [X–Y] with your REAL production + carrier "
               "timelines and attach the matching Etsy shipping profile."),
    ]
    H.append('<article class="md"><h2>③–⑧ Copy-paste the listing</h2>'
             + "".join(blocks) + '</article>')

    # next steps
    H.append('<article class="md"><h2>Next steps</h2><div class="lknext">'
             f'<a class="pullbtn" href="/photo-brief?q={iv._uq(kw)}">📸 Photo '
             'prompts + GPT runner</a>'
             f'<a class="pullbtn" href="/ads-plan?q={iv._uq(kw)}">📣 Etsy Ads '
             'plan</a>'
             f'<a class="pullbtn" href="/edge?q={iv._uq(kw)}">🥊 Beat the '
             'competition</a>'
             f'<a class="pullbtn" href="/grade?title={iv._uq(title)}">🔍 Grade '
             'this listing</a></div>'
             '<p class="note">Assembled from live data where reachable; '
             'missing signals stay blank, never invented. Publish manually '
             'inside Etsy after the four gates pass.</p></article>')

    # send FINAL to manager (goes into the existing /admin/reviews queue)
    if not sent:
        H.append(
            '<article class="md lksubmit"><h2>⑨ Send FINAL to manager</h2>'
            '<p>Done with the human fields? Send this kit for approval. The '
            'manager sees a one-screen summary in the '
            '<a href="/admin/reviews">Review Queue</a> and decides '
            '<b>List</b> / <b>Fix</b> / <b>Decline</b> with a comment. '
            'Publishing stays manual either way.</p>'
            '<form method="post" action="/launch-kit/submit">'
            f'<input type="hidden" name="q" value="{_e(kw)}">'
            f'<input type="hidden" name="mode" value="{_e(mode)}">'
            '<textarea name="note" maxlength="1000" placeholder="Note to the '
            'manager (optional): price you set, photos status, anything to '
            'double-check…"></textarea>'
            '<button type="submit">📤 Send for approval</button></form>'
            '</article>')
    return "".join(H)
