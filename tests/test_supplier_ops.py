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


def test_the_owners_named_matcher_cases():
    """The exact phrases the owner listed for the canonical matcher. These are
    real keyword shapes: a buyer-intent phrase wraps the product noun in
    modifiers, which is why raw token overlap against a supplier's 'TSHIRT'
    scored every one of them the same 50/100."""
    assert so.product_family("custom crew t-shirt") == "tshirt"
    assert so.product_family("embroidered hoodie") == "hoodie"
    assert so.product_family("wash cap monogram") == "cap"
    assert so.product_family("personalized name tote handbag") == "tote"
    assert so.product_family("40th birthday cozies") == "koozie"
    # names no product at all -> None, which the gate reads as UNKNOWN
    assert so.product_family("40th birthday gift for her") is None


def test_a_koozie_is_not_a_mug():
    """A drink sleeve and a ceramic mug are different products from different
    suppliers; they used to share one family."""
    assert so.product_family("can cooler") == "koozie"
    assert so.product_family("personalized coffee mug") == "mug"
    assert so.product_family("koozie") != so.product_family("mug")


def test_an_unknown_product_is_unknown_or_needs_check_never_a_block(lib):
    """Owner's rule for the tail of the matcher: not recognising a product is a
    gap in our vocabulary, never a statement that the shop cannot make it."""
    from src import feasibility_gate as fg
    # names no product -> UNKNOWN
    assert fg.supplier_fit("nurse graduation gift", "embroidery", lib)[0] \
        == fg.UNKNOWN
    # names a product we have no supplier for, on an INCOMPLETE library
    assert fg.supplier_fit("custom throw blanket", "embroidery", lib)[0] \
        == fg.NEEDS_SUPPLIER_CHECK


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


# --- the CSV importer: keep real data, allow the record to be completed -------
def test_day_range_reads_a_window_and_never_guesses():
    assert so._day_range("US ePacket 7-12 business days - INCLUDED in price") == ("7", "12")
    assert so._day_range("3-5") == ("3", "5")
    assert so._day_range("5 business days") == ("5", "5")
    assert so._day_range("7") == ("7", "7")
    for empty in ("", None, "ships free", "INCLUDED in price"):
        assert so._day_range(empty) == ("", "")


def _sheet(tmp_path, header, *rows):
    p = tmp_path / "Embroidery.csv"
    p.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return str(p)


_HEAD = "product,size,price_us_epacket_usd,material,shipping"
_ROW = "TSHIRT,S,16.43,cotton,US ePacket 7-12 business days - INCLUDED in price"


def test_import_keeps_the_shipping_window_the_sheet_already_carries(tmp_path):
    """The sheet has always said "7-12 business days"; the importer dropped it."""
    out = str(tmp_path / "out.csv")
    rec = so.import_csv("embroidery", _sheet(tmp_path, _HEAD, _ROW), out)[0]
    assert (rec["shipping_time_min"], rec["shipping_time_max"]) == ("7", "12")


def test_the_two_missing_facts_can_be_supplied_as_optional_columns(tmp_path):
    """Every row sits at SUPPLIER_PARTIAL for want of product_url and a lead
    time, and the upload form accepts only this one layout — so there was no way
    to supply them at all. Adding the columns must complete the record."""
    out = str(tmp_path / "out.csv")
    rec = so.import_csv("embroidery", _sheet(
        tmp_path, _HEAD + ",product_url,processing_days",
        _ROW + ",https://supplier.example/tshirt,3-5"), out)[0]
    assert rec["product_url"] == "https://supplier.example/tshirt"
    assert (rec["processing_time_min"], rec["processing_time_max"]) == ("3", "5")
    assert rec["supplier_status"] == "SUPPLIER_CONFIRMED"
    assert rec["missing_fields"] == ""


def test_absent_optional_columns_stay_absent_and_are_never_inferred(tmp_path):
    out = str(tmp_path / "out.csv")
    rec = so.import_csv("embroidery", _sheet(tmp_path, _HEAD, _ROW), out)[0]
    assert rec["product_url"] == "" and rec["processing_time_min"] == ""
    assert rec["supplier_status"] == "SUPPLIER_PARTIAL"


def test_scores_stay_ranked_and_bounded(lib):
    scored = so.match("wash cap", "embroidery", path=lib, verbose=False)
    assert [s for s, _ in scored] == sorted((s for s, _ in scored), reverse=True)
    assert all(0 <= s <= 100 for s, _ in scored)
    assert scored[0][1]["product_name"] == "WASH CAP"      # the right supplier


# --- V38.3: HPW + HogoToPod price-sheet importers ---------------------------
# Both sheets have multi-row/merged-cell headers a plain DictReader can't
# represent, and mix decimal-separator conventions cell to cell. Real-shaped
# fixtures below (not just clean synthetic rows) pin the parsing quirks
# actually found in the live sheets, not an idealized version of them.

def test_money_normalizes_mixed_decimal_separators():
    """Same column, same sheet, both '$9.00' and '13,88' (comma-decimal,
    the sheet's original locale) appear -- no thousands-separator use
    anywhere in this sheet (every value is a single/double-digit dollar
    amount), so a lone comma is always the decimal point here."""
    assert so._money("$9.00") == "9.00"
    assert so._money("13,88") == "13.88"
    assert so._money("$13,07") == "13.07"
    assert so._money("18,4") == "18.40"
    assert so._money("") == ""
    assert so._money(None) == ""


def test_vnd_strips_thousands_separator_never_converts():
    assert so._vnd("130,000") == "130000"
    assert so._vnd("43,000") == "43000"
    assert so._vnd("") == ""


def _hpw_sheet(tmp_path, *rows):
    # real header: col0's cell literally contains an embedded newline in the
    # source sheet (a stray ID bled into row 1 col A) -- csv correctly reads
    # it as ONE header row when properly quoted, same as the live export.
    header = ('"FN1.3985710955 \n",Loại áo,SIZE,GIÁ,Gia công,,'
             'TRỌNG LƯƠNG,SHIP HPW LINE NHANH 6-8')
    p = tmp_path / "hpw.csv"
    p.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return str(p)


def test_hpw_import_keeps_vnd_raw_and_uses_real_usd_shipping(tmp_path):
    out = str(tmp_path / "out.csv")
    sheet = _hpw_sheet(
        tmp_path,
        'Sweatshirt - S,SWEATER,S,"130,000","120,000",,446,11.91',
        'Tote bag,TÚI TOTE,,"43,000","120,000",,200,7.29')
    new = so.import_csv("hpw", sheet, out)
    assert len(new) == 2
    tote = next(r for r in new if r["product_name"] == "Tote bag")
    assert tote["shipping_cost"] == "7.29"          # real USD, used directly
    assert tote["base_cost"] == ""                  # never a guessed USD conversion
    assert "43000 VND" in tote["notes"] and "120000 VND" in tote["notes"]
    assert "NOT converted to USD" in tote["notes"]
    assert tote["shipping_time_min"] == "6" and tote["shipping_time_max"] == "8"


def _hogo_sheet(tmp_path, *product_rows):
    p = tmp_path / "hogotopod.csv"
    header_rows = [
        "title,,,,,,,,,",
        "Product,Picture Demo,Size Chart US,Base cost ($) With Standard shipping,,,,,,",
        ",,,EMBROIDERY,,,,,,",
        ',,,sub,sub,sub,sub,sub,sub,sub',
    ]
    footer = ["PHƯƠNG THỨC THEO DÕI TRẠNG THÁI VẬN ĐƠN,,,,,,,,,",
             "1. Tuyến US,,,,,,,,,"]
    p.write_text("\n".join(header_rows + list(product_rows) + footer) + "\n",
                encoding="utf-8")
    return str(p)


def test_hogotopod_forward_fills_product_name_across_size_rows(tmp_path):
    """The product name is written ONLY on a group's first row (merged cell
    in the source); every size row after it must inherit it, not go blank."""
    out = str(tmp_path / "out.csv")
    sheet = _hogo_sheet(
        tmp_path,
        'T-SHIRT,,S,$9.00,$16.93,$17.86,$19.55,$23.31,$21.75,$14.10',
        ',,M,$9.00,$17.49,$18.41,$20.49,$23.59,$21.99,$14.32')
    new = so.import_csv("hogotopod", sheet, out)
    assert [r["product_name"] for r in new] == ["T-SHIRT", "T-SHIRT"]
    assert [r["sizes"] for r in new] == ["S", "M"]
    assert new[0]["base_cost"] == "9.00"


def test_hogotopod_bundles_shipping_when_no_bare_base_cost_is_given(tmp_path):
    """Specialty items (dog bandana, tote, wreath sash...) have no separate
    no-ship base cost column filled in -- only bundled fulfillment prices.
    That must not silently double-count as base_cost + a real shipping_cost."""
    out = str(tmp_path / "out.csv")
    sheet = _hogo_sheet(
        tmp_path,
        'Dog Bandana,,23.6x17.7 inch,,"$13,07","$13,72","$14,99","$20,24","$18,72","$10,53"')
    new = so.import_csv("hogotopod", sheet, out)
    assert len(new) == 1
    r = new[0]
    assert r["base_cost"] == "13.07"        # the US 7-12d fulfillment price
    assert r["shipping_cost"] == "0.00"     # already included, not double-counted
    assert "already bundled" in r["notes"]
    assert "TikTok-label fulfillment: $10.53" in r["notes"]


def test_hogotopod_excludes_the_tracking_footer_section(tmp_path):
    out = str(tmp_path / "out.csv")
    sheet = _hogo_sheet(
        tmp_path,
        'Patch,,2x2,,,,,,,')
    new = so.import_csv("hogotopod", sheet, out)
    names = [r["product_name"] for r in new]
    assert "PHƯƠNG THỨC THEO DÕI TRẠNG THÁI VẬN ĐƠN" not in names
    assert "1. Tuyến US" not in names
    # a row with no cost data at all is still imported, honestly empty
    assert new[0]["product_name"] == "Patch" and new[0]["base_cost"] == ""
