"""Full photo-prompt set for an Etsy listing - every image, ready to paste into
GPT-image / Midjourney / Ideogram.

V35: EVERY slot - including the REAL-photo slots - carries a full AI image
prompt, so staff can generate an AI draft of the complete 12-image set and
compare it against the real shots. The honesty rule is unchanged and printed
per-slot: for any slot marked REAL PHOTO, the AI version is for
comparison/mockup only - the PUBLISHED image must be the real photo (policy +
trust). An AI render published as your real product is a misleading claim.

Etsy shows up to 10 images; the FIRST is the thumbnail and does most of the
converting. This returns an ordered set with a purpose + a ready prompt each,
plus a single "GPT runner" prompt that generates all 12 in order.
"""

EMB_RULES = ("bold clean shapes, flat solid colors, max 6 thread colors, no "
             "gradients, no photorealism, no tiny thin lines, readable text, "
             "clear separation between elements, stitch-friendly vector-like art")
POD_RULES = ("crisp high-contrast print-ready art, sharp edges, no ultra-fine "
             "detail, clean vector-like shapes")

AI_NOTE = ("AI version for comparison/mockup only — the PUBLISHED image must be "
           "the real photo (policy + trust).")


def _rules(mode):
    return EMB_RULES if (mode or "").lower().startswith("emb") else POD_RULES


def build(keyword, product="Embroidered Sweatshirt", mode="embroidery", pers=True):
    """Return an ordered list of image slots, each:
    {n, slot, purpose, real_photo (bool), prompt, ai_note (real slots only)}."""
    kw = (keyword or "your niche").strip()
    prod = product or "sweatshirt"
    rules = _rules(mode)
    emb = (mode or "").lower().startswith("emb")
    made = "embroidered" if emb else "printed"

    slots = [
        ("Hero / thumbnail", "Converts the click. Product worn in a real, on-brand "
         "scene - this one image decides your CTR.", True,
         f"Lifestyle product photo: a {prod.lower()} with a {made} '{kw}' design "
         "on the chest, worn by a smiling model in a bright, natural setting that "
         "fits the buyer (e.g. a cozy cafe or sunny doorway). Soft daylight, "
         "shallow depth of field, product sharp and centered, warm inviting mood, "
         "photorealistic. Square 2000x2000."),

        ("Front flat", "Clean full view of the product + design on a neutral surface.",
         True,
         f"Flat-lay product photo of the {prod.lower()} on a clean neutral "
         f"background, {made} '{kw}' design centered and crisp, even soft "
         "lighting, no clutter, true-to-life colors, photorealistic. Square."),

        ("Macro stitch" if emb else "Print detail",
         "Proof of quality - the close texture that justifies the price.", True,
         (f"Extreme macro close-up of an embroidered '{kw}' design on fabric: "
          "individual thread stitches, satin-stitch edges and visible fabric "
          "weave, raking side light revealing thread texture and slight sheen, "
          "photorealistic macro photography.") if emb else
         (f"Close-up photo of the printed '{kw}' design on fabric showing crisp "
          "print edges, saturated color and the fabric weave beneath, "
          "photorealistic macro photography.")),

        ("Personalization example", "Shows exactly what the buyer customizes and how "
         "it looks. Kills 'how does the name appear?' questions.", False,
         f"Clean informational graphic on a soft solid background: a mockup of the "
         f"{prod.lower()} chest area with an example name in the {made} font, an "
         "arrow/callout pointing to the personalization spot, short label 'Add any "
         "name - max 12 characters'. Simple, modern, legible; " + rules + "."),

        ("Size chart", "Reduces returns + wrong-size messages.", False,
         "A clean, modern size-chart graphic (S-3XL) with chest width and length in "
         "inches and cm, brand-neutral soft background, large legible sans-serif "
         "type, a small garment silhouette showing where measurements are taken. "
         "[Replace the numbers with your blank's real measurements.]"),

        ("Color / variant grid", "Lets the buyer self-select their color fast.", False,
         f"A tidy grid showing the {prod.lower()} in each available garment color "
         f"with the {made} '{kw}' design on each, evenly lit, color name under each "
         "swatch, clean neutral background. Mockups are fine here; keep colors true."),

        ("How to order", "Removes friction - the 3 steps to a personalized order.", False,
         "A simple numbered step graphic on a soft solid background: '1. Click "
         "Personalize  2. Type the name + pick color/size  3. Add to cart - we "
         f"{made} it made-to-order'. Three clean line icons, short labels, modern "
         "legible sans-serif. " + rules + "."),

        ("Bundle / gift set", "Lifts average order value - offer the set.", False,
         f"A styled flat-lay showing the {prod.lower()} paired as a gift set (e.g. "
         "with a matching mug, tote, or gift card) on a clean warm background, small "
         "'Bundle & save' badge, cohesive props. Composite REAL product photos into "
         "the set; keep the design true to your item."),

        ("Gift / occasion", "Triggers the gift-buyer - staged as a present.", False,
         f"Warm lifestyle scene: the folded {prod.lower()} styled as a gift with "
         "kraft wrap, ribbon and a sprig of eucalyptus on a wooden table, soft cozy "
         f"light, suggesting a thoughtful '{kw}' gift. Product/design must match your "
         "real item (composite a REAL product photo into the styled scene)."),

        ("Fabric / fit detail", "Second trust signal - drape, cuff, weight.", True,
         f"Detail product photo of the {prod.lower()} cuff, collar and fabric "
         "drape on a model or wooden hanger, soft window light showing garment "
         "quality, weight and fit, photorealistic."),

        ("Care + processing", "Sets expectations - handmade, care, dispatch time.", False,
         "A simple icon graphic: 'Made to order', 'Ships in [X] business days', "
         "'Wash cold / inside out', 'Embroidery won't crack or fade', on a soft "
         "solid background with clean line icons and short labels. " + rules + "."),

        ("Video thumbnail / 360", "Video lifts Etsy quality score.", True,
         f"A single video-frame style image: slow 360 turn of the {prod.lower()} "
         f"on a model showing the {made} '{kw}' design and texture up close, "
         "bright even light, smooth studio background, photorealistic."),
    ]
    out = []
    for i, (slot, purpose, real, prompt) in enumerate(slots, 1):
        d = {"n": i, "slot": slot, "purpose": purpose,
             "real_photo": real, "prompt": prompt}
        if real:
            d["ai_note"] = AI_NOTE
        out.append(d)
    return out


def runner(keyword, product="Embroidered Sweatshirt", mode="embroidery",
           slots=None):
    """ONE copy-paste prompt that makes ChatGPT generate the whole 12-image set
    IN ORDER, one image per message, advancing when the user replies '.' -
    same product, colors and style across all 12. The 12 slot briefs are
    inlined so the runner is fully self-contained."""
    kw = (keyword or "your niche").strip()
    prod = product or "sweatshirt"
    slots = slots or build(kw, product=prod, mode=mode)
    emb = (mode or "").lower().startswith("emb")
    made = "embroidered" if emb else "printed"
    L = [f"You are my product-photo generator for ONE Etsy listing: a "
         f"{prod.lower()} with a {made} '{kw}' design.",
         "",
         "RULES:",
         "1. You will generate 12 images, ONE per message, in the exact order "
         "below. Start with image 1 immediately.",
         "2. After each image, stop and wait. When I reply with a single '.' "
         "generate the NEXT image in the list. If I reply with anything else, "
         "treat it as a correction, regenerate the SAME slot, then wait again.",
         "3. KEEP CONSISTENCY: the same product, same design, same design "
         "colors, same style in every image - it must read as one listing.",
         "4. Square format, no watermarks, no brand logos, no text unless the "
         "slot brief asks for it.",
         "5. IMPORTANT: slots tagged [AI draft for comparison only] are "
         "planning/mockup images - DO NOT USE THE AI OUTPUT AS THE FINAL ETSY "
         "IMAGE for those slots; the published photo must be a real photo of "
         "the actual product / sew-out.",
         "",
         "THE 12 SLOTS:"]
    for s in slots:
        tag = (" [AI draft for comparison only - published image must be a real "
               "photo]" if s.get("real_photo") else "")
        L.append(f"{s['n']}. {s['slot']}{tag}: {s['prompt']}")
    L += ["", "Begin with image 1 now."]
    return "\n".join(L)
