"""Build Queue (V36) — turn the noisy 1,000+ keyword base into a short, ranked
"make these next" list, straight from keyword_data.csv.

Why this exists: the base is ~5% gold, ~95% noise. Half the rows carry NO real
Etsy market data (listings/views/revenue all zero) — that is "unknown", not
"low competition", so building on them is guessing. This module:

  1. classifies every keyword  PROVEN / PARTIAL / UNVERIFIED  by real signal,
  2. scores the PROVEN buildable rows with a transparent Build Score,
  3. flags trademark risk (⚠) so risky terms never reach a designer clean,
  4. routes each pick to the Design Analyzer + Launch Kit in one click,
  5. remembers what's already been actioned so nobody repeats work,
  6. can archive the all-empty rows so the base stops looking bigger than it is.

It is READ-mostly: the only writes are the tiny actioned ledger and the opt-in
archive. It never changes the ranking-engine math (that stays frozen); Build
Score is a separate, clearly-labelled surfacing score.
"""
import csv
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path

MASTER = Path("keyword_data.csv")
ARCHIVE = Path("data/keyword_archive.csv")
ACTIONED = Path("data/build_actioned.csv")

# buildable gate (matches the analysis the owner signed off on)
MAX_LISTINGS = 300      # above this = too crowded for a fast win
MIN_PRICE = 8.0         # below this = thin margin for POD/embroidery

_THEMES = [
    ("Personalized", ("custom", "personali", "monogram", "name", "text", "face")),
    ("Family / role", ("grandpa", "grandma", "mom", "dad", "papa", "nana", "mama",
                       "son", "daughter", "family", "kids", "wife", "husband",
                       "uncle", "aunt")),
    ("Apparel", ("shirt", "tee", "hoodie", "sweatshirt", "sock", "cap", "hat",
                 "crewneck")),
    ("Bag / accessory", ("bag", "pouch", "tote", "mirror", "koozie", "keychain")),
    ("Occasion", ("birthday", "graduation", "christmas", "halloween", "anniversary",
                  "wedding", "retirement", "celebration", "valentine", "4th of july",
                  "fathers day", "mothers day")),
]


def _num(v, default=0.0):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _theme(kw):
    k = kw.lower()
    for name, needles in _THEMES:
        if any(n in k for n in needles):
            return name
    return "Other"


def _tm_level(kw):
    try:
        from src import trademark as tm
        return (tm.check(kw) or ("OK", ""))[0]
    except Exception:  # noqa: BLE001
        return "OK"


def _load_master(path=None):
    p = Path(path) if path else MASTER
    rows = []
    if not p.is_file():
        return rows
    with p.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            kw = (r.get("keyword") or "").strip()
            if kw:
                rows.append(r)
    return rows


# The two end states a keyword can reach. DONE means "we finished working it"
# (designed, or decided against). PUBLISHED_MANUALLY means the owner actually put
# the listing live on Etsy BY HAND — the tool never publishes, so this is the
# only way that fact can enter the system.
DONE, PUBLISHED = "DONE", "PUBLISHED_MANUALLY"
# Post-launch review points. Day 3 = is it getting impressions at all.
# Day 7 = enough signal to keep, re-tag, or kill.
CHECK_DAYS = (3, 7)

# Appended columns are optional on read, so rows written before this existed
# (keyword,user,ts) still load — they simply read as DONE with no checks due.
_FIELDS = ["keyword", "user", "ts", "status", "listing_url",
           "check_day3", "check_day7"]


def load_actioned():
    done = {}
    if not ACTIONED.is_file():
        return done
    try:
        with ACTIONED.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                k = (r.get("keyword") or "").strip().lower()
                if not k:
                    continue
                # last write wins: a keyword marked DONE then PUBLISHED ends
                # PUBLISHED, because the file is an append-only ledger
                done[k] = {"user": r.get("user", ""), "ts": r.get("ts", ""),
                           "status": (r.get("status") or DONE).strip() or DONE,
                           "listing_url": (r.get("listing_url") or "").strip(),
                           "check_day3": (r.get("check_day3") or "").strip(),
                           "check_day7": (r.get("check_day7") or "").strip()}
    except OSError:
        pass
    return done


def mark_done(keyword, user="", status=DONE, listing_url=""):
    """Append an end state for a keyword. Never rewrites, never deletes.

    PUBLISHED_MANUALLY also stamps the day-3 and day-7 review dates, so the
    follow-up is scheduled by the act of publishing rather than remembered.
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return False
    status = (status or DONE).strip().upper()
    if status not in (DONE, PUBLISHED):
        status = DONE
    checks = {}
    if status == PUBLISHED:
        today = date.today()
        for d in CHECK_DAYS:
            checks[f"check_day{d}"] = str(today + timedelta(days=d))
    ACTIONED.parent.mkdir(parents=True, exist_ok=True)
    new = not ACTIONED.is_file()
    with ACTIONED.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({"keyword": keyword, "user": (user or "")[:60],
                    "ts": time.strftime("%Y-%m-%d %H:%M"), "status": status,
                    "listing_url": (listing_url or "")[:300], **checks})
    return True


def follow_ups(today=None):
    """[(keyword, day, due_date)] for published listings whose review is due.

    Read-only. Nothing schedules itself or nags — this is the list the owner
    looks at, so a launch cannot quietly go unreviewed.
    """
    now = today or date.today()
    if isinstance(now, str):
        now = date.fromisoformat(now[:10])
    out = []
    for kw, rec in load_actioned().items():
        if rec.get("status") != PUBLISHED:
            continue
        for d in CHECK_DAYS:
            due = rec.get(f"check_day{d}") or ""
            if not due:
                continue
            try:
                when = date.fromisoformat(due)
            except ValueError:
                continue
            if when <= now:
                out.append((kw, d, due))
    return sorted(out, key=lambda x: (x[2], x[1]))


def _classify(r):
    li = _num(r.get("etsy_listings"))
    vi = _num(r.get("views_24h"))
    rev = _num(r.get("avg_revenue"))
    cv = _num(r.get("conversion_rate"))
    if li > 0 and vi > 0 and rev > 0 and cv > 0:
        return "PROVEN"
    if li > 0 or vi > 0 or rev > 0:
        return "PARTIAL"
    return "UNVERIFIED"


def analyze(path=None, source=None):
    """Return the full picture: counts, the ranked buildable queue, and the
    reasons. Pure read — no side effects. source='mine' ALSO folds in the
    listing-mined keyword candidates from the store (keywords YTuong doesn't
    have), so the queue reflects your own research, not just the on-disk base."""
    rows = _load_master(path)
    if source == "mine":
        try:
            from src import data_store as _ds
            seen = {(r.get("keyword") or "").strip().lower() for r in rows}
            for mr in _ds.master_rows(mined_only=True):
                if (mr.get("keyword") or "").strip().lower() not in seen:
                    rows.append(mr)
        except Exception:  # noqa: BLE001
            pass
    total = len(rows)
    actioned = load_actioned()
    proven, partial, unverified = [], [], []
    for r in rows:
        cls = _classify(r)
        rec = {
            "keyword": r["keyword"].strip(),
            "listings": int(_num(r.get("etsy_listings"))),
            "sellers": int(_num(r.get("seller_count"))),
            "views": int(_num(r.get("views_24h"))),
            "price": round(_num(r.get("avg_price")), 2),
            "revenue": round(_num(r.get("avg_revenue")), 2),
            "conv": _num(r.get("conversion_rate")),
            "momentum": round(_num(r.get("momentum")), 1),
            "source": r.get("source", ""),
            "class": cls,
        }
        (proven if cls == "PROVEN" else partial if cls == "PARTIAL"
         else unverified).append(rec)

    # ---- Build Score on the PROVEN set (transparent, min-max within set) ----
    def _mm(vals):
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        return lambda x: (x - lo) / span

    buildable = []
    if proven:
        z_dem = _mm([math.log1p(p["views"]) for p in proven])
        z_cv = _mm([p["conv"] for p in proven])
        z_pr = _mm([min(p["price"], 60) for p in proven])
        z_mo = _mm([p["momentum"] for p in proven])
        z_li = _mm([math.log1p(p["listings"]) for p in proven])
        for p in proven:
            score = (0.30 * z_dem(math.log1p(p["views"]))
                     + 0.20 * z_cv(p["conv"])
                     + 0.15 * z_pr(min(p["price"], 60))
                     + 0.15 * z_mo(p["momentum"])
                     + 0.20 * (1 - z_li(math.log1p(p["listings"]))))
            p["build_score"] = round(100 * score, 1)
            p["theme"] = _theme(p["keyword"])
            p["tm"] = _tm_level(p["keyword"])
            rec = actioned.get(p["keyword"].lower())
            p["done"] = rec is not None
            if rec:
                p.update({k: rec.get(k, "") for k in
                          ("status", "listing_url", "check_day3", "check_day7")})
            # buildable = proven, not too crowded, real margin, not a hard TM hit
            if (p["listings"] <= MAX_LISTINGS and p["price"] >= MIN_PRICE
                    and p["tm"] != "HIGH"):
                buildable.append(p)
    buildable.sort(key=lambda p: p["build_score"], reverse=True)

    open_q = [p for p in buildable if not p["done"]]
    done_q = [p for p in buildable if p["done"]]
    caution = sum(1 for p in buildable if p["tm"] == "CAUTION")
    return {
        "total": total,
        "counts": {"proven": len(proven), "partial": len(partial),
                   "unverified": len(unverified)},
        "buildable": buildable, "open": open_q, "done": done_q,
        "caution": caution,
    }


def archive_empties(path=None):
    """Move the all-empty (UNVERIFIED) rows out of the base into the archive
    file, so the base reflects real, usable size. Reversible: nothing is
    deleted, just relocated. Returns (moved, kept)."""
    p = Path(path) if path else MASTER
    if not p.is_file():
        return 0, 0
    with p.open(encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        fields = rdr.fieldnames or []
        keep, move = [], []
        for r in rdr:
            (move if _classify(r) == "UNVERIFIED" else keep).append(r)
    if not move:
        return 0, len(keep)
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    arch_new = not ARCHIVE.is_file()
    with ARCHIVE.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if arch_new:
            w.writeheader()
        w.writerows(move)
    tmp = p.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(keep)
    os.replace(tmp, p)
    return len(move), len(keep)


# ---- HTML render (kept here so web.py stays a thin route) -------------------
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _pct(x):
    return f"{100 * x:.1f}%"


def _kfmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(int(n))


def _ages(picks):
    """Batched freshness for the queue -> a per-row formatter. One DB read for
    the whole table, not one per row."""
    from src import freshness as fr
    try:
        labels = fr.labels_for([p.get("keyword") for p in picks or []])
    except Exception:  # noqa: BLE001 - the column never breaks the queue
        labels = {}
    return lambda p: labels.get(p.get("keyword"), fr.NEW)


def _row_html(i, p, csrf, age=None):
    tmbadge = ""
    if p["tm"] == "CAUTION":
        tmbadge = ('<span class="pill" style="background:#fef3c7;color:#92400e">'
                   '⚠ verify TM</span> ')
    donecls = ' style="opacity:.5"' if p["done"] else ""
    kw = _esc(p["keyword"])
    if p["done"]:
        st = (p.get("status") or DONE)
        if st == PUBLISHED:
            due = " · ".join(f"day {d} {p.get('check_day%d' % d)}"
                             for d in CHECK_DAYS if p.get("check_day%d" % d))
            action = ('<span class="note">🏷 published manually'
                      + (f'<br>review: {_esc(due)}' if due else "") + '</span>')
        else:
            action = '<span class="note">✅ done</span>'
    else:
        def _mark(status, label, title, cls=""):
            return (f'<form method="post" action="/build-queue/done" '
                    'style="display:inline">'
                    f'<input type="hidden" name="csrf" value="{csrf}">'
                    f'<input type="hidden" name="keyword" value="{kw}">'
                    f'<input type="hidden" name="status" value="{status}">'
                    f'<button class="tkbtn {cls}" title="{title}">{label}'
                    '</button></form> ')
        action = (
            f'<a class="tkbtn" href="/design-analyzer?q={kw}" '
            'title="Analyze / design this">🎨 Design</a> '
            f'<a class="tkbtn" href="/launch-kit?q={kw}" '
            'title="Full launch kit">🚀 Kit</a> '
            # PUBLISHED_MANUALLY is the only way the tool learns a listing went
            # live: it never publishes, so the owner records the fact by hand.
            + _mark(PUBLISHED, "🏷 Published",
                    "I published this on Etsy myself — schedules day 3 / day 7 review",
                    "primary")
            + _mark(DONE, "✓", "Mark done (worked, not published)"))
    fresh = age(p) if age else ""
    return (
        f'<tr{donecls}><td>{i}</td>'
        f'<td><b>{kw}</b> {tmbadge}<br>'
        f'<span class="note">{_esc(p["theme"])}</span></td>'
        f'<td><span class="note">{_esc(fresh)}</span></td>'
        f'<td><b>{p["build_score"]}</b></td>'
        f'<td>{p["listings"]}</td>'
        f'<td>{_kfmt(p["views"])}</td>'
        f'<td>${p["price"]:.2f}</td>'
        f'<td>{_pct(p["conv"])}</td>'
        f'<td>{p["momentum"]}</td>'
        f'<td>{action}</td></tr>')


def render_html(data, csrf, limit=40):
    c = data["counts"]
    total = data["total"]
    prov = c["proven"]
    head = (
        '<article class="md"><h1>🎯 Build Queue — make these next</h1>'
        '<p class="tklead">Straight from your keyword base. Only <b>PROVEN</b> '
        'keywords (real listings + views + revenue + conversion) are ranked here '
        '— building on empty rows is guessing. Score, competition and trademark '
        'risk are shown so a pick is safe before anyone designs it.</p>'
        f'<p>Base: <b>{total}</b> keywords · '
        f'<b style="color:#15803d">{prov}</b> proven '
        f'({_pct(prov/total) if total else "0%"}) · '
        f'<span style="color:#a16207">{c["partial"]}</span> partial · '
        f'<span style="color:#999">{c["unverified"]}</span> empty · '
        f'<b>{len(data["open"])}</b> to build · '
        f'<b>{len(data["done"])}</b> done.</p>')

    if not data["buildable"]:
        return (head + '<p class="empty">No proven buildable keywords yet — run '
                'the MCP harvest (or import a YTrends <b>keyword</b> table) to add '
                'real market numbers, then refresh.</p></article>')

    thead = ('<table><tr><th>#</th><th>Keyword / theme</th><th>Added</th>'
             '<th>Build&nbsp;Score</th>'
             '<th>Listings</th><th>Views&nbsp;24h</th><th>Price</th>'
             '<th>Conv</th><th>Momentum</th><th>Action</th></tr>')
    # one lookup covering both tables below
    age = _ages(list(data["open"][:limit]) + list(data["done"]))
    open_rows = "".join(_row_html(i + 1, p, csrf, age)
                        for i, p in enumerate(data["open"][:limit]))
    # Post-launch reviews that are due. A launch nobody reviews is how a bad
    # listing sits live for a month, so this rides above the queue.
    due = ""
    try:
        pend = follow_ups()
        if pend:
            items = " · ".join(f"<b>{_esc(k)}</b> day {d}" for k, d, _t in pend[:8])
            due = ('<p class="note" style="background:var(--accent-bg);'
                   'border:1px solid var(--accent);border-radius:9px;'
                   f'padding:9px 12px">📅 <b>Post-launch review due:</b> {items}'
                   ' — check impressions/views, then keep, re-tag, or kill.</p>')
    except Exception:  # noqa: BLE001 - never break the queue
        due = ""
    body = (due + '<h2>🔨 To build (top ' + str(min(limit, len(data["open"]))) +
            ')</h2>' + thead + open_rows + '</table>')
    if len(data["open"]) > limit:
        body += (f'<p class="note">+{len(data["open"]) - limit} more buildable '
                 'below the top ' + str(limit) + '. Mark some done to surface them.</p>')

    if data["done"]:
        done_rows = "".join(_row_html(i + 1, p, csrf, age)
                            for i, p in enumerate(data["done"]))
        body += ('<details class="archive"><summary>✅ Done (' +
                 str(len(data["done"])) + ')</summary>' + thead + done_rows +
                 '</table></details>')

    # maintenance: archive the empty rows (item #3)
    maint = ('<details class="archive"><summary>🧹 Base maintenance</summary>'
             f'<p class="note">Your base has <b>{c["unverified"]}</b> empty '
             'keywords (no listings/views/revenue). Archiving moves them to '
             '<code>data/keyword_archive.csv</code> (reversible) so the base '
             'reflects real usable size. They come back the next time the MCP '
             'harvest finds real numbers for them.</p>'
             '<form method="post" action="/build-queue/archive-empties">'
             f'<input type="hidden" name="csrf" value="{csrf}">'
             '<button class="tkbtn" '
             f'onclick="return confirm(\'Archive {c["unverified"]} empty '
             'keywords?\')">Archive empty keywords</button></form></details>')

    legend = ('<p class="note"><b>Build Score</b> blends demand (views), '
              'conversion, price, momentum and low competition into one 0–100 '
              'number — higher = faster, safer win. <b>⚠ verify TM</b> = check '
              'the trademark before designing.</p>')
    return head + body + maint + legend + '</article>'
