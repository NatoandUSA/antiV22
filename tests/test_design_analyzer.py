"""Design Analyzer — offline tests (Gemini call is monkeypatched).

Covers the parts that must be right without the network: JSON handling, tag
normalisation, the deterministic IP/stitch gate LAYERED over the model, graceful
failure with no key, and that the render helpers produce HTML.
"""
import json

from src import design_analyzer as da

BASE = {
    "content_en": "A cute cartoon dachshund with flowers.",
    "content_vi": "Chú chó lạp xưởng dễ thương với hoa.",
    "meaning_en": "A playful dog design for dog lovers.",
    "meaning_vi": "Thiết kế chó vui nhộn cho người yêu chó.",
    "trademark_en": "Appears to be an original generic dog illustration.",
    "trademark_vi": "Có vẻ là hình minh hoạ chó gốc, chung chung.",
    "ip_owner": "",
    "risk_level": "Low",
    "risk_reason_en": "Generic subject, no brand references.",
    "risk_reason_vi": "Chủ đề chung chung, không tham chiếu thương hiệu.",
    "subject": "dachshund dog",
    "style": "vintage line-art",
    "extracted_text": [],
    "prompt_original": "Recreate: a centered vintage line-art dachshund ...",
    "prompt_redesign_standard": "Original: a stylised dachshund with daisies ...",
    "prompt_redesign_embroidery": "Bold 4-color dachshund badge, thick outlines ...",
    "seo_title": "Cute Dachshund Dog Shirt Weiner Dog Lover Gift for Her",
    "seo_tags": ["dog shirt", "dachshund gift", "dog mom tee", "weiner dog",
                 "puppy lover", "dog lover gift", "cute dog shirt", "dog owner tee",
                 "pet gift idea", "dog dad shirt", "doxie shirt", "dog art tee",
                 "gift for her", "an extra 14th tag"],   # 14 -> must trim to 13
    "seo_description": "A charming dachshund design — a great gift for dog moms.",
}


def _fake(payload):
    def _f(*a, **k):
        return json.dumps(payload)
    return _f


def test_missing_key_is_graceful():
    r = da.analyze(b"\xff\xd8\xffdata", title="dog shirt", key="")
    assert r["ok"] is False and "GEMINI_API_KEY" in r["error"]


def test_happy_path_parses_and_trims_tags(monkeypatch):
    monkeypatch.setattr("src.design_analyzer._gemini", _fake(BASE))
    r = da.analyze(b"\x89PNG\r\n\x1a\n....", title="dachshund flower shirt",
                   mode=None, key="test")
    assert r["ok"] is True
    assert len(r["seo_tags"]) == 13            # trimmed from 14
    assert all(len(t) <= 20 for t in r["seo_tags"])
    g = r["gates"]
    assert g["ip_level"] == "LOW"
    assert g["produce_verdict"] == "OK_TO_DESIGN"


def test_blocklist_overrides_model_low_risk(monkeypatch):
    # model says Low, but our OWN trademark gate must catch the brand in the title
    monkeypatch.setattr("src.design_analyzer._gemini", _fake(BASE))
    r = da.analyze(b"\xff\xd8\xffx", title="bluey birthday shirt", key="test")
    assert r["ok"] is True
    assert r["gates"]["ip_level"] == "HIGH"
    assert r["gates"]["produce_verdict"] == "SKIP"


def test_named_owner_lifts_risk_to_at_least_medium(monkeypatch):
    p = dict(BASE, risk_level="Low", ip_owner="Disney",
             trademark_en="Mickey silhouette present.")
    monkeypatch.setattr("src.design_analyzer._gemini", _fake(p))
    r = da.analyze(b"\xff\xd8\xffx", title="cute mouse shirt", key="test")
    assert r["gates"]["ip_level"] in ("MEDIUM", "HIGH")
    assert r["gates"]["produce_verdict"] in ("VERIFY", "SKIP")


def test_embroidery_stitch_risk_triggers_redesign(monkeypatch):
    p = dict(BASE, subject="galaxy nebula portrait",
             style="watercolor gradient photorealistic",
             content_en="A watercolor galaxy nebula with fine gradient detail.")
    monkeypatch.setattr("src.design_analyzer._gemini", _fake(p))
    r = da.analyze(b"\xff\xd8\xffx", title="galaxy watercolor art", mode="embroidery",
                   key="test")
    assert r["gates"]["stitch"]["label"] == "STITCH_RISK"
    assert r["gates"]["produce_verdict"] == "REDESIGN"


def test_bad_json_is_graceful(monkeypatch):
    monkeypatch.setattr("src.design_analyzer._gemini", lambda *a, **k: "not json at all")
    r = da.analyze(b"\xff\xd8\xffx", title="x", key="test")
    assert r["ok"] is False and "JSON" in r["error"]


def test_model_fallback_on_retired_model(monkeypatch):
    # first model 404s ("no longer available"); analyze must fall back and succeed.
    calls = []

    def _f(image_b64, mime, prompt, model, key, timeout=45):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("Gemini HTTP 404: model no longer available")
        return json.dumps(BASE)

    monkeypatch.setattr("src.design_analyzer._gemini", _f)
    r = da.analyze(b"\xff\xd8\xffx", title="dog shirt", key="test")
    assert r["ok"] is True
    assert len(calls) >= 2                    # retried at least once


def test_auth_error_does_not_retry(monkeypatch):
    # a non-model error (e.g. bad key) must fail fast, not loop the fallbacks.
    calls = []

    def _f(*a, **k):
        calls.append(1)
        raise RuntimeError("Gemini HTTP 403: API key invalid")

    monkeypatch.setattr("src.design_analyzer._gemini", _f)
    r = da.analyze(b"\xff\xd8\xffx", title="x", key="test")
    assert r["ok"] is False and len(calls) == 1


def test_render_helpers_produce_html(monkeypatch):
    monkeypatch.setattr("src.design_analyzer._gemini", _fake(BASE))
    r = da.analyze(b"\xff\xd8\xffx", title="dog shirt", key="test")
    out = da.result_html(r, "csrf123")
    assert "Etsy SEO pack" in out and "Design Analyzer" in out
    frm = da.form_html("csrf123")
    assert 'name="_csrf"' in frm and "multipart/form-data" in frm
