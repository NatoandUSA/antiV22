"""Best Etsy Idea Report: clusters keywords into product concepts,
scores them (demand/competition/conversion/AOV/momentum/profit/safety/
differentiation), auto-rejects risky ideas, and outputs an action plan.
Run: py main.py ideas
"""
import csv
import statistics
from datetime import date
from pathlib import Path

from src.discover import (
    GENERIC_JUNK, SERVICE_TERMS, looks_like_shop_name, demand_signal,
    load_niche_terms, matches_mode,
)
from src.trademark import check as tm_check
from src.ytrends_client import top_keywords, trending, hidden_gems

WEIGHTS = {
    "demand": 0.15, "competition": 0.15, "conversion": 0.10, "aov": 0.10,
    "momentum": 0.10, "profit": 0.15, "safety": 0.15, "differentiation": 0.10,
}

CLUSTER_MAP = {
    "bags & pouches": {"bag", "bags", "pouch", "tote", "purse", "organizer",
                       "insert", "backpack", "clutch", "wristlet"},
    "apparel": {"shirt", "tee", "tshirt", "t-shirt", "hoodie", "sweatshirt",
                "crewneck", "sweater", "tank", "pajamas", "onesie", "bodysuit"},
    "jewelry": {"necklace", "bracelet", "ring", "earring", "earrings",
                "pendant", "charm", "jewelry", "keychain"},
    "drinkware": {"mug", "tumbler", "cup", "bottle"},
    "wall art & prints": {"print", "poster", "canvas", "sign", "art"},
    "home & textile": {"blanket", "pillow", "towel", "mat", "apron",
                       "ornament", "decor"},
    "headwear": {"hat", "cap", "beanie", "bandana"},
    "stickers & paper": {"sticker", "decal", "card", "invitation"},
}

SEASONS = {  # term: (launch months, event months or None=season, label)
    "christmas": ({8, 9, 10}, {11, 12}, "Christmas"),
    "halloween": ({7, 8, 9}, {10}, "Halloween"),
    "valentine": ({12, 1}, {2}, "Valentine's"),
    "easter": ({1, 2, 3}, {3, 4}, "Easter"),
    "mothers day": ({3, 4}, {5}, "Mother's Day"),
    "mother's day": ({3, 4}, {5}, "Mother's Day"),
    "fathers day": ({4, 5}, {6}, "Father's Day"),
    "father's day": ({4, 5}, {6}, "Father's Day"),
    "usa": ({4, 5, 6}, {7}, "July 4th"),
    "patriotic": ({4, 5, 6}, {7}, "July 4th"),
    "4th of july": ({4, 5, 6}, {7}, "July 4th"),
    "graduation": ({2, 3, 4}, {5, 6}, "Graduation"),
    "back to school": ({6, 7}, {8, 9}, "Back to school"),
    "summer": ({3, 4, 5, 6}, {6, 7, 8}, "Summer"),
    "beach": ({3, 4, 5, 6}, {6, 7, 8}, "Summer"),
    "pool": ({3, 4, 5, 6}, {6, 7, 8}, "Summer"),
    "fall": ({7, 8}, {9, 10, 11}, "Fall"),
    "autumn": ({7, 8}, {9, 10, 11}, "Fall"),
    "winter": ({9, 10}, {11, 12, 1, 2}, "Winter"),
    "wedding": (set(range(1, 13)), None, "Wedding (year-round)"),
    "bridesmaid": (set(range(1, 13)), None, "Wedding (year-round)"),
}

INTENTS = {
    "gift": {"gift", "gifts", "bridesmaid", "grandma", "nana", "mama", "mom",
             "dad", "papa", "teacher", "nurse", "her", "him"},
    "personalization": {"custom", "personalized", "name", "monogram",
                        "initial", "photo"},
    "event": {"wedding", "bridesmaid", "bachelorette", "party", "birthday",
              "graduation", "baby shower", "anniversary", "memorial"},
    "fashion": {"aesthetic", "preppy", "vintage", "retro", "boho", "trendy",
                "cute", "seersucker", "chenille", "crochet"},
    "utility": {"organizer", "travel", "toiletry", "insert", "storage",
                "makeup", "cosmetic", "beach"},
}

# Etsy fee model (edit ADS_RESERVE to your real ad spend share)
TRANSACTION_FEE = 0.065
PAYMENT_FEE_PCT = 0.03
PAYMENT_FEE_FLAT = 0.25
LISTING_FEE = 0.20
ADS_RESERVE = 0.10  # save 10% of price for Etsy Ads / offsite ads exposure


def load_costs(path="costs.csv", mode=None):
    """Cheapest supplier per cluster -> {cluster: (base, ship, supplier)}.

    Mode-aware so POD and Embroidery price off different, real supplier data:
    - 'pod'  -> print-on-demand suppliers only (embroidery rows excluded).
    - 'embroidery' -> the real embroidery-partner price wherever we have it
      (apparel, headwear), falling back to the POD baseline for clusters we have
      no embroidery quote for, so the report stays populated.
    - None -> POD baseline (same as 'pod')."""
    p = Path(path)
    if not p.exists():
        return {}
    pod, emb = {}, {}
    with p.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                cl = row["cluster"].strip().lower()
                base = float(row["base_cost"])
                ship = float(row["shipping_cost"])
                supplier = (row.get("supplier") or "?").strip()
            except (KeyError, ValueError):
                continue
            is_emb = ("embroider" in supplier.lower()
                      or "chenille" in supplier.lower())
            target = emb if is_emb else pod
            if cl not in target or base + ship < target[cl][0] + target[cl][1]:
                target[cl] = (base, ship, supplier)
    if mode == "embroidery":
        merged = dict(pod)   # POD baseline for clusters with no embroidery quote
        merged.update(emb)   # real embroidery price wins where we have it
        return merged
    return pod  # 'pod' / None: print-on-demand costs only


def load_tm_verified(path="tm_verified.csv"):
    ok, blocked = set(), set()
    p = Path(path)
    if not p.exists():
        return ok, blocked
    with p.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kw = (row.get("keyword") or "").strip().lower()
            status = (row.get("status") or "").strip().upper()
            if kw and status == "CLEAR":
                ok.add(kw)
            elif kw and status == "BLOCKED":
                blocked.add(kw)
    return ok, blocked


def cluster_of(tag):
    words = set(tag.split())
    for name, terms in CLUSTER_MAP.items():
        if words & terms:
            return name
    return None


def intents_of(tag):
    words = set(tag.split())
    return sorted(i for i, terms in INTENTS.items() if words & terms)


def season_of(tag, today=None):
    today = today or date.today()
    m = today.month
    for term, (launch, event, label) in SEASONS.items():
        if term in tag:
            if event is None:
                return label, "EVERGREEN"
            if m in launch:
                return label, "LAUNCH NOW"
            if m in event:
                # mid-event: late for new listings unless season is long
                return label, "IN SEASON (late to launch)" if len(event) <= 2 else "IN SEASON"
            return label, "PASSED / TOO EARLY"
    return None, "EVERGREEN"


def margin_at(price, cluster, costs):
    c = costs.get(cluster)
    if not c or not price:
        return None
    base, ship = c[0], c[1]
    fees = price * (TRANSACTION_FEE + PAYMENT_FEE_PCT + ADS_RESERVE) \
        + PAYMENT_FEE_FLAT + LISTING_FEE
    return round(price - fees - base - ship, 2)


def gather_rows(mode=None):
    seen, rows = set(), []

    def _ok(tag):
        return (tag and tag not in seen and tag not in GENERIC_JUNK
                and not looks_like_shop_name(tag) and matches_mode(tag, mode))

    # 1) the live YTrends-MCP harvested pool (keyword_data.csv) — the rich,
    #    current data written by `main.py harvest`. This is what gives both
    #    modes (especially Embroidery) a deep keyword universe.
    kd = Path("keyword_data.csv")
    if kd.exists():
        import csv as _csv

        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0
        with kd.open(newline="", encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                tag = (r.get("keyword") or "").strip().lower()
                if not _ok(tag):
                    continue
                seen.add(tag)
                rows.append({
                    "tag": tag, "source": r.get("source") or "keyword_data",
                    "listing_count": _f(r.get("etsy_listings")),
                    "seller_count": _f(r.get("seller_count")),
                    "demand_24h": _f(r.get("views_24h")),
                    "avg_price": _f(r.get("avg_price")),
                    "avg_revenue": _f(r.get("avg_revenue")),
                    "conversion": _f(r.get("conversion_rate")),
                    "momentum": _f(r.get("momentum")),
                })

    # 2) legacy live client — supplements anything not already seen. Guarded so
    #    an expired cookie / API hiccup can't wipe out the harvested pool above.
    for source, fetch in (("keywords", top_keywords), ("trending", trending),
                          ("hidden_gems", hidden_gems)):
        try:
            fetched = fetch()
        except Exception:
            continue
        for r in fetched:
            tag = (r.get("tag") or "").strip().lower()
            if not _ok(tag):
                continue
            seen.add(tag)
            rows.append({
                "tag": tag, "source": source,
                "listing_count": r.get("listing_count") or 0,
                "seller_count": r.get("seller_count") or 0,
                "demand_24h": demand_signal(r),
                "avg_price": r.get("avg_price") or 0,
                "avg_revenue": r.get("avg_revenue") or 0,
                "conversion": r.get("avg_conversion_rate") or 0,
                "momentum": r.get("momentum_score") or r.get("gem_score") or 0,
            })
    return rows


# Minimum 24h views to count as real demand. Embroidery is a premium, niche,
# high-margin line (avg price ~$27, supplier cost ~$17) — healthy niches there
# run at lower volume than broad POD, so a lower floor is correct, not lax.
DEMAND_FLOOR = {"embroidery": 150}
DEFAULT_DEMAND_FLOOR = 300


def evaluate(rows, costs, tm_ok, tm_blocked, mode=None):
    accepted, rejected = [], []
    floor = DEMAND_FLOOR.get(mode, DEFAULT_DEMAND_FLOOR)
    for x in rows:
        tag = x["tag"]
        risk, reason = tm_check(tag)
        if tag in tm_blocked:
            risk, reason = "HIGH", "team verified BLOCKED on USPTO"
        elif tag in tm_ok:
            risk, reason = "OK", "team verified clear on USPTO"
        x["tm_risk"], x["tm_reason"] = risk, reason
        x["intents"] = intents_of(tag)
        x["season"], x["season_status"] = season_of(tag)
        x["cluster"] = cluster_of(tag)
        x["margin"] = margin_at(x["avg_price"], x["cluster"], costs)

        why = None
        if set(tag.split()) & SERVICE_TERMS:
            why = "service keyword (different policy/fulfillment risk)"
        elif risk == "HIGH":
            why = f"trademark HIGH: {x['tm_reason']}"
        elif risk == "CAUTION":
            why = "trademark CAUTION unverified - check USPTO, log in tm_verified.csv"
        elif x["season_status"].startswith("PASSED"):
            why = f"seasonal window passed ({x['season']})"
        elif x["demand_24h"] < floor:
            why = f"demand too low ({x['demand_24h']} views/24h, floor {floor})"
        elif x["margin"] is not None and x["margin"] < 4:
            why = f"margin too thin (${x['margin']} after fees/costs)"
        elif x["cluster"] is None:
            why = "not mappable to a physical product cluster"

        (rejected if why else accepted).append((x, why))
    return [a for a, _ in accepted], rejected


def _norm(vals):
    lo, hi = min(vals), max(vals)
    return [(v - lo) / (hi - lo) if hi > lo else 0.5 for v in vals]


def score_clusters(accepted, costs):
    groups = {}
    for x in accepted:
        groups.setdefault(x["cluster"], []).append(x)

    clusters = []
    for name, xs in groups.items():
        med = lambda k: statistics.median(v[k] for v in xs)
        margins = [x["margin"] for x in xs if x["margin"] is not None]
        clusters.append({
            "name": name, "keywords": xs, "n": len(xs),
            "demand": med("demand_24h"),
            "competition": med("listing_count"),
            "conversion": med("conversion"),
            "aov": med("avg_price"),
            "momentum": med("momentum"),
            "profit": statistics.median(margins) if margins else None,
            "safety": sum(1 for x in xs if x["tm_risk"] == "OK") / len(xs),
            "differentiation": len({i for x in xs for i in x["intents"]})
                               + min(len(xs), 6) / 6,
            "supplier": costs.get(name, (0, 0, None))[2],
        })
    if not clusters:
        return []

    comps = {
        "demand": [c["demand"] for c in clusters],
        "competition": [-c["competition"] for c in clusters],
        "conversion": [c["conversion"] for c in clusters],
        "aov": [c["aov"] for c in clusters],
        "momentum": [c["momentum"] for c in clusters],
        "profit": [c["profit"] if c["profit"] is not None else 0 for c in clusters],
        "safety": [c["safety"] for c in clusters],
        "differentiation": [c["differentiation"] for c in clusters],
    }
    normed = {k: _norm(v) for k, v in comps.items()}
    for i, c in enumerate(clusters):
        c["score"] = round(sum(WEIGHTS[k] * normed[k][i] for k in WEIGHTS), 3)
        strong = c["n"] >= 3 and c["safety"] >= 0.7
        if c["score"] >= 0.55 and strong:
            c["verdict"] = "DESIGN NOW"
        elif c["score"] >= 0.35:
            c["verdict"] = "VALIDATE FIRST"
        else:
            c["verdict"] = "SKIP FOR NOW"
    clusters.sort(key=lambda c: -c["score"])
    return clusters


def action_plan(c):
    xs = sorted(c["keywords"], key=lambda x: -x["demand_24h"])
    top = xs[0]["tag"]
    kws = [x["tag"] for x in xs]
    tags13 = [k for k in kws if len(k) <= 20][:13]
    price = round(statistics.median(x["avg_price"] for x in xs) * 1.15, 2)
    designs = [f"{i+1}. Original design targeting '{k}' "
               f"({', '.join(intents_of(k)) or 'general'} intent)"
               for i, k in enumerate(kws[:5])]
    return {
        "title_formula": f"[{top.title()}], [Personalization], "
                         f"[{kws[1].title() if len(kws) > 1 else 'Benefit'}], "
                         "[Occasion/Gift], [Style], [Secondary keyword]",
        "tags13": tags13,
        "price": price,
        "designs": designs,
    }


def run_ideas(mode=None):
    costs = load_costs(mode=mode)
    tm_ok, tm_blocked = load_tm_verified()
    if not costs:
        print("NOTE: costs.csv missing/empty -> profit checks limited. "
              "Fill it with real supplier costs.")
    mode_label = {"pod": " (POD)", "embroidery": " (Embroidery/Theu)"}.get(mode, "")
    print(f"Building Best Etsy Idea Report{mode_label}...")
    rows = gather_rows(mode)
    accepted, rejected = evaluate(rows, costs, tm_ok, tm_blocked, mode)
    clusters = score_clusters(accepted, costs)
    path = write_ideas_report(clusters, rejected, costs, mode_label, mode)
    print(f"\n{len(rows)} keywords -> {len(accepted)} accepted, "
          f"{len(rejected)} rejected -> {len(clusters)} clusters")
    for c in clusters[:5]:
        print(f"  {c['verdict']:<15} {c['name']:<22} score={c['score']} "
              f"({c['n']} keywords)")
    print(f"\nReport: {path}")


def _cost_basis_intro(mode, clusters, rejected):
    """A short, data-driven cost-basis banner so each mode's report is
    distinct and self-explaining even when few keywords pass. Numbers are the
    real supplier prices loaded for this mode (see costs.csv / supplier data)."""
    n_kw = sum(c.get("n", 0) for c in clusters) if clusters else 0
    if mode == "embroidery":
        return [
            "> **Embroidery line — real supplier cost basis "
            "(shipping INCLUDED, US ePacket 7–12 business days):**",
            ">",
            "> - Embroidered T-shirt **$16.99** · Sweatshirt **$23.23** · "
            "Hoodie **$26.38** · Wash cap **$13.40** (size M / one size).",
            "> - Design to the CONFIRMED areas: chest max **250mm** wide · "
            "sleeve **70mm × 250mm** (vertical only) · cap front **120mm × 60mm** "
            "(fits 56–58cm head) · max 6 thread colours, flat fills.",
            "> - Every margin below uses these real embroidery numbers "
            "(POD estimates are only used as a fallback for product lines we "
            "have no embroidery quote for yet).",
            f"> - Embroidery-mappable keywords this run: **{n_kw} accepted**, "
            f"{len(rejected)} rejected — embroidery niches are rarer than POD, "
            "so this list is intentionally shorter and higher-signal.",
            "",
        ]
    if mode == "pod":
        return [
            "> **Print-on-Demand line — cost basis:** cheapest POD supplier per "
            "product line (Printify · Printway · BurgerPrints · PGprint · "
            "ShineOn jewelry). Every margin below uses these real per-cluster "
            "costs — no embroidery pricing is mixed in.",
            "",
        ]
    return []


def write_ideas_report(clusters, rejected, costs, mode_label="", mode=None):
    from src.report_paths import rdir
    path = rdir(date.today(), "ideas") / f"ideas_{date.today()}.md"
    L = [f"# Báo cáo Ý tưởng Etsy Tốt nhất{mode_label} - {date.today()}", ""]
    L += _cost_basis_intro(mode, clusters, rejected)

    L.append("## Việc cần làm hôm nay")
    n = 0
    for c in clusters:
        if c["verdict"] == "DESIGN NOW":
            n += 1
            L.append(f"{n}. **THIẾT KẾ NGAY (DESIGN NOW) -> {c['name']}**: designer "
                     "bắt đầu 5 thiết kế bên dưới. Seller chuẩn bị listing.")
    for c in clusters:
        if c["verdict"] == "VALIDATE FIRST":
            n += 1
            L.append(f"{n}. **KIỂM CHỨNG TRƯỚC (VALIDATE FIRST) -> {c['name']}**: chỉ "
                     "đăng 2 listing thử nghiệm. Chưa làm loạt thiết kế lớn.")
    skips = [c["name"] for c in clusters if c["verdict"] == "SKIP FOR NOW"]
    if skips:
        n += 1
        L.append(f"{n}. **BỎ QUA (SKIP)**: {', '.join(skips)}.")
    L.append("")

    for c in clusters[:3]:
        if c["verdict"] == "SKIP FOR NOW":
            continue
        L.append(f"## {c['name'].title()} - {c['verdict']}")
        prof = (f"lãi khoảng ${c['profit']:.2f} mỗi đơn ở mức giá hiện tại"
                if c["profit"] is not None
                else "chưa rõ lợi nhuận - hãy điền giá supplier vào costs.csv")
        sup = f" Supplier rẻ nhất: {c['supplier']}." if c.get("supplier") else ""
        L.append(f"Sản phẩm này có người tìm mua mỗi ngày và mức cạnh tranh có thể "
                 f"thắng được. Ước tính: {prof}.{sup}")
        L.append("")

        plan = action_plan(c)
        L.append("**Làm 5 thiết kế này trước:**")
        L += plan["designs"]
        L.append("")
        L.append("**Cách đăng listing:**")
        L.append(f"- Tiêu đề: {plan['title_formula']}")
        L.append(f"- Tags (copy đủ 13): {', '.join(plan['tags13'])}")
        margin_note = ""
        if c["profit"] is not None:
            margin_note = f" -> bạn giữ lại khoảng ${c['profit']:.2f} sau phí Etsy + giá gốc"
        L.append(f"- Giá bán: ${plan['price']}{margin_note}")
        L.append("- Trước khi thiết kế: mở 3 listing đối thủ lớn nhất. Ghi lại ảnh đầu, "
                 "số review, tùy chọn cá nhân hóa, tốc độ ship. Làm tốt hơn đối thủ yếu nhất.")
        L.append("")

        L.append("**Các từ khóa trong nhóm này:**")
        L.append("| Từ khóa | Kết quả Etsy | Views/ngày | Giá TB | An toàn? |")
        L.append("|---|---|---|---|---|")
        for x in sorted(c["keywords"], key=lambda x: -x["demand_24h"]):
            safe = "an toàn" if x["tm_risk"] == "OK" else x["tm_risk"]
            L.append(f"| {x['tag']} | {x['listing_count']} | "
                     f"{x['demand_24h']} | ${x['avg_price']} | {safe} |")
        L.append("")
        L.append("**Kiểm chứng 7 ngày:** Ngày 1-2 đăng 3 listing (từ khóa top). "
                 "Ngày 3-4 đăng thêm 2. Ngày 5-7: 0 view = đổi tags; "
                 "có favorite/giỏ hàng = làm thêm 3 biến thể của thiết kế đó.")
        L.append("")

    rescuable = [(x, w) for x, w in rejected if w.startswith("margin too thin")]
    if rescuable:
        L.append("## Nhu cầu tốt nhưng cần giá bán cao hơn")
        L.append("_Bán chạy nhưng giá phổ biến quá thấp để có lãi. CHỈ dùng với phiên bản "
                 "cá nhân hóa/cao cấp ở mức 'giá tối thiểu', hoặc tìm supplier rẻ hơn._")
        L.append("")
        L.append("| Từ khóa | Giá phổ biến | Giá tối thiểu | Để lãi $6 |")
        L.append("|---|---|---|---|")
        for x, _ in sorted(rescuable, key=lambda t: -t[0]["demand_24h"])[:12]:
            c2 = costs.get(x["cluster"])
            if not c2:
                continue
            base, ship = c2[0], c2[1]
            fixed = base + ship + PAYMENT_FEE_FLAT + LISTING_FEE
            pct = TRANSACTION_FEE + PAYMENT_FEE_PCT + ADS_RESERVE
            L.append(f"| {x['tag']} | ${x['avg_price']} | "
                     f"${fixed / (1 - pct):.2f} | ${(fixed + 6) / (1 - pct):.2f} |")
        L.append("")

    caution = [x for x, w in rejected if "CAUTION" in (w or "")]
    if caution:
        L.append("## Chờ kiểm tra thương hiệu - trademark (2 phút/từ)")
        L.append("_Tra từng cụm tại tmsearch.uspto.gov (lọc: Live). Không có nhãn hiệu "
                 "sống trong ngành hàng -> ghi CLEAR vào tm_verified.csv kèm link. "
                 "Có -> ghi BLOCKED._")
        for x in caution[:15]:
            L.append(f"- {x['tag']}")
        L.append("")

    L.append("## Phụ lục số liệu (dành cho leader)")
    L.append("| Cluster | Verdict | Score | Keywords | Median views/day | "
             "Median listings | Conv | Avg price | Est. margin | TM-safe % |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for c in clusters:
        prof = f"${c['profit']:.2f}" if c["profit"] is not None else "?"
        L.append(f"| {c['name']} | {c['verdict']} | {c['score']} | {c['n']} | "
                 f"{int(c['demand'])} | {int(c['competition'])} | "
                 f"{c['conversion']*100:.1f}% | ${c['aov']:.0f} | {prof} | "
                 f"{int(c['safety']*100)}% |")
    L.append("")
    L.append("<details><summary>Tất cả từ khóa bị loại - bảng đầy đủ (bấm để mở)</summary>")
    L.append("")
    L.append("| Từ khóa | Views/ngày | Kết quả Etsy | Giá TB | Lý do loại |")
    L.append("|---|---|---|---|---|")
    for x, why in sorted(rejected, key=lambda t: -t[0]["demand_24h"]):
        L.append(f"| {x['tag']} | {x['demand_24h']} | {x['listing_count']} | "
                 f"${x['avg_price']} | {why} |")
    L.append("")
    L.append("</details>")
    path.write_text("\n".join(L), encoding="utf-8")
    from src.lang import finalize_report
    finalize_report(path)
    return path
