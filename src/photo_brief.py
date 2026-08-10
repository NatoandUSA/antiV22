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

REAL_NOTE = ("📸 REAL-PHOTO slot — generate the prompt above as an AI REFERENCE "
             "to plan the shot and check framing/composition, keep it as a "
             "reference, and a human reviews it. The PUBLISHED image must be the "
             "real photo of the actual product / sew-out — not the AI render.")


def _rules(mode):
    return EMB_RULES if (mode or "").lower().startswith("emb") else POD_RULES


# Several slots below default to garment anatomy (chest, cuff, collar, worn by
# a model, chest measurements) -- wrong for a bag. Minimal, keyword-based
# branch, same word list as launch_kit_page._is_bag (kept local: 8 words, not
# worth a cross-module import for this).
_BAG_WORDS = ("bag", "tote", "pouch", "purse", "backpack", "duffel", "duffle",
              "clutch", "satchel")


def _is_bag(kw):
    k = (kw or "").lower()
    return any(w in k for w in _BAG_WORDS)


# V37.4: turn rival-review complaints (from the Evidence Router) into concrete
# "what to PROVE with this photo" guidance, mapped to the slots that can answer
# each worry. Each entry = (slot-name substrings that match, note). Buyer worries
# come straight from real Etsy reviews of competing listings.
def _proof_notes(evidence):
    if not evidence or not evidence.get("has_evidence"):
        return []
    notes = []
    comp = evidence.get("complaints") or {}
    if comp.get("material"):
        notes.append((("macro", "print detail", "fabric"),
                      f"Rival reviews flag thin / low quality ×{comp['material']} — "
                      "shoot a dense close-up that proves fabric weight and stitch "
                      "coverage; show thickness, not just the design."))
    if comp.get("size"):
        notes.append((("size chart", "fabric"),
                      f"Buyers mention sizing ×{comp['size']} — show the garment "
                      "measured flat with your blank's REAL numbers, not stock ones."))
    if comp.get("shipping"):
        notes.append((("care", "how to order"),
                      f"Rivals get shipping complaints ×{comp['shipping']} — state a "
                      "realistic dispatch time and 'made to order' clearly."))
    if comp.get("accuracy") or comp.get("personalization"):
        n = (comp.get("accuracy", 0) + comp.get("personalization", 0))
        notes.append((("personalization",),
                      f"Reviews mention wrong / misspelled personalization ×{n} — "
                      "show the exact preview the buyer gets and a 'we confirm "
                      "spelling before we make it' step."))
    if evidence.get("photo_expectation_signals"):
        notes.append((("hero", "front flat"),
                      f"Buyers post their own photos ×{evidence['photo_expectation_signals']} "
                      "— your real photos must match reality; shoot true-to-life."))
    top_recip = None
    recs = evidence.get("recipient_nouns") or []
    if recs:
        top_recip = recs[0].get("value")
    if top_recip:
        notes.append((("gift", "occasion"),
                      f"Top buyer buys for **{top_recip}** — stage the gift scene for "
                      f"a {top_recip} (age-appropriate props, gift wrap)."))
    variants = evidence.get("top_mentioned_variants") or []
    if variants:
        tv = variants[0].get("value")
        if tv:
            notes.append((("color", "variant"),
                          f"Most-mentioned variant is **{tv}** — put it first in the "
                          "color grid and the hero."))
    return notes


def build(keyword, product="Embroidered Sweatshirt", mode="embroidery", pers=True,
          evidence=None):
    """Return an ordered list of image slots, each:
    {n, slot, purpose, real_photo (bool), prompt, ai_note (real slots only),
     prove (optional list of review-driven 'prove this' notes)}.

    `evidence` (optional) is the Evidence Router's evidence_for_keyword() dict; when
    present, buyer worries from rival reviews are attached to the matching slots as
    `prove` notes. It never changes the prompts themselves and never overrides the
    real-photo honesty rule.
    """
    kw = (keyword or "your niche").strip()
    prod = product or "sweatshirt"
    rules = _rules(mode)
    emb = (mode or "").lower().startswith("emb")
    made = "embroidered" if emb else "printed"
    bag = _is_bag(kw) or _is_bag(prod)
    # Embroidery is stitched thread -- "won't crack or fade" is a safe, near-
    # universal claim about the METHOD. Print quality varies by supplier/ink/
    # process, so an equally absolute print claim isn't ours to make without
    # manufacturer evidence -- care guidance instead of a durability promise.
    durability = ("Embroidery won't crack or fade" if emb else
                 "Follow the care instructions to help preserve print quality")

    hero_prompt = (
        f"Lifestyle product photo: a {prod.lower()} with a {made} '{kw}' design "
        "on the front, held or set down naturally by a person in a bright, "
        "natural setting that fits the buyer (e.g. an airport, a doorway before "
        "travel). Soft daylight, shallow depth of field, product sharp and "
        "centered, warm inviting mood, photorealistic. Square 2000x2000."
        if bag else
        f"Lifestyle product photo: a {prod.lower()} with a {made} '{kw}' design "
        "on the chest, worn by a smiling model in a bright, natural setting that "
        "fits the buyer (e.g. a cozy cafe or sunny doorway). Soft daylight, "
        "shallow depth of field, product sharp and centered, warm inviting mood, "
        "photorealistic. Square 2000x2000.")

    slots = [
        ("Hero / thumbnail", "Converts the click. Product shown in a real, on-brand "
         "scene - this one image decides your CTR.", True, hero_prompt),

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
         f"{prod.lower()} {'front panel' if bag else 'chest area'} with an example "
         f"name in the {made} font, an arrow/callout pointing to the "
         "personalization spot, short label 'Add any name - max 12 characters'. "
         "Simple, modern, legible; " + rules + "."),

        ("Size chart", "Reduces returns + wrong-size / wrong-capacity messages.", False,
         ("A clean, modern dimensions graphic showing width x height x depth in "
          "inches and cm, brand-neutral soft background, large legible "
          "sans-serif type, a small product silhouette showing where each "
          "measurement is taken. [Replace the numbers with your blank's real "
          "measurements.]") if bag else
         ("A clean, modern size-chart graphic (S-3XL) with chest width and length "
          "in inches and cm, brand-neutral soft background, large legible "
          "sans-serif type, a small garment silhouette showing where "
          "measurements are taken. [Replace the numbers with your blank's real "
          "measurements.]")),

        ("Color / variant grid", "Lets the buyer self-select their color fast.", False,
         f"A tidy grid showing the {prod.lower()} in each available color "
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

        (("Material / hardware detail" if bag else "Fabric / fit detail"),
         ("Second trust signal - straps, closure, lining quality." if bag else
          "Second trust signal - drape, cuff, weight."), True,
         (f"Detail product photo of the {prod.lower()}'s handles/strap, closure "
          "and interior lining, soft window light showing material quality and "
          "construction, photorealistic.") if bag else
         (f"Detail product photo of the {prod.lower()} cuff, collar and fabric "
          "drape on a model or wooden hanger, soft window light showing garment "
          "quality, weight and fit, photorealistic.")),

        ("Care + processing", "Sets expectations - handmade, care, dispatch time.", False,
         # No real per-day processing time is known at prompt-build time, and
         # this text gets rendered as literal pixels by an image generator --
         # unlike listing copy, there's no human-edit step before publish, so
         # a bracket placeholder here would bake "[X]" into the graphic itself
         # instead of getting caught and filled in. Omit the day-count clause
         # rather than guess or leave a placeholder for the AI to render.
         ("A simple icon graphic: 'Made to order', 'Spot clean only', "
          f"'{durability}', on a soft solid background with clean line icons "
          "and short labels. " + rules + ".")
         if bag else
         ("A simple icon graphic: 'Made to order', 'Wash cold / inside out', "
          f"'{durability}', on a soft solid background with clean line icons "
          "and short labels. " + rules + ".")),

        ("Video thumbnail / 360", "Video lifts Etsy quality score.", True,
         (f"A single video-frame style image: slow 360 turn of the {prod.lower()} "
          f"on a turntable showing the {made} '{kw}' design and texture up close, "
          "bright even light, smooth studio background, photorealistic.") if bag else
         (f"A single video-frame style image: slow 360 turn of the {prod.lower()} "
          f"on a model showing the {made} '{kw}' design and texture up close, "
          "bright even light, smooth studio background, photorealistic.")),
    ]
    proof = _proof_notes(evidence)
    out = []
    for i, (slot, purpose, real, prompt) in enumerate(slots, 1):
        d = {"n": i, "slot": slot, "purpose": purpose,
             "real_photo": real, "prompt": prompt}
        if real:
            # every slot carries a full, listing-matched prompt; on real-photo
            # slots the prompt is a SHOT BRIEF the staff shoot + review, not an
            # "AI for review only" caveat.
            d["ai_note"] = REAL_NOTE
        # attach review-driven "prove this" notes to the slots that can answer
        # each buyer worry (matched by slot name, case-insensitive substring)
        sl = slot.lower()
        pv = [note for subs, note in proof if any(s in sl for s in subs)]
        if pv:
            d["prove"] = pv
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
        tag = (" [REAL-PHOTO slot — the AI render is a REFERENCE to plan the "
               "shot; a human reviews it and the PUBLISHED image must be a real "
               "photo of the actual product]" if s.get("real_photo") else "")
        L.append(f"{s['n']}. {s['slot']}{tag}: {s['prompt']}")
    L += ["", "Begin with image 1 now."]
    return "\n".join(L)
