"""Supplier detail pulling.

Commands:
  py main.py supplier pod "clear concert bag"
  py main.py supplier embroidery "chenille name bag"

Printify is pulled LIVE via its API (product match + real US shipping).
ShineOn / BurgerPrints / Printway have no public data API, so records are
created with the catalog URL and missing_fields listed - the team completes
them from each dashboard. Nothing is ever invented: a field the source does
not provide stays empty and appears in missing_fields.
"""
import csv
from pathlib import Path

def _load_sources():
    """Supplier registry from data/suppliers/supplier_sources.json (catalog URLs,
    types, modes). Falls back to the built-in defaults below."""
    import json
    p = Path("data/suppliers/supplier_sources.json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


SUPPLIER_SOURCES = _load_sources()

SUPPLIER_CATALOGS = {
    "printify": "https://printify.com/app/products",
    "burgerprints": "https://burgerprints.com/catalog/",
    "printway": "https://printway.io/en/all-products",
    "catkissfish": "https://www.catkissfish.com/product-home",
    "pgprints": "https://pgprints.io/product-category/all/",
    "merchize": "https://merchize.com/all-products/",
    "shineon": "https://teamshineon.zendesk.com/hc/en-us/articles/10195816837265",
    "embroidery partner": "(internal price sheet: data/embroidery_supplier_prices.csv)",
}
# Registry catalog URLs win when present.
for _sid, _info in SUPPLIER_SOURCES.items():
    if _info.get("catalog_url"):
        SUPPLIER_CATALOGS[_sid] = _info["catalog_url"]

FIELDS = ["product_idea", "production_type", "supplier_name",
          "supplier_catalog_url", "product_name_from_supplier", "product_url",
          "product_match_score", "base_cost", "shipping_cost",
          "target_country", "processing_time", "shipping_time_estimate",
          "available_sizes", "available_colors", "material", "print_method",
          "print_area", "embroidery_supported", "embroidery_type",
          "embroidery_area", "stitch_limit", "thread_colors_available",
          "monogram_supported", "name_personalization_supported",
          "chenille_patch_supported", "minimum_order_quantity",
          "personalization_supported", "variants_available",
          "mockup_available", "production_partner_required",
          "supplier_notes", "supplier_status", "missing_fields", "sku",
          "fulfillment_region", "last_verified",
          "production_partner_disclosed",
          "seller_original_design_confirmed", "manual_review",
          "real_photo_confirmed"]

POD_REQUIRED = ["product_url", "base_cost", "shipping_cost", "material",
                "available_sizes", "processing_time"]
EMB_REQUIRED = POD_REQUIRED + ["embroidery_supported", "embroidery_area"]

CSV_PATH = Path("supplier_products.csv")

EMB_SIGNS = ("embroider", "chenille", "monogram", "applique", "stitch",
             "patch", "knit", "crochet")


def classify_production_type(product_idea):
    t = product_idea.lower()
    if "chenille" in t:
        return "CHENILLE_PATCH"
    if any(s in t for s in EMB_SIGNS):
        return "EMBROIDERY"
    if any(s in t for s in ("necklace", "bracelet", "pendant", "jewelry",
                            "ring", "earring")):
        return "JEWELRY"
    if any(s in t for s in ("svg", "digital", "printable", "download")):
        return "DIGITAL"
    if any(s in t for s in ("bag", "pouch", "shirt", "hoodie", "sweatshirt",
                            "mug", "tumbler", "poster", "canvas", "ornament",
                            "case", "organizer", "tote", "hat", "towel",
                            "blanket", "pillow", "purse", "kit")):
        return "POD_PRINT"
    return "UNKNOWN"


def compute_status(rec, kind):
    required = EMB_REQUIRED if kind == "embroidery" else POD_REQUIRED
    if kind == "embroidery":
        emb = (rec.get("embroidery_supported") or "").strip().lower()
        if emb in ("no", "false", "0"):
            return "EMBROIDERY_NOT_SUPPORTED", []
        chen = (rec.get("chenille_patch_supported") or "").strip().lower()
        if rec.get("production_type") == "CHENILLE_PATCH" and \
                chen in ("no", "false", "0"):
            return "CHENILLE_NOT_SUPPORTED", []
    missing = [f for f in required if not (rec.get(f) or "").strip()]
    if not (rec.get("product_url") or "").strip() and \
            not (rec.get("product_name_from_supplier") or "").strip():
        return ("SUPPLIER_NOT_FOUND" if not missing else
                "NEED_SUPPLIER_DETAILS"), missing
    if not missing:
        return "SUPPLIER_CONFIRMED", []
    if len(missing) < len(required):
        return "SUPPLIER_PARTIAL", missing
    return "NEED_SUPPLIER_DETAILS", missing


def _read_csv(path):
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _known_fields(product_idea, kind, supplier):
    """Pre-fill ONLY from our real data files (supplier_costs.csv). Never invents
    — a field we don't actually have stays empty and shows up in missing_fields."""
    out = {}
    try:
        from src.idea_report import cluster_of
        cluster = (cluster_of(product_idea.lower()) or "").lower()
    except Exception:  # noqa: BLE001
        cluster = ""
    sup = supplier.lower()
    for r in _read_csv("supplier_costs.csv"):
        if ((r.get("product_type") or "").lower() == cluster
                and (r.get("supplier_name") or "").lower() == sup):
            out.update({
                "base_cost": r.get("base_cost", ""),
                "shipping_cost": r.get("shipping_cost", ""),
                "processing_time": r.get("processing_time", ""),
                "material": r.get("material", ""),
                "available_sizes": r.get("size", ""),
                "variants_available": r.get("variants_available", ""),
                "personalization_supported": r.get("personalization_supported", ""),
                "production_partner_required":
                    (r.get("production_partner_required") or "yes"),
                "supplier_notes": "Pre-filled from supplier_costs.csv — verify the "
                                  "exact product URL + remaining fields.",
            })
            break
    return out


def load_supplier_products(path=CSV_PATH):
    rows = []
    p = Path(path)
    if p.exists():
        with p.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    return rows


def save_supplier_products(rows, path=CSV_PATH):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def best_record_for(product_idea, kind=None):
    """Best saved record for a product idea -> (record, status, missing)."""
    idea = product_idea.strip().lower()
    kind = kind or ("embroidery" if classify_production_type(idea) in
                    ("EMBROIDERY", "CHENILLE_PATCH") else "pod")
    candidates = [r for r in load_supplier_products()
                  if (r.get("product_idea") or "").strip().lower() == idea]
    best, best_rank = None, -1
    order = ["SUPPLIER_CONFIRMED", "SUPPLIER_PARTIAL", "NEED_SUPPLIER_DETAILS",
             "SUPPLIER_NOT_FOUND", "EMBROIDERY_NOT_SUPPORTED",
             "CHENILLE_NOT_SUPPORTED", "PRODUCT_NOT_SUPPORTED"]
    for r in candidates:
        st, miss = compute_status(r, kind)
        rank = len(order) - order.index(st) if st in order else 0
        if rank > best_rank:
            best, best_rank = (r, st, miss), rank
    return best  # None if nothing saved yet


def _printify_matches(primary_keyword):
    """Live Printify blueprint matches (title/brand/id). No costs in API."""
    try:
        from src.printify import _get
        bps = _get("/catalog/blueprints.json")
    except SystemExit:
        print("  (Printify token missing in .env -> skipping live pull)")
        return []
    except Exception as exc:
        print(f"  (Printify pull failed: {exc})")
        return []
    words = [w for w in primary_keyword.lower().split() if len(w) > 3]
    hits = []
    for b in bps:
        title = (b.get("title") or "").lower()
        score = sum(1 for w in words if w in title) / max(len(words), 1)
        if score >= 0.5:
            hits.append((score, b))
    hits.sort(key=lambda t: -t[0])
    return hits[:3]


def run_pull(kind, product_idea, primary_keyword=None, cluster="",
             target_country="US", suppliers=None, output=None,
             preferred=None, fallback=("shineon",)):
    kind = kind.lower()
    primary_keyword = primary_keyword or product_idea
    ptype = classify_production_type(product_idea)
    # supplier list: explicit --suppliers wins; else a sensible per-mode default.
    if suppliers:
        supplier_list = suppliers
    elif preferred:
        supplier_list = list(preferred) + list(fallback)
    elif kind == "embroidery":
        supplier_list = ["embroidery partner", "printify", "printway", "burgerprints"]
    else:
        supplier_list = ["printify", "printway", "burgerprints", "shineon"]
    out_path = Path(output) if output else CSV_PATH

    print(f"\nPULL_SUPPLIER_DETAILS_{kind.upper()}: {product_idea}")
    print(f"  production_type: {ptype} · country: {target_country} · "
          f"suppliers: {', '.join(supplier_list)} · output: {out_path}")
    if kind == "pod" and ptype in ("EMBROIDERY", "CHENILLE_PATCH"):
        print("  WARNING: this product classifies as embroidery/chenille. "
              "Do not pretend a printed product is embroidery - use:\n"
              f'  py main.py supplier embroidery "{product_idea}"')
    if kind == "embroidery" and ptype == "DIGITAL":
        print("  NOTE: digital product — embroidery not applicable.")

    existing = load_supplier_products(out_path)
    key = product_idea.strip().lower()
    updated = [r for r in existing
               if (r.get("product_idea") or "").strip().lower() != key]
    new_rows = []

    printify_hits = _printify_matches(primary_keyword) \
        if "printify" in [p.lower() for p in supplier_list] else []

    for sup in supplier_list:
        s = sup.lower()
        rec = {f: "" for f in FIELDS}
        rec.update({
            "product_idea": key, "production_type": ptype,
            "supplier_name": s,
            "supplier_catalog_url": SUPPLIER_CATALOGS.get(s, ""),
            "target_country": target_country,
            "production_partner_required": "yes",
        })
        rec.update(_known_fields(product_idea, kind, s))   # real data pre-fill
        if ptype in ("DIGITAL", "UNKNOWN"):
            rec["supplier_status"] = "PRODUCT_NOT_SUPPORTED"
            rec["missing_fields"] = ""
            new_rows.append(rec)
            print(f"  {s:<18} status=PRODUCT_NOT_SUPPORTED ({ptype})")
            continue
        if s == "printify" and printify_hits:
            score, bp = printify_hits[0]
            rec["product_name_from_supplier"] = bp.get("title", "")
            rec["product_url"] = (f"https://printify.com/app/products/"
                                  f"{bp.get('id')}")
            rec["product_match_score"] = f"{score:.2f}"
            rec["supplier_notes"] = ("Matched via Printify API. Base cost is "
                                     "not exposed by the API - read it from "
                                     "the product page. Shipping: py main.py "
                                     f"printify cost {bp.get('id')}")
        elif s == "printify":
            rec["supplier_notes"] = "No matching Printify blueprint found."
        else:
            rec["supplier_notes"] = ("No data API for this supplier - fill "
                                     "fields from the dashboard/catalog page.")
        st, missing = compute_status(rec, kind)
        rec["supplier_status"] = st
        rec["missing_fields"] = ";".join(missing)
        new_rows.append(rec)
        print(f"  {s:<14} status={st:<24} "
              f"missing={len(missing)} fields"
              + (f"  match={rec['product_match_score']}"
                 if rec.get("product_match_score") else ""))

    save_supplier_products(updated + new_rows, out_path)
    print(f"\nRecords saved to {out_path}. Team: open the file, fill the "
          "missing fields for the supplier you choose (costs, material, "
          "sizes, processing), then rerun 'py main.py manager'.")
    print("A product can only become PUBLISH_READY once one supplier row "
          "reaches SUPPLIER_CONFIRMED. Nothing is guessed for you.")
    return new_rows
