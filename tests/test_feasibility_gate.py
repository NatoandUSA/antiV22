"""The early supplier/Pinterest feasibility gate (workflow steps 2 + 3).

The rule this file exists to defend: a miss in the supplier library only means
"we cannot make this" when the library is COMPLETE. Measured on the real
library — 25 rows from one of eight registered suppliers, none confirmed — a
miss is a gap in our data, so it must produce a BADGE and never a block.

Fixtures are synthetic and written to tmp_path; the real library is only ever
read, never written.
"""
import csv
import json

import pytest

from src import feasibility_gate as fg
from src import supplier_ops as so

_ROW = {f: "" for f in so.SCHEMA}


def _lib(tmp_path, rows, name="supplier_products.csv"):
    p = tmp_path / name
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=so.SCHEMA, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**_ROW, **r})
    fg._SNAP.clear()                     # the snapshot cache must not leak state
    return str(p)


def _sources(tmp_path, monkeypatch, ids):
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({i: {"name": i} for i in ids}), encoding="utf-8")
    monkeypatch.setattr(so, "SOURCES_JSON", p)
    fg._SNAP.clear()


@pytest.fixture()
def partial(tmp_path, monkeypatch):
    """The real library's shape: one supplier of eight, rows not confirmed."""
    _sources(tmp_path, monkeypatch, ["embroidery", "printify"])
    return _lib(tmp_path, [
        {"supplier_id": "embroidery", "product_name": "TSHIRT",
         "production_mode": "EMBROIDERY", "supplier_status": "SUPPLIER_PARTIAL",
         "last_updated": "2026-07-07"},
        {"supplier_id": "embroidery", "product_name": "WASH CAP",
         "production_mode": "EMBROIDERY", "supplier_status": "SUPPLIER_PARTIAL",
         "last_updated": "2026-07-07"},
    ])


@pytest.fixture()
def complete(tmp_path, monkeypatch):
    """Every registered supplier has products and every row is confirmed."""
    _sources(tmp_path, monkeypatch, ["embroidery"])
    return _lib(tmp_path, [
        {"supplier_id": "embroidery", "product_name": "TSHIRT",
         "production_mode": "EMBROIDERY", "supplier_status": "SUPPLIER_CONFIRMED",
         "last_updated": "2026-08-01"},
    ], name="complete.csv")


# --- coverage (item D) -------------------------------------------------------
def test_coverage_is_unknown_when_nothing_is_imported(tmp_path):
    fg._SNAP.clear()
    cov = fg.coverage(str(tmp_path / "missing.csv"))
    assert cov["status"] == fg.COV_NONE
    assert fg.has_supplier_library(str(tmp_path / "missing.csv")) is False


def test_a_registered_supplier_with_no_products_makes_coverage_partial(partial):
    cov = fg.coverage(partial)
    assert cov["status"] == fg.COV_PARTIAL
    assert "printify" in cov["missing_sources"]
    assert cov["products"] == 2 and cov["confirmed"] == 0
    assert cov["last_updated"] == "2026-07-07"


def test_coverage_is_complete_only_when_every_row_is_confirmed(complete):
    assert fg.coverage(complete)["status"] == fg.COV_COMPLETE


def test_a_sync_placeholder_row_does_not_count_as_covering_a_supplier(tmp_path, monkeypatch):
    """`supplier sync` writes a CATALOG_URL_ONLY row with an id and no product.
    Counting that as "this supplier has products" would hide the whole gap."""
    _sources(tmp_path, monkeypatch, ["embroidery", "printify"])
    p = _lib(tmp_path, [
        {"supplier_id": "embroidery", "product_name": "TSHIRT",
         "production_mode": "EMBROIDERY", "supplier_status": "SUPPLIER_CONFIRMED"},
        {"supplier_id": "printify", "product_name": "",       # <- the placeholder
         "production_mode": "POD", "supplier_status": "CATALOG_URL_ONLY"},
    ], name="placeholder.csv")
    cov = fg.coverage(p)
    assert "printify" in cov["missing_sources"]
    assert cov["status"] == fg.COV_PARTIAL and cov["products"] == 1


def test_coverage_is_asked_per_mode_so_one_mode_can_be_finished(tmp_path, monkeypatch):
    """Judged as a whole, this library can never be complete — six POD catalogs
    are registered and unimported, which would keep enforcement (item F) dead
    forever. Per mode, embroidery can be finished on its own."""
    _sources(tmp_path, monkeypatch, ["embroidery", "printify"])
    monkeypatch.setattr(so, "SOURCES_JSON", tmp_path / "sources.json")
    (tmp_path / "sources.json").write_text(json.dumps({
        "embroidery": {"modes": ["EMBROIDERY", "CHENILLE_PATCH"]},
        "printify": {"modes": ["POD"]}}), encoding="utf-8")
    p = _lib(tmp_path, [
        {"supplier_id": "embroidery", "product_name": "TSHIRT",
         "production_mode": "EMBROIDERY", "supplier_status": "SUPPLIER_CONFIRMED"},
    ], name="permode.csv")
    assert fg.coverage(p, "embroidery")["status"] == fg.COV_COMPLETE
    assert fg.coverage(p, "pod")["status"] == fg.COV_NONE     # nothing imported
    assert fg.coverage(p)["status"] == fg.COV_PARTIAL         # overall still honest
    # enforcement is live for embroidery only
    assert fg.supplier_fit("chenille name bag", "embroidery", p)[0] == fg.NOT_MAKEABLE
    assert fg.supplier_fit("chenille name bag", "pod", p)[0] == fg.UNKNOWN


# --- supplier_fit ------------------------------------------------------------
def test_makeable_when_a_mode_correct_supplier_makes_that_family(partial):
    fit, d = fg.supplier_fit("custom crew t-shirt", "embroidery", partial)
    assert fit == fg.MAKEABLE
    assert d["product_family"] == "tshirt"
    assert d["supplier_source"] == "embroidery"
    # a SUPPLIER_PARTIAL row proves they make it, not that we know cost/lead time
    assert d["confidence"] == "medium"


def test_a_miss_on_an_incomplete_library_is_a_question_not_a_block(partial):
    fit, d = fg.supplier_fit("chenille name bag", "embroidery", partial)
    assert fit == fg.NEEDS_SUPPLIER_CHECK
    assert d["product_family"] == "tote"
    assert d["coverage_status"] == fg.COV_PARTIAL
    assert d["confidence"] == "low"


def test_the_same_miss_on_a_complete_library_is_not_makeable(complete):
    fit, d = fg.supplier_fit("chenille name bag", "embroidery", complete)
    assert fit == fg.NOT_MAKEABLE
    assert d["confidence"] == "high"


def test_a_keyword_naming_no_product_stays_unknown(partial):
    """Most of the master is like this — an occasion, not a product."""
    fit, d = fg.supplier_fit("nurse graduation gift", "embroidery", partial)
    assert fit == fg.UNKNOWN
    assert d["product_family"] is None


def test_mode_correct_an_embroidery_row_cannot_serve_a_pod_request(partial):
    """An embroidery supplier can never answer a POD request. And because this
    library has NO POD rows at all, the honest POD answer is "not checked" —
    'needs a supplier check' would claim we looked, when there was nothing to
    look in."""
    assert fg.supplier_fit("custom crew t-shirt", "pod", partial)[0] == fg.UNKNOWN
    assert fg.supplier_fit("custom crew t-shirt", None, partial)[0] == fg.MAKEABLE


def test_empty_or_missing_library_is_unknown_never_a_block(tmp_path):
    fg._SNAP.clear()
    p = str(tmp_path / "nope.csv")
    assert fg.supplier_fit("custom crew t-shirt", "embroidery", p)[0] == fg.UNKNOWN
    assert fg.build_allowed("custom crew t-shirt", "embroidery", p)[0] is True


def test_every_verdict_carries_the_owners_five_fields(partial):
    for kw in ("custom crew t-shirt", "chenille name bag", "nurse graduation gift", ""):
        _, d = fg.supplier_fit(kw, "embroidery", partial)
        for f in ("product_family", "supplier_source", "coverage_status",
                  "last_updated", "confidence"):
            assert f in d, f"{kw!r} verdict is missing {f}"


# --- build_allowed + apply_to_row (items E + F) ------------------------------
def test_an_incomplete_library_can_never_block_a_build(partial):
    for kw in ("chenille name bag", "custom crew t-shirt", "nurse graduation gift"):
        assert fg.build_allowed(kw, "embroidery", partial)[0] is True


def test_apply_to_row_is_badge_only_while_the_library_is_incomplete(partial):
    row = {"keyword": "chenille name bag", "action": "CONFIRM_FIRST",
           "route": "pattern", "priority": 4, "score": 71}
    fg.apply_to_row(row, "embroidery", partial)
    assert row["supplier_fit"] == fg.NEEDS_SUPPLIER_CHECK
    assert row["supplier_label"] == "Needs supplier check"
    assert row["build_allowed"] is True
    # nothing the engine decided moved
    assert (row["action"], row["route"], row["priority"], row["score"]) \
        == ("CONFIRM_FIRST", "pattern", 4, 71)


def test_apply_to_row_blocks_only_once_the_library_is_complete(complete):
    row = {"keyword": "chenille name bag", "action": "CONFIRM_FIRST",
           "route": "pattern", "priority": 4, "score": 71}
    fg.apply_to_row(row, "embroidery", complete)
    assert row["build_allowed"] is False
    assert row["action"] == fg.BLOCK_ACTION and row["supplier_blocked"] is True
    assert row["revivable"] is True and row["reason"] == fg.BLOCK_REASON
    assert row["score"] == 71                     # the ranking math is untouched


def test_a_trademark_block_is_never_downgraded(complete):
    row = {"keyword": "chenille name bag", "action": "BLOCKED", "priority": 0}
    fg.apply_to_row(row, "embroidery", complete)
    assert row["action"] == "BLOCKED"              # BLOCKED outranks SKIP


def test_the_labels_are_the_four_the_owner_asked_for():
    assert set(fg.LABELS.values()) == {
        "Makeable", "Not checked", "Needs supplier check", "Supplier blocked"}


def test_summary_counts_every_verdict(partial):
    rows = [fg.apply_to_row({"keyword": k, "action": "WATCH"}, "embroidery", partial)
            for k in ("custom crew t-shirt", "chenille name bag", "gift for mom")]
    s = fg.summary(rows)
    assert s[fg.MAKEABLE] == 1 and s[fg.NEEDS_SUPPLIER_CHECK] == 1
    assert s[fg.UNKNOWN] == 1 and s[fg.NOT_MAKEABLE] == 0


def test_the_live_library_blocks_nothing_until_it_is_complete():
    """Read-only check against the REAL library: the gate is allowed to stop work
    only on a complete library, whatever state that library is in today."""
    if fg.coverage()["status"] != fg.COV_COMPLETE:
        for kw in ("chenille name bag", "custom crew t-shirt", "40th birthday cozies"):
            assert fg.build_allowed(kw, "embroidery")[0] is True


# --- wired into the Inbox as a BADGE (item E) --------------------------------
def test_the_inbox_badge_changes_no_verdict_action_or_score(monkeypatch):
    """Hard guarantee for the live Inbox: turning the badge on must leave every
    row the frozen engine produced exactly as it was."""
    from src import opportunity_inbox as oi

    def rank():
        oi._CACHE.clear()
        return [(r["keyword"], r["verdict"], r["action"], r["score"],
                 r["priority"]) for r in oi.build_inbox(None, limit=100000)["rows"]]

    with_badge = rank()
    # same run with the gate switched off entirely
    monkeypatch.setattr(fg, "coverage", lambda path=None: {"status": fg.COV_NONE})
    without = rank()
    oi._CACHE.clear()
    assert with_badge == without


def test_the_inbox_exposes_the_badge_and_the_coverage_that_justifies_it():
    from src import opportunity_inbox as oi
    oi._CACHE.clear()
    sup = oi.build_inbox(None, limit=100000).get("supplier") or {}
    cov, fit = sup.get("coverage"), sup.get("fit")
    assert cov and fit, "the Inbox must report supplier coverage + fit counts"
    assert set(fit) >= {fg.MAKEABLE, fg.NEEDS_SUPPLIER_CHECK, fg.UNKNOWN,
                        fg.NOT_MAKEABLE}
    if cov["status"] != fg.COV_COMPLETE:
        assert fit[fg.NOT_MAKEABLE] == 0, "a partial library must block nothing"


def test_importing_a_supplier_busts_the_inbox_cache():
    """The gate's promise is that a flag revives automatically when a supplier
    arrives — which only holds if the library is part of the cache stamp."""
    import inspect

    from src import opportunity_inbox as oi
    assert "supplier_products.csv" in inspect.getsource(oi._data_stamp)


# --- Pinterest is advisory ---------------------------------------------------
def test_pinterest_never_blocks_and_separates_unchecked_from_empty(monkeypatch):
    assert fg.pinterest_label("")[0] == fg.PIN_UNKNOWN

    from src import crosscheck
    monkeypatch.setattr(crosscheck, "pinterest_signal",
                        lambda kw: (_ for _ in ()).throw(RuntimeError("no key")))
    # "we did not check" must not read as "we checked and found nothing"
    assert fg.pinterest_label("dog mom shirt")[0] == fg.PIN_UNKNOWN
    monkeypatch.setattr(crosscheck, "pinterest_signal", lambda kw: {"found": False})
    assert fg.pinterest_label("dog mom shirt")[0] == fg.NONE_
    monkeypatch.setattr(crosscheck, "pinterest_signal",
                        lambda kw: {"found": True, "growth": "rising"})
    assert fg.pinterest_label("dog mom shirt")[0] == fg.RISING


def test_pinterest_cannot_change_a_build_decision(partial, monkeypatch):
    """Owner's rule: a second marketplace corroborates, it never vetoes. The
    verdict must be identical whether Pinterest says RISING, NONE or nothing."""
    from src import crosscheck
    seen = set()
    for sig in ({"found": True, "growth": "rising"}, {"found": False}, None):
        monkeypatch.setattr(crosscheck, "pinterest_signal", lambda kw, s=sig: s)
        allowed, info = fg.build_allowed("chenille name bag", "embroidery", partial)
        seen.add((allowed, info["fit"]))
    assert seen == {(True, fg.NEEDS_SUPPLIER_CHECK)}


# --- the freeze --------------------------------------------------------------
def test_no_frozen_imports():
    """ranking_engine.py and opportunity_score.py are frozen: nothing new may
    point at them, not even a read-only import. Parsed, not grepped — the module
    is allowed to NAME them in prose (it explains why it copies _PRI instead)."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path("src/feasibility_gate.py").read_text(encoding="utf-8"))
    frozen = {"ranking_engine", "opportunity_score"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[-1] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {a.name.split(".")[-1] for a in node.names}
            imported |= {(node.module or "").split(".")[-1]}
    assert not (imported & frozen), \
        f"feasibility_gate imports frozen module(s): {sorted(imported & frozen)}"
