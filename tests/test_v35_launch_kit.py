"""V35 tests: niche proof roll-up, Launch Kit copy-paste page, Photo Studio
AI prompts + GPT runner. Offline - no live MCP, proof sources patched."""
import socket

socket.setdefaulttimeout(4)


# --------------------------- niche proof roll-up ---------------------------

def _pm(*items):
    """Build a proof_map from (keyword, sold) pairs via the real aggregator
    keys, mirroring build_proof output shape."""
    from src import etsy_proof as ep
    out = {}
    for kw, sold in items:
        out[ep._canon(kw)] = {
            "keyword": kw, "sold": sold, "sold_24h": 0, "revenue": sold * 20.0,
            "shops": 2, "shops_known": True, "listings": 3, "young": 0,
            "score": 50.0, "verdict": "SELLING" if sold else "LISTED",
            "evidence": f"{sold} sold",
        }
    return out


def test_niche_proof_rolls_up_siblings():
    from src import etsy_proof as ep
    pm = _pm(("kindergarten teacher shirt", 47),
             ("teacher shirt", 27),
             ("kindergarten teacher gift shirt", 16),
             ("nurse shirt", 99))          # different subject - excluded
    agg = ep.niche_proof("personalized kindergarten teacher embroidered shirt",
                         pm)
    assert agg is not None and agg["match"] == "niche"
    assert agg["sold"] == 47 + 27 + 16     # nurse group NOT absorbed
    assert agg["groups"] == 3
    assert agg["members"][0]["keyword"] == "kindergarten teacher shirt"


def test_niche_proof_needs_a_subject_token():
    from src import etsy_proof as ep
    pm = _pm(("kindergarten teacher shirt", 47))
    # generic phrase (product + modifier only) must never absorb a niche
    assert ep.niche_proof("personalized embroidered shirt", pm) is None


def test_niche_proof_product_compatibility():
    from src import etsy_proof as ep
    pm = _pm(("teacher mug", 80), ("teacher shirt", 10))
    agg = ep.niche_proof("kindergarten teacher embroidered shirt", pm)
    # mug proof must not prop up a shirt launch
    assert agg is not None and agg["sold"] == 10


def test_niche_proof_never_mints_higher_verdict():
    from src import etsy_proof as ep
    pm = _pm(("teacher shirt", 30), ("teacher retirement shirt", 40))
    agg = ep.niche_proof("personalized teacher appreciation shirt", pm)
    assert agg["verdict"] == "SELLING"     # best member tier, not PROVEN


# --------------------------- kit evidence fallback -------------------------

def test_kit_evidence_niche_fallback(monkeypatch):
    from src import interactive as iv
    from src import etsy_proof as ep

    pm = _pm(("kindergarten teacher shirt", 47), ("teacher shirt", 27))
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: pm)
    # exact keyword has NO index entry -> enrich adds nothing
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    ev = iv.kit_evidence("personalized kindergarten teacher embroidered shirt",
                         "embroidery")
    assert ev["exact_indexed"] is False
    assert ev["proof"] and ev["proof"]["match"] == "niche"
    assert ev["proof"]["sold"] == 74
    lines = "\n".join(iv._niche_fallback_lines(ev))
    assert "Niche-level evidence" in lines and "open lane" in lines


def test_kit_verdict_keeps_exact_when_indexed(monkeypatch):
    from src import interactive as iv
    from src import etsy_proof as ep
    pm = _pm(("patchwork usa tee", 12))
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: pm)

    def fake_enrich(d, m=None):
        d["avg_conversion_rate"] = 3.0
        d["listing_count"] = 500
        d["avg_price"] = 25.0
        d["search_volume"] = 900
        return True

    monkeypatch.setattr("src.shortlister_integration._enrich_row", fake_enrich)
    ev = iv.kit_evidence("patchwork usa tee", "pod")
    assert ev["exact_indexed"] is True
    # exact canonical proof stays exact - the roll-up must NOT replace it
    assert ev["proof"] and ev["proof"]["match"] == "exact"


# --------------------------- photo studio ----------------------------------

def test_every_slot_has_ai_prompt_and_real_flags():
    from src import photo_brief as pb
    slots = pb.build("teacher shirt 4x", mode="embroidery")
    assert len(slots) == 12
    for s in slots:
        assert s["prompt"] and "REAL PHOTO" not in s["prompt"].upper()
        if s["real_photo"]:
            assert "real photo" in s["ai_note"].lower()
    assert sum(1 for s in slots if s["real_photo"]) >= 4


# --------------------------- V38.3 bag-vs-apparel audit fix -----------------
# Launch Kit's audit (owner: "make sure output quality is right, not just the
# pipeline") found every copy/photo template hardcoded to apparel (sizing S-3XL,
# garment color, worn-on-chest photos) regardless of actual product. 2 of the
# 3 open Build Queue sprint keywords are bags. Minimal bag branch, not a full
# product-category system -- pin that apparel keeps its original wording and
# bag keywords get bag-appropriate wording, in both files that had the bug.

def test_photo_brief_bag_prompts_avoid_garment_anatomy():
    from src import photo_brief as pb
    slots = pb.build("mens carry on bag", product="Printed Tote Bag", mode="pod")
    joined = " ".join(s["prompt"].lower() for s in slots)
    for bad in ("chest", "cuff", "collar", "worn by a smiling model",
                "garment color", "garment silhouette"):
        assert bad not in joined, f"garment-only phrase leaked into bag prompts: {bad!r}"
    assert "handles" in joined or "strap" in joined


def test_photo_brief_apparel_prompts_unchanged():
    from src import photo_brief as pb
    slots = pb.build("teacher shirt 4x", mode="embroidery")
    joined = " ".join(s["prompt"].lower() for s in slots)
    assert "chest" in joined and "cuff" in joined and "collar" in joined


def test_launch_kit_description_bag_vs_apparel():
    from src import launch_kit_page as lkp
    bag_desc = lkp._description("mens carry on bag", "pod", "[price note]")
    assert "s–3xl" not in bag_desc.lower() and "garment color" not in bag_desc.lower()
    assert "dimensions" in bag_desc.lower() or "capacity" in bag_desc.lower()
    shirt_desc = lkp._description("teacher shirt", "pod", "[price note]")
    assert "s–3xl" in shirt_desc.lower()


def test_launch_kit_policies_bag_care_not_wash_instructions():
    from src import launch_kit_page as lkp
    bag_policy = lkp._policies("mini bride tote bags", "pod")
    assert "machine wash cold" not in bag_policy.lower()
    assert "spot clean" in bag_policy.lower()
    shirt_policy = lkp._policies("teacher shirt", "pod")
    assert "machine wash cold" in shirt_policy.lower()


def test_bag_style_echoes_keyword_not_a_default_tote():
    """Defaulting every bag keyword's photo/description product label to
    'Tote Bag' would assert a specific style the keyword never claimed.
    Only name a sub-type when the keyword itself says one."""
    from src import launch_kit_page as lkp
    assert lkp._bag_style("mens carry on bag") == "Bag"          # no sub-type named -> neutral
    assert lkp._bag_style("mini bride tote bags") == "Tote Bag"  # keyword says tote -> echo it
    assert lkp._bag_style("mens duffel bag") == "Duffel Bag"
    assert lkp._bag_style("weekender bag for men") == "Weekender Bag"
    assert lkp._bag_style("leather backpack purse") == "Backpack"  # first/most-specific match wins


def test_launch_kit_build_product_label_uses_bag_style(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import launch_kit_page as lkp
    html = lkp.build("mens carry on bag", "pod")
    assert "tote bag" not in html.lower()
    html2 = lkp.build("mini bride tote bags", "pod")
    assert "tote bag" in html2.lower()


# --------------------------- V38.3 title placeholder fix --------------------

def test_title_never_contains_bracket_placeholder(sandbox):
    from src import launch_kit_page as lkp
    title = lkp._title("mens carry on bag", "pod")
    assert "[Recipient]" not in title and "[" not in title


def test_title_uses_real_recipient_when_evidence_exists(sandbox, monkeypatch):
    from src import launch_kit_page as lkp
    monkeypatch.setattr(
        "src.feed_evidence_router.evidence_for_keyword",
        lambda kw, max_listings=6: {"recipient_nouns": [{"value": "granddaughter", "count": 3}]})
    title = lkp._title("personalized name tote handbag", "pod")
    assert "Gift for Granddaughter" in title
    assert "[Recipient]" not in title


def test_title_omits_gift_clause_without_evidence(sandbox, monkeypatch):
    from src import launch_kit_page as lkp
    monkeypatch.setattr(
        "src.feed_evidence_router.evidence_for_keyword",
        lambda kw, max_listings=6: {"recipient_nouns": []})
    title = lkp._title("mens carry on bag", "pod")
    assert "Gift for" not in title
    assert "[Recipient]" not in title


def test_photo_brief_care_durability_claim_matches_mode():
    from src import photo_brief as pb
    pod_slots = pb.build("mens carry on bag", product="Printed Tote Bag", mode="pod")
    care = next(s for s in pod_slots if "care" in s["slot"].lower())
    assert "embroidery" not in care["prompt"].lower()
    # POD print quality varies by supplier/ink -- no absolute durability
    # promise without manufacturer evidence, care guidance instead.
    assert "won't fade" not in care["prompt"].lower()
    assert "won't crack" not in care["prompt"].lower()
    assert "preserve print quality" in care["prompt"].lower()
    emb_slots = pb.build("teacher shirt 4x", mode="embroidery")
    care2 = next(s for s in emb_slots if "care" in s["slot"].lower())
    assert "embroidery won't crack or fade" in care2["prompt"].lower()


def test_photo_brief_no_shipping_day_placeholder_baked_into_image_prompt():
    """'[X] business days' sat inside the literal render-this-text portion of
    an image-generation prompt -- no human-edit step exists between this
    prompt and an AI generator, so the bracket would get drawn as pixels.
    'Made to order' alone stays true without guessing a real number."""
    from src import photo_brief as pb
    for kw, kwargs in (("mens carry on bag",
                        {"product": "Printed Tote Bag", "mode": "pod"}),
                       ("teacher shirt 4x", {"mode": "embroidery"})):
        slots = pb.build(kw, **kwargs)
        care = next(s for s in slots if "care" in s["slot"].lower())
        assert "[X]" not in care["prompt"]
        assert "business days" not in care["prompt"].lower()
        assert "made to order" in care["prompt"].lower()


def test_gpt_runner_contains_all_12_briefs():
    from src import photo_brief as pb
    r = pb.runner("teacher shirt 4x", mode="embroidery")
    for n in range(1, 13):
        assert f"{n}. " in r
    assert "'.'" in r          # advance-on-dot instruction
    assert "ONE per message" in r
    assert "real photo" in r.lower()


def test_photo_prompts_page_has_runner_block():
    from src import interactive as iv
    out = iv.photo_prompts("teacher shirt 4x", "embroidery")
    assert "GPT runner" in out
    assert "comparison/mockup only" in out


# --------------------------- launch kit page -------------------------------

def test_launch_kit_page_builds(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import launch_kit_page as lkp
    html = lkp.build("personalized kindergarten teacher embroidered shirt",
                     "embroidery")
    # red human fields present
    assert html.count("needs-human") >= 5
    # copy targets for every block
    for tid in ("lk-title", "lk-tags", "lk-desc", "lk-pers", "lk-order",
                "lk-policy"):
        assert f'data-copy="{tid}"' in html and f'id="{tid}"' in html
    # marketplace layout + gallery + gates
    assert 'class="pv"' in html and "lkgal" in html and "lkgates" in html
    assert "HOW TO ORDER" in html and "Vietnam" in html
    # never a fabricated number: no index data -> price honest-null
    assert "SET PRICE" in html or "market price —" in html


def test_launch_kit_page_escapes_keyword(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import launch_kit_page as lkp
    html = lkp.build("teacher's 'gift' shirt", "embroidery")
    assert "<script" not in html.lower().replace("</script", "")


def test_launch_kit_page_compact_preview_and_submit_form(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import launch_kit_page as lkp
    html = lkp.build("goose funny shirt", "pod")
    # compact preview: thumb strip + collapsible 12-image plan, capped width
    assert "lkpv" in html and "lkthumbs" in html
    assert "Full 12-image plan" in html
    # send-to-manager section present with the three decision words explained
    assert 'action="/launch-kit/submit"' in html
    assert "List</b> / <b>Fix</b> / <b>Decline" in html
    # sent=True swaps the form for the confirmation bar
    html2 = lkp.build("goose funny shirt", "pod", sent=True)
    assert "lksent" in html2 and 'action="/launch-kit/submit"' not in html2


def test_launch_kit_submit_creates_review_task(monkeypatch, tmp_path):
    import socket
    socket.setdefaulttimeout(4)
    from src import appdb
    old_db = appdb.DB_PATH
    appdb.DB_PATH = tmp_path / "app.db"
    try:
        from src import auth, web
        from src import etsy_proof as ep
        appdb.init_db()
        monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
        monkeypatch.setattr(
            "src.shortlister_integration._enrich_row", lambda d, m=None: False)
        auth.create_user("owner2@test.local", "pw12345", "Owner", "OWNER", "t")
        u = auth.get_user_by_email("owner2@test.local")
        app = web.build_app("", "secret")
        app.config["TESTING"] = True
        c = app.test_client()
        with c.session_transaction() as s:
            s["uid"] = u["user_id"]
            s["_csrf"] = "t"
        r = c.post("/launch-kit/submit",
                   data={"q": "goose funny shirt", "mode": "pod",
                         "note": "price set to $27", "_csrf": "t"})
        assert r.status_code in (301, 302) and "sent=1" in r.headers["Location"]
        from src import tasks as tk
        q = tk.review_queue()
        assert any(t["title"] == "List approval: goose funny shirt"
                   and "price set to $27" in (t.get("work_report") or "")
                   and "LISTING APPROVAL REQUEST" in (t.get("work_report") or "")
                   for t in q)
    finally:
        appdb.DB_PATH = old_db


# --------------------------- V35.2 trust hotfix ----------------------------

def test_momentum_only_capped_watch():
    from src import opportunity_score as osc
    s = osc.score({"tag": "monogrammed makeup bag", "momentum_score": 92,
                   "competition_level": "low"}, keyword="monogrammed makeup bag")
    assert s["verdict"] == "WATCH" and s["demand_grounded"] is False
    assert any("demand" in r.lower() for r in s["rationale"])


def test_demand_grounded_row_can_still_go():
    from src import opportunity_score as osc
    # real revenue + views -> demand grounded; the cap must NOT hold this back
    s = osc.score({"tag": "kindergarten teacher shirt", "momentum_score": 90,
                   "revenue": 250000, "views_24h": 400,
                   "avg_conversion_rate": 0.06, "competition_level": "low"},
                  keyword="kindergarten teacher shirt")
    assert s["demand_grounded"] is True
    assert s["verdict"] in ("GO", "CONDITIONAL")


def test_copy_warning_travels_with_red_blocks(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import launch_kit_page as lkp
    html = lkp.build("teacher shirt 4x", "embroidery")
    # red blocks carry the warning INSIDE the copyable value
    for tid in ("lk-pers", "lk-policy"):
        seg = html.split(f'id="{tid}"')[1].split("</div>")[0]
        assert "[CHECK REQUIRED BEFORE PUBLISHING]" in seg, tid
    # the title block is not red - no warning inside it
    seg = html.split('id="lk-title"')[1].split("</div>")[0]
    assert "[CHECK REQUIRED" not in seg
    # description carries its own confirm-and-delete line
    seg = html.split('id="lk-desc"')[1].split("</div>")[0]
    assert "CHECK REQUIRED BEFORE PUBLISHING" in seg
    # no pre-filled shipping promise anywhere
    assert "7–14" not in html and "DRAFT ONLY — DO NOT PUBLISH" in html


def test_photo_prompt_copy_carries_real_photo_warning():
    from src import interactive as iv
    from src import photo_brief as pb
    out = iv.photo_prompts("teacher shirt 4x", "embroidery")
    # every REAL slot's fenced (= copyable) block starts with the AI-draft
    # warning; graphic slots stay clean
    slots = pb.build("teacher shirt 4x", mode="embroidery")
    for s in slots:
        block = out.split(f"## {s['n']}. {s['slot']}")[1].split("```")[1]
        if s["real_photo"]:
            assert "do NOT use the AI output as the final Etsy image" in block
        else:
            assert "final Etsy image" not in block


def test_runner_forbids_ai_as_final_image():
    from src import photo_brief as pb
    r = pb.runner("teacher shirt 4x", mode="embroidery")
    assert "DO NOT USE THE AI OUTPUT AS THE FINAL ETSY IMAGE" in r


def test_cache_stamp_includes_proof_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import os
    from src import opportunity_inbox as oi
    led = tmp_path / "data" / "imports" / "etsy_spy" / "_proof_ledger.jsonl"
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text("{}\n", encoding="utf-8")
    s1 = oi._data_stamp()
    os.utime(led, (led.stat().st_atime, led.stat().st_mtime + 10))
    assert oi._data_stamp() != s1     # ledger-only change busts the cache


def test_xss_payloads_escaped_in_launch_kit(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    monkeypatch.setattr(
        "src.interactive._tags_for",
        lambda kw, limit=13, mode=None: ['<img src=x onerror=alert(1)>',
                                         'teacher " onclick="alert(1)',
                                         '[x](javascript:alert(1))'])
    from src import launch_kit_page as lkp
    html = lkp.build("teacher shirt", "embroidery")
    assert "<img src=x" not in html          # escaped, not raw
    assert 'onclick="alert' not in html
    # escaped TEXT may mention javascript: - what must never exist is a LIVE
    # javascript: URL inside a link/attribute
    import re
    assert not re.search(r'(href|src)\s*=\s*["\']?\s*javascript:', html,
                         re.IGNORECASE)


def test_tags_fill_to_13_when_keyword_unindexed(monkeypatch):
    # V35.3: MCP down + no captures -> the tag block must still fill from the
    # owner's data cascade and buyer-intent combos, never stop at 1 tag
    monkeypatch.setattr("src.ytrends_mcp.research_keyword",
                        lambda kw, days=30: {})
    from src import interactive as iv
    tags = iv._tags_for("funny birding tee", mode="pod")
    assert len(tags) == 13
    assert tags[0] == "funny birding tee"
    assert all(3 <= len(t) <= 20 for t in tags)
    assert len(set(tags)) == 13                      # no duplicates
    assert any("gift" in t for t in tags)            # buyer-intent covered


# --------------------------- V35.4 tag provenance --------------------------

def test_tags_carry_source_and_count(monkeypatch):
    monkeypatch.setattr("src.ytrends_mcp.research_keyword",
                        lambda kw, days=30: {})
    monkeypatch.setattr(
        "src.pattern_miner.mine",
        lambda kw=None: {"have": True, "matched": 5,
                         "top_tags": [("emo cat shirt", 9),
                                      ("custom teacher shirt", 7)],
                         "phrases": []})
    from src import interactive as iv
    infos = iv.tags_with_sources("funny emo shirt", mode="pod")
    srcs = {t["tag"]: t for t in infos}
    assert infos[0] == {"tag": "funny emo shirt", "source": "keyword",
                        "why": "your keyword - always tag 1", "count": None}
    # capture tag carries its competitor-listing count + reason
    assert srcs["emo cat shirt"]["source"] == "captures"
    assert srcs["emo cat shirt"]["count"] == 9
    assert "9 captured competitor" in srcs["emo cat shirt"]["why"]
    # product-only overlap ('shirt') must NOT ride in from captures
    assert "custom teacher shirt" not in srcs
    assert all(t["source"] in ("keyword", "related", "captures", "master",
                               "fill") for t in infos)


def test_launch_kit_top_layout_and_tag_legend(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import launch_kit_page as lkp
    html = lkp.build("funny emo shirt", "pod")
    # preview + title/tags share the top row; long blocks follow below
    assert "lktop" in html and "lkside" in html
    assert html.index('id="lk-title"') < html.index("⑤–⑧ Copy-paste")
    assert html.index('id="lk-tags"') < html.index('id="lk-desc"')
    # provenance visible: source chips + legend
    assert "tsrc-" in html and "Sources (hover any tag)" in html


def test_launch_kit_markdown_still_works(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import interactive as iv
    out = iv.launch_kit("teacher shirt 4x", "embroidery")
    assert "Launch Kit" in out and "checklist" in out.lower()
