"""Tests for Multi-Page Raw Data Ingestion & Analytics Engine."""
import csv
from pathlib import Path
from src import raw_ingest as ri


def test_parse_price_usd():
    assert ri.parse_price_usd("1,000,000") == 40.0
    assert ri.parse_price_usd("500000") == 20.0
    assert ri.parse_price_usd("$29.99") == 29.99
    assert ri.parse_price_usd("35.50") == 35.50
    assert ri.parse_price_usd(None) is None
    assert ri.parse_price_usd("") is None


def test_ingest_raw_folder_deduplication(tmp_path):
    # Create two dummy CSV files with overlapping listing_ids
    csv1 = tmp_path / "page1.csv"
    csv2 = tmp_path / "page2.csv"
    
    rows1 = [
        {"listing_id": "101", "title": "Daughter Gift Necklace", "price_num": "1000000",
         "he_tags": "daughter gift; para mi hija; necklace", "he_categories": "Jewelry HeyEtsy.com",
         "he_sold": "50", "he_views": "200", "he_favorites": "30", "star_seller": "1"},
        {"listing_id": "102", "title": "Custom Blanket for Daughter", "price_num": "800000",
         "he_tags": "daughter blanket; custom blanket", "he_categories": "Bedding HeyEtsy.com",
         "he_sold": "20", "he_views": "100", "he_favorites": "10", "star_seller": "0"},
    ]
    rows2 = [
        {"listing_id": "101", "title": "Duplicate Necklace", "price_num": "1000000",
         "he_tags": "daughter gift; para mi hija", "he_categories": "Jewelry HeyEtsy.com",
         "he_sold": "50", "he_views": "200", "he_favorites": "30", "star_seller": "1"},
        {"listing_id": "103", "title": "Daughter Keychain Token", "price_num": "250000",
         "he_tags": "daughter keychain; pocket hug", "he_categories": "Accessories HeyEtsy.com",
         "he_sold": "5", "he_views": "50", "he_favorites": "2", "star_seller": "0"},
    ]
    
    fieldnames = list(rows1[0].keys())
    with open(csv1, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows1)
        
    with open(csv2, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows2)

    res = ri.ingest_raw_folder(tmp_path, keyword="test niche")
    assert res["total_listings"] == 3  # 101, 102, 103 (101 was deduplicated)
    assert res["pricing"]["median"] == 32.0  # [10.0, 32.0, 40.0]
    assert "daughter gift" in res["tags_counter"]
    assert res["tags_counter"]["daughter gift"] == 1
    assert res["signals"]["total_sold"] == 75


def test_extract_html_chips(tmp_path):
    html_file = tmp_path / "test_search.html"
    content = """
    <html>
        <body>
            <a href="https://www.etsy.com/search?q=para+mi+hija+collar">Collar</a>
            <a href="/search?q=regalo%20de%20cumpleanos">Cumpleanos</a>
            <a href="/search?q=daughter+necklace">Daughter Necklace</a>
        </body>
    </html>
    """
    html_file.write_text(content, encoding="utf-8")
    chips = ri.extract_html_chips(html_file)
    assert "para mi hija collar" in chips
    assert "regalo de cumpleanos" in chips
    assert "daughter necklace" in chips
