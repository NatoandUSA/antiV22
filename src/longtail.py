"""Long-tail lane — the specific phrases a small shop can actually sell.

Rank (opportunity_inbox) asks "how big is this market?", so it structurally
favours 1-2 word head terms: GO needs an overall >= 80 and the demand leg is
revenue+views, which a long-tail can never win on absolute volume. Measured on
the current master, the highest-scoring 4-word keyword reaches 73.6 — so no
long-tail is ever promoted on merit, and the only rows that reach Build now are
head terms carried there by the Etsy-proof override.

This module asks the other question: **which specific phrases are already
selling, in a market small enough to enter?** It is a VIEW — it re-reads the
rows the frozen L0-L4 engine already produced and applies its own transparent
selection. No score, verdict or action is changed anywhere.

Two hard rules, both inherited from the rest of the codebase:
  * honest-nulls — a keyword with no conversion and no revenue is EXCLUDED, not
    scored low. Absence of evidence never becomes a number.
  * unit-safe money — revenue is always read per listing (see _rev_per_listing).
"""
import math
import re

# Ranked over four legs. Money and conversion dominate because the question is
# "does this actually sell", not "is this niche big".
WEIGHTS = {"money": 0.35, "conversion": 0.30, "room": 0.20, "specific": 0.15}
PUSH, TEST, WATCH = "PUSH", "TEST", "WATCH"
MIN_WORDS = 3            # 1-2 words is the price war the engine already rejects
MAX_LISTINGS = 2000      # above this a new shop does not get seen


def words(kw):
    return len(re.findall(r"[a-z0-9]+", (kw or "").lower()))


def _rev_per_listing(row):
    """Revenue per listing, unit-safe across old and new master rows.

    harvest used to write scout_opportunities' `total_revenue_usd` (niche total)
    into the same `avg_revenue` column that trending fills with per-listing
    revenue, so an opportunity-sourced keyword read ~250x richer than an
    identical trending-sourced one. Rows written since the fix carry the niche
    total in `rev_total`; older opportunity rows still hold it in `rev`.
    """
    rev, listings = row.get("rev"), row.get("comp")
    if rev is None or rev <= 0:
        return None
    if row.get("rev_total") is None and (row.get("source") or "") == "mcp:opportunity":
        if not listings:
            return None
        return rev / listings
    return rev


def _money(rpl):
    """$25/listing -> 0, $250 -> 50, $2500 -> 100 (log — revenue spans decades)."""
    return min(100.0, max(0.0, (math.log10(rpl) - 1.4) / 2.0 * 100.0))


def _conversion(cr):
    """Same shape opportunity_score uses, so 'good conversion' means one thing
    across the app: 0-5% linear to 80, then flattening to 100."""
    if cr <= 0.05:
        return cr * 1600.0
    return 80.0 + 20.0 * (1.0 - math.exp(-25.0 * (cr - 0.05)))


def _room(listings, sellers=None):
    """How much space is left. Mirrors opportunity_score's listings-per-market
    curve, then penalises a market a few shops already own."""
    ci = max(10.0, min(95.0, -40.0 + 41.0 * math.log10(max(listings, 1.0))))
    score = 100.0 - ci
    if sellers and listings and sellers > 0 and listings / sellers >= 3:
        score *= 0.75            # 3+ listings per seller = concentrated holders
    return max(0.0, score)


def _specific(n):
    return {3: 60.0, 4: 85.0}.get(n, 100.0 if n >= 5 else 0.0)


def sellability(row, min_words=MIN_WORDS, max_listings=MAX_LISTINGS):
    """Score one inbox row, or None when it doesn't belong in this lane.

    Returns None (never a low score) when the row is short-tail, unbuildable, or
    has no sales evidence — an unmeasured keyword must not be ranked at all.
    """
    kw = row.get("keyword") or ""
    n = words(kw)
    if n < min_words:
        return None
    if not row.get("launchable") or row.get("action") in ("BLOCKED", "SKIP"):
        return None
    cr, listings = row.get("conv"), row.get("comp")
    rpl = _rev_per_listing(row)
    if not cr or cr <= 0 or rpl is None:
        return None                       # no proof it converts / earns
    if not listings or listings > max_listings:
        return None                       # no competition read, or too crowded
    parts = {"money": round(_money(rpl), 1),
             "conversion": round(_conversion(cr), 1),
             "room": round(_room(listings, row.get("sellers")), 1),
             "specific": _specific(n)}
    total = round(sum(parts[k] * w for k, w in WEIGHTS.items()), 1)
    return {"keyword": kw, "score": total, "parts": parts, "words": n,
            "rev_per_listing": round(rpl, 2), "conv": cr, "listings": listings,
            "verdict": PUSH if total >= 70 else TEST if total >= 55 else WATCH,
            "action": row.get("action"), "fit_label": row.get("fit_label"),
            "proof_tier": row.get("proof_tier", 9), "source": row.get("source"),
            "why": (f"${round(rpl):,}/listing · {cr * 100:.1f}% conv · "
                    f"{int(listings)} listings · {n} words")}


def shortlist(mode=None, min_words=MIN_WORDS, max_listings=MAX_LISTINGS,
              limit=40, q=None):
    """The lane: evidence-backed long-tails, best first. Also returns the counts
    behind the filter so the page can be honest about what it dropped."""
    from src import opportunity_inbox as oi
    data = oi.build_inbox(mode, limit=100000, show_archived=True)
    rows = data["rows"]
    if q:
        rows = oi.focus_rows(rows, q) or rows
    scored, long_rows = [], 0
    for r in rows:
        if words(r.get("keyword")) >= min_words:
            long_rows += 1
        s = sellability(r, min_words, max_listings)
        if s:
            scored.append(s)
    scored.sort(key=lambda s: -s["score"])
    return {"rows": scored[:limit], "n_scored": len(scored),
            "n_long": long_rows, "n_total": len(rows),
            "dropped_no_evidence": long_rows - len(scored)}


# ---------------------------------------------------------------- supply ----
# Where long-tails come from. YTrends' research_keyword returns the related
# long-tail tags it actually indexes WITH per-tag revenue + conversion, so these
# arrive demand-grounded and can score immediately — unlike Keyword Lab
# candidates, whose enrich path (shortlister_integration._enrich_row) fills
# conversion/listings but never revenue or views, leaving them capped at WATCH.
def pull(seeds, per_seed=10, min_words=MIN_WORDS, log=lambda s: None):
    """Ask YTrends for the long-tails related to each seed. Returns master rows.

    Network-bound and best-effort: a seed the MCP can't answer is skipped, never
    guessed. Nothing is written here — see save_rows.
    """
    from src import ytrends_mcp as mcp
    try:
        from src.trademark import check as tm_check
    except Exception:  # noqa: BLE001
        def tm_check(_):
            return ("OK", "")
    out, seen = [], set()
    for seed in seeds:
        try:
            data = mcp.research_keyword(seed) or {}
        except Exception as exc:  # noqa: BLE001 - one dead seed can't stop the run
            log(f"  {seed}: {str(exc)[:60]}")
            continue
        related = (data.get("related_keywords") or [])[:per_seed * 3]
        kept = 0
        for rk in related:
            tag = re.sub(r"\s+", " ", str(rk.get("tag") or "")).strip().lower()
            if not tag or tag in seen or words(tag) < min_words:
                continue
            if tm_check(tag)[0] == "HIGH":
                continue
            rev = rk.get("avg_revenue")
            cr = rk.get("avg_conversion_rate")
            if not rev or not cr:
                continue                   # no evidence -> don't add a dead row
            seen.add(tag)
            out.append({"keyword": tag,
                        "etsy_listings": rk.get("tag_listing_count") or "",
                        "avg_revenue": round(float(rev), 2),
                        "conversion_rate": round(float(cr), 4),
                        "source": "longtail:related", "seed": seed,
                        "lift": rk.get("lift")})
            kept += 1
            if kept >= per_seed:
                break
        log(f"  {seed}: +{kept} long-tail(s)")
    return out


def page(mode=None, q="", min_words=MIN_WORDS, limit=40):
    """The /longtail view, as markdown (rendered by web._render_tool)."""
    from urllib.parse import quote_plus as uq
    r = shortlist(mode, min_words=min_words, limit=limit, q=q or None)
    rows = r["rows"]
    L = ["# \U0001F48E Long-tail lane — what can actually sell", "",
         "_**Rank** asks how big a market is, so 1-2 word head terms win it and "
         "a long-tail can never clear the GO band on volume. This lane asks the "
         "other question: **which specific phrases are already selling, in a "
         "market small enough to enter?** Same data, same frozen engine — a "
         "different question. Ranked on money per listing, conversion, room to "
         "rank, and specificity._", ""]
    L += [f"> Scanned **{r['n_total']}** ranked keywords · **{r['n_long']}** are "
          f"{min_words}+ words · **{r['n_scored']}** carry real sales evidence "
          f"(revenue **and** conversion). The other **{r['dropped_no_evidence']}** "
          "are excluded, not down-ranked — a keyword nobody has measured is not "
          "an opportunity, it's a blank.", ""]
    if not rows:
        L += ["**Nothing qualifies yet.** Every long-tail in the base is missing "
              "revenue or conversion. Run **Pull long-tails** to fetch phrases "
              "that arrive with their own market data."]
        return "\n".join(L)
    groups = [(PUSH, "\U0001F680 Push — build these",
               "Real money per listing, converts, and few enough listings to get seen."),
              (TEST, "\U0001F9EA Test — worth one design",
               "Decent evidence, thinner margin for error. One design, then judge."),
              (WATCH, "\U0001F7E1 Keep watching", "Evidence is real but slim.")]
    for verdict, title, blurb in groups:
        part = [s for s in rows if s["verdict"] == verdict]
        if not part:
            continue
        L += [f"## {title} ({len(part)})", "", f"_{blurb}_", "",
              "| # | Keyword | $/listing | Conv | Listings | Words | Score | Fit "
              "| Engine says | Do |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for i, s in enumerate(part, 1):
            act = (s["action"] or "").replace("_", " ").title()
            proof = " ✅" if s["proof_tier"] == 0 else ""
            L.append(
                f"| {i} | **{s['keyword']}** | ${round(s['rev_per_listing']):,} "
                f"| {s['conv'] * 100:.1f}% | {int(s['listings'])} | {s['words']} "
                f"| {s['score']} | {s['fit_label'] or '—'} | {act}{proof} "
                f"| [Build](/launch-kit?q={uq(s['keyword'])}) · "
                f"[Angle](/pattern-miner?q={uq(s['keyword'])}) |")
        L.append("")
    L += ["---", "",
          "**Reading a row.** `$/listing` is revenue per listing in that niche — "
          "always per listing, never a niche total. `Conv` is the niche average "
          "conversion. `Listings` is what you'd rank against. `Engine says` is "
          "the untouched Rank verdict, shown so you can see where the two "
          "disagree: a row that says *Watch* here is one Rank rejected on volume "
          "while it was already selling."]
    return "\n".join(L)


def save_rows(rows, path="keyword_data.csv"):
    """Append new long-tails to the master, skipping ones already there.

    Writes by COLUMN NAME against the file's real header, so a master written
    before the total_revenue column still takes these rows correctly.
    """
    import csv
    from datetime import date
    from pathlib import Path
    p = Path(path)
    header, existing = None, set()
    if p.is_file():
        with p.open(encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            header = rd.fieldnames
            for r in rd:
                existing.add((r.get("keyword") or "").strip().lower())
    if not header:
        from src.harvest import KDATA_FIELDS
        header = list(KDATA_FIELDS)
        with p.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=header).writeheader()
    today = str(date.today())
    added = 0
    with p.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        for r in rows:
            kw = (r.get("keyword") or "").strip().lower()
            if not kw or kw in existing:
                continue
            existing.add(kw)
            w.writerow({c: {"keyword": kw,
                            "etsy_listings": r.get("etsy_listings", ""),
                            "avg_revenue": r.get("avg_revenue", ""),
                            "conversion_rate": r.get("conversion_rate", ""),
                            "source": r.get("source", "longtail:related"),
                            "collected_at": today}.get(c, "")
                        for c in header})
            added += 1
    return added
