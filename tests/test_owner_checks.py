"""Owner Check + owner-set price persistence. Writes to the real local
data/app.db, same convention test_routes.py already uses for auth -- a
distinctive test keyword keeps this from colliding with anything real.
"""
import time

from src import appdb, owner_checks as oc

_KW = "___test_owner_check_keyword___"
_MODE = "pod"


def setup_module():
    appdb.init_db()


def test_unsaved_field_is_simply_absent_not_a_default_false_row():
    checks = oc.get_checks(f"{_KW}_absent", _MODE)
    assert "Material Composition" not in checks


def test_save_and_read_back_a_verified_check():
    kw = f"{_KW}_{time.time()}"
    oc.save_check(kw, _MODE, "Material Composition", value="100% Cotton",
                 verified=True, note="checked with supplier", updated_by="boss")
    checks = oc.get_checks(kw, _MODE)
    assert checks["Material Composition"]["value"] == "100% Cotton"
    assert checks["Material Composition"]["verified"] is True
    assert checks["Material Composition"]["updated_by"] == "boss"


def test_saving_again_updates_in_place_not_a_duplicate_row():
    kw = f"{_KW}_{time.time()}"
    oc.save_check(kw, _MODE, "Material Composition", value="Cotton", verified=False)
    oc.save_check(kw, _MODE, "Material Composition", value="100% Cotton", verified=True)
    checks = oc.get_checks(kw, _MODE)
    assert checks["Material Composition"]["value"] == "100% Cotton"
    assert checks["Material Composition"]["verified"] is True


def test_checks_are_scoped_per_keyword_and_mode():
    kw = f"{_KW}_{time.time()}"
    oc.save_check(kw, "pod", "Material Composition", value="Cotton", verified=True)
    embroidery_checks = oc.get_checks(kw, "embroidery")
    assert "Material Composition" not in embroidery_checks


def test_price_starts_unset():
    assert oc.get_price(f"{_KW}_unset_{time.time()}", _MODE) is None


def test_save_and_read_back_a_price():
    kw = f"{_KW}_{time.time()}"
    oc.save_price(kw, _MODE, 24.99, updated_by="boss")
    p = oc.get_price(kw, _MODE)
    assert p["price"] == 24.99
    assert p["currency"] == "USD"
    assert p["updated_by"] == "boss"


def test_saving_price_again_updates_in_place():
    kw = f"{_KW}_{time.time()}"
    oc.save_price(kw, _MODE, 20.00)
    oc.save_price(kw, _MODE, 25.00)
    p = oc.get_price(kw, _MODE)
    assert p["price"] == 25.00
