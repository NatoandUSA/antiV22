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
    # V37.2: page is the thin "Design Inbox"; no Gemini, no "Bridge" naming.
    assert "Design Inbox" in html and "Gemini" not in html and "Bridge" not in html


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


def test_no_autoreject_on_run_id_mismatch(sandbox):
    # V37.2: NO auto-reject. A run_id mismatch is no longer an error — the owner
    # decides. The only hard failure is "no JSON found" (tested below).
    inp = _pack()
    v = b.import_result(inp["bridge_run_id"], _good_result("BR-WRONG-0000"))
    assert v["ok"] and v["errors"] == []


def test_red_ip_is_warning_not_reject(sandbox):
    # V37.2: RED IP is surfaced as a WARNING, not an auto-reject.
    inp = _pack()
    bad = _good_result(inp["bridge_run_id"], safety={"ip_status": "RED"},
                       ip_status="RED")
    v = b.import_result(inp["bridge_run_id"], bad)
    assert v["ok"] and any("RED" in w for w in v["warnings"])


def test_machine_file_claim_is_warning_not_reject(sandbox):
    # V37.2: machine-file wording warns, never blocks import.
    inp = _pack()
    r = json.loads(_good_result(inp["bridge_run_id"]).split("\n", 1)[1].rsplit("\n", 2)[0])
    r["artifacts"] = ["ready DST file, machine-ready"]
    raw = "```RESULT_JSON\n" + json.dumps(r) + "\n```"
    v = b.import_result(inp["bridge_run_id"], raw)
    assert v["ok"] and any("achine" in w for w in v["warnings"])


def test_only_hard_failure_is_no_json(sandbox):
    inp = _pack()
    v = b.import_result(inp["bridge_run_id"], "no json here at all")
    assert not v["ok"] and v["errors"]


def test_flat_format_result_is_accepted_and_seeds_flat(sandbox):
    # The new lean skill emits a FLAT object (main_keyword/buyer/... at top level).
    flat = '```RESULT_JSON\n{"main_keyword":"nurse gift","buyer":"nurses",' \
           '"ip_status":"GREEN","target_product":"sweatshirt"}\n```'
    run_id, v = b.import_pasted(flat)
    assert v["ok"]
    b.approve(run_id, owner="Alex")
    seeds = b.listing_seeds(run_id)
    assert seeds["main_keyword"] == "nurse gift"


def test_delete_run_removes_it(sandbox):
    inp = _pack()
    b.import_result(inp["bridge_run_id"], _good_result(inp["bridge_run_id"]))
    assert any(r["run_id"] == inp["bridge_run_id"] for r in b.list_runs())
    out = b.delete_run(inp["bridge_run_id"])
    assert out["ok"]
    assert not any(r["run_id"] == inp["bridge_run_id"] for r in b.list_runs())


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


# ---- WS1.2 management table + WS1.1 routing tests ---------------------------
def test_mgmt_table_renders_nine_columns(sandbox):
    _pack(keyword="dog mom shirt")
    html = b.management_table_html(b.list_runs(), csrf="T")
    for col in ("Run ID", "Keyword", "Batch", "Created", "Target", "Mode",
                "State", "Launched by", "Next action"):
        assert col in html, col


def test_waiting_run_shows_view_and_delete(sandbox):
    # V37.2: a run with no result is housekeeping only — View + Delete, no
    # prompt/pack actions (the page no longer generates prompts).
    _pack()
    runs = b.list_runs()
    assert runs and runs[0]["state"] in ("PACK_CREATED", "WAITING_FOR_RESULT")
    html = b.management_table_html(runs, csrf="T")
    assert "View" in html and "Delete" in html
    assert "Copy Prompt" not in html


def test_pack_run_link_opens_work_page_not_rejected(sandbox):
    inp = _pack()
    run = b.get_run(inp["bridge_run_id"])
    html = b.run_view_html(run, csrf="T")
    assert "Waiting for GPT result" in html          # work page
    assert "Rejected" not in html                    # WS1.1: NOT the rejected page
    assert 'id="import"' in html                      # has the import box


def test_missing_result_is_not_rejected(sandbox):
    inp = _pack()
    runs = b.list_runs()
    assert runs[0]["state"] != "REJECTED"
    assert runs[0]["state"] != "IMPORT_FAILED"
    assert runs[0]["state"] == "WAITING_FOR_RESULT" or runs[0]["state"] == "PACK_CREATED"


def test_rejected_state_only_for_failed_or_rejected(sandbox):
    # a) failed import -> IMPORT_FAILED (not a bare pack)
    inp = _pack()
    b.import_result(inp["bridge_run_id"], "not json at all")
    assert b.list_runs()[0]["state"] == "IMPORT_FAILED"
    # b) owner rejection -> REJECTED
    inp2 = _pack()
    b.import_result(inp2["bridge_run_id"], _good_result(inp2["bridge_run_id"]))
    b.reject(inp2["bridge_run_id"], owner="Alex")
    st = {r["run_id"]: r["state"] for r in b.list_runs()}
    assert st[inp2["bridge_run_id"]] == "REJECTED"


def test_batch_fallback_single_run(sandbox):
    _pack()
    assert b.list_runs()[0]["batch"] == "single-run"
    inp = _pack(batch="autumn-drop")
    assert {r["run_id"]: r["batch"] for r in b.list_runs()}[inp["bridge_run_id"]] == "autumn-drop"


def test_launched_by_fallback(sandbox):
    _pack()                       # no launched_by supplied
    assert b.list_runs()[0]["launched_by"] in ("unknown", "owner")
    inp = _pack(launched_by="Quyen")
    assert {r["run_id"]: r["launched_by"] for r in b.list_runs()}[inp["bridge_run_id"]] == "Quyen"


def test_filters_render(sandbox):
    _pack()
    html = b.management_table_html(b.list_runs(), csrf="T")
    for f in ('id="dsb-q"', 'id="dsb-state"', 'id="dsb-batch"', 'id="dsb-user"', 'id="dsb-date"'):
        assert f in html, f


def test_candidate_actions_are_two_decisions_plus_delete(sandbox):
    # V37.2: a candidate shows exactly the owner's 2 decision buttons
    # (Approve / Reject) + Review + Delete. "Send to Launch Kit" only appears
    # AFTER approval, never on a raw candidate.
    inp = _pack()
    b.import_result(inp["bridge_run_id"], _good_result(inp["bridge_run_id"]))
    html = b.management_table_html(b.list_runs(), csrf="T")
    assert b.list_runs()[0]["state"] == "VALIDATED_CANDIDATE"
    for a in ("Review", "Approve", "Reject", "Delete"):
        assert a in html, a
    assert "Send to Launch Kit" not in html
    # after approval the handoff button appears
    b.approve(inp["bridge_run_id"], owner="Alex")
    html2 = b.management_table_html(b.list_runs(), csrf="T")
    assert "Send to Launch Kit" in html2


def test_no_network_on_render(sandbox, monkeypatch):
    import socket
    def _boom(*a, **k):
        raise AssertionError("network call during render!")
    monkeypatch.setattr(socket.socket, "connect", _boom)
    _pack()
    b.management_table_html(b.list_runs(), csrf="T")   # must not touch the network
    b.form_html(csrf="T", runs=b.list_runs())
