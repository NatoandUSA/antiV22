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
            assert "comparison/mockup only" in s["ai_note"]
    assert sum(1 for s in slots if s["real_photo"]) >= 4


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


def test_launch_kit_markdown_still_works(monkeypatch):
    from src import etsy_proof as ep
    monkeypatch.setattr(ep, "build_proof", lambda mode=None: {})
    monkeypatch.setattr(
        "src.shortlister_integration._enrich_row", lambda d, m=None: False)
    from src import interactive as iv
    out = iv.launch_kit("teacher shirt 4x", "embroidery")
    assert "Launch Kit" in out and "checklist" in out.lower()
