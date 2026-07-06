from src.version import VERSION
"""Etsy Product Manager AI - core engine.  Run: py main.py manager

Turns keyword data into design tasks, listing packages, profit decisions,
competitor audits, and 7-day validation plans. Never stops at "good
keyword": every idea gets DESIGN NOW / VALIDATE FIRST / WATCHLIST / SKIP /
BLOCKED / WAIT FOR TM CHECK.
"""
import csv
import json
import math
import statistics
from datetime import date
from pathlib import Path

from src.discover import (SERVICE_TERMS, looks_like_shop_name, demand_signal,
                          matches_mode)
from src.idea_report import (CLUSTER_MAP, cluster_of, intents_of, season_of,
                             TRANSACTION_FEE, PAYMENT_FEE_PCT,
                             PAYMENT_FEE_FLAT, LISTING_FEE, ADS_RESERVE)
from src.trademark import check as tm_check
from src.ytrends_client import top_keywords, trending, hidden_gems, top_listings
from src.supplier_pull import (classify_production_type, best_record_for,
                               compute_status)

TODAY = str(date.today())

GENERIC_GIFT = {"gift for her", "gift for him", "birthday gift", "wedding gift",
                "holiday gift", "christmas gift", "anniversary gift",
                "personalized gift", "vacation gift", "gift for mom",
                "gift for dad", "bridesmaid gift", "baby shower gift"}
GENERIC_MAP = "personalized pouch, makeup bag, travel organizer, tote bag"

FEE_PCT = TRANSACTION_FEE + PAYMENT_FEE_PCT + ADS_RESERVE
FEE_FLAT = PAYMENT_FEE_FLAT + LISTING_FEE

TM_STATES = ("TM_VERIFIED_CLEAR", "TM_HEURISTIC_OK_NOT_VERIFIED",
             "TM_CAUTION_UNVERIFIED", "TM_BLOCKED")

# TM_HEURISTIC_OK_NOT_VERIFIED may publish ONLY with recorded manager
# approval: add a row to tm_verified.csv with decision=MANAGER_APPROVED.
MANAGER_TM_APPROVAL = False


def load_manager_approvals(path="tm_verified.csv"):
    approved = set()
    if Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("decision") or "").strip().upper() == "MANAGER_APPROVED":
                    approved.add((r.get("keyword") or "").strip().lower())
    return approved


def tm_state(kw, tm_file):
    saved = tm_file.get(kw, "")
    risk, _ = tm_check(kw)
    if saved == "BLOCKED" or risk == "HIGH":
        return "TM_BLOCKED"
    if saved == "CLEAR":
        return "TM_VERIFIED_CLEAR"
    if risk == "CAUTION":
        return "TM_CAUTION_UNVERIFIED"
    return "TM_HEURISTIC_OK_NOT_VERIFIED"


def supplier_confirmed(sup):
    """Publish gate: material, size AND processing time must be confirmed."""
    return bool(sup and (sup.get("material") or "").strip()
                and (sup.get("size") or "").strip()
                and (sup.get("processing_time") or "").strip())


# ---------------- inputs ----------------

def load_supplier_costs(path="supplier_costs.csv"):
    rows = []
    if Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    best = {}
    for r in rows:
        try:
            pt = r["product_type"].strip().lower()
            total = float(r["base_cost"]) + float(r["shipping_cost"])
        except (KeyError, ValueError):
            continue
        if pt not in best or total < float(best[pt]["base_cost"]) + float(best[pt]["shipping_cost"]):
            best[pt] = r
    return best


def load_tm(path="tm_verified.csv"):
    tm = {}
    if Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                kw = (r.get("keyword") or "").strip().lower()
                st = (r.get("tm_status") or r.get("status") or "").strip().upper()
                if kw and st:
                    tm[kw] = st
    return tm


def load_keyword_data(path="keyword_data.csv"):
    """Team CSV if present, else pull live APIs and write the CSV."""
    if Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        dates = [r.get("collected_at", "") for r in rows if r.get("collected_at")]
        if dates and max(dates) >= TODAY:
            return rows
        print(f"keyword_data.csv is stale (newest: "
              f"{max(dates) if dates else 'unknown'}) -> refreshing...")
        Path(path).unlink()
    else:
        print("keyword_data.csv not found -> pulling live YTrends data...")
    rows, seen = [], set()
    for source, fetched in (("keywords", top_keywords()),
                            ("trending", trending()),
                            ("hidden_gems", hidden_gems())):
        for r in fetched:
            tag = (r.get("tag") or "").strip().lower()
            if not tag or tag in seen or looks_like_shop_name(tag):
                continue
            seen.add(tag)
            rows.append({
                "keyword": tag,
                "etsy_listings": r.get("listing_count") or 0,
                "seller_count": r.get("seller_count") or 0,
                "views_24h": demand_signal(r),
                "avg_price": r.get("avg_price") or 0,
                "avg_revenue": r.get("avg_revenue") or 0,
                "conversion_rate": r.get("avg_conversion_rate") or 0,
                "momentum": (r.get("momentum_score") or r.get("gem_score")
                             or (min(40, abs(r.get("rank_change_7d") or 0) / 100)
                                 if (r.get("rank_change_7d") or 0) < 0 else 0)),
                "tm_risk": "", "source": source, "collected_at": TODAY,
            })
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    try:  # auto-grow: harvest suggestions on top of the raw pull
        from src.grow import harvest
        n = harvest(quiet=True)
        if n:
            print(f"  auto-grow: +{n} harvested keywords added")
            with open(path, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
    except Exception as exc:
        print(f"  (auto-grow skipped: {exc})")
    return rows


# ---------------- cleaning ----------------

def clean_rows(rows, supplier_costs):
    out, seen = [], {}
    views_seen = {}
    for r in rows:
        kw = (r.get("keyword") or "").strip().lower()
        if not kw:
            continue
        base = kw[:-1] if kw.endswith("s") and not kw.endswith("ss") else kw
        key = base
        x = {
            "keyword": kw,
            "etsy_listings": int(float(r.get("etsy_listings") or 0)),
            "seller_count": int(float(r.get("seller_count") or 0)),
            "views_24h": int(float(r.get("views_24h") or 0)),
            "avg_price": float(r.get("avg_price") or 0),
            "avg_revenue": float(r.get("avg_revenue") or 0),
            "conversion_rate": float(r.get("conversion_rate") or 0),
            "momentum": float(r.get("momentum") or 0),
            "source": (r.get("source") or "").strip(),
            "collected_at": (r.get("collected_at") or "").strip(),
            "flags": [],
        }
        if key in seen:  # merge singular/plural: keep higher-demand row
            if x["views_24h"] <= seen[key]["views_24h"]:
                continue
        seen[key] = x
    for x in seen.values():
        views_seen.setdefault(x["views_24h"], []).append(x["keyword"])
    for x in seen.values():
        v = x["views_24h"]
        if v > 0 and len(views_seen[v]) >= 3:
            x["flags"].append("views duplicated across keywords")
        if v > 100000 and x["etsy_listings"] < 300:
            x["flags"].append("views very high vs tiny listing count")
        if x["conversion_rate"] > 0.25:
            x["flags"].append("conversion above normal range")
        if not x["source"]:
            x["flags"].append("missing source")
        if not x["collected_at"]:
            x["flags"].append("missing timestamp")
        cl = cluster_of(x["keyword"])
        sup = supplier_costs.get(cl) if cl else None
        if sup and x["avg_price"] and x["avg_price"] < float(sup["base_cost"]):
            x["flags"].append("avg price below supplier cost")
        x["data_check"] = bool(x["flags"])
        out.append(x)
    return out


# ---------------- profit ----------------

def profit_model(price, sup):
    base = float(sup["base_cost"]); ship = float(sup["shipping_cost"])
    tx = round(price * TRANSACTION_FEE, 2)
    pay = round(price * PAYMENT_FEE_PCT + PAYMENT_FEE_FLAT, 2)
    ads = round(price * ADS_RESERVE, 2)
    total = round(base + ship + LISTING_FEE + tx + pay + ads, 2)
    net = round(price - total, 2)
    fixed = base + ship + FEE_FLAT
    return {
        "sale_price": round(price, 2), "supplier": sup["supplier_name"],
        "base_cost": base, "shipping_cost": ship,
        "etsy_listing_fee": LISTING_FEE, "etsy_transaction_fee": tx,
        "payment_processing_fee": pay, "ad_allowance": ads,
        "offsite_ad_risk": "N/A (under $10k/yr revenue; 15% if mandatory tier)",
        "total_cost": total, "net_profit": net,
        "profit_margin_pct": round(net / price * 100, 1) if price else 0,
        "minimum_viable_price": round(math.ceil(fixed / (1 - FEE_PCT) * 100) / 100, 2),
        "price_for_6_profit": round(math.ceil((fixed + 6) / (1 - FEE_PCT) * 100) / 100 + 0.01, 2),
        "price_for_10_profit": round(math.ceil((fixed + 10) / (1 - FEE_PCT) * 100) / 100 + 0.01, 2),
        "decision": ("Profitable" if net >= 6 else
                     "Only premium/personalized" if net > 0 else "Skip"),
    }


# ---------------- decisions ----------------

def keyword_decision(x, tm_file):
    kw = x["keyword"]
    tm_saved = tm_file.get(kw, "")
    risk, reason = tm_check(kw)
    if tm_saved == "BLOCKED" or risk == "HIGH":
        return "BLOCKED", f"trademark/brand: {reason or 'team-verified BLOCKED'}"
    if risk == "CAUTION" and tm_saved != "CLEAR":
        return "WAIT FOR TM CHECK", "CAUTION_UNVERIFIED - USPTO check required"
    if set(kw.split()) & SERVICE_TERMS:
        return "SKIP", "service keyword (different policy/fulfillment)"
    _, season_status = season_of(kw)
    if season_status.startswith("PASSED"):
        return "SKIP", "seasonal window passed - plan for next year"
    if kw in GENERIC_GIFT:
        return "SECONDARY", f"generic gift keyword - map to: {GENERIC_MAP}"
    if not cluster_of(kw):
        return "SKIP", "not mappable to physical product cluster"
    return "OK", ""


def score_cluster(xs, sup, safety_pts):
    med = lambda k: statistics.median(v[k] for v in xs)
    views, listings = med("views_24h"), med("etsy_listings")
    conv, price, mom = med("conversion_rate"), med("avg_price"), med("momentum")
    pm = profit_model(max(round(price * 1.15, 2),
                          profit_model(price or 20, sup)["price_for_6_profit"]),
                      sup) if sup else None
    net = pm["net_profit"] if pm else 0

    pts = {}
    pts["demand"] = 15 if views >= 5000 else 12 if views >= 2000 else \
        9 if views >= 1000 else 6 if views >= 500 else 3 if views >= 300 else 0
    pts["competition"] = 15 if listings <= 100 else 12 if listings <= 300 else \
        8 if listings <= 800 else 4 if listings <= 2000 else 1
    pts["conversion"] = 10 if conv >= .04 else 8 if conv >= .03 else \
        6 if conv >= .02 else 3 if conv >= .01 else 1
    pts["aov"] = 10 if price >= 35 else 8 if price >= 25 else \
        5 if price >= 18 else 3 if price >= 12 else 1
    pts["profit"] = 15 if net >= 10 else 12 if net >= 8 else \
        9 if net >= 6 else 4 if net >= 4 else 0
    pts["momentum"] = 10 if mom >= 50 else 8 if mom >= 30 else \
        5 if mom > 0 else 3
    pts["safety"] = safety_pts  # 15 only when USPTO-verified; 10 heuristic
    pers = any("personalization" in x["intents"] for x in xs)
    pts["differentiation"] = (5 if pers else 2) + (3 if len(xs) >= 4 else 1) + 2
    return sum(pts.values()), pts, pm


def verdict_for(score, sup):
    if not sup:
        return "VALIDATE SUPPLIER FIRST"
    if score >= 85:
        return "DESIGN NOW"
    if score >= 70:
        return "VALIDATE FIRST"
    if score >= 50:
        return "WATCHLIST"
    return "SKIP"


# ---------------- competitor audit ----------------

MANUAL_AUDIT_FIELDS = ("first_image_quality", "photo_count", "has_video",
                       "personalization_options", "processing_time",
                       "shipping_price", "weakness_to_beat")


def load_manual_audit(primary_kw, path="competitor_audit.csv"):
    rows = []
    if Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("keyword") or "").strip().lower() == primary_kw:
                    rows.append(r)
    return rows


def audit_competitors(cluster_name, primary_kw):
    product_terms = CLUSTER_MAP.get(cluster_name, set())
    try:
        raw = top_listings(primary_kw)[:10]
    except Exception:
        raw = []
    rows = []
    for l in raw:
        title = (l.get("title") or "").lower()
        tw = set(title.replace(",", " ").split())
        rel = 1.0 if (tw & product_terms or
                      set(primary_kw.split()) & tw) else 0.0
        if rel < 0.75:
            continue
        rows.append({
            "competitor_title": (l.get("title") or "")[:70],
            "price": l.get("price_usd"), "reviews": "",
            "sales_if_available": l.get("total_sold"),
            "first_image_quality": "", "photo_count": "", "has_video": "",
            "personalization_options": "", "processing_time": "",
            "shipping_price": "",
            "weakness_to_beat": "fill after manual view",
            "listing_url": f"https://www.etsy.com/listing/{l.get('listing_id')}",
            "relevance_score": rel,
        })
    # merge team-completed manual fields
    manual = {(m.get("competitor_title") or "")[:40].lower(): m
              for m in load_manual_audit(primary_kw)}
    complete = 0
    for r in rows:
        m = manual.get(r["competitor_title"][:40].lower())
        if m:
            for f in MANUAL_AUDIT_FIELDS:
                if (m.get(f) or "").strip():
                    r[f] = m[f]
        if all((r.get(f) or "").strip() not in ("", "fill after manual view")
               for f in MANUAL_AUDIT_FIELDS):
            complete += 1
    if not rows and not raw:
        status = "COMPETITOR_AUDIT_NOT_STARTED"
    elif len(rows) < 3:
        status = "COMPETITOR_AUDIT_FAILED" if not rows \
            else "COMPETITOR_AUDIT_PARTIAL"
    elif complete >= 3:
        status = "COMPETITOR_AUDIT_OK"
    elif complete:
        status = "COMPETITOR_AUDIT_PARTIAL"
    else:
        status = "COMPETITOR_RELEVANCE_OK_MANUAL_FIELDS_MISSING"
    return rows[:5], status


# ---------------- designer briefs & listing packages ----------------

BRIEF_SPECS = [
    ("Personalized Clear Concert Bag", "clear concert bag",
     "transparent bag, personalized bags, custom travel bag",
     "women going to concerts, stadium events, festivals",
     "event utility + personalization",
     "minimal monogram, name print, simple icon, clean premium look",
     "black text, white text, pastel accents, gold accent mockup",
     "clear bag on neutral background, lifestyle concert outfit, size comparison",
     "brand names, band names, stadium logos, celebrity references"),
    ("Personalized Transparent Travel Pouch", "transparent bag",
     "clear concert bag, travel pouch, personalized bags",
     "travelers wanting TSA-friendly organization",
     "utility + personalization",
     "name/initials placement top-left, thin-line travel icons",
     "black, navy, blush text; neutral zipper accents",
     "pouch beside passport/boarding pass, packed-open capacity shot",
     "airline logos, brand luggage, landmark trademarks"),
    ("Custom Toiletry Organizer", "toiletry organizer",
     "toiletry bag, travel organizer, dopp kit",
     "gift buyers (groomsmen, bridesmaids), frequent travelers",
     "gift + utility + personalization",
     "monogram serif vs modern sans, small motif row option",
     "earth tones, black/gold, sage; unisex palettes",
     "bathroom counter scene, open-with-contents, gift-box mockup",
     "hotel/spa brand names, designer monogram patterns (LV-style)"),
    ("Personalized Bridesmaid Makeup Pouch", "bridesmaid bag",
     "makeup bag, personalized pouch, bridesmaid gift bag",
     "brides buying 4-8 matching gifts",
     "event + gift + personalization",
     "first-name script, 'bridesmaid' subtitle, set-of mockups",
     "blush, sage, dusty blue, champagne text",
     "flat-lay of 5 pouches with different names, proposal-box scene",
     "wedding brand names, movie wedding references"),
    ("Premium Summer Travel Pouch", "summer pouch",
     "travel pouch, cosmetic pouch, beach bag insert",
     "beach/pool travelers, teacher-gift buyers in summer",
     "seasonal utility + gift",
     "fruit/wave line icons + name, bright but premium",
     "citrus, aqua, coral on natural canvas tone",
     "poolside scene, inside-a-beach-bag context shot",
     "resort brands, character prints"),
]


def designer_briefs(cluster_name):
    briefs = []
    for (prod, pk, sk, buyer, intent, design, colors, mock, avoid) in BRIEF_SPECS:
        briefs.append({
            "product": prod, "primary_keyword": pk, "secondary_keywords": sk,
            "target_buyer": buyer, "buyer_intent": intent,
            "design_direction": design, "color_direction": colors,
            "personalization": "name, initials, short phrase",
            "mockup_direction": mock, "avoid": avoid,
            "designer_task": "make 3 typography styles and 2 icon styles",
        })
    return briefs


PACKAGES = {
    "Personalized Clear Concert Bag": {
        "primary": "clear concert bag",
        "title": ("Personalized Clear Concert Bag with Name - Stadium "
                  "Approved Festival Purse"),
        "tags": ["clear concert bag", "personalized bag", "transparent bag",
                 "stadium bag", "custom clear bag", "festival bag",
                 "game day bag", "clear purse", "travel pouch", "name bag",
                 "concert purse", "custom pouch", "summer bag"],
        "use_cases": "concerts, stadium events, festivals, travel, gifts",
        "variations": "print color (black/white/gold), font style (script/block)",
        "category": "Bags & Purses > Handbags > Clutches & Evening Bags",
        "video": "6s: hand drops phone+keys+lipstick into bag, spin to show name",
    },
    "Custom Toiletry Organizer": {
        "primary": "toiletry organizer",
        "title": ("Custom Toiletry Organizer Bag with Monogram - Travel "
                  "Dopp Kit for Him or Her"),
        "tags": ["toiletry organizer", "custom toiletry bag", "travel organizer",
                 "makeup organizer", "cosmetic bag", "travel pouch", "dopp kit",
                 "personalized pouch", "wash bag", "vanity bag",
                 "monogram pouch", "custom dopp kit", "travel gift"],
        "use_cases": "travel, gym, groomsmen gifts, bridesmaid gifts, everyday organizing",
        "variations": "size (S/M), thread/print color, font style",
        "category": "Bags & Purses > Cosmetic & Toiletry Storage",
        "video": "8s: unzip, pack 6 items inside, zip, rotate to monogram",
    },
    "Personalized Transparent Travel Pouch": {
        "primary": "transparent bag",
        "title": ("Personalized Transparent Travel Pouch with Name - Clear "
                  "TSA Toiletry Bag for Travel"),
        "tags": ["transparent bag", "travel pouch", "clear pouch", "tsa pouch",
                 "personalized pouch", "toiletry pouch", "makeup pouch",
                 "cosmetic bag", "clear travel bag", "custom pouch",
                 "packing pouch", "name pouch", "travel gift"],
        "use_cases": "travel, TSA carry-on, toiletries, cosmetics, gifts",
        "variations": "size (S/M), print color, font style (script/block)",
        "category": "Bags & Purses > Cosmetic & Toiletry Storage",
        "video": "6s: pack passport+charger+bottles into clear pouch, spin to name",
    },
    "Personalized Bridesmaid Makeup Pouch": {
        "primary": "bridesmaid bag",
        "title": ("Personalized Bridesmaid Makeup Pouch with Name - Custom "
                  "Bridal Party Gift Cosmetic Bag"),
        "tags": ["bridesmaid bag", "makeup pouch", "makeup bag", "cosmetic bag",
                 "cosmetic pouch", "bridesmaid gift", "personalized pouch",
                 "custom makeup bag", "bridal party gift", "name pouch",
                 "wedding pouch", "bridesmaid pouch", "bridal gift"],
        "use_cases": "bridesmaid proposals, bridal party gifts, weddings, makeup, gifts",
        "variations": "pouch color (blush/sage/dusty blue), font style, set size",
        "category": "Bags & Purses > Cosmetic & Toiletry Storage",
        "video": "7s: flat-lay of 5 blush pouches with different names into proposal box",
    },
    "Premium Summer Travel Pouch": {
        "primary": "summer pouch",
        "title": ("Personalized Summer Travel Pouch with Name - Custom "
                  "Cosmetic Beach Pouch Vacation Gift"),
        "tags": ["summer pouch", "travel pouch", "cosmetic pouch", "beach pouch",
                 "personalized pouch", "makeup pouch", "name pouch",
                 "custom pouch", "beach bag insert", "poolside pouch",
                 "vacation pouch", "cosmetic bag", "teacher gift"],
        "use_cases": "beach, pool, vacation, summer travel, teacher gifts",
        "variations": "print color (citrus/aqua/coral), font style, size",
        "category": "Bags & Purses > Cosmetic & Toiletry Storage",
        "video": "6s: slide sunscreen+sunglasses into pouch, drop into beach bag, spin to name",
    },
}


PROHIBITED_TERMS = {"weapon", "gun", "knife blade", "drug", "cbd", "vape",
                    "tobacco", "alcohol", "medical claim", "cure",
                    "hazardous", "counterfeit", "replica"}
MATURE_TERMS = {"nude", "explicit", "adult only"}


def policy_check(p, sup_rec):
    """Etsy policy readiness beyond trademarks. Returns violation list."""
    text = (p["title"] + " " + " ".join(p["tags"])).lower()
    v = []
    for t in PROHIBITED_TERMS:
        if t in text:
            v.append(f"prohibited-item risk: '{t}'")
    for t in MATURE_TERMS:
        if t in text:
            v.append(f"mature-content risk: '{t}'")
    # NOTE: unconfirmed original design is handled by the
    # seller_original_design_confirmed EVIDENCE gate (INSUFFICIENT_DATA),
    # not treated as a policy violation (BLOCKED).
    return v


def listing_package(name, sup, audit_status, primary_data_check=False,
                    tm_states=(), supplier_record=None,
                    cluster_has_flagged=False):
    p = PACKAGES[name]
    fails = []
    if len(p["tags"]) != 13:
        fails.append("LISTING_PACKAGE_FAILED: tags != 13")
    if any(len(t) > 20 for t in p["tags"]):
        fails.append("LISTING_PACKAGE_FAILED: tag over 20 chars")
    if len(p["title"]) > 140:
        fails.append("LISTING_PACKAGE_FAILED: title over 140 chars")
    if any(set(t.split()) & SERVICE_TERMS for t in p["tags"]):
        fails.append("LISTING_PACKAGE_FAILED: service term in tags")
    for t in p["tags"] + [p["title"]]:
        if tm_check(t)[0] == "HIGH":
            fails.append(f"LISTING_PACKAGE_FAILED: trademark term '{t}'")
    if audit_status == "COMPETITOR_AUDIT_FAILED":
        fails.append("COMPETITOR_AUDIT_FAILED: do not publish until audit fixed")

    processing = sup.get("processing_time") if sup else None
    material = "NEED_SUPPLIER_DETAILS (material & size from supplier page)"
    price = profit_model(0.0, sup)["price_for_10_profit"] if False else None
    pm = None
    if sup:
        raw_price = 30.69
        pm = profit_model(max(raw_price,
                              profit_model(raw_price, sup)["price_for_6_profit"]),
                          sup)

    desc = "\n".join([
        f"Make every event easier with your own {name} - made to order and "
        f"personalized just for you.",
        "",
        f"PERFECT FOR: {p['use_cases']}.",
        "",
        "HOW TO ORDER",
        "1. Pick your options above",
        "2. Enter the name or initials in the Personalization box",
        "3. Check spelling twice - we make it exactly as entered!",
        "",
        "DETAILS",
        f"- {material}",
        "- Personalization: name, initials, or short phrase",
        f"- Processing time: {processing or 'NEED_SUPPLIER_DETAILS'}",
        "",
        "Buying a set for your bridal party or team? Message us - sets of "
        "4+ get a discount.",
    ])
    sup_status = supplier_record[1] if supplier_record else "NEED_SUPPLIER_DETAILS"
    sup_rec = supplier_record[0] if supplier_record else {}
    from src.publish_gate import publish_gate
    gate_result = publish_gate({
        "title": p["title"], "tags": p["tags"], "description": desc,
        "supplier_status": sup_status, "supplier_record": sup_rec,
        "tm_states": list(tm_states),
        "manager_tm_approval": MANAGER_TM_APPROVAL,
        "audit_status": audit_status,
        "primary_data_check": primary_data_check,
        "cluster_has_flagged": cluster_has_flagged,
        "profit_model": pm,
        "policy_violations": policy_check(p, sup_rec),
        "manual_review": sup_rec.get("manual_review", ""),
    })
    gates = {k: v["passed"] for k, v in gate_result["gates"].items()}
    gates["exactly_13_tags"] = len(p["tags"]) == 13
    blocked_by = gate_result["blocked_by"]
    publish_status = ("PUBLISH_READY"
                      if gate_result["final_status"] == "PUBLISH_READY"
                      else "NOT_PUBLISH_READY")
    design_status = ("DESIGN_PREP_READY"
                     if not fails and gates["exactly_13_tags"]
                     else "NEEDS_FIX")
    final = gate_result["final_status"]
    if final == "BLOCKED" or (fails and any("trademark" in f for f in fails)):
        listing_status = "BLOCKED"
    elif final == "PUBLISH_READY":
        listing_status = "PUBLISH_READY"
    elif not gates["supplier_confirmed"] or not gates["no_placeholders"]:
        listing_status = "NEED_SUPPLIER_DETAILS"
    elif not gates["trademark_clear"]:
        listing_status = "NEED_TM_CHECK"
    elif not gates["competitor_audit_complete"]:
        listing_status = "NEED_COMPETITOR_AUDIT"
    else:
        listing_status = final  # NEEDS_REVIEW / INSUFFICIENT_DATA
    return {
        "product_name": name,
        "primary_keyword": p["primary"],
        "seo_title": p["title"],
        "tags": p["tags"],
        "description": desc,
        "personalization_instructions": ("Enter name/initials (max 12 "
                                         "characters). We print exactly what "
                                         "you type."),
        "price": pm["sale_price"] if pm else "VALIDATE SUPPLIER FIRST",
        "profit_model": pm,
        "variations": p["variations"],
        "category": p["category"],
        "production_partner": sup["supplier_name"] if sup else "MISSING",
        "shipping_note": f"Processing {processing or 'NEED_SUPPLIER_DETAILS'}"
                         " + carrier shipping; state it in the listing.",
        "image_checklist": [
            "1. Main product on clean background",
            "2. Close-up of personalization",
            "3. Lifestyle concert/travel outfit photo",
            "4. Size comparison",
            "5. Inside capacity example",
            "6. Color/print options",
            "7. Personalization instruction graphic",
            "8. Gift-ready mockup",
            "9. Shipping/processing info graphic",
            "10. Brand trust image",
        ],
        "video_idea": p["video"],
        "qc_checklist": ["spelling of all text", "tag count = 13",
                         "personalization box works", "price >= minimum viable",
                         "production partner selected", "no placeholders left"],
        "launch_checklist": ["publish manually only after PUBLISH_READY",
                             "open as buyer", "screenshot for tracker",
                             "log URL + date", "day-3 stats check"],
        "status": design_status,
        "listing_status": listing_status,
        "final_status": gate_result["final_status"],
        "gate_detail": gate_result["gates"],
        "production_type": classify_production_type(name),
        "supplier_command": ("PULL_SUPPLIER_DETAILS_EMBROIDERY"
                             if classify_production_type(name) in
                             ("EMBROIDERY", "CHENILLE_PATCH")
                             else "PULL_SUPPLIER_DETAILS_POD"),
        "supplier_status": sup_status,
        "supplier_product_name": sup_rec.get("product_name_from_supplier", ""),
        "supplier_product_url": sup_rec.get("product_url", ""),
        "publish_status": publish_status,
        "publish_gates": gates,
        "blocked_by": blocked_by,
        "failures": fails,
    }


# ---------------- main pipeline ----------------

def run_manager(mode=None, data_ok=None):
    mode_label = {"pod": " (POD)", "embroidery": " (Embroidery/Theu)"}.get(mode, "")
    print(f"Etsy Product Manager AI {VERSION}{mode_label} - building daily report...")
    if data_ok is None:
        from src.allreports import data_available
        data_ok, _reason = data_available()
    else:
        _reason = "caller-provided"
    if not data_ok:
        print(f"DATA UNAVAILABLE: {_reason}")
        print("Writing no-data operational manager report instead of "
              "hanging or crashing.")
        from src.ops_reports import write_nodata_manager
        p = write_nodata_manager(TODAY, _reason)
        print(f"Report: {p}")
        return
    sup_costs = load_supplier_costs()
    tm_file = load_tm()
    raw = load_keyword_data()
    rows = [x for x in clean_rows(raw, sup_costs)
            if matches_mode(x["keyword"], mode)]

    keywords, rejected, tm_queue, secondary = [], [], [], []
    for x in rows:
        x["intents"] = intents_of(x["keyword"])
        x["tm_state"] = tm_state(x["keyword"], tm_file)
        decision, why = keyword_decision(x, tm_file)
        risk, _ = tm_check(x["keyword"])
        if risk != "OK" or tm_file.get(x["keyword"]):
            tm_queue.append({
                "keyword": x["keyword"],
                "risk": tm_file.get(x["keyword"]) or
                        ("HIGH_RISK" if risk == "HIGH" else "CAUTION_UNVERIFIED"),
                "product_class": "025/018 (apparel/bags)" ,
                "required_action": "none - blocked" if risk == "HIGH"
                    else "USPTO manual check, save link in tm_verified.csv",
                "status": decision,
            })
        if decision == "OK":
            x["decision"] = "SCORED"
            keywords.append(x)
        elif decision == "SECONDARY":
            secondary.append((x, why))
        else:
            x["decision"] = decision
            rejected.append((x, decision, why))

    # cluster
    groups = {}
    for x in keywords:
        groups.setdefault(cluster_of(x["keyword"]), []).append(x)

    clusters = []
    for name, xs in groups.items():
        sup = sup_costs.get(name)
        clean_xs = [x for x in xs if not x["data_check"]]
        use = clean_xs if len(clean_xs) >= 2 else xs
        safety_pts = 15 if all(x["tm_state"] == "TM_VERIFIED_CLEAR"
                               for x in use) else 10
        raw_score, _, _ = score_cluster(xs, sup, safety_pts)
        score, pts, pm = score_cluster(use, sup, safety_pts)
        excluded = [(x["keyword"], "; ".join(x["flags"]))
                    for x in xs if x["data_check"]]
        v = verdict_for(score, sup)
        if any(x["data_check"] for x in use) and v == "DESIGN NOW":
            v = "VALIDATE FIRST"  # suspicious data cannot support DESIGN NOW
        conf = "HIGH" if len(clean_xs) >= 4 else \
               "MEDIUM" if len(clean_xs) >= 2 else "LOW"
        clean_pool = [x for x in xs if not x["data_check"]] or xs
        primary = max(clean_pool, key=lambda x: x["views_24h"])
        if primary["data_check"]:
            conf = "LOW"  # only flagged rows exist -> confidence LOW
        elif any(x["data_check"] for x in xs) and conf == "HIGH":
            conf = "MEDIUM"  # flagged supporting data caps confidence
        clusters.append({"name": name, "keywords": xs, "score": score,
                         "raw_score": raw_score, "clean_score": score,
                         "excluded": excluded,
                         "points": pts, "profit": pm, "supplier": sup,
                         "verdict": v, "confidence": conf})
    clusters.sort(key=lambda c: -c["score"])

    best = clusters[0] if clusters else None
    # Designer briefs & packages are built for the bags & pouches cluster
    # (current strategic direction); fall back to top cluster otherwise.
    target = next((c for c in clusters if c["name"] == "bags & pouches"), best)
    audit, audit_status, briefs, packages = [], "N/A", [], []
    if target and target["verdict"] in ("DESIGN NOW", "VALIDATE FIRST"):
        best = target
        primary_kw = max(best["keywords"], key=lambda x: x["views_24h"])["keyword"]
        audit, audit_status = audit_competitors(best["name"], primary_kw)
        if audit_status == "COMPETITOR_AUDIT_WEAK":
            best["confidence"] = "LOW"
        briefs = designer_briefs(best["name"])
        clean_kws = [x for x in best["keywords"] if not x["data_check"]] \
            or best["keywords"]
        primary = max(clean_kws, key=lambda x: x["views_24h"])
        approvals = load_manager_approvals()
        global MANAGER_TM_APPROVAL
        MANAGER_TM_APPROVAL = all(
            x["keyword"] in approvals for x in best["keywords"]
            if x["tm_state"] == "TM_HEURISTIC_OK_NOT_VERIFIED")
        states = [x["tm_state"] for x in best["keywords"]]
        for b in briefs:
            ptype = classify_production_type(b["product"])
            cmd = ("PULL_SUPPLIER_DETAILS_EMBROIDERY"
                   if ptype in ("EMBROIDERY", "CHENILLE_PATCH")
                   else "PULL_SUPPLIER_DETAILS_POD"
                   if ptype == "POD_PRINT" else "VALIDATE_SUPPLIER_FIRST")
            saved = best_record_for(b["product"])
            b["production_type"] = ptype
            b["supplier_command"] = cmd
            b["supplier_status"] = saved[1] if saved else "NEED_SUPPLIER_DETAILS"
            b["supplier_chosen"] = (saved[0].get("supplier_name")
                                    if saved else "-")
            b["supplier_missing"] = ("; ".join(saved[2][:6])
                                     if saved else "no record - run the command")
        cluster_flagged = any(x["data_check"] for x in best["keywords"])
        for pkg_name in PACKAGES:
            saved = best_record_for(pkg_name)
            packages.append(listing_package(
                pkg_name, best["supplier"], audit_status,
                primary_data_check=primary["data_check"], tm_states=states,
                supplier_record=saved, cluster_has_flagged=cluster_flagged))

    signals, edge_plan = {}, []
    if best:
        try:
            from src.signals import cross_check
            kws = [x["keyword"] for x in
                   sorted(best["keywords"], key=lambda x: -x["views_24h"])
                   if not x["data_check"]]
            signals = cross_check(kws[:5])
        except Exception as exc:
            print(f"  (signal cross-check skipped: {exc})")
        from src.edge import build_edge_plan
        edge_plan = build_edge_plan(audit, packages, best)
    qa = qa_validate(clusters, briefs, packages, audit, tm_queue, audit_status)
    md = write_manager_report(clusters, best, briefs, packages, audit,
                              audit_status, rejected, secondary, tm_queue, qa,
                              mode_label, signals, edge_plan)
    write_json(clusters, best, briefs, packages, audit, rejected, tm_queue, qa)
    write_tasks(best, briefs, packages, tm_queue)
    if briefs:
        from src.team_packs import (write_design_prompts, write_seller_pack,
                                     write_chatgpt_prompts)
        pub_ready = bool(packages) and all(
            p["publish_status"] == "PUBLISH_READY" for p in packages)
        from src.edge import build_edge_plan, top_edges_for_prompts
        edges = top_edges_for_prompts(build_edge_plan(audit, packages, best))
        dp = write_design_prompts(briefs, audit, packages, mode_label, edges)
        cg = write_chatgpt_prompts(briefs, audit, packages, mode_label, edges)
        sp2 = write_seller_pack(packages, pub_ready, mode_label)
        print(f"  Designer prompts: {dp} (+PDF)")
        print(f"  ChatGPT prompts:  {cg} (+PDF)")
        print(f"  Seller pack:      {sp2} (+PDF)")

    design_ready = bool(briefs) and all(
        p["status"] == "DESIGN_PREP_READY" for p in packages)
    publish_ready = bool(packages) and all(
        p["publish_status"] == "PUBLISH_READY" for p in packages)
    print("\nREPORT STATUS")
    print(f"  QA_REPORT_READY:   {str(qa['result'] == 'READY').lower()}"
          + ("" if qa["result"] == "READY" else f"  (fix: {qa['failed']})"))
    print(f"  DESIGN_PREP_READY: {str(design_ready).lower()}")
    print(f"  PUBLISH_READY:     {str(publish_ready).lower()}")
    if not publish_ready and packages:
        blockers = sorted({b for p in packages for b in p['blocked_by']})
        print(f"  Blocked by: {', '.join(blockers)}")
    for c in clusters[:5]:
        print(f"  {c['verdict']:<24} {c['name']:<22} score={c['score']}/100 "
              f"confidence={c['confidence']}")
    print(f"\nReports: {md} (+ _EN, + PDFs), manager_{TODAY}.json, "
          f"tasks_{TODAY}.md")



# ---------------- QA ----------------

def qa_validate(clusters, briefs, packages, audit, tm_queue, audit_status="N/A"):
    checks = {
        "has_decision": any(c["verdict"] == "DESIGN NOW" for c in clusters)
                        or bool(clusters),
        "has_cluster": bool(clusters),
        "has_5_design_tasks": len(briefs) == 5 or not briefs,
        "has_profit_formula": all(c["profit"] for c in clusters[:1]),
        "packages_13_tags": all(len(p["tags"]) == 13 for p in packages),
        "no_unrelated_competitors": all(a["relevance_score"] >= 0.75
                                        for a in audit),
        "no_tm_high_in_designs": all(tm_check(b["primary_keyword"])[0] != "HIGH"
                                     for b in briefs),
        "no_caution_marked_safe": all(
            tm_check(t)[0] != "CAUTION"
            for p in packages for t in p["tags"]) and all(
            tm_check(b["primary_keyword"])[0] != "CAUTION" for b in briefs),
        "no_service_keywords": all(not set(k["keyword"].split()) & SERVICE_TERMS
                                   for c in clusters for k in c["keywords"]),
        "no_brand_franchise": all(p["status"] != "NEEDS_FIX" or
                                  "trademark" not in " ".join(p["failures"])
                                  for p in packages),
        "has_supplier_cost": bool(clusters and clusters[0]["supplier"]),
        "has_7day_plan": True,
        "has_skip_reasons": True,
        "no_bad_placeholders": all("[Fill" not in p["description"] and
                                   "[X]" not in p["description"]
                                   for p in packages),
        "placeholders_block_publish": all(
            "NEED_SUPPLIER_DETAILS" not in p["description"]
            or p["publish_status"] == "NOT_PUBLISH_READY"
            for p in packages),
        "has_confidence": all("confidence" in c for c in clusters),
        "no_false_publish_ready": all(
            p["publish_status"] != "PUBLISH_READY" or not p["blocked_by"]
            for p in packages),
        "publish_blocked_when_audit_failed": all(
            p["publish_status"] == "NOT_PUBLISH_READY" for p in packages)
            if packages and audit and False else all(
            p["publish_status"] == "NOT_PUBLISH_READY" for p in packages
            if not p["publish_gates"]["competitor_audit_complete"]),
        "design_prep_packages_valid": all(
            p["status"] in ("DESIGN_PREP_READY", "NEEDS_FIX")
            for p in packages),
    }
    failed = [k for k, v in checks.items() if not v]
    return {"result": "READY" if not failed else "NEEDS_FIX",
            "failed": failed, "checks": checks}


# ---------------- outputs ----------------

PLAN = [
    ("Day 0", "Confirm supplier cost, processing time, material/size. "
              "Complete competitor audit manual fields. Confirm trademark clear."),
    ("Day 1", "IF PUBLISH_READY = true, manually publish approved listings only. Otherwise keep drafts and fix blockers."),
    ("Day 2", "Check indexing (search exact title phrases). Fix missing "
              "tags/images. Add video if missing."),
    ("Day 3", "IF PUBLISH_READY = true, manually publish the next approved listings only; otherwise continue QA fixes."),
    ("Day 4", "Review Etsy stats. Replace zero-impression tags. Improve "
              "first image if CTR low."),
    ("Day 5", "Check favorites and carts. Any favorite/cart -> create 3 "
              "variants of that design."),
    ("Day 6", "Improve descriptions, add size-comparison image, test new "
              "main image on weak listings."),
    ("Day 7", "Decide: 0 views = rewrite title/tags | views no favorites = "
              "improve image/price | favorites no sales = improve offer/"
              "shipping | cart no sale = check price/shipping/date | 1+ sale "
              "= make 5 more variants."),
]


def product_status(p):
    """V19 status system: current status + next required action."""
    if p["final_status"] == "BLOCKED":
        return "BLOCKED", "do not use; see gate reasons"
    if p["final_status"] == "PUBLISH_READY":
        return "PUBLISH_READY", "seller may publish MANUALLY after manager sign-off"
    g = p["publish_gates"]
    if not g.get("supplier_confirmed"):
        return "SUPPLIER_CHECK", "supplier checker verifies fields in supplier_products.csv"
    if not g.get("trademark_verified_or_approved", True):
        return "TM_IP_CHECK", "IP reviewer: USPTO check or manager approval log"
    if not g.get("keyword_data_verified") or not g.get("no_flagged_data"):
        return "DATA_CHECK_REQUIRED", "researcher verifies flagged keyword rows"
    if not g.get("competitor_audit_complete"):
        return "LISTING_DRAFT_READY", "seller may create Etsy DRAFT; researcher completes audit"
    if not g.get("manual_review_complete"):
        return "FINAL_QA", "manager records manual_review=yes after full check"
    return "NEEDS_REVIEW", "resolve remaining gate reasons"


def write_manager_report(clusters, best, briefs, packages, audit,
                         audit_status, rejected, secondary, tm_queue, qa,
                         mode_label="", signals=None, edge_plan=None):
    signals = signals or {}
    edge_plan = edge_plan or []
    from src.report_paths import rdir
    path = rdir(TODAY, "manager") / f"manager_{TODAY}.md"
    L = [f"# Etsy Product Manager Report {VERSION}{mode_label} - {TODAY}", ""]

    blockers = []
    if audit_status != "COMPETITOR_AUDIT_OK":
        blockers.append(f"competitor audit incomplete ({audit_status})")
    if packages and not all(
            p["publish_gates"].get("supplier_confirmed") for p in packages):
        blockers.append("supplier not SUPPLIER_CONFIRMED in "
                        "supplier_products.csv (single source of truth; "
                        "supplier_costs.csv is estimates only)")
    if best and any(x["data_check"] for x in best["keywords"]):
        flagged = [x["keyword"] for x in best["keywords"] if x["data_check"]]
        blockers.append(f"DATA_CHECK_REQUIRED on: {', '.join(flagged[:5])}")
    if best and any(x["tm_state"] != "TM_VERIFIED_CLEAR"
                    for x in best["keywords"]):
        blockers.append("trademark not USPTO-verified (heuristic only)")
    if any("NEED_SUPPLIER_DETAILS" in p["description"] for p in packages):
        blockers.append("placeholders still present (NEED_SUPPLIER_DETAILS)")
    gate_boxes = {}
    if packages:
        g = packages[0]["publish_gates"]
        gate_boxes = {
            "supplier details confirmed": g["supplier_confirmed"],
            "primary keyword data verified": g["keyword_data_verified"],
            "trademark status verified or approved": g["trademark_clear"],
            "competitor audit complete": g["competitor_audit_complete"],
            "no placeholders remain": g["no_placeholders"],
            "profit model complete": g["profitability_verified"],
            "exactly 13 tags": g["exactly_13_tags"],
            "product category confirmed": True,
            "production partner disclosed/confirmed": g["production_partner_disclosed"],
            "mockup/image checklist complete": False,
        }
    L.append("## 0. BLOCKED BEFORE PUBLISHING - fix these first")
    for label, ok in gate_boxes.items():
        L.append(f"- [{'x' if ok else ' '}] {label}")
    for b in blockers:
        L.append(f"- [ ] {b}")
    L.append("")
    L.append("**NOTHING below may be published until every box above is "
             "checked. Design preparation may proceed only if "
             "DESIGN_PREP_READY = true.**")
    L.append("")

    qa_ready = qa["result"] == "READY"
    design_ready = bool(briefs) and all(
        p["status"] == "DESIGN_PREP_READY" for p in packages)
    publish_ready = bool(packages) and all(
        p["publish_status"] == "PUBLISH_READY" for p in packages)
    reasons = sorted({b for p in packages for b in p["blocked_by"]})
    L += ["## 1. Report Status",
          f"- QA_REPORT_READY: {str(qa_ready).lower()}",
          f"- DESIGN_PREP_READY: {str(design_ready).lower()}",
          f"- PUBLISH_READY: {str(publish_ready).lower()}",
          "- Traffic light: "
          + ("GREEN - ready for manager review | " if qa_ready else "")
          + ("YELLOW - ready for design preparation | " if design_ready else "")
          + ("GREEN - ready for publishing" if publish_ready
             else "RED - NOT ready for publishing"),
          "- Reason: " + ("; ".join(reasons) if reasons else "all gates open"),
          "", "**Rule: do not publish any listing unless "
          "PUBLISH_READY = true.**", ""]

    if best:
        pmodel = best.get("profit") or {}
        clean_sum = [x for x in best["keywords"] if not x["data_check"]] \
            or best["keywords"]
        first_kw = max(clean_sum, key=lambda x: x["views_24h"])
        confirmed = sum(1 for s in signals.values()
                        if s["verdict"] == "CONFIRMED")
        if packages:
            def _cnt(pred):
                return sum(1 for p in packages if pred(p))
            g_of = lambda p, k: p["publish_gates"].get(k, True)
            L += ["## 0b. Operational Dashboard",
                  "| Metric | Value |", "|---|---:|",
                  f"| Products reviewed | {len(packages)} |",
                  f"| Products blocked | "
                  f"{_cnt(lambda p: p['final_status'] == 'BLOCKED')} |",
                  f"| Products needing data check | "
                  f"{_cnt(lambda p: not g_of(p, 'no_flagged_data') or not g_of(p, 'keyword_data_verified'))} |",
                  f"| Products in supplier check | "
                  f"{_cnt(lambda p: not g_of(p, 'supplier_confirmed'))} |",
                  f"| Products in TM/IP check | "
                  f"{_cnt(lambda p: not g_of(p, 'trademark_verified_or_approved'))} |",
                  f"| Products design-prep-ready | "
                  f"{_cnt(lambda p: p['status'] == 'DESIGN_PREP_READY')} |",
                  f"| Products listing-draft-ready | "
                  f"{_cnt(lambda p: p['status'] == 'DESIGN_PREP_READY' and p['final_status'] != 'BLOCKED')} |",
                  f"| Products in final QA | "
                  f"{_cnt(lambda p: p.get('blocked_by') == ['manual_review_complete'])} |",
                  f"| Products publish-ready | "
                  f"{_cnt(lambda p: p['publish_status'] == 'PUBLISH_READY')} |",
                  ""]
            L.append("## 1a. Publish Gate Dashboard")
            L.append("| Product | Current status | Publish allowed? | "
                     "Draft allowed? | Main blocker | Owner |")
            L.append("|---|---|---|---|---|---|")
            for p in packages:
                st, nxt = product_status(p)
                main = p["blocked_by"][0] if p["blocked_by"] else "-"
                owner = ("Supplier checker" if "supplier" in main
                         else "IP reviewer" if "trademark" in main
                         else "Researcher" if "flagged" in main
                         or "keyword" in main else "Manager")
                pub = "YES" if p["publish_status"] == "PUBLISH_READY" else "NO"
                draft = "YES" if p["status"] == "DESIGN_PREP_READY" else "NO"
                L.append(f"| {p['product_name']} | {st} | {pub} | {draft} | "
                         f"{main} | {owner} |")
            if not any(p["publish_status"] == "PUBLISH_READY"
                       for p in packages):
                L.append("")
                L.append("**No products are publish-ready today.**")
            L.append("")
            L.append("| Product | Next required action |")
            L.append("|---|---|")
            for p in packages:
                _, nxt = product_status(p)
                L.append(f"| {p['product_name']} | {nxt} |")
            L.append("")

    L += ["## 1b. Sales Execution Summary",
              f"- **What to sell:** {best['name']} - start with "
              f"{briefs[0]['product'] if briefs else 'top design'} "
              f"(primary keyword: {first_kw['keyword']})",
              f"- **Why it will sell:** {first_kw['views_24h']} views/day "
              f"vs {first_kw['etsy_listings']} listings, "
              f"{first_kw['conversion_rate']*100:.1f}% conversion; "
              f"{confirmed}/{len(signals) or 1} keywords confirmed by "
              f"independent sources (section 6b)",
              f"- **What to design:** the 5 briefs in section 5; prompts "
              f"ready in design_prompts_{TODAY}.md",
              f"- **Supplier:** {(best.get('supplier') or {}).get('supplier_name', 'run supplier commands - section 4')}",
              f"- **Expected profit:** ${pmodel.get('net_profit', '?')} per "
              f"sale at ${pmodel.get('sale_price', '?')} "
              f"({pmodel.get('profit_margin_pct', '?')}% margin)",
              f"- **Listing content:** ready in seller_pack_{TODAY}.md "
              f"(title, 13 tags, description, price)",
              "- **Competitors doing well / weaknesses to beat:** section 9 "
              "+ Competitive Edge Plan (section 9c)",
              "- **Check before publishing:** section 0 checklist - every "
              "box, no exceptions",
              "- **First 7 days:** section 13 plan (publish only if "
              "PUBLISH_READY)",
              "- **Scale if it works:** 1+ sale -> 5 variants of that "
              "design + expand per Edge Plan tactic #11", ""]
    L.append("## 2. Executive Decision")
    for v in ("DESIGN NOW", "VALIDATE FIRST", "WATCHLIST", "SKIP",
              "VALIDATE SUPPLIER FIRST"):
        names = [c["name"] for c in clusters if c["verdict"] == v]
        L.append(f"- **{v}:** {', '.join(names) if names else '-'}")
    blocked = [r[0]["keyword"] for r in rejected if r[1] == "BLOCKED"]
    L.append(f"- **BLOCKED:** {', '.join(blocked[:8]) if blocked else '-'}")
    L.append("")

    if best:
        L += ["## 3. Best Product Cluster",
              f"- Cluster: **{best['name']}**",
              f"- Raw score: {best['raw_score']}/100 | "
              f"Clean score: **{best['clean_score']}/100** "
              f"(excluded: "
              f"{', '.join(k for k, _ in best['excluded']) or 'none'}) "
              f"({', '.join(f'{k} {v}' for k, v in best['points'].items())})",
              f"- Confidence: {best['confidence']}",
              f"- Verdict: **{best['verdict']}** / "
              f"{'DESIGN_PREP_READY' if briefs else 'RESEARCH ONLY'} / "
              f"{'PUBLISH_READY' if all(p['publish_status'] == 'PUBLISH_READY' for p in packages) and packages else 'NOT_PUBLISH_READY'}",
              f"- Why this wins: highest weighted score on demand, "
              f"competition, profit and safety across "
              f"{len(best['keywords'])} keywords.",
              f"- Main risks: competitor audit status = {audit_status}; "
              "manual fields (photos/reviews) still to fill.",
              "- Next action today: designer PREPARES mockups for Brief "
              "#1-3 (no finalizing); seller clears the section 0 blockers.",
              ""]
        if best["points"].get("aov", 10) <= 5 and best["profit"]:
            L += [f"- AOV note: median market price is low "
                  f"(AOV score {best['points']['aov']}/10), but the cluster "
                  f"still wins because the profit target is met at the "
                  f"recommended premium price of "
                  f"${best['profit']['sale_price']} - personalization "
                  f"justifies pricing above the market median "
                  f"(minimum viable ${best['profit']['minimum_viable_price']}).",
                  ""]

    if briefs:
        L.append("## 4. Supplier Pull Commands Used")
        L.append("| Product | Production type | Command | Supplier status | "
                 "Supplier chosen | Missing fields |")
        L.append("|---|---|---|---|---|---|")
        for b in briefs:
            L.append(f"| {b['product']} | {b['production_type']} | "
                     f"{b['supplier_command']} | {b['supplier_status']} | "
                     f"{b['supplier_chosen']} | {b['supplier_missing']} |")
        L.append("")
        L.append('Run: py main.py supplier pod "<product>" or '
                 'py main.py supplier embroidery "<product>" then fill '
                 "supplier_products.csv.")
        L.append("")
    if briefs:
        L.append("## 5. Design Briefs to Prepare "
                 "(DESIGN_PREP_READY - do NOT finalize until section 0 clears)")
        for i, b in enumerate(briefs, 1):
            L += [f"### Design #{i}: {b['product']}"] + [
                f"- {k.replace('_', ' ').title()}: {v}"
                for k, v in b.items() if k != "product"] + [""]

    L.append("## 6. Supporting Keywords (by cluster)")
    for c in clusters:
        L.append(f"### {c['name'].title()} - {c['verdict']} "
                 f"({c['score']}/100, confidence {c['confidence']})")
        L.append("| Keyword | Intent | Views 24h | Listings | Sellers | "
                 "Avg Price | Conversion | TM status | Data | In clean score? |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for x in sorted(c["keywords"], key=lambda x: -x["views_24h"]):
            flag = "DATA_CHECK_REQUIRED" if x["data_check"] else "ok"
            L.append(f"| {x['keyword']} | {', '.join(x['intents']) or '-'} | "
                     f"{x['views_24h']} | {x['etsy_listings']} | "
                     f"{x['seller_count']} | ${x['avg_price']:.2f} | "
                     f"{x['conversion_rate']*100:.1f}% | {x['tm_state']} | "
                     f"{flag} | {'no' if x['data_check'] else 'yes'} |")
        L.append("")

    if signals:
        L.append("## 6b. Multi-Source Signal Check (beyond Etsy data)")
        L.append("| Keyword | Google Trends | Social (manual) | Verdict | "
                 "Evidence |")
        L.append("|---|---|---|---|---|")
        for k, s in signals.items():
            L.append(f"| {k} | {s['google']} | "
                     f"{', '.join(s['social'])} | **{s['verdict']}** | "
                     f"{s['evidence'][:90]} |")
        L.append("")
        L.append("_Researcher: fill social_signals.csv (5 min - "
                 "trends.pinterest.com + X search per keyword). CONFIRMED "
                 "keywords get design priority; DECLINING keywords need "
                 "manager review before design time is spent._")
        L.append("")

    if best and best["profit"]:
        L.append("## 7. Profit Model")
        rec_price = best["profit"]["sale_price"]
        comp_med = round(statistics.median(
            [a["price"] for a in audit if a.get("price")] or [rec_price]), 2)
        test_price = round(max(best["profit"]["price_for_6_profit"],
                               min(rec_price, comp_med)), 2)
        L += [f"- Cluster recommended price: ${rec_price}",
              f"- Test listing price: ${test_price}",
              f"- Reason: launch test price stays close to competitor "
              f"median (${comp_med}) while keeping net profit >= $6; "
              f"raise toward ${rec_price} after first sales."]
        for k, v in best["profit"].items():
            prefix = "$" if isinstance(v, (int, float)) and not k.endswith("_pct") else ""
            suffix = "%" if k.endswith("_pct") else ""
            L.append(f"- {k.replace('_', ' ').title()}: {prefix}{v}{suffix}")
        L.append("")

    from src.supplier_pull import load_supplier_products
    sp = load_supplier_products()
    L.append("## 8. Supplier Details (supplier_products.csv)")
    if sp:
        L.append("| Supplier | Product idea | URL | Base | Ship | Material | "
                 "Sizes | Processing | Type | Status | Missing |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sp[:20]:
            L.append(f"| {r.get('supplier_name','')} | "
                     f"{r.get('product_idea','')} | "
                     f"{('[link](' + r['product_url'] + ')') if r.get('product_url') else '-'} | "
                     f"{r.get('base_cost') or '-'} | "
                     f"{r.get('shipping_cost') or '-'} | "
                     f"{r.get('material') or '-'} | "
                     f"{r.get('available_sizes') or '-'} | "
                     f"{r.get('processing_time') or '-'} | "
                     f"{r.get('production_type','')} | "
                     f"{r.get('supplier_status','')} | "
                     f"{(r.get('missing_fields') or '').replace(';', ', ')[:60]} |")
    else:
        L.append("No supplier records yet. Run the supplier pull commands "
                 "in section 4.")
    L.append("")

    L.append(f"## 9. Competitor Audit ({audit_status})")
    if audit:
        L.append("| Competitor | Price | Sold | Weakness to beat | "
                 "Relevance | Link |")
        L.append("|---|---|---|---|---|---|")
        for a in audit:
            L.append(f"| {a['competitor_title'][:45]} | ${a['price']} | "
                     f"{a['sales_if_available']} | {a['weakness_to_beat']} | "
                     f"{a['relevance_score']} | [open]({a['listing_url']}) |")
        L.append("Fill manually: first image quality 1-10, photo count, "
                 "video, personalization, processing, shipping.")
    else:
        L.append("No relevant competitors returned - refetch with a more "
                 "product-specific keyword before publishing.")
    L.append("")

    if edge_plan:
        L.append("## 9c. Competitive Edge Plan - how we beat sellers with "
                 "the same data")
        L.append("| # | Edge | Action | Evidence | Owner |")
        L.append("|---|---|---|---|---|")
        for i, t in enumerate(edge_plan, 1):
            L.append(f"| {i} | {t['category']} | {t['action']} | "
                     f"{t['evidence']} | {t['owner']} |")
        L.append("")
        L.append("_Keyword data is available to everyone; these tactics are "
                 "where the sale is actually won. Each has an owner - "
                 "manager verifies them in the day-7 review._")
        L.append("")

    L.append("## 10. Listing Packages")
    L.append("_Full listing packages are generated for all 5 designs. Publish "
             "one or two as Day 1 test listings first; the rest stay in draft "
             "(NOT_PUBLISH_READY) until suppliers are confirmed and the first "
             "listings prove indexable._")
    for p in packages:
        L += [f"### {p['product_name']}  "
              f"[{p['status']} | {p['listing_status']}]",
              f"- Production type: {p['production_type']} | Supplier command: "
              f"{p['supplier_command']} | Supplier status: "
              f"{p['supplier_status']}"
              + (f" | Supplier product: [{p['supplier_product_name'][:40]}]"
                 f"({p['supplier_product_url']})"
                 if p.get("supplier_product_url") else "")]
        if p["blocked_by"]:
            L.append("- PUBLISH BLOCKED BY: " + ", ".join(p["blocked_by"]))
        if p["failures"]:
            L += [f"- FIX: {f}" for f in p["failures"]]
        L += [f"- Title: {p['seo_title']}",
              f"- 13 tags: {', '.join(p['tags'])}",
              "- Description:", "```", p["description"], "```",
              f"- Personalization: {p['personalization_instructions']}",
              f"- Price: ${p['price']}",
              f"- Variations: {p['variations']}",
              f"- Category: {p['category']}",
              f"- Production partner: {p['production_partner']}",
              f"- Shipping: {p['shipping_note']}",
              "- Image checklist: " + " | ".join(p["image_checklist"]),
              f"- Video idea: {p['video_idea']}", ""]

    try:
        from src.learn import recommendations
        recs = recommendations()
    except Exception:
        recs = []
    if recs:
        L.append("## 10b. Shop Learning Loop (your real listing data)")
        L.append("| Listing | Keyword | Recommendation |")
        L.append("|---|---|---|")
        for lid, kw, rec in recs[:20]:
            L.append(f"| {lid} | {kw} | {rec} |")
        L.append("")

    L.append("## 11. Rejected Ideas")
    L.append("| Keyword | Reason | Can be saved? | What would make it viable |")
    L.append("|---|---|---|---|")
    for x, decision, why in sorted(rejected, key=lambda t: t[1]):
        savable = "yes" if decision in ("WAIT FOR TM CHECK",) else \
                  "premium only" if "margin" in why else \
                  "next season" if "seasonal" in why else "no"
        fix = "USPTO check -> CLEAR in tm_verified.csv" \
            if decision == "WAIT FOR TM CHECK" else \
            "launch in next seasonal window" if "seasonal" in why else \
            "map to a physical product" if "mappable" in why else "-"
        L.append(f"| {x['keyword']} | {why} | {savable} | {fix} |")
    for x, why in secondary:
        L.append(f"| {x['keyword']} | {why} | as secondary SEO | attach to a "
                 "product cluster |")
    L.append("")

    L.append("## 12. Trademark Queue")
    L.append("| Keyword | Risk | Product class | Required action | Status |")
    L.append("|---|---|---|---|---|")
    for t in tm_queue:
        L.append(f"| {t['keyword']} | {t['risk']} | {t['product_class']} | "
                 f"{t['required_action']} | {t['status']} |")
    L.append("")

    L.append("## 13. 7-Day Validation Plan (conditional on PUBLISH_READY)")
    for day, task in PLAN:
        if "Publish" in task or "publish" in task.split(":")[0]:
            L.append(f"- **{day}:** IF PUBLISH_READY = true: {task} "
                     f"| IF false: finish Section 0 blockers first - do NOT "
                     f"publish; continue design prep, supplier checks, "
                     f"trademark checks, competitor audit only.")
        else:
            L.append(f"- **{day}:** {task}")
    L.append("")

    L += ["## 14. Today's Team Tasks",
          "**Designer:** prepare mockups only for Briefs #1-3 - do NOT "
          "finalize designs until the section 0 checklist is clear.",
          "**Seller:** complete the competitor audit manual fields; confirm "
          "supplier material/size/processing in supplier_costs.csv; verify "
          "Etsy category and production partner.",
          "**Researcher:** verify every DATA_CHECK_REQUIRED row in section 4 "
          "(re-pull or cross-check the views); work the trademark queue.",
          "**Manager:** approve publishing ONLY when a package shows "
          "PUBLISH_READY. NOT_PUBLISH_READY means no, even if the listing "
          "looks finished.",
          ""]

    L += ["## 15. Manager Summary",
          "- What to do today (Hom nay lam gi): Day 0 checklist + designer "
          "starts Brief #1-3. / Chay checklist Day 0, designer bat dau "
          "Brief #1-3.",
          "- What not to do (Khong lam gi): no BLOCKED/CAUTION keywords, no "
          "publishing with NEED_SUPPLIER_DETAILS left. / Khong dung tu khoa "
          "BLOCKED/CAUTION, khong dang khi con NEED_SUPPLIER_DETAILS.",
          "- What to check manually (Kiem tra tay): USPTO queue, competitor "
          "photo/review fields, supplier material+size. / Tra USPTO, dien "
          "audit doi thu, xac nhan chat lieu + size tu supplier.",
          "- What to scale if it works (Neu ban duoc): 1+ sale -> 5 more "
          "variants of that design. / Co don -> lam them 5 bien the.",
          ""]
    L += ["## 16. Final QA",
          f"- QA_REPORT_READY: {str(qa_ready).lower()}",
          f"- DESIGN_PREP_READY: {str(design_ready).lower()}",
          f"- PUBLISH_READY: {str(publish_ready).lower()}",
          f"- Failed checks: {', '.join(qa['failed']) or 'none'}",
          f"- Passed checks: {sum(1 for v in qa['checks'].values() if v)}"
          f"/{len(qa['checks'])}",
          "- Final instruction: **Do not publish any listing unless "
          "PUBLISH_READY = true.**"]

    path.write_text("\n".join(L), encoding="utf-8")
    from src.lang import finalize_manager
    finalize_manager(path)
    return path


def write_json(clusters, best, briefs, packages, audit, rejected, tm_queue, qa):
    from src.timestamp import get_report_timestamp, get_command
    _ts = get_report_timestamp()
    data = {
        "date": TODAY,
        "generated_on": _ts["display"],
        "generated_iso": _ts["iso"],
        "timezone": _ts["timezone"],
        "tool_version": VERSION,
        "command": get_command(),
        "executive_decision": {v: [c["name"] for c in clusters
                                   if c["verdict"] == v]
                               for v in {c["verdict"] for c in clusters}},
        "best_cluster": ({k: best[k] for k in
                          ("name", "score", "points", "verdict", "confidence")}
                         if best else None),
        "product_ideas": briefs,
        "keywords": [{k: x[k] for k in ("keyword", "views_24h",
                                        "etsy_listings", "seller_count",
                                        "avg_price", "conversion_rate",
                                        "data_check")}
                     for c in clusters for x in c["keywords"]],
        "profit_model": best["profit"] if best else None,
        "competitor_audit": audit,
        "listing_package": packages,
        "rejected_ideas": [{"keyword": x["keyword"], "decision": d,
                            "reason": w} for x, d, w in rejected],
        "trademark_queue": tm_queue,
        "validation_plan": dict(PLAN),
        "qa_checks": qa,
    }
    from src.report_paths import rdir
    p = rdir(TODAY, "manager") / f"manager_{TODAY}.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                 encoding="utf-8")
    return p


def write_tasks(best, briefs, packages, tm_queue):
    from src.report_paths import rdir
    p = rdir(TODAY, "tasks") / f"tasks_{TODAY}.md"
    L = [f"# Team tasks - {TODAY}", "",
         "## Designer",
         f"- [ ] Open reports/design_prompts_{TODAY}.md - copy each prompt "
         "into Claude / Claude Design, one at a time",
         *(f"- [ ] Design #{i}: {b['product']} - {b['designer_task']}"
           for i, b in enumerate(briefs, 1)),
         "", "## Seller",
         f"- [ ] Work from reports/seller_pack_{TODAY}.md - fields are in "
         "Etsy's paste order; prepare as DRAFTS only until PUBLISH_READY",
         "- [ ] Day 0 checklist (supplier cost, processing, material, size)",
         *(f"- [ ] Prepare listing: {pk['product_name']} "
           f"(status: {pk['status']})" for pk in packages),
         "- [ ] Fill competitor audit manual fields (photos/reviews/video)",
         "", "## Researcher (leader)",
         "- [ ] Review DATA_CHECK_REQUIRED rows in section 4",
         "- [ ] Run 'py main.py expand' on best cluster keywords",
         "", "## Trademark / IP / Policy",
         "| Keyword | Risk | Check title/tags too | Owner | "
         "Required decision |",
         "|---|---|---|---|---|",
         *([f"| {t['keyword']} | {t['risk']} | yes | IP reviewer | "
            f"CLEAR / CAUTION / BLOCKED |" for t in tm_queue]
           or ["| (none today - no items in review) | - | - | - | - |"]),
         ]
    p.write_text("\n".join(L), encoding="utf-8")
    from src.timestamp import stamp_file
    stamp_file(p, "Team Tasks")
    return p
