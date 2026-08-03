"""supplier_ops.match() — the canonical product-family matcher.

Pins the bug found in V37.11: match() scored raw token overlap between a keyword
and a supplier product NAME, then added 50 points for metadata (base cost,
material, personalization) that describes how COMPLETE a supplier record is, not
how well it FITS. Measured on the real 25-row library that scored every one of
the 1,523 master keywords exactly 50/100 "weak" — "custom crew t-shirt" did not
token-match "TSHIRT", and "chenille name bag" came back with TSHIRT as its best
supplier, with no warning.

All fixtures are synthetic and written to tmp_path; the real library is never
read or written by these tests.
"""
import csv

import pytest

from src import supplier_ops as so

_LIB = [
    # the real library's shape: a name, a mode, costs, no product_url
    {"supplier_id": "embroidery", "supplier_name": "Embroidery",
     "product_name": "TSHIRT", "production_mode": "EMBROIDERY",
     "base_cost": "16.43", "material": "cotton", "sizes": "S",
     "personalization_supported": "yes", "supplier_status": "SUPPLIER_PARTIAL"},
    {"supplier_id": "embroidery", "supplier_name": "Embroidery",
     "product_name": "WASH CAP", "production_mode": "EMBROIDERY",
     "base_cost": "9.10", "material": "cotton", "sizes": "OS",
     "personalization_supported": "yes", "supplier_status": "SUPPLIER_PARTIAL"},
]


@pytest.fixture()
def lib(tmp_path):
    p = tmp_path / "supplier_products.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=so.SCHEMA, extrasaction="ignore")
        w.writeheader()
        for r in _LIB:
            w.writerow({**{f: "" for f in so.SCHEMA}, **r})
    return str(p)


def _best(product, mode, path):
    scored = so.match(product, mode=mode, path=path, verbose=False)
    return scored[0][0] if scored else 0


# --- the shared vocabulary ---------------------------------------------------
def test_product_family_reads_a_product_and_stays_none_for_an_occasion():
    assert so.product_family("custom crew t-shirt") == "tshirt"
    assert so.product_family("TSHIRT") == "tshirt"
    assert so.product_family("chenille name bag") == "tote"
    assert so.product_family("wash cap") == "cap"
    # unknown is NOT a mismatch: most keywords name an occasion, not a product
    assert so.product_family("nurse graduation gift") is None
    assert so.product_family("") is None


def test_sweatshirt_does_not_collapse_into_tshirt():
    """'shirt' is a tshirt token; word-boundary matching must keep them apart."""
    assert so.product_family("embroidered sweatshirt") == "sweatshirt"
    assert so.product_family("hooded sweatshirt") == "sweatshirt"


def test_the_gate_shares_this_matcher_and_does_not_fork_its_own():
    """One canonical matcher: the whole point of the fix. If feasibility_gate
    grows a private copy again, the two surfaces can disagree about whether the
    shop can make a product."""
    from src import feasibility_gate as fg
    assert fg._family is so.product_family


# --- match() -----------------------------------------------------------------
def test_same_family_is_a_strong_match_even_with_no_shared_token(lib):
    """The documented failure: 'custom crew t-shirt' shares no token with
    'TSHIRT', yet it is exactly what that supplier makes."""
    assert _best("custom crew t-shirt", "embroidery", lib) >= 70


def test_a_different_family_is_not_a_weak_match_it_is_no_match(lib):
    """A t-shirt supplier cannot make a bag. This used to score 50/100 'weak'."""
    assert _best("chenille name bag", "embroidery", lib) == 0


def test_a_keyword_naming_no_product_never_scores_on_metadata_alone(lib):
    """The 50-point floor: every keyword in the master looked like a weak match
    because the supplier row had a base cost and a material on file."""
    assert _best("nurse graduation gift", "embroidery", lib) == 0


def test_an_explicit_mode_is_a_production_constraint_not_a_preference(lib):
    """The library is embroidery-only, so a POD request has no supplier at all —
    it must not come back as a 65/100 'weak' embroidery match."""
    assert _best("custom crew t-shirt", "pod", lib) == 0
    # auto mode has not been told which method to use, so it stays soft
    assert _best("custom crew t-shirt", None, lib) > 0


def test_empty_library_returns_nothing_rather_than_a_guess(tmp_path):
    assert so.match("custom crew t-shirt", "embroidery",
                    path=str(tmp_path / "missing.csv"), verbose=False) == []


def test_scores_stay_ranked_and_bounded(lib):
    scored = so.match("wash cap", "embroidery", path=lib, verbose=False)
    assert [s for s, _ in scored] == sorted((s for s, _ in scored), reverse=True)
    assert all(0 <= s <= 100 for s, _ in scored)
    assert scored[0][1]["product_name"] == "WASH CAP"      # the right supplier
