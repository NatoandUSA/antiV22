"""Multi-Page Raw Data Ingestion & Analytics Engine.

Ingests HeyEtsy search result CSVs (multi-page exports) and HTML DOM snapshots,
deduplicates listings, normalizes pricing (VND -> USD), extracts rich competitor tags,
parses category breadcrumbs, and extracts search query chips.
"""
import csv
import glob
import os
import re
import statistics
from collections import Counter
from pathlib import Path


def parse_price_usd(price_num_str, default=None):
    """Normalize price string to USD float. Converts VND (>1000) using 25,000 rate."""
    if not price_num_str:
        return default
    clean = str(price_num_str).replace(",", "").replace("$", "").strip()
    try:
        val = float(clean)
        if val > 1000:
            return round(val / 25000.0, 2)
        return round(val, 2)
    except (ValueError, TypeError):
        return default


def extract_html_chips(html_path):
    """Extract search query chips / filter keywords from an Etsy HTML snapshot."""
    chips = set()
    p = Path(html_path)
    if not p.exists():
        return []
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        # Match search links: search?q=...
        matches = re.findall(r'href=[\"\'][^\"\']*search[^\"\']*q=([^&\"\'\>]+)', content)
        for m in matches:
            # Decode url encoding like '+' or '%20'
            m_dec = m.replace("+", " ").replace("%20", " ").strip().lower()
            m_dec = re.sub(r'[^a-zA-Z0-9\sáéíóúñüÁÉÍÓÚÑÜ]', '', m_dec).strip()
            if 2 < len(m_dec) < 50 and not m_dec.startswith("http"):
                chips.add(m_dec)
    except Exception:
        pass
    return sorted(chips)


def ingest_raw_folder(folder_path, keyword=None):
    """Ingest, deduplicate, and analyze all CSVs and HTML snapshots in a folder.

    Returns a comprehensive structured dictionary:
    {
        "keyword": keyword,
        "total_files": int,
        "total_listings": int,
        "listings": list of dicts,
        "top_tags": list of (tag, count, pct),
        "tags_counter": Counter,
        "categories": list of (category, count, pct),
        "pricing": {
            "median": float, "mean": float, "p25": float, "p75": float,
            "min": float, "max": float, "by_category": dict
        },
        "signals": {
            "star_seller_pct": float,
            "bestseller_pct": float,
            "free_shipping_pct": float,
            "ad_pct": float,
            "total_sold": int,
            "total_views": int,
            "total_favorites": int,
        },
        "html_query_chips": list of str,
    }
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    csv_files = sorted(glob.glob(os.path.join(str(folder), "*.csv")))
    html_files = sorted(glob.glob(os.path.join(str(folder), "*.html")))

    seen_ids = set()
    listings = []
    all_tags = []
    prices_usd = []
    category_prices = {}
    sales_list = []
    views_list = []
    fav_list = []

    star_count = 0
    best_count = 0
    free_ship_count = 0
    ad_count = 0

    for cf in csv_files:
        with open(cf, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            for r in reader:
                lid = (r.get("listing_id") or "").strip()
                if not lid or lid in seen_ids:
                    continue
                seen_ids.add(lid)

                # Title & shop
                title = (r.get("title") or "").strip()
                shop = (r.get("shop") or "").strip()

                # Price normalization
                p_usd = parse_price_usd(r.get("price_num"))
                r["price_usd"] = p_usd
                if p_usd is not None:
                    prices_usd.append(p_usd)

                # Parse he_tags
                htags = r.get("he_tags") or ""
                tags_for_listing = []
                if htags and "no tags" not in htags.lower():
                    for t in htags.split(";"):
                        t_clean = t.strip().lower()
                        if t_clean:
                            tags_for_listing.append(t_clean)
                            all_tags.append(t_clean)
                r["parsed_tags"] = tags_for_listing

                # Parse category
                raw_cat = r.get("he_categories") or ""
                cat_clean = raw_cat.split(" HeyEtsy")[0].strip()
                r["category_clean"] = cat_clean
                if p_usd is not None and cat_clean:
                    category_prices.setdefault(cat_clean, []).append(p_usd)

                # Numerical sales & engagement
                sold_val = 0
                sold_s = (r.get("he_sold") or "").replace(",", "").strip()
                if sold_s.isdigit():
                    sold_val = int(sold_s)
                    sales_list.append(sold_val)
                r["sold_num"] = sold_val

                views_val = 0
                views_s = (r.get("he_views") or "").replace(",", "").strip()
                if views_s.isdigit():
                    views_val = int(views_s)
                    views_list.append(views_val)
                r["views_num"] = views_val

                fav_val = 0
                fav_s = (r.get("he_favorites") or "").replace(",", "").strip()
                if fav_s.isdigit():
                    fav_val = int(fav_s)
                    fav_list.append(fav_val)
                r["favorites_num"] = fav_val

                # Signals
                if r.get("star_seller") in ("1", "true", "True"):
                    star_count += 1
                if r.get("bestseller") in ("1", "true", "True"):
                    best_count += 1
                if r.get("free_shipping") in ("1", "true", "True"):
                    free_ship_count += 1
                if r.get("ad") in ("1", "true", "True"):
                    ad_count += 1

                listings.append(r)

    # HTML Chips extraction
    html_chips = []
    for hf in html_files:
        html_chips.extend(extract_html_chips(hf))
    html_chips = sorted(set(html_chips))

    total_n = len(listings)
    tag_counter = Counter(all_tags)
    top_tags = [
        (t, cnt, round(cnt / total_n * 100, 1) if total_n else 0.0)
        for t, cnt in tag_counter.most_common(50)
    ]

    cat_counter = Counter([l["category_clean"] for l in listings if l.get("category_clean")])
    top_categories = [
        (c, cnt, round(cnt / total_n * 100, 1) if total_n else 0.0)
        for c, cnt in cat_counter.most_common(20)
    ]

    pricing = {
        "median": round(statistics.median(prices_usd), 2) if prices_usd else None,
        "mean": round(statistics.mean(prices_usd), 2) if prices_usd else None,
        "min": round(min(prices_usd), 2) if prices_usd else None,
        "max": round(max(prices_usd), 2) if prices_usd else None,
        "p25": round(statistics.quantiles(prices_usd, n=4)[0], 2) if len(prices_usd) >= 4 else None,
        "p75": round(statistics.quantiles(prices_usd, n=4)[2], 2) if len(prices_usd) >= 4 else None,
        "by_category": {},
    }
    for c_name, c_prices in category_prices.items():
        if c_prices:
            pricing["by_category"][c_name] = {
                "median": round(statistics.median(c_prices), 2),
                "count": len(c_prices),
                "min": round(min(c_prices), 2),
                "max": round(max(c_prices), 2),
            }

    signals = {
        "star_seller_pct": round(star_count / total_n * 100, 1) if total_n else 0.0,
        "bestseller_pct": round(best_count / total_n * 100, 1) if total_n else 0.0,
        "free_shipping_pct": round(free_ship_count / total_n * 100, 1) if total_n else 0.0,
        "ad_pct": round(ad_count / total_n * 100, 1) if total_n else 0.0,
        "total_sold": sum(sales_list),
        "total_views": sum(views_list),
        "total_favorites": sum(fav_list),
    }

    # Save to data/historical
    hist_dir = Path("data/historical")
    hist_dir.mkdir(parents=True, exist_ok=True)
    if keyword:
        safe_k = re.sub(r'[^a-zA-Z0-9_]', '_', keyword.lower())[:30]
        out_csv = hist_dir / f"ingested_{safe_k}.csv"
    else:
        out_csv = hist_dir / "ingested_raw_listings.csv"

    fieldnames = [
        "listing_id", "title", "shop", "price_usd", "price", "price_num",
        "sold_num", "views_num", "favorites_num", "star_seller", "bestseller",
        "free_shipping", "category_clean", "he_tags", "url", "rank_position"
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for l in listings:
            writer.writerow(l)

    return {
        "keyword": keyword,
        "total_files": len(csv_files) + len(html_files),
        "total_listings": total_n,
        "listings": listings,
        "top_tags": top_tags,
        "tags_counter": tag_counter,
        "categories": top_categories,
        "pricing": pricing,
        "signals": signals,
        "html_query_chips": html_chips,
        "saved_path": str(out_csv),
    }


def find_ingested_data(keyword=None):
    """Find previously ingested data in data/historical strictly matching keyword."""
    hist_dir = Path("data/historical")
    if not hist_dir.exists() or not keyword:
        return None
    
    safe_k = re.sub(r'[^a-zA-Z0-9_]', '_', keyword.lower())[:30]
    target = hist_dir / f"ingested_{safe_k}.csv"
    if target.exists():
        return str(target)
    
    # Check if keyword words match any ingested_<name>.csv
    kw_words = set(keyword.lower().split())
    for p in hist_dir.glob("ingested_*.csv"):
        name_words = set(p.stem.replace("ingested_", "").split("_"))
        if kw_words & name_words and len(kw_words & name_words) >= min(len(kw_words), len(name_words)):
            return str(p)
    return None

