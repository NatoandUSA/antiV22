"""Keyword Lab: long-tail-only emission, sane subjects, adjacent-buyer expansion."""
import json
from pathlib import Path

import pytest

from src import keyword_lab as kl


@pytest.fixture
def seeded_captures(tmp_path, monkeypatch):
    """Seed a capture fixture AND guarantee the miner actually reads it.

    Two defects this replaces. The fixture used to be written into the REAL
    `data/imports/etsy_spy`, polluting live capture data. And `load_batch`
    prefers the SQLite index over capture files, so on any machine with a
    populated `data/db/etsy.db` the seeded rows were silently ignored and the
    test graded whatever the server happened to hold — on the VPS that is 102
    graduation-embroidery listings, which derive the subject
    "embroidery graduation" instead of "nurse".

    Every source `load_batch` consults is redirected: captures to tmp_path, the
    index to an empty temp DB, the master CSV to a path that does not exist.
    """
    from src import data_store as ds
    from src import pattern_miner as pm

    caps = tmp_path / "etsy_spy"
    caps.mkdir()
    (caps / "zz_test_lab.json").write_text(json.dumps({
        "view": "etsy",
        "headers": ["title", "price", "shop", "search"],
        "rows": [["Personalized Nurse Embroidered Sweatshirts", "39.99", "A", "nurse"],
                 ["Custom Nurse RN Sweatshirt Gift", "42", "B", "nurse"]]}),
        encoding="utf-8")
    monkeypatch.setattr(pm, "_IMPORT_DIR", caps)
    monkeypatch.setattr(pm, "_SEARCH_DIR", tmp_path / "etsy_search")   # absent
    monkeypatch.setattr(pm, "MASTER", tmp_path / "no_master.csv")      # absent
    monkeypatch.setattr(ds, "DB_PATH", tmp_path / "db" / "empty.db")   # empty

    # THE GUARD, checked on the RESULT rather than on the call. Wrapping
    # _from_db looks stronger but anything that later re-patches it silently
    # disables the wrapper; asking the index directly cannot be bypassed.
    yield caps
    rows = pm._from_db("nurse sweatshirt")
    assert not rows, (
        "DB fast-path returned %d row(s) while a capture fixture was seeded — "
        "the fixture is being shadowed by the SQLite index, so the assertions "
        "graded unrelated data: %s"
        % (len(rows), [r.get("title") for r in rows[:3]]))


def test_candidates_are_long_tail_only_and_subject_sane(seeded_captures):
    g = kl.generate("nurse sweatshirt")
    assert g["candidates"], "should generate candidates"
    # the seeded fixture is the data under test, not the server's captures
    assert g.get("subject") == "nurse", g.get("subject")
    for c in g["candidates"]:
        assert len(c["keyword"].split()) >= 3, c
        assert "sweatshirts" not in c["keyword"]          # no plural garbage
        assert c["keyword"].count("sweatshirt") <= 1      # no product doubling
    # adjacent-buyer expansion present
    assert any("er nurse" in c["keyword"] or "icu nurse" in c["keyword"]
               for c in g["candidates"])


def test_the_seeded_fixture_is_the_data_actually_mined(seeded_captures):
    """Proves the isolation itself, so a future regression cannot make the test
    above pass against unrelated server data."""
    from src import pattern_miner as pm
    res = pm.mine("nurse sweatshirt")
    assert res["n"] == 2, res["n"]
    titles = {b["title"] for b in pm.load_batch("nurse sweatshirt")[1]}
    assert titles == {"Personalized Nurse Embroidered Sweatshirts",
                      "Custom Nurse RN Sweatshirt Gift"}


def test_the_fixture_never_writes_into_the_real_capture_dir(seeded_captures):
    """The old helper wrote into data/imports/etsy_spy and deleted it afterwards
    — a test that mutates live capture data."""
    assert not (Path("data/imports/etsy_spy") / "zz_test_lab.json").exists()


def test_trademarked_seed_not_suggested_as_buildable():
    # V37.4 safety regression: a trademarked seed must not yield build-ready
    # infringing long-tails. All HIGH-trademark candidates are screened out.
    g = kl.generate("disney princess shirt")
    assert g.get("tm_dropped", 0) > 0
    assert all("disney" not in c["keyword"] for c in g["candidates"])


def test_mode_aware_material_and_keyword_product():
    # POD keeps no material word; embroidery adds "embroidered"; the keyword's own
    # product (sweatshirt) drives candidates rather than a pattern-derived noun.
    pod = [c["keyword"] for c in kl.generate("nurse sweatshirt", mode="pod")["candidates"]]
    emb = [c["keyword"] for c in kl.generate("nurse sweatshirt", mode="embroidery")["candidates"]]
    assert pod and all("embroidered" not in k for k in pod)     # POD: no material word
    assert any("sweatshirt" in k for k in pod)                  # product from keyword
    assert any("embroidered" in k for k in emb)                 # embroidery keeps it


# ---------------------------------------------------------------------------
# save_candidates is the ONE path keywords enter the master (Keyword Lab AND the
# winner->Inbox push both call it). Two things it must never do.
# ---------------------------------------------------------------------------
def test_save_candidates_writes_blanks_not_fabricated_zeros(tmp_path,
                                                            monkeypatch):
    """A 0 in a count column reads downstream as 'this niche has zero
    competitors' — opportunity_score scores that as the most wide-open market
    there is. Unknown must stay blank."""
    import csv as _csv
    monkeypatch.chdir(tmp_path)

    def _zero_enrich(d, _mode=None):
        d["listing_count"] = 0.0          # what the MCP returns for "no data"
        d["seller_count"] = 0.0
        return True
    monkeypatch.setattr("src.shortlister_integration._enrich_row", _zero_enrich)
    added, _ = kl.save_candidates(["zzz probe long tail keyword"], "embroidery")
    assert added == 1
    row = next(iter(_csv.DictReader(
        Path("keyword_data.csv").open(encoding="utf-8-sig"))))
    assert row["etsy_listings"] == ""     # blank, NOT "0.0"
    assert row["seller_count"] == ""
