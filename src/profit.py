"""Profit Center — real P&L per sale, per product / supplier / mode.

Applies the Etsy fee model, stores each sale, and feeds supplier profit back into
the learning system so future supplier scores reflect what actually earns. Stores:
data/performance/profit_center.{json,csv}. Never publishes.
"""
import csv
import json
from datetime import date
from pathlib import Path

PERF = Path("data/performance")
STORE = PERF / "profit_center.json"
CSV_STORE = PERF / "profit_center.csv"

# Etsy US fee model. Source: Etsy "Fees and Taxes for Selling on Etsy"
# (help.etsy.com/hc/en-us/articles/115014483627), verified through 2026-08-06.
# Re-check that page (and the shop's actual Payment Account) before trusting
# these rates on a date far past that.
LISTING_FEE = 0.20            # per listing / renewal
TRANSACTION_RATE = 0.065      # 6.5% of item + shipping
PAYMENT_RATE = 0.03           # ~3% ...
PAYMENT_FIXED = 0.25          # ... + $0.25 (US)
OFFSITE_ADS_RATE = 0.15       # only when the sale came from an offsite ad
CURRENCY_RATE = 0.025         # ~2.5% USD->VND payout conversion (VN shops).
                              #   Set to 0.0 if your Etsy payout account is USD.

COLS = ["record_id", "date", "keyword", "product_mode", "supplier",
        "sale_price", "product_cost", "shipping_cost", "listing_fee",
        "transaction_fee", "payment_fee", "offsite_ad_fee", "currency_fee",
        "refund_or_issue", "net_profit", "margin", "notes"]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def compute(price, product_cost, shipping_cost=0.0, offsite_ad=False,
            refunded=False):
    """Return the fee breakdown + net profit + margin for one sale."""
    price, pc, sc = _f(price), _f(product_cost), _f(shipping_cost)
    if refunded:
        # refund: you lose the product+ship cost and keep no revenue.
        net = -(pc + sc)
        return {"listing_fee": LISTING_FEE, "transaction_fee": 0.0,
                "payment_fee": 0.0, "offsite_ad_fee": 0.0, "currency_fee": 0.0,
                "net_profit": round(net, 2),
                "margin": round(net / price, 4) if price else 0.0}
    txn = TRANSACTION_RATE * (price + sc)
    pay = PAYMENT_RATE * price + PAYMENT_FIXED
    # Etsy charges offsite ads on the full order (item + shipping), not item only.
    offsite = OFFSITE_ADS_RATE * (price + sc) if offsite_ad else 0.0
    # Currency conversion applies to the whole payout (item + shipping).
    currency = CURRENCY_RATE * (price + sc)
    net = price - pc - sc - LISTING_FEE - txn - pay - offsite - currency
    return {"listing_fee": round(LISTING_FEE, 2),
            "transaction_fee": round(txn, 2), "payment_fee": round(pay, 2),
            "offsite_ad_fee": round(offsite, 2),
            "currency_fee": round(currency, 2), "net_profit": round(net, 2),
            "margin": round(net / price, 4) if price else 0.0}


def load():
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return []


def _write(rows):
    PERF.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with CSV_STORE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def add(d):
    rows = load()
    rid = max([r.get("id", 0) for r in rows], default=0) + 1
    refunded = str(d.get("refund_or_issue") or "").strip().lower() not in (
        "", "no", "none", "0", "false")
    fees = compute(d.get("sale_price"), d.get("product_cost"),
                   d.get("shipping_cost"),
                   offsite_ad=str(d.get("offsite_ad") or "").lower() in ("1", "yes", "true"),
                   refunded=refunded)
    rec = {"id": rid, "record_id": f"pf-{date.today()}-{rid}",
           "date": str(date.today()),
           "keyword": d.get("keyword", ""), "product_mode": d.get("product_mode", ""),
           "supplier": d.get("supplier", ""),
           "sale_price": _f(d.get("sale_price")),
           "product_cost": _f(d.get("product_cost")),
           "shipping_cost": _f(d.get("shipping_cost")),
           "refund_or_issue": d.get("refund_or_issue", ""),
           "notes": d.get("notes", ""), **fees}
    rows.append(rec)
    _write(rows)
    # feed supplier profit into the learning system
    try:
        from src import learning
        sp = learning._load("supplier")
        learning._bump(sp["suppliers"], rec["supplier"],
                       net_profit_cents=int(rec["net_profit"] * 100),
                       sales=1)
        learning._save("supplier", sp)
    except Exception:  # noqa: BLE001
        pass
    return rec


def summary():
    rows = load()
    by_sup, by_mode = {}, {}
    total = 0.0
    for r in rows:
        total += _f(r.get("net_profit"))
        s = by_sup.setdefault(r.get("supplier") or "?",
                              {"sales": 0, "net": 0.0, "margin_sum": 0.0})
        s["sales"] += 1
        s["net"] += _f(r.get("net_profit"))
        s["margin_sum"] += _f(r.get("margin"))
        m = by_mode.setdefault(r.get("product_mode") or "?",
                               {"sales": 0, "net": 0.0})
        m["sales"] += 1
        m["net"] += _f(r.get("net_profit"))
    for s in by_sup.values():
        s["avg_margin"] = round(s["margin_sum"] / s["sales"], 4) if s["sales"] else 0
        s["net"] = round(s["net"], 2)
    for m in by_mode.values():
        m["net"] = round(m["net"], 2)
    return {"sales": len(rows), "net_total": round(total, 2),
            "by_supplier": by_sup, "by_mode": by_mode}
