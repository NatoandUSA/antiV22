"""Full photo-prompt set for an Etsy listing - every image, ready to paste into
GPT-image / Midjourney / Ideogram.

HONESTY RULE (baked in): AI is for CONCEPT, mockup, background and graphics only.
The photos that show YOUR actual embroidered product - the hero, the macro stitch -
must be a REAL photo / sew-out. An AI render of your real item is a misleading
product claim. Every product-photo slot below says this out loud.

Etsy shows up to 10 images; the FIRST is the thumbnail and does most of the
converting. This returns an ordered set with a purpose + a ready prompt each.
"""

EMB_RULES = ("bold clean shapes, flat solid colors, max 6 thread colors, no "
             "gradients, no photorealism, no tiny thin lines, readable text, "
             "clear separation between elements, stitch-friendly vector-like art")
POD_RULES = ("crisp high-contrast print-ready art, sharp edges, no ultra-fine "
             "detail, clean vector-like shapes")


def _rules(mode):
    return EMB_RULES if (mode or "").lower().startswith("emb") else POD_RULES


def build(keyword, product="Embroidered Sweatshirt", mode="embroidery", pers=True):
    """Return an ordered list of image slots, each:
    {n, slot, purpose, real_photo (bool), prompt}."""
    kw = (keyword or "your niche").strip()
    prod = product or "sweatshirt"
    rules = _rules(mode)
    emb = (mode or "").lower().startswith("emb")
    made = "embroidered" if emb else "printed"

    slots = [
        ("Hero / thumbnail", "Converts the click. Product worn in a real, on-brand "
         "scene - this one image decides your CTR.", True,
         f"Lifestyle product photo: a {prod.lower()} with a {made} '{kw}' design, "
         "worn by a smiling model in a bright, natural setting that fits the buyer "
         "(e.g. a nurse in a cozy cafe). Soft daylight, shallow depth of field, "
         "product sharp and centered, warm inviting mood. Square 2000x2000. "
         "REAL PHOTO of your finished item - do not AI-generate the product."),

        ("Front flat", "Clean full view of the product + design on a neutral surface.",
         True,
         f"Flat-lay of the {prod.lower()} on a clean neutral background, {made} "
         f"'{kw}' design centered and crisp, even lighting, no clutter, true colors. "
         "Square. REAL PHOTO of your finished item."),

        ("Macro stitch" if emb else "Print detail",
         "Proof of quality - the close texture that justifies the price.", True,
         (f"Extreme macro close-up of the {made} '{kw}' design showing individual "
          "thread stitches, satin edges and fabric weave, raking light to reveal "
          "texture. REAL PHOTO / sew-out - never AI.") if emb else
         (f"Close-up of the printed '{kw}' design showing crisp edges and color on "
          "the fabric weave. REAL PHOTO of your finished item.")),

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

        ("Gift / occasion", "Triggers the gift-buyer - staged as a present.", False,
         f"Warm lifestyle scene: the folded {prod.lower()} styled as a gift with "
         "kraft wrap, ribbon and a sprig of eucalyptus on a wooden table, soft cozy "
         f"light, suggesting a thoughtful '{kw}' gift. Product/design must match your "
         "real item (composite a REAL product photo into the styled scene)."),

        ("Fabric / fit detail", "Second trust signal - drape, cuff, weight.", True,
         f"Detail shot of the {prod.lower()} cuff/collar and fabric drape on the "
         "model or a hanger, showing quality and fit. REAL PHOTO."),

        ("Care + processing", "Sets expectations - handmade, care, dispatch time.", False,
         "A simple icon graphic: 'Made to order', 'Ships in [X] business days', "
         "'Wash cold / inside out', 'Embroidery won't crack or fade', on a soft "
         "solid background with clean line icons and short labels. " + rules + "."),

        ("Video thumbnail / 360", "Video lifts Etsy quality score.", True,
         f"A frame for a short product video: slow 360 turn of the {prod.lower()} on "
         "a model showing the design and stitch up close, bright and smooth. REAL "
         "footage of your finished item."),
    ]
    out = []
    for i, (slot, purpose, real, prompt) in enumerate(slots, 1):
        out.append({"n": i, "slot": slot, "purpose": purpose,
                    "real_photo": real, "prompt": prompt})
    return out
