"""Recovering extension keywords must never cost the master anything.

The keywords in data/imports/ytrends_ext/*.json reached the master once and were
wiped three times by the old PC->VPS overwrite. Re-merging them is a union, and
these tests pin that it stays one.

The dedupe bug this guards: comparing with `.lower()` reported 1,432 orphans
where only 1,193 were real. The other 239 are keywords `harvest._clean` rejects
outright, and re-adding them writes null metrics over rows that already have
data.
"""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from src import ext_recovery as er
from src import harvest as H

COLS = ["keyword", "etsy_listings", "seller_count", "views_24h", "avg_price",
        "avg_revenue", "total_revenue", "conversion_rate", "momentum",
        "niche_age_days", "tm_risk", "source", "collected_at",
        "opportunity_score"]


def _master(tmp_path, rows):
    p = tmp_path / "keyword_data.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    return str(p)


def _rich(kw, **kw2):
    base = {"keyword": kw, "etsy_listings": 7, "seller_count": 3,
            "views_24h": 169, "avg_price": 24.5, "avg_revenue": 1397.7,
            "total_revenue": 58415.0, "conversion_rate": 0.0436,
            "momentum": 43.5, "niche_age_days": 120, "source": "mcp:ranking",
            "collected_at": "2026-07-09", "opportunity_score": 81.2}
    base.update(kw2)
    return base


def _payload(view, headers, rows):
    return {"view": view, "headers": headers, "rows": rows}


@pytest.fixture
def ext(tmp_path):
    """A capture pool with the real mix: keyword tables, an Amazon capture, a
    connection test with no headers, and a listing table with no keyword column.
    """
    d = tmp_path / "ytrends_ext"
    d.mkdir()

    def w(name, payload):
        (d / name).write_text(json.dumps(payload), encoding="utf-8")

    w("kw1.json", _payload("ytrends-en", ["keyword", "score"],
                           [["4th of july shirt", "40"],
                            ["40oz tumbler gift", "35"],
                            ["mini bride tote bags", "30"]]))   # already in master
    w("kw2.json", _payload("ytrends-en_trending", ["keyword", "score"],
                           [["disney princess tee", "50"],      # trademark HIGH
                            ["tee", "20"],                      # single word
                            ["ab", "10"],                       # too short
                            ["1776 png", "15"],                 # no product family
                            ["80s nostalgia tee", "45"]]))
    w("amazon-thing.json", _payload("amazon-embroidered_ghost",
                                    ["asin", "title", "price"],
                                    [["B01", "Ghost Sweatshirt", "20"]]))
    w("conn.json", {"view": "connection-test", "headers": [], "rows": []})
    w("listings.json", _payload("etsy-spy", ["title", "price", "shop"],
                                [["Some Listing", "20", "ShopA"]]))
    return str(d)


# --- 1-3. canonical dedupe ----------------------------------------------------
def test_recovery_uses_harvest_clean_for_dedupe(ext, tmp_path):
    """Not .lower(). The writer normalises with _clean, so detection must too."""
    assert er._clean is not str.lower
    # case and edge whitespace are normalised...
    assert er._clean("  Mini Bride Tote Bags ") == H._clean("mini bride tote bags")
    # ...but INTERNAL whitespace is NOT collapsed by harvest._clean, so these
    # stay distinct keys. Pinned as measured behaviour, not endorsed: changing
    # _clean would change what the master writer considers the same keyword, and
    # that is a bigger decision than a recovery script should make.
    assert er._clean("mini   bride tote bags") != er._clean("mini bride tote bags")


def test_a_surface_form_duplicate_is_skipped_not_re_added(ext, tmp_path):
    """'Mini Bride Tote Bags' must not be re-added over 'mini bride tote bags'."""
    m = _master(tmp_path, [_rich("mini bride tote bags")])
    fresh, skipped = er.orphans(ext, m)
    assert skipped["already_in_master"] >= 1
    assert H._clean("mini bride tote bags") not in fresh


def test_junk_keywords_clean_rejects_are_never_offered(ext, tmp_path):
    m = _master(tmp_path, [])
    fresh, _ = er.orphans(ext, m)
    for k in fresh:
        assert k and k.strip(), "a blank key reached the candidate set"


# --- 12-13. payload skipping --------------------------------------------------
def test_amazon_captures_are_skipped(ext, tmp_path):
    _fresh, skipped = er.orphans(ext, _master(tmp_path, []))
    assert skipped["amazon"] == 1


def test_headerless_and_keywordless_payloads_are_skipped(ext, tmp_path):
    _fresh, skipped = er.orphans(ext, _master(tmp_path, []))
    assert skipped["no_headers"] == 1          # connection test
    assert skipped["no_keyword_column"] == 1   # etsy-spy listing table


# --- 14-16. Set C filter ------------------------------------------------------
def test_set_c_excludes_trademark_high_single_word_and_no_family(ext, tmp_path):
    fresh, _ = er.orphans(ext, _master(tmp_path, []))
    keep, dropped = er.set_c(sorted(fresh.values()))
    assert "4th of july shirt" in keep
    assert "80s nostalgia tee" in keep
    assert "tee" not in keep and dropped["single_word"] >= 1
    assert "ab" not in keep and dropped["too_short"] >= 1
    assert "1776 png" not in keep
    assert not any("disney" in k for k in keep), keep


# --- 4-9. the union invariants ------------------------------------------------
def test_set_c_recovery_is_union_only_with_no_deletions(tmp_path):
    m = _master(tmp_path, [_rich("mini bride tote bags"), _rich("canvas wine tote")])
    rep = er.recover(["4th of july shirt", "80s nostalgia tee"], path=m)
    assert rep["aborted"] is False
    assert rep["added"] == 2
    assert rep["after"]["rows"] == rep["before"]["rows"] + 2
    with open(m, encoding="utf-8-sig") as f:
        kept = {H._clean(r["keyword"]) for r in csv.DictReader(f)}
    assert H._clean("mini bride tote bags") in kept
    assert H._clean("canvas wine tote") in kept


def test_row_count_never_decreases(tmp_path):
    m = _master(tmp_path, [_rich(f"kw {i}") for i in range(20)])
    rep = er.recover(["4th of july shirt"], path=m)
    assert rep["after"]["rows"] >= rep["before"]["rows"]


def test_unique_keyword_count_equals_rows_after_merge(tmp_path):
    m = _master(tmp_path, [_rich("mini bride tote bags")])
    rep = er.recover(["4th of july shirt", "4th of july shirt"], path=m)
    assert rep["after"]["unique"] == rep["after"]["rows"]


@pytest.mark.parametrize("col", er.GUARDED)
def test_guarded_enrichment_counts_never_decrease(tmp_path, col):
    m = _master(tmp_path, [_rich(f"kw {i}") for i in range(12)])
    rep = er.recover(["4th of july shirt", "80s nostalgia tee"], path=m)
    assert rep["after"][col] >= rep["before"][col], col


# --- 10. the views rule, documented -------------------------------------------
def test_positive_views_never_decrease_though_zeros_may_normalise(tmp_path):
    """A literal views_24h=0 normalises to blank on ANY write (harvest._f maps
    0 -> None, honest-nulls). That is not evidence loss, so the invariant is on
    POSITIVE views, which must hold."""
    rows = [_rich("kept a", views_24h=169), _rich("kept b", views_24h=42),
            _rich("zero one", views_24h=0), _rich("zero two", views_24h=0)]
    m = _master(tmp_path, rows)
    before = er.counts(m)
    assert before["views_positive"] == 2
    rep = er.recover(["4th of july shirt"], path=m)
    assert rep["aborted"] is False
    assert rep["after"]["views_positive"] == 2, "a positive views row was lost"


# --- 11. the cron keywords ----------------------------------------------------
def test_the_97_cron_keywords_are_preserved(tmp_path):
    cron = [_rich(f"cron kw {i}", collected_at="2026-08-06") for i in range(97)]
    m = _master(tmp_path, cron + [_rich("older one")])
    rep = er.recover(["4th of july shirt"], path=m)
    assert rep["aborted"] is False
    with open(m, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    still = sum(1 for r in rows if (r.get("collected_at") or "").startswith("2026-08-06"))
    assert still == 97, f"cron keywords lost: {still}/97"


# --- the abort guard ----------------------------------------------------------
def test_a_write_that_would_lose_enrichment_is_refused(tmp_path, monkeypatch):
    m = _master(tmp_path, [_rich(f"kw {i}") for i in range(10)])
    # a merge that carries NOTHING back — the exact shape of the old bug
    monkeypatch.setattr(H, "merge_existing", lambda store, **k: 0)
    rep = er.recover(["4th of july shirt"], path=m, write=True,
                     backup=str(tmp_path / "b.bak"))
    assert rep["aborted"] is True
    assert "would lose" in rep["reason"]


def test_a_production_write_without_a_backup_is_refused(tmp_path):
    m = _master(tmp_path, [_rich("a b c")])
    rep = er.recover(["4th of july shirt"], path=m, write=True, backup=None)
    assert rep["aborted"] is True and "backup" in rep["reason"]


def test_dry_run_is_the_default_and_writes_nothing(tmp_path):
    m = _master(tmp_path, [_rich("a b c")])
    before = Path(m).read_bytes()
    rep = er.recover(["4th of july shirt"], path=m)      # no write=True
    assert rep["added"] == 1                              # it SIMULATED the add
    assert Path(m).read_bytes() == before, "dry run modified the file"


# --- 17-19. blast radius ------------------------------------------------------
def test_production_master_is_not_touched_by_a_dry_run(tmp_path):
    prod = Path("keyword_data.csv")
    if not prod.is_file():
        pytest.skip("no local master")
    before = hashlib.sha256(prod.read_bytes()).hexdigest()
    er.recover(["zzz probe keyword phrase"], path=_master(tmp_path, [_rich("a b c")]))
    assert hashlib.sha256(prod.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("db", ["data/app.db", "data/agent.db", "data/db/etsy.db"])
def test_no_database_is_touched(tmp_path, db):
    p = Path(db)
    if not p.is_file():
        pytest.skip(f"{db} absent")
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    er.recover(["zzz probe keyword phrase"], path=_master(tmp_path, [_rich("a b c")]))
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before, db


def test_recovery_writes_only_the_master_never_a_db():
    """Static guard: no database may be named in live CODE.

    Comments and docstrings are stripped first — the module explains in prose
    which databases it must never touch, and a raw grep would make that
    explanation itself the failure.
    """
    import ast
    import io
    import tokenize
    src = Path("src/ext_recovery.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None) or []
        if body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            docs.add((body[0].lineno, body[0].col_offset))
    code = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.start in docs:
            continue
        code.append(tok.string)
    code = " ".join(code)
    for bad in ("app.db", "agent.db", "etsy.db", "sqlite3"):
        assert bad not in code, f"ext_recovery references {bad} in live code"


def test_publish_automation_remains_false():
    from src.team_ops import PUBLISH_AUTOMATION
    assert PUBLISH_AUTOMATION is False
