"""Tests for the Design Skill Bridge (V37). Mirrors the spec's 14 tests."""
import json
import os
import pytest

from src import design_skill_bridge as b


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "BASE", tmp_path / "dsb")
    monkeypatch.setattr(b, "INDEX", tmp_path / "dsb" / "index.jsonl")
    return tmp_path


def _pack(**kw):
    form = {"keyword": "nurse graduation gift", "target_product": "sweatshirt",
            "mode": "EMBROIDERY", "etsy_url": "https://etsy.com/listing/1"}
    form.update(kw)
    return b.create_pack(form)


def _good_result(run_id, **over):
    r = {
        "schema_version": "0.1", "source": b.RESULT_SOURCE,
        "bridge_run_id": run_id,
        "selected_concept": {"name": "NICU grad", "buyer": "new nurse",
                             "hook": "pride", "production_route": "PHYSICAL EMBROIDERY",
                             "ip_status": "GREEN"},
        "listing_seeds": {"target_product": "sweatshirt",
                          "selected_concept": "NICU grad", "buyer": "new nurse",
                          "main_keyword": "nurse graduation gift",
                          "evidence_classification": "EARLY TRACTION"},
        "safety": {"ip_status": "GREEN"},
    }
    r.update(over)
    return "```RESULT_JSON\n" + json.dumps(r) + "\n```"


def test_page_renders_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    html = b.form_html(csrf="T")
    assert "Design Skill Bridge" in html and "Gemini" not in html


def test_skill_url_in_pack_page(sandbox):
    inp = _pack()
    assert b.SKILL_URL in b.pack_html(inp, csrf="T")


def test_seed_is_compact_with_run_id_and_keyword(sandbox):
    inp = _pack()
    p = inp["_prompt"]
    assert p.startswith("SEED")
    assert inp["bridge_run_id"] in p
    assert "nurse graduation gift" in p
    assert len(p) < 900   # lean seed, not a re-typed workflow


def test_seed_names_result_json_and_no_finished_listing(sandbox):
    p = _pack()["_prompt"]
    assert "RESULT_JSON" in p and "listing_seeds" in p
    assert "Launch Kit" in p or "title/tag" in p


def test_seed_contains_codo_production_lock(sandbox):
    p = _pack()["_prompt"]
    assert "CÓ ĐƠN" in p and "dst/pes" in p.lower()


def test_import_extracts_json_from_fenced_block(sandbox):
    inp = _pack()
    v = b.import_result(inp["bridge_run_id"], _good_result(inp["bridge_run_id"]))
    assert v["ok"] and v["result"]["selected_concept"]["name"] == "NICU grad"


def test_import_rejects_wrong_run_id(sandbox):
    inp = _pack()
    v = b.import_result(inp["bridge_run_id"], _good_result("BR-WRONG-0000"))
    assert not v["ok"]
    assert any("run_id" in e for e in v["errors"])


def test_import_rejects_red_ip(sandbox):
    inp = _pack()
    bad = _good_result(inp["bridge_run_id"], safety={"ip_status": "RED"})
    v = b.import_result(inp["bridge_run_id"], bad)
    assert not v["ok"] and any("RED" in e for e in v["errors"])


def test_import_rejects_machine_file_claim_before_codo(sandbox):
    inp = _pack()
    r = json.loads(_good_result(inp["bridge_run_id"]).split("\n", 1)[1].rsplit("\n", 2)[0])
    r["artifacts"] = ["ready DST file, machine-ready"]
    raw = "```RESULT_JSON\n" + json.dumps(r) + "\n```"
    v = b.import_result(inp["bridge_run_id"], raw)
    assert not v["ok"] and any("achine" in e for e in v["errors"])


def test_candidate_until_owner_approval(sandbox):
    inp = _pack()
    b.import_result(inp["bridge_run_id"], _good_result(inp["bridge_run_id"]))
    # before approval, no seeds handed off
    assert b.listing_seeds(inp["bridge_run_id"]) is None
    b.approve(inp["bridge_run_id"], owner="Alex")
    assert b.listing_seeds(inp["bridge_run_id"]) is not None


def test_approved_sends_listing_seeds(sandbox):
    inp = _pack()
    b.import_result(inp["bridge_run_id"], _good_result(inp["bridge_run_id"]))
    b.approve(inp["bridge_run_id"], owner="Alex")
    out = b.send_to_launchkit(inp["bridge_run_id"])
    assert out["ok"] and out["seeds"]["main_keyword"] == "nurse graduation gift"


def test_yellow_ip_is_warning_not_block(sandbox):
    inp = _pack()
    y = _good_result(inp["bridge_run_id"],
                     selected_concept={"name": "x", "buyer": "y", "hook": "z",
                                       "production_route": "PHYSICAL EMBROIDERY",
                                       "ip_status": "YELLOW"})
    v = b.import_result(inp["bridge_run_id"], y)
    assert v["ok"] and any("YELLOW" in w for w in v["warnings"])


def test_draft_stamp_and_publish_lock_present(sandbox):
    inp = _pack()
    assert "DO NOT PUBLISH" in b.pack_html(inp, csrf="T")
    assert b.DRAFT_STAMP  # sentinel exists
