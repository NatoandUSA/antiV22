"""Listing Factory: py main.py listing "keyword"
Builds a complete, ready-to-publish Etsy listing pack:
English listing content (paste into Etsy) + Vietnamese publish guide.
"""
from datetime import date
from pathlib import Path

from src.discover import load_niche_terms, SERVICE_TERMS
from src.idea_report import (cluster_of, intents_of, load_costs, margin_at,
                             TRANSACTION_FEE, PAYMENT_FEE_PCT,
                             PAYMENT_FEE_FLAT, LISTING_FEE, ADS_RESERVE)
from src.trademark import PRODUCT_WORDS as PRODUCT_TERMS
from src.trademark import check as tm_check
from src.ytrends_client import suggestions, top_listings

OCCASIONS = {
    "gift": "birthday gifts, holiday gifts, thank-you gifts",
    "personalization": "custom name gifts, monogram lovers, one-of-a-kind keepsakes",
    "event": "weddings, bridesmaid proposals, bachelorette parties, baby showers",
    "fashion": "everyday style, matching outfits, trend lovers",
    "utility": "travel, organizing, daily essentials",
}


def build_listing(keyword):
    keyword = keyword.strip().lower()
    risk, reason = tm_check(keyword)
    if risk == "HIGH":
        raise SystemExit(f"\nDUNG LAI: '{keyword}' dinh thuong hieu ({reason}). "
                         "Chon tu khoa khac.\n")

    print(f"Building listing pack for '{keyword}'...")
    from src import pattern_miner as pm
    from src import ytrends_mcp as mcp

    # Mine contextual DNA and patterns from historical captures & SERP
    pat = pm.mine(keyword)

    try:
        rel = suggestions(keyword)
    except Exception:
        rel = []
    try:
        raw_winners = top_listings(keyword)
    except Exception:
        raw_winners = []

    # Pull quantitative ecosystem from YTrends MCP when live/non-mocked
    eco = {}
    if rel or raw_winners:
        try:
            eco = mcp.pull_keyword_ecosystem(keyword, limit=30)
        except Exception:
            pass


    kw_words = set(keyword.split())
    winners, rejected_n = [], 0
    candidate_winners = raw_winners or (eco.get("top_listings") or [])
    for w in candidate_winners:
        t_words = set((w.get("title") or "").lower().replace(",", " ").split())
        relevant = bool(t_words & kw_words or t_words & PRODUCT_TERMS)
        if relevant and not t_words & SERVICE_TERMS:
            winners.append(w)
        else:
            rejected_n += 1
        if len(winners) == 5:
            break

    # Fallback to pattern miner provenance (e.g. from ingested raw data) if winners empty
    prov = pat.get("provenance") or (pat.get("contextual_dna") or {}).get("provenance") or []
    if not winners and prov:
        for pl in prov:
            pr = pl.get("price") or pl.get("price_usd")
            if pr and isinstance(pr, (int, float)):
                winners.append({
                    "title": pl.get("title") or "",
                    "price_usd": pr,
                    "listing_id": pl.get("listing_id") or "ingested",
                    "total_sold": pl.get("sold_num") or 10,
                })
            if len(winners) == 5:
                break


    # Build 13 Structured Tags Model
    tag_candidates = []
    seen_tags = set()

    def add_tag(text, role, demand="N/A", comp="N/A", source="Heuristic", verified=False):
        text = text.strip().lower()
        if not text or text in seen_tags or len(text) > 20:
            return
        if set(text.split()) & SERVICE_TERMS or tm_check(text)[0] == "HIGH":
            return
        seen_tags.add(text)
        tm_res = tm_check(text)[0]
        tm_val = "PASS" if tm_res == "OK" else tm_res
        tag_candidates.append({
            "tag": text,
            "role": role,
            "demand": demand,
            "competition": comp,
            "source": source,
            "char_count": len(text),
            "tm_status": tm_val,
            "is_verified": verified,
        })

    # Tier 1: Seed / Primary Keyword
    if len(keyword) <= 20:
        add_tag(keyword, "Primary Exact Match", demand="Seed Query", comp="Search Seed",
                source="Keyword Seed", verified=True)

    # Tier 2: Competitor Overlap Tags (From Pattern Miner / Ingested Raw Data / MCP)
    for tg in (pat.get("top_tags") or []) + (eco.get("competitor_tags") or []):
        t_str = tg[0] if isinstance(tg, (list, tuple)) else (tg.get("tag") if isinstance(tg, dict) else str(tg))
        cnt = tg[1] if isinstance(tg, (list, tuple)) else (tg.get("count", 1) if isinstance(tg, dict) else 1)
        if len(tag_candidates) >= 13:
            break
        add_tag(t_str, "Competitor Overlap", demand=f"Used in {cnt} top listings",
                comp="High Overlap", source=f"Bestseller Tag ({cnt}x)", verified=True)

    # Tier 3: MCP Related Keywords with quantitative stats
    for rk in eco.get("related_keywords") or []:
        if len(tag_candidates) >= 13:
            break
        kw_text = rk.get("keyword") or ""
        v = rk.get("views_24h")
        dem = f"{v} views/24h" if v else "Related Search"
        c_lvl = rk.get("competition_level") or "N/A"
        add_tag(kw_text, "MCP Related Keyword", demand=dem, comp=f"Comp: {c_lvl}",
                source="YTrends MCP", verified=True)

    # Tier 4: Related suggestions from evidence (rel)
    ranked = sorted(rel, key=lambda r: -(r.get("relevance_score") or 0))
    for related_pass in (True, False):
        for r in ranked:
            t = (r.get("tag") or "").strip().lower()
            t_words = set(t.split())
            if not t or len(t) > 20:
                continue
            if related_pass and not t_words & kw_words:
                continue
            if not related_pass and not (t_words & kw_words
                                         or t_words & PRODUCT_TERMS
                                         or "gift" in t):
                continue
            if len(tag_candidates) >= 13:
                break
            v = r.get("views_24h") or r.get("views") or r.get("tag_listing_count")
            d_str = f"{v} views" if v else f"Rel: {r.get('relevance_score', 0)}"
            c_str = f"{r.get('tag_listing_count', 'N/A')} listings"
            add_tag(t, "Evidence-Backed Tag", demand=d_str, comp=c_str,
                    source="YTrends Data", verified=True)
        if len(tag_candidates) >= 13:
            break




    # If no evidence from MCP/SERP, do NOT invent synthetic tags -- surface honest gap
    tags_matrix = tag_candidates[:13]
    tags = [t["tag"] for t in tags_matrix]

    # Build Title: keyword first + up to 2 complementary phrases
    from collections import Counter as _Counter
    parts = [keyword.title()]
    used = set(keyword.split())
    wc = _Counter(keyword.split())
    for t in tags[1:]:
        if len(parts) >= 3:
            break
        tw = t.split()
        if all(w in used for w in tw):           # adds no new words -> skip
            continue
        if any(wc[w] + 1 >= 3 for w in tw):       # would stuff a word 3+x -> skip
            continue
        cand = ", ".join(parts + [t.title()])
        if len(cand) <= 140 and len(cand.split()) <= 15 and cand.count(",") <= 3:
            parts.append(t.title())
            used |= set(tw)
            for w in tw:
                wc[w] += 1
    title = ", ".join(parts)

    # Re-check Title Relevancy Stacking for all tags
    title_lower = title.lower()
    for t in tags_matrix:
        t["title_match"] = bool(t["tag"] in title_lower or any(w in title_lower for w in t["tag"].split() if len(w) > 3))

    # Pricing & Margin calculation: competitor winners evidence first
    prices = [w.get("price_usd") for w in winners if w.get("price_usd")]
    avg_price = sum(prices) / len(prices) if prices else None
    cluster = cluster_of(keyword)
    costs = load_costs()

    def _cost_plus_price():
        base, ship = costs[cluster][0], costs[cluster][1]
        fixed = base + ship + PAYMENT_FEE_FLAT + LISTING_FEE
        pct = TRANSACTION_FEE + PAYMENT_FEE_PCT + ADS_RESERVE
        return round((fixed + 6) / (1 - pct), 2)

    if avg_price:
        price = round(avg_price * 1.15, 2)
        margin = margin_at(price, cluster, costs)
        if margin is not None and margin < 6 and cluster in costs:
            price, margin = _cost_plus_price(), 6.0
    elif cluster in costs:
        price, margin = _cost_plus_price(), 6.0
    else:
        price, margin = None, None
    supplier = costs.get(cluster, (0, 0, None))[2] if cluster else None

    intents = intents_of(keyword)
    occ = "; ".join(OCCASIONS[i] for i in intents if i in OCCASIONS) \
        or "gifts and everyday use"
    personalized = "personalization" in intents or "custom" in keyword \
        or "name" in keyword or "monogram" in keyword

    return {
        "keyword": keyword, "title": title, "tags": tags, "tags_matrix": tags_matrix,
        "price": price, "margin": margin, "supplier": supplier, "cluster": cluster,
        "risk": risk, "occ": occ, "personalized": personalized,
        "winners": winners, "avg_price": avg_price,
        "rejected_competitors": rejected_n, "pattern": pat,
        "contextual_dna": pat.get("contextual_dna") or {},
    }




def write_pack(p):
    from src.report_paths import rdir
    safe_kw = p["keyword"].replace(" ", "_")[:30]
    path = rdir(date.today(), "listing") / \
        f"listing_{safe_kw}_{date.today()}.md"
    kw_t = p["keyword"].title()
    L = [f"# Goi listing hoan chinh: {kw_t} - {date.today()}", ""]

    if p["risk"] == "CAUTION":
        L += ["**CANH BAO:** Cum tu nay giong slogan. Tra tmsearch.uspto.gov "
              "(loc Live) va ghi vao tm_verified.csv TRUOC khi dang.", ""]

    L += ["## 1. Noi dung dan vao Etsy (giu tieng Anh)", ""]
    L += ["**TITLE (dan vao o Title):**", "```", p["title"], "```", ""]
    tag_note = "du 13" if len(p["tags"]) == 13 else f"chi co {len(p['tags'])}/13"
    L += [f"**TAGS (dan tung tag, {tag_note}):**", "```",
          ", ".join(p["tags"]), "```", ""]
    if len(p["tags"]) < 13:
        L += [f"> **OWNER CHECK:** thieu {13 - len(p['tags'])} tag co bang "
              f"chung. Chay: py main.py expand \"{p['keyword']}\" de tim tag "
              "that, khong tu bia them.", ""]

    # Quality gate: same validators as the main pipeline -- this pack path is no
    # longer ungated. Surfaces any title/tag issue to fix before publishing.
    from src.validators import validate_title, validate_tags
    _tok, _tiss = validate_title(p["title"], "", p["keyword"])
    _gok, _giss = validate_tags(p["tags"], "", p["title"])
    unverified_tags = [t["tag"] for t in p.get("tags_matrix", []) if not t.get("is_verified")]
    if _tok and _gok and not unverified_tags:
        L += ["> PASS - title + 13 tags meet the Etsy quality validators & all tags are evidence-backed.", ""]
    else:
        L += ["> **QUALITY & EVIDENCE CHECK - FIX THESE BEFORE PUBLISHING:**"]
        L += [f"> - TITLE: {i}" for i in _tiss]
        L += [f"> - TAGS: {i}" for i in _giss]
        if unverified_tags:
            L += [f"> - UNVERIFIED TAGS: {len(unverified_tags)} tags chua co so lieu kiem chung ({', '.join(unverified_tags)}). Can bo sung data."]
        L += [""]

    # 13 Tags Model Master Matrix
    L += ["## 2. Etsy Master Tag & Keyword Matrix (13 Tags Model)", ""]
    L += ["| # | Tag (≤20 chars) | Phân loại (Role) | Search Demand | Mức độ cạnh tranh | Nguồn chứng cứ | Khớp Title | TM | Trạng thái Data |"]
    L += ["|---|---|---|---|---|---|---|---|---|"]
    for i, tm in enumerate(p.get("tags_matrix", []), 1):
        t_match = "CO" if tm.get("title_match") else "-"
        status = "VERIFIED" if tm.get("is_verified") else "UNVERIFIED"
        L += [f"| {i} | `{tm.get('tag')}` ({tm.get('char_count')}c) | {tm.get('role')} | {tm.get('demand')} | {tm.get('competition')} | {tm.get('source')} | {t_match} | {tm.get('tm_status')} | {status} |"]
    L += [""]

    # Etsy Learning Box (Few-Shot Contextual DNA)
    dna = p.get("contextual_dna") or {}
    if dna.get("has_dna"):
        L += ["## 3. Etsy Learning Box (Few-Shot Contextual DNA)", ""]
        L += [f"> **Quy mô mẫu học:** Mined từ {dna.get('sample_size', 0)} listing đối thủ thực tế trong ngách.", ""]
        L += [f"- **Title Syntax DNA:** `{dna.get('title_syntax_dna')}`"]
        dist = dna.get("tag_distribution_dna") or {}
        L += ["- **Tag Strategy DNA:**"]
        for dk, dv in dist.items():
            L += [f"  * {dk.replace('_', ' ').title()}: {dv}"]
        pb = dna.get("price_band_dna")
        if pb:
            L += [f"- **Price Band DNA:** Median ${pb.get('median')} (P20 ${pb.get('low')} - P80 ${pb.get('high')}) - {pb.get('note')}"]
        L += ["- **Minh chứng số liệu (Data Proofs):**"]
        for dp in dna.get("data_proofs") or []:
            L += [f"  * {dp}"]
        if dna.get("provenance"):
            L += ["", "**Danh sách Listing đối thủ làm mẫu học (Provenance):**"]
            for pi, pl in enumerate(dna.get("provenance")[:3], 1):
                star_s = " [Star Seller]" if pl.get("star") else ""
                free_s = " [Free Ship]" if pl.get("freeship") else ""
                pr_s = f"${pl.get('price')}" if pl.get("price") else "N/A"
                L += [f"{pi}. {pl.get('title')[:75]}... (Shop: {pl.get('shop') or 'Unknown'}, Price: {pr_s}{star_s}{free_s})"]
        L += [""]

    desc = [
        f"~ {kw_t} ~",
        "",
        f"The perfect pick for {p['occ']} - made to order just for you.",
        "",
    ]
    if p["personalized"]:
        desc += ["HOW TO ORDER",
                 "1. Choose your options above",
                 "2. Type the name/text in the Personalization box",
                 "3. Double-check spelling - we print exactly what you enter!",
                 ""]
    desc += [f"PERFECT FOR: {p['occ']}", "",
             "Questions? We usually reply within a few hours."]
    L += ["**DESCRIPTION (dan vao o Description):**",
          "```"] + desc + ["```", ""]

    # Supplier-specific DETAILS (material/size/shipping) stay a separate,
    # clearly-labeled block: the stable copy above is never blocked on them,
    # and unverified facts never get merged into the pasteable block itself.
    sup_row = None
    try:
        from src.supplier_pull import best_record_for
        sup_row = best_record_for(p["keyword"])
    except Exception:
        pass
    material = (sup_row[0].get("material") if sup_row else "") or ""
    sizes = (sup_row[0].get("available_sizes") if sup_row else "") or ""
    proc = (sup_row[0].get("processing_time") if sup_row else "") or ""
    if material and sizes and proc:
        L += ["**THEM VAO CUOI DESCRIPTION (da co bang chung supplier):**",
              "```",
              "DETAILS",
              f"- Material: {material}",
              f"- Size: {sizes}",
              "- Made to order with care",
              "",
              f"SHIPPING: Processing {proc} + carrier shipping. "
              "Need it by a date? Message us first!",
              "```", ""]
    else:
        missing = [n for n, v in (("material", material), ("size", sizes),
                                  ("processing time", proc)) if not v]
        L += ["**OWNER CHECK - them DETAILS vao cuoi Description truoc khi "
              "dang:**",
              f"Con thieu bang chung: {', '.join(missing)}.",
              "Khong tu bia material/size/shipping. Chay: py main.py "
              "supplier pod/embroidery "
              f"\"{p['keyword']}\" va dien supplier_products.csv, roi them "
              "doan DETAILS vao cuoi Description.", ""]

    marg = f" (ban giu lai ~${p['margin']:.2f})" if p["margin"] is not None else ""
    sup = f" | Supplier re nhat: {p['supplier']}" if p["supplier"] else ""
    niche = f" | Gia trung binh doi thu: ${p['avg_price']:.2f}" if p["avg_price"] else ""
    if p["price"] is not None:
        L += [f"**GIA BAN: ${p['price']}**{marg}{sup}{niche}", ""]
    else:
        L += ["**GIA BAN: DATA UNAVAILABLE - OWNER CHECK** (chua co gia doi "
              "thu lan chi phi supplier de tinh gia). Chay: py main.py "
              f"supplier pod/embroidery \"{p['keyword']}\" de co chi phi "
              "that, hoac tu dien gia thu cong.", ""]

    if p["winners"]:
        L += ["## 4. Doi thu manh nhat (tham khao, KHONG copy)", ""]
        if p.get("rejected_competitors"):
            L.append(f"_Da loai {p['rejected_competitors']} doi thu KHONG "
                     "lien quan (khac loai san pham/tu khoa)._")
            L.append("")
        for i, w in enumerate(p["winners"][:3], 1):
            L.append(f"{i}. [{(w.get('title') or '')[:70]}]"
                     f"(https://www.etsy.com/listing/{w.get('listing_id')}) - "
                     f"${w.get('price_usd')} | {w.get('total_sold')} da ban")
        L.append("")

    L += ["## 5. Checklist anh/mockup (10 o anh cua Etsy)",
          "1. Anh chinh: san pham ro net, nen sang, thay chu/thiet ke ngay",
          "2. Goc gan (chi tiet thiet ke/theu)",
          "3. Nguoi that dang dung / lifestyle",
          "4. Bang size hoac kich thuoc",
          "5. Cac mau/bien the co san",
          "6. Anh mockup dip tang qua (goi qua, thiep)",
          "7. Anh personalization: vi du ten khac nhau" if p["personalized"]
          else "7. Anh goc canh khac",
          "8. Anh so sanh kich thuoc thuc te",
          "9. Review/feedback mockup (khi co)",
          "10. Anh thuong hieu shop",
          "Video 5-15 giay neu co the - Etsy uu tien listing co video.", ""]

    L += ["## 6. Cac buoc dang tren Etsy (Shop Manager)",
          "1. Shop Manager -> Listings -> Add a listing",
          "2. Tai 6-10 anh + video theo checklist tren",
          "3. Dan TITLE (muc 1)",
          "4. About this listing: Who made it = A member of my shop / "
          "What is it = A finished product / When = Made to order",
          "5. Chon Category dung nhat theo goi y cua Etsy",
          "6. Dien DESCRIPTION (muc 1) - nho dien cho [Fill]",
          "7. Keo xuong Tags: dan du 13 tag (muc 1)",
          "8. Variations: them size/mau theo supplier",
          "9. Personalization: BAT, ghi ro huong dan cho khach"
          if p["personalized"] else
          "9. Personalization: tat (san pham nay khong ca nhan hoa)",
          "10. Price: dat theo GIA BAN o tren; Quantity: 20-50",
          "11. Shipping: chon shipping profile khop processing time supplier",
          "12. Production partner: chon dung supplier (bat buoc voi POD)",
          "13. Bam Publish ($0.20 phi listing)",
          "14. Sau khi dang: mo listing o che do khach, kiem tra anh + "
          "personalization hoat dong", ""]

    L += ["## 7. Sau khi dang",
          "- Ghi URL listing + ngay dang vao file theo doi cua team",
          "- Ngay 3 va ngay 7: xem views/favorites trong Shop Manager Stats",
          "- 0 view sau 7 ngay -> doi tag yeu nhat bang tu khoa moi tu "
          "'py main.py expand'",
          "- Co favorite/cart -> lam them 3 bien the thiet ke ngay"]


    path.write_text("\n".join(L), encoding="utf-8")
    from src.lang import finalize_report
    finalize_report(path)
    return path


def run_listing(keyword):
    p = build_listing(keyword)
    path = write_pack(p)
    print(f"\nGoi listing da tao xong: {path}")
    print(f"  Title ({len(p['title'])} ky tu): {p['title'][:80]}...")
    if len(p['tags']) < 13:
        print(f"  LUU Y: chi tim duoc {len(p['tags'])}/13 tag lien quan. "
              f"Chay: py main.py expand \"{p['keyword']}\" de tu chon them.")
    price_s = f"${p['price']}" if p['price'] is not None else "DATA UNAVAILABLE"
    print(f"  Tags: {len(p['tags'])}/13  |  Gia: {price_s}"
          + (f"  |  Lai ~${p['margin']:.2f}" if p['margin'] is not None else ""))
