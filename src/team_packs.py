"""Team packs: files each role actually works from.

- design_prompts_<date>.md : one COPY-PASTE prompt per design brief, ready
  to paste into Claude / Claude Design, built from the keyword + Etsy
  best-seller data, with production-type-specific specs (POD vs embroidery).
- seller_pack_<date>.md    : listing fields in Etsy's paste order, gated by
  publish status.
"""
from datetime import date
from pathlib import Path

TODAY = str(date.today())

POD_SPEC = """OUTPUT SPEC (print-on-demand):
- Final artwork: 4500 x 5400 px, 300 DPI, TRANSPARENT background PNG
- Design must read clearly at thumbnail size (Etsy first image is tiny)
- Text converted to outlines; high contrast against both light and dark products
- Leave the personalization area obvious: show placement with the sample name "Emma"
- Deliver: 3 typography style variations + 2 icon style variations,
  each as a complete visual, plus a one-line mockup direction for each"""

EMB_SPEC = """OUTPUT SPEC (embroidery - STRICT production limits):
- Maximum 6 thread colors, flat solid fills only - NO gradients, NO photos,
  NO tiny details (minimum line thickness ~1mm at final size)
- Bold, simple shapes that survive stitching; satin-stitch friendly lettering
- Embroidery area: assume 4x4 in (10x10 cm) unless supplier confirms larger
- For chenille: 2-3 inch bold letters/initials only, single color per patch
- Show placement with the sample name "Emma"
- Deliver: 3 lettering style variations + 2 motif variations, each described
  precisely enough to digitize (shapes, colors by thread, placement, size)"""


def _market_block(audit, tags):
    lines = []
    if audit:
        prices = [a["price"] for a in audit if a.get("price")]
        if prices:
            lines.append(f"- Best sellers price range: "
                         f"${min(prices)}-${max(prices)}")
        for a in audit[:3]:
            sold = f", {a['sales_if_available']} sold" \
                if a.get("sales_if_available") else ""
            lines.append(f"- Winning listing: \"{a['competitor_title'][:60]}\""
                         f" (${a['price']}{sold})")
    if tags:
        lines.append(f"- Proven search tags buyers use: {', '.join(tags[:13])}")
    if not lines:
        lines.append("- (No competitor data yet - run the audit first for "
                     "stronger prompts)")
    return "\n".join(lines)


def write_design_prompts(briefs, audit, packages, mode_label="", edges=None):
    from src.report_paths import rdir
    path = rdir(TODAY, "design") / f"design_prompts_{TODAY}.md"
    pkg_tags = {p["product_name"]: p["tags"] for p in packages}

    L = [f"# Claude Design Prompts{mode_label} - {TODAY}",
         "",
         "How to use: copy ONE full prompt block below into Claude / Claude "
         "Design and send. The market data is for understanding buyers, "
         "never for copying competitor designs.", ""]

    for i, b in enumerate(briefs, 1):
        is_emb = b.get("production_type") in ("EMBROIDERY", "CHENILLE_PATCH")
        spec = EMB_SPEC if is_emb else POD_SPEC
        tags = pkg_tags.get(b["product"], [])
        L += [f"## PROMPT #{i}: {b['product']}",
              "",
              "``````",
              f"You are an expert Etsy {'embroidery' if is_emb else 'print-on-demand'} designer. "
              f"Create ORIGINAL design concepts for this product. Do not "
              f"reference any brand, franchise, celebrity, or existing design.",
              "",
              f"PRODUCT: {b['product']}",
              f"PRIMARY ETSY KEYWORD: {b['primary_keyword']}",
              f"SECONDARY KEYWORDS: {b['secondary_keywords']}",
              f"TARGET BUYER: {b['target_buyer']}",
              f"WHY THEY BUY: {b['buyer_intent']}",
              "",
              "ETSY MARKET DATA (for understanding, NOT copying):",
              _market_block(audit, tags),
              "",
              f"DESIGN DIRECTION: {b['design_direction']}",
              f"COLOR DIRECTION: {b['color_direction']}",
              f"PERSONALIZATION: {b['personalization']}",
              f"MOCKUP DIRECTION: {b['mockup_direction']}",
              f"STRICTLY AVOID: {b['avoid']}",
              "",
              "COMPETITIVE EDGE TO EXPRESS IN THE DESIGN:",
              *[f"- {e}" for e in (edges or
                ["First image: must read clearly at thumbnail size"])],
              "",
              spec,
              "",
              "For each variation explain in one line why it will stand out "
              "in Etsy search results next to the winning listings above.",
              "``````", ""]

    path.write_text("\n".join(L), encoding="utf-8")
    from src.lang import finalize_pack
    finalize_pack(path)
    return path


# ChatGPT image generators (GPT-4o / DALL-E) return ONE image per message and
# cannot output transparent PNGs or 300 DPI print files. So each design
# variation is written as its own single-image prompt to send one at a time.
CG_TYPO_STYLES = [
    ("Typography A - modern minimal sans",
     "a clean, evenly-spaced modern sans-serif"),
    ("Typography B - elegant script",
     "an elegant flowing hand-script / signature style"),
    ("Typography C - bold serif monogram",
     "a bold serif monogram using strong capital initials"),
]
CG_ICON_STYLES = [
    ("Icon A - thin line motif + name",
     "one simple original thin line-art motif that fits the product theme, "
     "placed above the name"),
    ("Icon B - filled emblem + name",
     "a small solid-shape emblem or badge that frames the name, balanced "
     "and symmetrical"),
]


def _cg_flat_prompt(b, is_emb, style_desc, icon_desc=None):
    prod_kind = "embroidery" if is_emb else "print-on-demand"
    lines = [
        "Generate ONE original design image, square 1:1 (1024x1024), on a "
        "plain solid off-white background.",
        f"Context: an Etsy {prod_kind} {b['product']} for {b['target_buyer']}.",
        f"Hero element: the personalization name \"Emma\" set in {style_desc}.",
    ]
    if icon_desc:
        lines.append(f"Add {icon_desc}.")
    lines += [
        f"Design direction: {b['design_direction']}.",
        f"Colors: {b['color_direction']}.",
        "Keep ONE clear focal point that stays readable at Etsy thumbnail "
        "size; high contrast, crisp edges, no photographic textures.",
    ]
    if is_emb:
        lines.append("Embroidery limits: flat solid fills only, max 6 thread "
                     "colors, NO gradients, bold shapes that survive stitching.")
    lines += [
        f"Strictly avoid brands, logos, cartoon characters, celebrities, and: "
        f"{b['avoid']}.",
        "The only text is the sample name \"Emma\" - no other words.",
    ]
    return "\n".join(lines)


def _cg_mockup_prompt(b):
    return "\n".join([
        "Generate ONE photorealistic lifestyle mockup image, portrait 2:3 "
        "(1024x1536).",
        f"Scene: {b['mockup_direction']}.",
        f"The product is a {b['product']} showing the name \"Emma\". Bright, "
        "clean, premium styling; the product is the clear focal point.",
        f"No brand logos, no readable third-party text, and no: {b['avoid']}.",
    ])


def write_chatgpt_prompts(briefs, audit, packages, mode_label="", edges=None):
    """Single-image prompts tuned for ChatGPT's image generator.

    One prompt per message: 3 typography + 2 icon design concepts and 1
    lifestyle mockup per product.
    """
    from src.report_paths import rdir
    path = rdir(TODAY, "design") / f"chatgpt_prompts_{TODAY}.md"
    edge_line = (edges or
                 ["First image must read clearly at thumbnail size"])[0]

    L = [f"# ChatGPT Image Prompts{mode_label} - {TODAY}",
         "",
         "How to use: open ChatGPT in image mode and send each numbered prompt "
         "below as its OWN message - one image comes back per message. Do them "
         "in order, then pick the strongest per product.",
         "",
         "Note: ChatGPT cannot output transparent PNGs or 300 DPI print files. "
         "Treat these as concept images; your designer rebuilds the winner as "
         "the final 4500x5400 transparent PNG for the supplier.", ""]

    for i, b in enumerate(briefs, 1):
        is_emb = b.get("production_type") in ("EMBROIDERY", "CHENILLE_PATCH")
        L += [f"## PRODUCT #{i}: {b['product']}",
              "",
              f"Buyers: {b['target_buyer']} - they buy for {b['buyer_intent']}.",
              f"Edge to express: {edge_line}",
              f"Primary Etsy keyword: {b['primary_keyword']}", ""]
        n, total = 0, len(CG_TYPO_STYLES) + len(CG_ICON_STYLES) + 1
        for label, style_desc in CG_TYPO_STYLES:
            n += 1
            L += [f"### {n} of {total} - {label}", "",
                  "``````",
                  _cg_flat_prompt(b, is_emb, style_desc),
                  "``````", ""]
        for label, icon_desc in CG_ICON_STYLES:
            n += 1
            L += [f"### {n} of {total} - {label}", "",
                  "``````",
                  _cg_flat_prompt(b, is_emb,
                                  "a simple clean typographic treatment",
                                  icon_desc=icon_desc),
                  "``````", ""]
        n += 1
        L += [f"### {n} of {total} - Lifestyle mockup", "",
              "``````",
              _cg_mockup_prompt(b),
              "``````", ""]

    path.write_text("\n".join(L), encoding="utf-8")
    from src.lang import finalize_pack
    finalize_pack(path)
    return path


def _customer_copy_allowed(p):
    """Customer-facing copy may be shown only when no placeholders remain."""
    gates = p.get("publish_gates") or {}
    return bool(gates.get("no_placeholders")) and "NEED_SUPPLIER_DETAILS" not in p.get("description", "")


def _safe_description_block(p):
    if _customer_copy_allowed(p):
        return ["**4. DESCRIPTION**", "```", p["description"], "```"]
    missing = [b for b in p.get("blocked_by", []) if b in (
        "supplier_confirmed", "supplier_last_verified", "product_url_recorded",
        "supplier_url_verified", "material_verified", "size_verified",
        "base_cost_verified", "shipping_cost_verified",
        "processing_time_verified", "no_placeholders")]
    return [
        "**4. DESCRIPTION - COPY BLOCKED**",
        "```",
        "Do NOT paste a customer-facing description yet.",
        "Reason: supplier/material/size/processing evidence is incomplete.",
        "Fix first: " + (", ".join(missing) if missing else "clear all placeholders"),
        "After the supplier checker verifies the fields, regenerate this seller pack.",
        "```",
    ]


def _post_publish_block(pub):
    if pub:
        return ["After MANAGER-APPROVED publish only (final QA status must "
                "be PUBLISH_READY): open as buyer, test personalization box, "
                "log URL + date in the team tracker."]
    return ["POST-PUBLISH ACTIONS: hidden until final QA status is PUBLISH_READY."]


def write_seller_pack(packages, publish_ready, mode_label=""):
    from src.report_paths import rdir
    path = rdir(TODAY, "seller") / f"seller_pack_{TODAY}.md"
    L = [f"# Seller Pack{mode_label} - {TODAY}", ""]
    if not publish_ready:
        L += ["## CANH BAO / WARNING",
              "PUBLISH_READY = false. DUOC PHEP chuan bi listing (nhap nhap, "
              "luu draft), KHONG DUOC bam Publish cho den khi muc 0 cua bao "
              "cao manager het o trong.",
              "You may PREPARE listings as drafts. Do NOT click Publish "
              "until Section 0 of the manager report is fully checked.", ""]
    for p in packages:
        pub = p["publish_status"] == "PUBLISH_READY"
        copy_allowed = _customer_copy_allowed(p)
        L += [f"## {p['product_name']}  [{p['listing_status']}]", "",
              f"- Draft allowed: "
              f"{'YES' if p['status'] == 'DESIGN_PREP_READY' else 'NO'}",
              f"- Publish allowed: {'YES' if pub else 'NO'}",
              f"- Customer-facing copy allowed: {'YES' if copy_allowed else 'NO'}",
              f"- Final QA owner: Manager (manual_review=yes required)"]
        if p["blocked_by"]:
            L.append(f"- Reason publish is blocked / missing evidence: "
                     f"{', '.join(p['blocked_by'])}")
        L.append("")
        L += ["Draft preparation order in Etsy Shop Manager -> Add a listing:",
              "Do not paste any field marked COPY BLOCKED.", "",
              "**1. TITLE**", "```", p["seo_title"], "```",
              "**2. ABOUT:** Who made it: A member of my shop | What: "
              "Finished product | When: Made to order",
              f"**3. CATEGORY:** {p['category']}"]
        L += _safe_description_block(p)
        L += [f"**5. TAGS (13, paste one by one)**", "```",
              ", ".join(p["tags"]), "```",
              f"**6. VARIATIONS:** {p['variations']}",
              f"**7. PERSONALIZATION (ON):** "
              f"{p['personalization_instructions']}",
              f"**8. PRICE:** ${p['price']}  | Quantity: 20-50",
              f"**9. SHIPPING:** {p['shipping_note']}",
              f"**10. PRODUCTION PARTNER:** {p['production_partner']} "
              "(required for POD - do not skip)",
              "**11. PHOTOS:** " + " | ".join(p["image_checklist"]),
              f"**12. VIDEO:** {p['video_idea']}",
              ""]
        L += _post_publish_block(pub) + [""]
    path.write_text("\n".join(L), encoding="utf-8")
    from src.lang import finalize_pack
    finalize_pack(path)
    return path
