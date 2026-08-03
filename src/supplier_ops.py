"""Supplier operations for the normalized library at data/suppliers/.

- sync       : record a URL-catalog supplier (no public data API -> the row is
               CATALOG_URL_ONLY; the team pulls products manually).
- import-csv : normalize a ShineOn / Embroidery CSV into the unified schema.
- match      : classify a product and score each supplier record (0-100).

Never invents data: a field a source doesn't provide stays empty and appears in
missing_fields. Uploaded CSVs are the truth for their supplier.
"""
import csv
import json
import re
from datetime import date
from pathlib import Path

from src.supplier_pull import classify_production_type

DEFAULT_OUT = "data/suppliers/supplier_products.csv"
SOURCES_JSON = Path("data/suppliers/supplier_sources.json")

SCHEMA = [
    "supplier_id", "supplier_name", "supplier_type", "catalog_url", "product_url",
    "product_name", "product_type", "production_mode", "product_category",
    "base_cost", "shipping_cost", "target_country", "processing_time_min",
    "processing_time_max", "shipping_time_min", "shipping_time_max", "material",
    "sizes", "colors", "variants", "print_method", "print_area",
    "embroidery_supported", "embroidery_type", "embroidery_area", "stitch_limit",
    "thread_colors", "chenille_supported", "personalization_supported",
    "mockup_supported", "production_partner_required", "csv_source_file",
    "last_updated", "missing_fields", "supplier_status", "notes"]

# fields we treat as "usable supplier" evidence when scoring completeness
CORE = ["product_url", "base_cost", "material", "sizes", "processing_time_min"]

# ---------------------------------------------------------------------------
# CANONICAL PRODUCT-FAMILY VOCABULARY — the ONE place a phrase becomes a product
# type. `match()` below and `feasibility_gate` both read it, so "can we make
# this?" gets the same answer wherever it is asked.
#
# It exists because match() scored raw token overlap between a keyword and a
# supplier product NAME. Measured on the real 25-row library (TSHIRT /
# SWEATSHIRT / HOODIE / WASH CAP) that gave EVERY keyword the same 50/100:
# "custom crew t-shirt" does not token-match "TSHIRT", and "chenille name bag"
# came back with TSHIRT as its best supplier. A 50-point floor made the
# strong/usable/weak bands meaningless and pointed staff at a supplier who
# cannot make the product. Both sides are now normalised to this vocabulary.
PRODUCT_FAMILIES = {
    "tshirt": ("tshirt", "t shirt", "tee", "tees", "shirt"),
    "sweatshirt": ("sweatshirt", "crewneck", "crew neck", "jumper"),
    "hoodie": ("hoodie", "hoody", "hooded"),
    "cap": ("cap", "hat", "beanie", "trucker", "snapback"),
    "tote": ("tote", "totebag", "handbag", "purse", "pouch", "bag"),
    "blanket": ("blanket", "throw"),
    "pillow": ("pillow", "cushion"),
    "towel": ("towel", "robe"),
    "mug": ("mug", "tumbler", "cup", "can cooler", "cozie", "cozies", "koozie"),
    "sticker": ("sticker", "decal"),
    "print": ("print", "poster", "wall art", "canvas"),
    "jewelry": ("necklace", "bracelet", "earring", "keychain", "charm"),
    "apron": ("apron",),
    "bib": ("bib",),
    "sock": ("sock", "socks"),
}


def product_family(text):
    """The product family a phrase implies, or None when it names no product.

    None is the COMMON case — "40th birthday gift" names an occasion, not a
    product — and it must stay None. Unknown is not a mismatch: we only ever act
    on a difference between two families we could both read.
    """
    t = " " + " ".join(str(text or "").lower().replace("-", " ").split()) + " "
    for fam, words in PRODUCT_FAMILIES.items():
        if any(f" {w} " in t for w in words):
            return fam
    return None


def load_sources():
    if SOURCES_JSON.exists():
        try:
            return json.loads(SOURCES_JSON.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _blank():
    return {f: "" for f in SCHEMA}


def load_products(path=DEFAULT_OUT):
    p = Path(path)
    if p.exists():
        with p.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return []


def save_products(rows, path=DEFAULT_OUT):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _status(rec):
    missing = [f for f in CORE if not (rec.get(f) or "").strip()]
    if not (rec.get("product_url") or rec.get("product_name") or "").strip():
        return "NEED_SUPPLIER_DETAILS", missing
    if not missing:
        return "SUPPLIER_CONFIRMED", []
    return ("SUPPLIER_PARTIAL" if len(missing) < len(CORE)
            else "NEED_SUPPLIER_DETAILS"), missing


def sync(source, country="US", out=DEFAULT_OUT):
    """Register a URL-catalog supplier. No public data API -> CATALOG_URL_ONLY."""
    src = source.lower()
    info = load_sources().get(src, {})
    rec = _blank()
    rec.update({
        "supplier_id": src, "supplier_name": info.get("name", source),
        "supplier_type": info.get("type", "catalog_url"),
        "catalog_url": info.get("catalog_url", ""),
        "production_mode": ",".join(info.get("modes", [])),
        "target_country": country, "production_partner_required": "yes",
        "last_updated": str(date.today()),
        "supplier_status": "CATALOG_URL_ONLY",
        "notes": "URL catalog — no public data API. Open the catalog and add "
                 "products with 'supplier match' / manual entry.",
    })
    rows = [r for r in load_products(out)
            if not (r.get("supplier_id") == src and not (r.get("product_name") or "").strip())]
    rows.append(rec)
    save_products(rows, out)
    print(f"Synced {rec['supplier_name']} ({rec['supplier_status']}) -> {out}")
    print(f"  catalog: {rec['catalog_url'] or 'n/a'}")
    return rec


def _import_shineon(reader, country):
    out = []
    for r in reader:
        rec = _blank()
        rec.update({
            "supplier_id": "shineon", "supplier_name": "ShineOn",
            "supplier_type": "csv_upload", "production_mode": "JEWELRY",
            "product_category": (r.get("type") or "jewelry"),
            "product_name": r.get("product_title", ""),
            "base_cost": r.get("base_cost_usd", ""),
            "material": r.get("metal", ""),
            "variants": r.get("variant_title", ""),
            "personalization_supported": "yes" if (r.get("engravings") or "").strip() else "",
            "mockup_supported": "yes", "target_country": country,
            "production_partner_required": "yes",
            "csv_source_file": "shineon_jewelry_acrylic.csv",
            "last_updated": str(date.today()),
        })
        st, miss = _status(rec)
        rec["supplier_status"], rec["missing_fields"] = st, ";".join(miss)
        out.append(rec)
    return out


def _day_range(text):
    """(min, max) days from "7-12 business days", a bare "3-5", or "5". ("","")
    when the text carries no day count — never a guess."""
    t = str(text or "").strip()
    m = (re.search(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)\s*(?:business\s*)?days?", t, re.I)
         or re.fullmatch(r"(\d+)\s*(?:-|–|—|to)\s*(\d+)", t))
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"(\d+)\s*(?:business\s*)?days?", t, re.I) or re.fullmatch(r"(\d+)", t)
    return (m.group(1), m.group(1)) if m else ("", "")


def _import_embroidery(reader, country):
    out = []
    for r in reader:
        rec = _blank()
        # The sheet ships "US ePacket 7-12 business days - INCLUDED in price".
        # That window is real supplier data the importer used to drop entirely.
        ship_min, ship_max = _day_range(r.get("shipping", ""))
        # OPTIONAL columns. Every row is stuck at SUPPLIER_PARTIAL because the
        # sheet has no product_url and no production lead time, and there was no
        # way to supply them — the upload form only accepts this one layout. Add
        # either column to the sheet and the rows can reach SUPPLIER_CONFIRMED.
        # Absent stays absent: nothing here is inferred.
        proc_min, proc_max = _day_range(r.get("processing_days")
                                        or r.get("processing_time_min", ""))
        rec.update({
            "supplier_id": "embroidery", "supplier_name": "Embroidery",
            "supplier_type": "csv_upload", "production_mode": "EMBROIDERY",
            "product_name": r.get("product", ""), "sizes": r.get("size", ""),
            "base_cost": r.get("price_us_epacket_usd", ""),
            "shipping_cost": "0.00",   # price INCLUDES shipping
            "shipping_time_min": ship_min, "shipping_time_max": ship_max,
            "product_url": (r.get("product_url") or "").strip(),
            "processing_time_min": proc_min, "processing_time_max": proc_max,
            "material": r.get("material", ""),
            "embroidery_supported": "yes",
            "personalization_supported": "yes",
            "target_country": country, "production_partner_required": "yes",
            "csv_source_file": "Embroidery.csv",
            "last_updated": str(date.today()),
            "notes": "US ePacket price INCLUDES shipping.",
        })
        st, miss = _status(rec)
        rec["supplier_status"], rec["missing_fields"] = st, ";".join(miss)
        out.append(rec)
    return out


def import_csv(source, file, out=DEFAULT_OUT, country="US"):
    src = source.lower()
    p = Path(file)
    if not p.exists():
        print(f"CSV not found: {file}  (status: CSV_REQUIRED)")
        return []
    with p.open(newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    if src == "shineon":
        new = _import_shineon(reader, country)
    elif src == "embroidery":
        new = _import_embroidery(reader, country)
    else:
        print(f"import-csv supports shineon | embroidery, not '{source}'.")
        return []
    kept = [r for r in load_products(out) if r.get("supplier_id") != src]
    save_products(kept + new, out)
    confirmed = sum(1 for r in new if r["supplier_status"] == "SUPPLIER_CONFIRMED")
    print(f"Imported {len(new)} {src} products -> {out} "
          f"({confirmed} SUPPLIER_CONFIRMED, {len(new)-confirmed} partial/need).")
    return new


def mode_allows(mode, production_mode):
    """Can a supplier row with this production_mode serve an explicit request?

    Embroidery must NOT be satisfied by a POD/JEWELRY row and vice-versa — this
    is the core of mode-correct matching. Auto (mode=None) allows everything:
    nobody has said which production method to use, so nothing can be ruled out.
    Shared with feasibility_gate so both ask the question the same way."""
    pm = (production_mode or "").upper()
    m = str(mode or "").upper()
    if m == "EMBROIDERY":
        return "EMBROIDERY" in pm or "CHENILLE" in pm
    if m == "POD":
        return "EMBROIDERY" not in pm  # any non-embroidery supplier can print
    return True


def _mode_ok(mode, pm, ptype):
    """mode_allows for match(), which also has a guessed production type to fall
    back on when no mode was requested."""
    pm = (pm or "").upper()
    if not mode:
        return ptype in pm
    if mode.upper() in ("EMBROIDERY", "POD"):
        return mode_allows(mode, pm)
    return ptype in pm or mode.upper() in pm   # BOTH / other


def match(product, mode=None, country="US", path=DEFAULT_OUT, verbose=True):
    """Score supplier products against a product idea. Returns ranked matches.

    Mode-correct: in embroidery mode only embroidery/chenille suppliers score the
    production-fit points; in POD mode embroidery-only suppliers do not.

    Family-correct: a supplier who makes t-shirts is not a weak match for a bag,
    it is not a match at all (see PRODUCT_FAMILIES)."""
    ptype = classify_production_type(product)
    fam_q = product_family(product)
    words = {w for w in product.lower().split() if len(w) > 2}
    rows = load_products(path)
    scored = []
    for r in rows:
        name = (r.get("product_name") or "").lower()
        pm = (r.get("production_mode") or "").upper()
        fam_r = product_family(name)
        if fam_q and fam_r and fam_q != fam_r:
            # Two families we can BOTH read, and they differ. The old code gave
            # this 50/100 ("weak") purely for having a base cost and a material
            # on file, so every caller saw a usable-looking supplier for a
            # product nobody on file can make.
            scored.append((0, r))
            continue
        # Same family beats token overlap: "custom crew t-shirt" IS a "TSHIRT".
        # Fall back to overlap only when a family could not be read on one side.
        fit = 40 if (fam_q and fam_q == fam_r) else (
            40 * (len(words & set(name.split())) / max(len(words), 1)) if words else 0)
        if fit <= 0:
            # No family match and no shared word. The remaining components below
            # measure how COMPLETE a supplier record is, not how well it fits —
            # awarding them here is what put a 50/100 floor under every keyword
            # in the master, including ones that name no product at all.
            scored.append((0, r))
            continue
        mode_fit = _mode_ok(mode, pm, ptype)
        if mode and not mode_fit:
            # An EXPLICIT pod/embroidery request is a production constraint, not
            # a preference: an embroidery-only supplier scoring 65/100 "weak" for
            # a POD job is the same lie as the family mismatch above. Auto mode
            # (mode=None) stays soft — it has not been told which method to use.
            scored.append((0, r))
            continue
        s = fit
        s += 25 if mode_fit else 0
        s += 15 if (r.get("base_cost") or "").strip() else 0
        s += 10 if (r.get("product_url") or "").strip() else 0
        s += 5 if (r.get("personalization_supported") or "").strip() else 0
        s += 5 if (r.get("material") or "").strip() else 0
        scored.append((round(min(100, s)), r))
    scored.sort(key=lambda t: -t[0])
    if not verbose:
        return scored
    print(f"\nSUPPLIER MATCH: {product}  (type={ptype}, mode={mode or 'auto'})")
    if not scored:
        print("  no supplier products on file yet — run supplier import-csv / sync "
              "(status: VALIDATE_SUPPLIER_FIRST, PUBLISH_READY=false)")
        return []
    for sc, r in scored[:6]:
        band = ("strong" if sc >= 90 else "usable" if sc >= 70 else
                "weak" if sc >= 50 else "do-not-use")
        print(f"  {sc:>3}/100 {band:<11} {r.get('supplier_name',''):<12} "
              f"{(r.get('product_name') or '')[:40]:<42} {r.get('supplier_status','')}")
    best = scored[0]
    if best[0] < 50:
        print("  best match < 50 -> VALIDATE_SUPPLIER_FIRST, PUBLISH_READY=false")
    return scored
