"""Team report portal for the Etsy Product Manager.

  python main.py web            -> serves http://127.0.0.1:8000

A read-only, login-gated portal where the team reads the latest reports. The
reports are built on the operator's laptop and synced here (see DEPLOY_VPS.md) —
this server only *serves* them, it never runs commands or fetches data. That
keeps it simple for the team and leaves no command-execution surface on the
public URL.

Login uses WEB_PASSWORD from .env; the app refuses to start without one. To
share with the team, run it behind a Cloudflare Tunnel — the login is the gate.
Reuses the burnt-amber "Command Card" palette so the app and the printed cheat
sheet feel like one tool.
"""
import os
import sys
from functools import wraps
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "reports" / "latest"

# The five daily reports, in reading order.
REPORTS = [
    ("00", "00_START_HERE.md", "Start here",
     "Today's status and your top actions. Read this first."),
    ("01", "01_MANAGER_ACTION_REPORT.md", "Manager Action Report",
     "Verdicts (design / validate / skip), blockers, and the publish gate."),
    ("02", "02_MARKET_KEYWORD_OPPORTUNITY_REPORT.md", "Market & Keyword Opportunity",
     "Ranked keywords, fresh ideas, and the best niches to chase."),
    ("03", "03_SELLER_EXECUTION_REPORT.md", "Seller Execution",
     "Draft titles, 13 tags, QA. Drafts only, never auto-published."),
    ("04", "04_DESIGNER_BRIEF_REPORT.md", "Designer Brief",
     "Design briefs + copy-paste prompts for each approved product."),
]

# Detailed reports each `daily` run also produces, mirrored to reports/latest
# under canonical names. Shown when present.
DETAIL_REPORTS = [
    ("market_pulse.md", "Market Pulse (live)",
     "What's hot RIGHT NOW from the live YTrends index — trending keywords, "
     "hidden gems, winning listings, seasonal calendar, cross-checked vs Google."),
    ("research_report.md", "Research Report",
     "Everything for this line in one place: ideas + analysis + discover + performance."),
    ("manager_report.md", "Manager Report (full)",
     "The complete manager report — 12 sections, profit model, audit."),
    ("ideas_report.md", "Best Ideas",
     "Product clusters, verdicts, and a 7-day validation plan."),
    ("discover_report.md", "Discover / Niches",
     "Rising, low-competition niches worth researching."),
    ("seller_pack.md", "Seller Pack (full)",
     "Every listing field in Etsy's paste order (drafts only)."),
    ("design_prompts.md", "Design Prompts (Claude)",
     "Copy-paste design briefs for Claude / Claude Design."),
    ("chatgpt_prompts.md", "ChatGPT Image Prompts",
     "One-image-per-message prompts for the ChatGPT app."),
    ("listing_pack.md", "Listing Pack",
     "A full listing draft for the top clean keyword."),
    ("daily_tasks.md", "Daily Tasks",
     "What each role should do today."),
    ("blocker_report.md", "Blockers",
     "What's blocking progress, grouped by severity."),
    ("product_status_board.md", "Status Board",
     "Product-by-product status at a glance."),
    ("final_qa.md", "Final QA", "Pre-publish QA summary."),
    ("performance_report.md", "Performance",
     "Shop performance from shop_performance.csv."),
]


def _last_updated(mdir):
    info = Path(mdir) / "_run_info.txt"
    if info.exists():
        lines = info.read_text(encoding="utf-8").splitlines()
        if len(lines) >= 2 and lines[1].strip():
            return lines[1].strip()
    return None


def _available_modes():
    """Report sets the team sees: Print on Demand + Embroidery only.

    The 'all keywords' root set is intentionally NOT surfaced — All and POD were
    near-identical, so the tab only added noise. Each production line gets its own
    focused, data-driven set."""
    modes = []
    for key, label in (("pod", "Print on Demand"), ("embroidery", "Embroidery")):
        if (LATEST / key / "00_START_HERE.md").exists():
            modes.append((key, label, key + "/"))
    return modes


def build_app(password, secret):
    from flask import (Flask, session, request, redirect, url_for,
                       abort, Response)
    import markdown as md

    app = Flask(__name__)
    app.secret_key = secret

    def login_required(fn):
        @wraps(fn)
        def wrap(*a, **k):
            if not session.get("ok"):
                return redirect(url_for("login"))
            return fn(*a, **k)
        return wrap

    def page(title, body):
        return Response(BASE.replace("{{TITLE}}", title)
                        .replace("{{BODY}}", body), mimetype="text/html")

    def _safe_report(name):
        """Return an existing file inside reports/latest, or None."""
        p = (LATEST / name).resolve()
        if LATEST.resolve() not in p.parents or not p.is_file():
            return None
        return p

    # ---- auth ----
    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        if request.method == "POST":
            if request.form.get("password", "") == password:
                session["ok"] = True
                return redirect(url_for("index"))
            error = '<p class="err">Wrong password.</p>'
        return page("Sign in", LOGIN.replace("{{ERROR}}", error))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ---- public privacy policy (NO login_required: reviewers/APIs must reach it) ----
    @app.route("/privacy")
    def privacy():
        return page("Privacy Policy", PRIVACY)

    def _card(sub, fname, badge, title, desc):
        return (f'<a class="report" href="/report/{sub}{fname}">'
                f'<span class="rid">{badge}</span>'
                f'<span class="rmeta"><span class="rt">{title}</span>'
                f'<span class="rd">{desc}</span></span>'
                f'<span class="ractions">'
                f'<span class="btn">Read &rarr;</span></span></a>')

    # ---- report list ----
    @app.route("/")
    @login_required
    def index():
        # The Command Center + live tools are MCP-backed and operator-independent,
        # so they ALWAYS render — even on a fresh deploy before the first report
        # sync. Only the (optional) daily-report archive depends on synced modes.
        modes = _available_modes()
        keys = [m[0] for m in modes]
        active = request.args.get("mode", "")
        if active not in keys:
            active = keys[0] if keys else "pod"
        sub = {m[0]: m[2] for m in modes}.get(active, "")
        mdir = LATEST / sub if sub else LATEST

        tabs = ""
        if len(modes) > 1:
            tabs = '<div class="tabs">' + "".join(
                f'<a class="tab{" on" if m[0] == active else ""}" '
                f'href="/?mode={m[0]}">{m[1]}</a>' for m in modes) + "</div>"

        daily = [_card(sub, f, rid, t, d) for rid, f, t, d in REPORTS
                 if modes and (mdir / f).exists()]
        detail = [_card(sub, f, "&bull;", t, d) for f, t, d in DETAIL_REPORTS
                  if modes and (mdir / f).exists()]
        active_label = ({m[0]: m[1] for m in modes}.get(active, active)
                        if modes else "Print on Demand")
        # --- Instant Product Command Center: one keyword -> full workspace ---
        tools = (
            '<h2 class="grouph">⚡ Instant Product Command Center</h2>'
            '<p class="lead">Type one keyword and build the whole opportunity — '
            '<b>verdict, scores, listing, design & action plan</b> — on one page. '
            'No waiting on the operator.</p>'
            '<form class="cmdbar" method="get" action="/run">'
            '<div class="modetoggle"><span>Product mode</span>'
            '<label><input type="radio" name="supplier_type" value="pod" checked>'
            ' Print on Demand</label>'
            '<label><input type="radio" name="supplier_type" value="embroidery">'
            ' Embroidery</label>'
            '<label><input type="radio" name="supplier_type" value="both">'
            ' Both</label></div>'
            '<div class="kwrow">'
            '<input name="q" aria-label="keyword" '
            'placeholder="Main keyword, e.g. usa raccoon shirt">'
            '<button class="primary" type="submit">Build full workspace →</button>'
            '</div>'
            '<div class="cmdopts">'
            '<input name="product_type" placeholder="Product type (optional)">'
            '<input name="niche" placeholder="Niche">'
            '<input name="target_customer" placeholder="Target customer">'
            '<input name="occasion" placeholder="Occasion">'
            '<input name="style" placeholder="Style">'
            '<input name="personalization" placeholder="Personalization">'
            '</div>'
            '<div class="cmdbtns">'
            '<button formaction="/analyze" name="do" value="analyze">Analyze</button>'
            '<button formaction="/analyze" name="do" value="expand">Expand</button>'
            '<button formaction="/should-sell">Should I sell?</button>'
            '<button formaction="/draft-listing">Build listing</button>'
            '<button formaction="/spy">🕵️ Spy</button>'
            '</div></form>'
            '<div class="toolgrid">'
            f'<a class="toolcard" href="/trending?mode={active}"><b>📈 Trending now'
            f'</b><span>Rising keywords in {active_label}</span></a>'
            f'<a class="toolcard" href="/opportunities?mode={active}"><b>💎 '
            'Opportunities</b><span>Low-competition sweet spots</span></a>'
            f'<a class="toolcard" href="/spy?mode={active}"><b>🕵️ Spy</b>'
            '<span>Mode-aware: who wins + can we make it in this mode</span></a>'
            f'<a class="toolcard" href="/calendar?mode={active}"><b>📅 Seasonal calendar</b>'
            '<span>Upcoming holidays + launch-by dates + keywords</span></a>'
            '<a class="toolcard" href="/research"><b>🔬 Saved research</b>'
            '<span>Past keyword lookups</span></a>'
            '<a class="toolcard" href="/shops"><b>🏪 Saved shops</b>'
            '<span>Auto-pull new shops already selling (&lt; 1yr, high CR)</span></a>'
            '<a class="toolcard" href="/listings"><b>📌 Saved listings</b>'
            '<span>Auto-pull young winners (&lt; 3mo, high CR/views/favs)</span></a>'
            '<a class="toolcard" href="/suppliers"><b>🏭 Suppliers</b>'
            '<span>Catalogs + ShineOn/Embroidery CSV upload</span></a>'
            '<a class="toolcard" href="/feedback"><b>📉 Sales feedback</b>'
            '<span>Post-launch: keep / change / kill / scale</span></a>'
            '<a class="toolcard" href="/grade"><b>📝 Grade my listing</b>'
            '<span>Paste a title + 13 tags + description → 0–100 + fixes</span></a>'
            '<a class="toolcard" href="/cheatsheet"><b>📖 Cheat Sheet</b>'
            '<span>Every command + workflow, in plain English</span></a>'
            '</div>')

        # Operator's daily reports kept reachable, but tucked away — the
        # Command Center above is the main workflow (no big Archive card).
        arch = ""
        if daily or detail:
            arch = ('<details class="archive"><summary>Operator daily reports '
                    '&amp; saved runs</summary>' + tabs
                    + ('<div class="reports">' + "".join(daily) + "</div>" if daily else "")
                    + ('<div class="reports">' + "".join(detail) + "</div>" if detail else "")
                    + '</details>')
        body = tools + arch
        upd = _last_updated(mdir)
        updated = f'<span class="updated">Updated {upd}</span>' if upd else ""
        return page("Reports", PORTAL
                    .replace("{{UPDATED}}", updated)
                    .replace("{{BODY}}", body))

    # ---- single report (name may include a pod/ or embroidery/ prefix) ----
    @app.route("/report/<path:name>")
    @login_required
    def report(name):
        p = _safe_report(name)
        if not p or p.suffix != ".md":
            abort(404)
        html = md.markdown(p.read_text(encoding="utf-8"),
                           extensions=["tables", "fenced_code", "sane_lists"])
        base = name.rsplit("/", 1)[-1]
        sub = name[:-len(base)]           # "" or "pod/" / "embroidery/"
        titles = {f: t for _, f, t, _ in REPORTS}
        titles.update({f: t for f, t, _ in DETAIL_REPORTS})
        title = titles.get(base, base)
        back = f'/?mode={sub.rstrip("/") or "all"}'
        bar = (f'<div class="rbar"><a class="back" href="{back}">&larr; All '
               f'reports</a></div>')
        return page(title, bar + f'<article class="md">{html}</article>' + COPY_JS)

    # ---- INTERACTIVE: a teammate types a keyword and gets a live answer ----
    @app.route("/analyze")
    @login_required
    def analyze():
        import html as _html
        raw = (request.args.get("q") or "").strip()[:80]
        do = "expand" if request.args.get("do") == "expand" else "analyze"
        # keep it a plain keyword (defensive; MCP args are JSON, not shell)
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        val = _html.escape(q)
        form = (
            '<form method="get" action="/analyze" '
            'style="display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0">'
            f'<input name="q" value="{val}" autofocus '
            'placeholder="Type a keyword, e.g. custom dad shirt" '
            'style="flex:1;min-width:220px;padding:.6rem .8rem;'
            'border:1px solid #d9c9a8;border-radius:8px;font-size:1rem">'
            '<button name="do" value="analyze" style="padding:.6rem 1rem;'
            'border:0;border-radius:8px;background:#b45309;color:#fff;'
            'font-weight:600;cursor:pointer">Analyze</button>'
            '<button name="do" value="expand" style="padding:.6rem 1rem;'
            'border:1px solid #b45309;border-radius:8px;background:#fff;'
            'color:#b45309;font-weight:600;cursor:pointer">Expand</button>'
            '</form>')
        head = ('<div class="rbar"><a class="back" href="/">&larr; All '
                'reports</a></div><article class="md"><h1>Analyze a keyword</h1>'
                '<p>Type any keyword for a live market read — demand, price, '
                'competition, and related ideas. Anyone on the team can run '
                'this; no waiting on the operator.</p>' + form + '</article>')
        results = ""
        if q:
            from src import interactive
            try:
                txt = (interactive.expand_keyword(q) if do == "expand"
                       else interactive.analyze_keyword(q))
                results = ('<article class="md">'
                           + md.markdown(txt, extensions=["tables",
                                         "fenced_code", "sane_lists"])
                           + '</article>' + COPY_JS)
            except SystemExit as exc:
                results = ('<article class="md"><p class="empty">The live data '
                           f'source is unavailable right now: {_html.escape(str(exc)[:200])}'
                           '</p></article>')
            except (SystemExit, Exception) as exc:  # noqa: BLE001
                results = ('<article class="md"><p class="empty">Could not '
                           f'analyze "{val}": {_html.escape(str(exc)[:200])}'
                           '</p></article>')
        return page("Analyze a keyword", head + results)

    # ---- KEYWORD RUN WORKSPACE: one keyword -> the whole opportunity ----
    _OPT_FIELDS = ("product_type", "niche", "target_customer", "occasion",
                   "style", "personalization", "supplier_type")

    def _run_inputs():
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        opts = {k: (request.args.get(k) or "").strip()[:60] for k in _OPT_FIELDS}
        return q, opts

    @app.route("/run")
    @login_required
    def run():
        import html as _html
        q, opts = _run_inputs()
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        if not q:
            return page("Keyword Run", bar + '<article class="md"><h1>Keyword Run '
                        'Workspace</h1><p class="empty">Type a keyword in the '
                        'Command Center on the <a href="/">home page</a>.</p>'
                        '</article>')
        from src import workspace
        try:
            ws = workspace.build_workspace(q, opts)
        except SystemExit as exc:
            return page("Keyword Run", bar + '<article class="md"><p class="empty">'
                        f'Live data unavailable: {_html.escape(str(exc)[:200])}'
                        '</p></article>')
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return page("Keyword Run", bar + '<article class="md"><p class="empty">'
                        f'Could not build the workspace for "{_html.escape(q)}": '
                        f'{_html.escape(str(exc)[:200])}</p></article>')
        head = (bar + f'<h1 style="margin:.1em 0 0">Keyword run — '
                f'{_html.escape(q)}</h1>')
        return page(f"Run: {q}", head + ws + WORKSPACE_JS)

    @app.route("/run/save")
    @login_required
    def run_save():
        import html as _html
        q, opts = _run_inputs()
        from src import workspace
        back = "/run?" + workspace.save_qs(q, opts) if q else "/"
        try:
            ws = workspace.build_workspace(q, opts)
            folder = workspace.save_run(q, opts, ws)
            msg = (f'Saved to <code>{_html.escape(str(folder))}</code>. It will '
                   'sync/appear under Reports.')
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            msg = f'Could not save: {_html.escape(str(exc)[:200])}'
        return page("Run saved",
                    f'<div class="rbar"><a class="back" href="{back}">&larr; Back '
                    f'to run</a></div><article class="md"><h1>Run saved</h1>'
                    f'<p>{msg}</p></article>')

    @app.route("/run/export/<role>")
    @login_required
    def run_export(role):
        import html as _html
        if role not in ("manager", "seller", "designer", "researcher"):
            abort(404)
        q, opts = _run_inputs()
        from src import workspace
        if not q:
            body = "<h1>Export</h1><p>No keyword — start a run first.</p>"
        else:
            try:
                G = workspace.run_data(q, opts)
                body = workspace.ROLE_REPORTS[role](G)
            except (SystemExit, Exception) as exc:  # noqa: BLE001
                body = (f"<h1>{role.title()} report</h1><p>Could not build it: "
                        f"{_html.escape(str(exc)[:200])}</p>")
        title = _html.escape(f"{role.title()} report — {q}")
        return Response(PRINT_BASE.replace("{{TITLE}}", title)
                        .replace("{{BODY}}", body), mimetype="text/html")

    # ---- Saved Shops + Saved Listings: competitor LEARNING library ----
    def _score_inputs(names):
        return ('<div class="scores">' + "".join(
            f'<label class="sc"><span>{n}</span><input type="number" min="0" '
            f'max="100" name="score_{n}"></label>' for n in names) + '</div>')

    def _parse_scores(names):
        out = {}
        for n in names:
            v = (request.form.get(f"score_{n}") or "").strip()
            if v.isdigit():
                out[n] = max(0, min(100, int(v)))
        return out

    def _pull_bar(endpoint, label, sub):
        return (
            '<div class="pullbar"><div class="pulltxt">'
            f'<b>⚡ Auto-pull {label} from the live index</b><span>{sub}</span></div>'
            '<div class="pullbtns">'
            f'<a class="pullbtn" href="/{endpoint}?mode=pod">Print on Demand</a>'
            f'<a class="pullbtn" href="/{endpoint}?mode=embroidery">Embroidery</a>'
            f'<a class="pullbtn primary" href="/{endpoint}">All lines</a>'
            '</div></div>')

    def _pull_banner():
        import html as _h
        p = request.args.get("pulled")
        if p is None:
            return ""
        t = _h.escape(str(request.args.get("total", p)))
        return (f'<div class="pullnote">✓ Auto-pulled <b>{t}</b> from the live '
                f'index · <b>{_h.escape(str(p))}</b> new (rest refreshed). '
                'Ranked below — study structure, never copy.</div>')

    def _chips(pairs):
        return ('<div class="chips">'
                + "".join(f'<span class="chip">{a}</span>' for a in pairs)
                + '</div>')

    @app.route("/shops")
    @login_required
    def shops():
        import html as _h
        from src import saved
        opts = "".join(f"<option>{s}</option>" for s in saved.SHOP_STATUS)
        form = (
            '<form class="savedform" method="post" action="/shops/add">'
            '<input name="shop_name" placeholder="Shop name" required>'
            '<input name="shop_url" placeholder="Shop URL (optional)">'
            '<input name="category" placeholder="Category">'
            '<input name="niche" placeholder="Niche">'
            f'<select name="status">{opts}</select>'
            '<textarea name="notes" placeholder="Notes — what to LEARN (never copy)">'
            '</textarea>'
            '<p class="note">Scores 0-100 (your read): '
            + ", ".join(saved.SHOP_SCORES) + '</p>' + _score_inputs(saved.SHOP_SCORES)
            + '<button class="primary" type="submit">Save shop</button></form>')
        # auto-pulled shops first (newest + highest CR), then manual
        rows = saved.load_shops()
        rows.sort(key=lambda r: (r.get("source") == "auto",
                                 (r.get("metrics") or {}).get("avg_conversion_rate", 0)),
                  reverse=True)
        items = ""
        for r in rows:
            is_auto = r.get("source") == "auto"
            ov = saved.overall(r.get("scores"))
            fw = "".join(f"<li>{_h.escape(f)}</li>" for f in saved.SHOP_FRAMEWORK)
            url = _h.escape(r.get("shop_url") or "")
            m = r.get("metrics") or {}
            chips = ""
            if is_auto and m:
                chips = _chips([
                    f'CR {m.get("avg_conversion_rate", 0) * 100:.1f}%',
                    f'sold/day {m.get("sold_24h")}',
                    f'{m.get("fresh_winners")} fresh winners',
                    f'youngest {m.get("youngest_age_days")}d (&lt; 1yr)',
                    f'{m.get("total_favorites")} favs',
                    f'rev/day ~${m.get("revenue_24h_est", 0):,.0f}',
                    f'TM {m.get("trademark", "-")}'])
            pill = "auto" if is_auto else _h.escape(r.get("status", ""))
            items += (
                f'<div class="saveditem{" auto" if is_auto else ""}"><div class="sihead">'
                f'<b>{_h.escape(r.get("shop_name",""))}</b> '
                f'<span class="pill{" apill" if is_auto else ""}">{pill}</span>'
                + (f' · <a href="{url}" target="_blank" rel="noopener">open</a>' if url else "")
                + f' <a class="cbtn" href="/shops/del/{r["id"]}">delete</a></div>'
                f'<div class="note">{_h.escape(r.get("category",""))} · '
                f'{_h.escape(r.get("niche",""))} · '
                + ("new-shop proxy (listing age)" if is_auto
                   else f'learning score {ov if ov is not None else "—"}/100')
                + f' · saved {r.get("last_analyzed_at","")}</div>'
                + chips
                + (f'<p>{_h.escape(r.get("notes",""))}</p>' if r.get("notes") else "")
                + '<details><summary>Analysis rubric — what to examine</summary>'
                f'<ul class="facts">{fw}</ul><p class="note">{saved.DO_NOT_COPY}</p>'
                '</details></div>')
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        pull = _pull_bar("shops/pull", "new shops already selling",
                         "New shops (recent listings &lt; 1 year) with real sales + "
                         "the highest conversion. Auto-saved + ranked. Refresh anytime.")
        return page("Saved Shops", bar + '<article class="md"><h1>Saved Shops</h1>'
                    f'<p>Competitor-learning library. {saved.DO_NOT_COPY}</p>'
                    + pull + _pull_banner()
                    + form + (items or '<p class="empty">No saved shops yet — '
                              'hit Auto-pull above.</p>')
                    + '</article>')

    @app.route("/shops/add", methods=["POST"])
    @login_required
    def shops_add():
        from src import saved
        saved.add_shop({
            "shop_name": (request.form.get("shop_name") or "").strip()[:80],
            "shop_url": (request.form.get("shop_url") or "").strip()[:300],
            "category": (request.form.get("category") or "").strip()[:60],
            "niche": (request.form.get("niche") or "").strip()[:60],
            "status": request.form.get("status") or "watching",
            "notes": (request.form.get("notes") or "").strip()[:2000],
            "scores": _parse_scores(saved.SHOP_SCORES)})
        return redirect(url_for("shops"))

    @app.route("/shops/del/<int:sid>")
    @login_required
    def shops_del(sid):
        from src import saved
        saved.delete_shop(sid)
        return redirect(url_for("shops"))

    @app.route("/shops/pull")
    @login_required
    def shops_pull():
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        from src import autopull, saved
        try:
            rows = autopull.pull_shops(mode=mode, limit=15)
            n = saved.auto_save_shops(rows)
            return redirect(url_for("shops", pulled=n, total=len(rows)))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Auto-pull shops", exc)

    @app.route("/listings")
    @login_required
    def listings():
        import html as _h
        from src import saved
        opts = "".join(f"<option>{s}</option>" for s in saved.LISTING_STATUS)
        form = (
            '<form class="savedform" method="post" action="/listings/add">'
            '<input name="listing_title" placeholder="Listing title" required>'
            '<input name="listing_url" placeholder="Listing URL (optional)">'
            '<input name="shop_name" placeholder="Shop name">'
            '<input name="main_keyword" placeholder="Main keyword (pulls live market data)">'
            f'<select name="status">{opts}</select>'
            '<textarea name="notes" placeholder="Notes — why it works / how to beat it">'
            '</textarea>'
            '<p class="note">Scores 0-100 (your read): '
            + ", ".join(saved.LISTING_SCORES) + '</p>'
            + _score_inputs(saved.LISTING_SCORES)
            + '<button class="primary" type="submit">Save listing</button></form>')
        # auto-pulled listings first (highest performance), then manual
        rows = saved.load_listings()
        rows.sort(key=lambda r: (r.get("source") == "auto",
                                 (r.get("metrics") or {}).get("performance_score", 0)),
                  reverse=True)
        items = ""
        for r in rows:
            is_auto = r.get("source") == "auto"
            ov = saved.overall(r.get("scores"))
            fw = "".join(f"<li>{_h.escape(f)}</li>" for f in saved.LISTING_FRAMEWORK)
            url = _h.escape(r.get("listing_url") or "")
            m = r.get("metrics") or {}
            thumb, chips = "", ""
            if is_auto and m:
                img = _h.escape(m.get("image_url") or "")
                if img:
                    thumb = (f'<img class="lthumb" src="{img}" alt="" '
                             'loading="lazy" referrerpolicy="no-referrer">')
                beats = ", ".join(m.get("outperforms_peers_on") or []) or "-"
                chips = _chips([
                    f'{m.get("listing_age_days")}d old (&lt; 3mo)',
                    f'CR {m.get("conversion_rate", 0) * 100:.1f}%',
                    f'{m.get("views_24h")} views/day',
                    f'{m.get("favorites")} favs',
                    f'sold/day {m.get("sold_24h")}',
                    f'perf {int(m.get("performance_score", 0))}',
                    f'beats peers on: {beats}',
                    f'TM {m.get("trademark", "-")}'])
            ctx = r.get("context") or {}
            ctx_html = ""
            if ctx:
                ctx_html = ('<div class="note">Live market for '
                            f'"{_h.escape(r.get("main_keyword",""))}": '
                            f'{ctx.get("listings","?")} listings · '
                            f'avg ${ctx.get("avg_price","?")} · related: '
                            f'{_h.escape(", ".join(ctx.get("related",[])[:4]))}</div>')
                if ctx.get("original_idea"):
                    ctx_html += f'<p><b>Original idea:</b> {_h.escape(ctx["original_idea"])}</p>'
            pill = "auto" if is_auto else _h.escape(r.get("status", ""))
            items += (
                f'<div class="saveditem{" auto" if is_auto else ""}"><div class="sihead">'
                f'<b>{_h.escape(r.get("listing_title","")[:70])}</b> '
                f'<span class="pill{" apill" if is_auto else ""}">{pill}</span>'
                + (f' · <a href="{url}" target="_blank" rel="noopener">open on Etsy</a>' if url else "")
                + f' <a class="cbtn" href="/listings/del/{r["id"]}">delete</a></div>'
                f'<div class="note">{_h.escape(r.get("shop_name",""))} · '
                + ("young high-performer" if is_auto
                   else f'listing score {ov if ov is not None else "—"}/100')
                + f' · saved {r.get("last_analyzed_at","")}</div>'
                + ('<div class="lrow">' + thumb + '<div>' + chips + '</div></div>'
                   if is_auto else "")
                + ctx_html
                + (f'<p>{_h.escape(r.get("notes",""))}</p>' if r.get("notes") else "")
                + '<details><summary>Analysis rubric + how to beat it</summary>'
                f'<ul class="facts">{fw}</ul>'
                '<p><b>Create a better original:</b> stronger first image, real '
                'personalization, tighter long-tail SEO, a bundle/gift angle — '
                f'your own design.</p><p class="note">{saved.DO_NOT_COPY}</p>'
                '</details></div>')
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        pull = _pull_bar("listings/pull", "young winning listings",
                         "Listings under ~3 months old already outperforming their "
                         "niche — highest conversion, views &amp; favorites. "
                         "(Add-to-cart isn't public; favorites + CR stand in.)")
        return page("Saved Listings", bar + '<article class="md"><h1>Saved Listings'
                    f'</h1><p>Competitor-listing library. {saved.DO_NOT_COPY}</p>'
                    + pull + _pull_banner()
                    + form + (items or '<p class="empty">No saved listings yet — '
                              'hit Auto-pull above.</p>')
                    + '</article>')

    @app.route("/listings/add", methods=["POST"])
    @login_required
    def listings_add():
        from src import saved
        kw = (request.form.get("main_keyword") or "").strip()[:80]
        try:
            ctx = saved.listing_market_context(kw) if kw else {}
        except Exception:  # noqa: BLE001
            ctx = {}
        saved.add_listing({
            "listing_title": (request.form.get("listing_title") or "").strip()[:140],
            "listing_url": (request.form.get("listing_url") or "").strip()[:300],
            "shop_name": (request.form.get("shop_name") or "").strip()[:80],
            "main_keyword": kw, "context": ctx,
            "status": request.form.get("status") or "inspiration",
            "notes": (request.form.get("notes") or "").strip()[:2000],
            "scores": _parse_scores(saved.LISTING_SCORES)})
        return redirect(url_for("listings"))

    @app.route("/listings/del/<int:lid>")
    @login_required
    def listings_del(lid):
        from src import saved
        saved.delete_listing(lid)
        return redirect(url_for("listings"))

    @app.route("/listings/pull")
    @login_required
    def listings_pull():
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        from src import autopull, saved
        try:
            rows = autopull.pull_listings(mode=mode, limit=20)
            n = saved.auto_save_listings(rows)
            return redirect(url_for("listings", pulled=n, total=len(rows)))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Auto-pull listings", exc)

    # ---- Supplier library: catalogs (open/sync) + CSV upload (ShineOn/Embroidery) ----
    @app.route("/suppliers")
    @login_required
    def suppliers():
        import html as _h
        import collections
        from src import supplier_ops as so
        sources = so.load_sources()
        counts = collections.Counter(r.get("supplier_id") for r in so.load_products())
        rows = ["<table><tr><th>Supplier</th><th>Type</th><th>Modes</th>"
                "<th>Catalog / CSV</th><th>Products</th><th>Action</th></tr>"]
        for sid, info in sources.items():
            typ, n = info.get("type", ""), counts.get(sid, 0)
            if typ == "catalog_url":
                link = (f'<a href="{_h.escape(info.get("catalog_url",""))}" '
                        'target="_blank" rel="noopener">Open catalog ↗</a>')
                action = f'<a class="cbtn" href="/suppliers/sync/{sid}">Sync</a>'
            else:
                link = f'CSV: {_h.escape(info.get("csv_file",""))}'
                action = (
                    '<form method="post" action="/suppliers/upload" '
                    'enctype="multipart/form-data" style="display:inline">'
                    f'<input type="hidden" name="source" value="{sid}">'
                    '<input type="file" name="file" accept=".csv" required>'
                    '<button class="cbtn" type="submit">Upload CSV</button></form>')
            rows.append(f"<tr><td><b>{_h.escape(info.get('name',sid))}</b></td>"
                        f"<td>{typ}</td><td>{', '.join(info.get('modes',[]))}</td>"
                        f"<td>{link}</td><td>{n}</td><td>{action}</td></tr>")
        rows.append("</table>")
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page("Suppliers", bar + '<article class="md"><h1>Supplier library</h1>'
                    '<p>POD catalogs (open + pull manually) and CSV suppliers '
                    '(ShineOn / Embroidery — upload to normalize into the library). '
                    'Nothing is scraped; uploaded CSVs are the truth. A product is '
                    'only publish-ready once a supplier reaches SUPPLIER_CONFIRMED.'
                    '</p>' + "".join(rows) + '<p class="note">CLI: <code>py main.py '
                    'supplier import-csv --source shineon --file &lt;csv&gt;</code> · '
                    '<code>supplier match --product "..." --mode embroidery</code></p>'
                    '</article>')

    @app.route("/suppliers/sync/<source>")
    @login_required
    def suppliers_sync(source):
        from src import supplier_ops as so
        if source.lower() in so.load_sources():
            try:
                so.sync(source.lower())
            except Exception:  # noqa: BLE001
                pass
        return redirect(url_for("suppliers"))

    @app.route("/suppliers/upload", methods=["POST"])
    @login_required
    def suppliers_upload():
        from src import supplier_ops as so
        source = (request.form.get("source") or "").lower()
        f = request.files.get("file")
        if f and source in ("shineon", "embroidery"):
            dest = Path("data/suppliers")
            dest.mkdir(parents=True, exist_ok=True)
            fname = ("shineon_jewelry_acrylic.csv" if source == "shineon"
                     else "Embroidery.csv")
            path = dest / fname
            try:
                f.save(str(path))
                so.import_csv(source, str(path))
            except Exception:  # noqa: BLE001
                pass
        return redirect(url_for("suppliers"))

    # ---- Sales Feedback Loop: log real numbers -> Day-3/7 recommendation ----
    @app.route("/feedback")
    @login_required
    def feedback():
        import html as _h
        from src import feedback as fb
        form = ('<form class="savedform" method="post" action="/feedback/add">'
                '<input name="listing_url" placeholder="Listing URL" required>'
                '<input name="keyword" placeholder="Main keyword (links the saved run)">'
                '<input name="publish_date" placeholder="Publish date (YYYY-MM-DD)">'
                '<input name="product_mode" placeholder="Mode (pod/embroidery)">'
                '<input name="supplier" placeholder="Supplier">'
                '<input name="product_cost" type="number" step="any" placeholder="Product cost">'
                '<input name="shipping_cost" type="number" step="any" placeholder="Shipping cost">'
                '<input name="price" type="number" step="any" placeholder="Price">'
                '<input name="title" placeholder="Title">'
                '<input name="main_image_version" placeholder="Main image version (e.g. v2)">'
                '<input name="mockup_style" placeholder="Mockup style (flat / lifestyle / gift)">'
                '<input name="personalization_offer" placeholder="Personalization offered">'
                '<input name="bundle_offer" placeholder="Bundle offered">'
                '<input name="day_1_impressions" type="number" placeholder="Day 1 impressions">'
                '<input name="day_3_views" type="number" placeholder="Day 3 views">'
                '<input name="day_7_views" type="number" placeholder="Day 7 views">'
                '<input name="favorites" type="number" placeholder="Favorites">'
                '<input name="carts" type="number" placeholder="Carts">'
                '<input name="orders" type="number" placeholder="Orders">'
                '<input name="revenue" type="number" step="any" placeholder="Revenue">'
                '<input name="profit" type="number" step="any" placeholder="Profit">'
                '<input name="refund_or_issue" placeholder="Refund / issue (or none)">'
                '<textarea name="notes" placeholder="Notes"></textarea>'
                '<button class="primary" type="submit">Log + get Day-3/7 recommendation</button>'
                '</form>')
        items = ""
        for r in reversed(fb.load()):
            a7 = r.get("day7_action") or r.get("recommendation", "")
            v = r.get("day_7_views") or r.get("views", 0)
            items += ('<div class="saveditem"><div class="sihead">'
                      f'<b>{_h.escape((r.get("title") or r.get("listing_url") or "")[:58])}</b> '
                      f'<span class="pill apill">{_h.escape(a7)}</span> '
                      f'<a class="cbtn" href="/feedback/del/{r["id"]}">delete</a></div>'
                      f'<div class="note">{_h.escape(r.get("product_mode",""))} · '
                      f'{v} views · {r.get("favorites",0)} favs · '
                      f'{r.get("carts",0)} carts · {r.get("orders",0)} orders · '
                      f'logged {r.get("added_at","")}</div>'
                      f'<p><b>Day 3 → {_h.escape(r.get("day3_action",""))}:</b> '
                      f'{_h.escape(r.get("day3_reason",""))}</p>'
                      f'<p><b>Day 7 → {_h.escape(a7)}:</b> '
                      f'{_h.escape(r.get("day7_reason") or r.get("rec_reason",""))}</p></div>')
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page("Sales feedback", bar + '<article class="md"><h1>Sales feedback '
                    'loop</h1><p>After you MANUALLY publish, log the listing\'s real '
                    'numbers to get a Day-3/7 <b>KEEP / CHANGE / KILL / SCALE</b> '
                    'recommendation. This private performance data is your edge.</p>'
                    + form + (items or '<p class="empty">No listings tracked yet.</p>')
                    + '</article>')

    @app.route("/feedback/add", methods=["POST"])
    @login_required
    def feedback_add():
        from src import feedback as fb
        fb.add({k: (request.form.get(k) or "").strip()[:300] for k in fb.FIELDS})
        return redirect(url_for("feedback"))

    @app.route("/feedback/del/<int:fid>")
    @login_required
    def feedback_del(fid):
        from src import feedback as fb
        fb.delete(fid)
        return redirect(url_for("feedback"))

    # ---- other live self-serve tools (all MCP-backed, run on the VPS 24/7) ----
    def _mode_switch(endpoint, current):
        """One-click POD / Embroidery / All toggle for mode-aware tool pages.
        Reuses the pullbar styling; the active line is highlighted."""
        row = []
        for val, label in (("pod", "Print on Demand"),
                           ("embroidery", "Embroidery"), ("", "All lines")):
            href = f"/{endpoint}?mode={val}" if val else f"/{endpoint}"
            cls = "pullbtn primary" if (current or "") == val else "pullbtn"
            row.append(f'<a class="{cls}" href="{href}">{label}</a>')
        return ('<div class="pullbar"><div class="pulltxt"><b>Product line</b>'
                '<span>Switch POD &#8646; Embroidery for this tool</span></div>'
                '<div class="pullbtns">' + "".join(row) + '</div></div>')

    def _render_tool(title, txt, switch=""):
        html = md.markdown(txt, extensions=["tables", "fenced_code",
                                            "sane_lists"])
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page(title, bar + switch
                    + f'<article class="md">{html}</article>' + COPY_JS)

    def _tool_error(title, exc):
        import html as _html
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page(title, bar + f'<article class="md"><h1>{title}</h1>'
                    f'<p class="empty">The live data source is unavailable right '
                    f'now: {_html.escape(str(exc)[:200])}</p></article>')

    def _kw_tool(fn, title):
        import html as _html
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        if not q:
            bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
            return page(title, bar + f'<article class="md"><h1>{title}</h1>'
                        '<p class="empty">Type a keyword in the search box on the '
                        '<a href="/">home page</a>, then pick this tool.</p></article>')
        from src import interactive
        try:
            return _render_tool(f"{title}: {q}", fn(interactive, q))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error(title, exc)

    def _mode_tool(fn, title):
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        endpoint = request.path.strip("/")
        from src import interactive
        try:
            return _render_tool(title, fn(interactive, mode),
                                switch=_mode_switch(endpoint, mode))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error(title, exc)

    @app.route("/should-sell")
    @login_required
    def should_sell():
        return _kw_tool(lambda iv, q: iv.should_sell(q), "Should I sell")

    @app.route("/draft-listing")
    @login_required
    def draft_listing():
        return _kw_tool(lambda iv, q: iv.draft_listing(q), "Listing draft")

    @app.route("/trending")
    @login_required
    def trending():
        return _mode_tool(lambda iv, m: iv.trending(m), "Trending now")

    @app.route("/opportunities")
    @login_required
    def opportunities():
        return _mode_tool(lambda iv, m: iv.opportunities(m), "Opportunities")

    @app.route("/calendar")
    @login_required
    def calendar():
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        from src import interactive
        try:
            return _render_tool("Seasonal calendar", interactive.calendar(mode),
                                switch=_mode_switch("calendar", mode))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Seasonal calendar", exc)

    @app.route("/spy")
    @login_required
    def spy():
        import html as _html
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        m = (request.args.get("supplier_type") or request.args.get("mode") or "").lower()
        mode = m if m in ("pod", "embroidery", "both") else None
        if not q:
            bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
            return page("Spy", bar + '<article class="md"><h1>🕵️ Spy</h1>'
                        '<p class="empty">Pick a <b>Product Mode</b> and type a keyword '
                        'in the Command Center on the <a href="/">home page</a>, then '
                        'click 🕵️ Spy — the mode is carried through.</p></article>')
        from src import interactive
        try:
            return _render_tool(f"Spy: {q}", interactive.spy(q, mode))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Spy", exc)

    @app.route("/grade", methods=["GET", "POST"])
    @login_required
    def grade():
        import html as _html
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        title = (request.form.get("title") or "").strip()
        tags = (request.form.get("tags") or "").strip()
        desc = (request.form.get("description") or "").strip()
        kw = (request.form.get("keyword") or "").strip()
        result_html = ""
        if request.method == "POST" and (title or tags or desc):
            from src import interactive
            try:
                out = interactive.grade_listing(title, tags, desc, kw)
                rendered = md.markdown(out, extensions=["tables", "fenced_code",
                                                        "sane_lists"])
                result_html = (f'<article class="md">{rendered}</article>' + COPY_JS)
            except (SystemExit, Exception) as exc:  # noqa: BLE001
                result_html = ('<p class="empty">Could not grade: '
                               f'{_html.escape(str(exc)[:200])}</p>')
        form = (
            '<article class="md"><h1>📝 Grade my listing</h1>'
            '<p class="lead">Paste an existing listing and get a 0–100 score with '
            'exact fixes — front-loading, tag character-packing, typos, trademark '
            'cautions, and description gaps. <b>Grade only — never publishes.</b></p>'
            '<form method="post" action="/grade" class="gradeform">'
            '<label>Focus keyword'
            f'<input name="keyword" value="{_html.escape(kw)}" '
            'placeholder="e.g. personalized dog mom shirt"></label>'
            '<label>Title'
            f'<input name="title" value="{_html.escape(title)}" '
            'placeholder="Your listing title"></label>'
            '<label>Tags (13, comma-separated)'
            f'<textarea name="tags" rows="3" '
            f'placeholder="tag one, tag two, ...">{_html.escape(tags)}</textarea></label>'
            '<label>Description'
            f'<textarea name="description" rows="6" '
            f'placeholder="Your full listing description">{_html.escape(desc)}'
            '</textarea></label>'
            '<button class="primary" type="submit">Grade listing →</button>'
            '</form></article>')
        return page("Grade my listing", bar + result_html + form)

    # ---- keyword research (from `py main.py expand`, synced in reports/latest) ----
    @app.route("/research")
    @login_required
    def research():
        p = LATEST / "expand_report.md"
        if not p.is_file():
            body = ('<div class="rbar"><a class="back" href="/">&larr; All '
                    'reports</a></div><article class="md"><h1>Keyword Research'
                    '</h1><p class="empty">No lookups yet. On the research '
                    'machine run <code>py main.py expand "your keyword"</code>, '
                    'then publish with the sync.</p></article>')
            return page("Keyword Research", body)
        html = md.markdown(p.read_text(encoding="utf-8"),
                           extensions=["tables", "fenced_code", "sane_lists"])
        bar = ('<div class="rbar"><a class="back" href="/">&larr; All '
               'reports</a></div>')
        return page("Keyword Research",
                    bar + f'<article class="md">{html}</article>' + COPY_JS)

    # ---- command cheat sheet (served from the repo's CHEATSHEET.md) ----
    @app.route("/cheatsheet")
    @login_required
    def cheatsheet():
        p = ROOT / "CHEATSHEET.md"
        if not p.is_file():
            abort(404)
        html = md.markdown(p.read_text(encoding="utf-8"),
                           extensions=["tables", "fenced_code", "sane_lists"])
        bar = ('<div class="rbar"><a class="back" href="/">&larr; All '
               'reports</a></div>')
        return page("Cheat Sheet",
                    bar + f'<article class="md">{html}</article>' + COPY_JS)

    return app


def run_server(args):
    from dotenv import load_dotenv
    load_dotenv()

    host, port = "127.0.0.1", 8000
    i = 0
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]; i += 2; continue
        if args[i] == "--port" and i + 1 < len(args):
            if not args[i + 1].isdigit():
                print(f"--port must be a number, got '{args[i + 1]}'.")
                sys.exit(2)
            port = int(args[i + 1]); i += 2; continue
        print(f"Unknown option: {args[i]}"); sys.exit(2)

    try:
        import flask  # noqa: F401
        import markdown  # noqa: F401
    except ImportError:
        print("The web portal needs Flask and Markdown.")
        print("Fix: py -m pip install flask markdown")
        sys.exit(1)

    password = os.getenv("WEB_PASSWORD", "").strip()
    if not password:
        print("WEB_PASSWORD is not set - refusing to start without a login.")
        print("Fix: add a line to your .env file:")
        print("  WEB_PASSWORD=choose-a-strong-password")
        sys.exit(1)
    secret = os.getenv("WEB_SECRET") or os.urandom(24).hex()

    if host == "0.0.0.0":
        print("WARNING: binding 0.0.0.0 exposes this on your network. Prefer "
              "the default 127.0.0.1 + a Cloudflare Tunnel for teams.")
    app = build_app(password, secret)
    print(f"Etsy Product Manager report portal -> http://{host}:{port}")
    print("Team logs in with WEB_PASSWORD. Ctrl+C to stop.")
    app.run(host=host, port=port, threaded=True)


# --------------------------- templates ---------------------------
CSS = """
:root{--paper:#FBFAF6;--surface:#FFF;--ink:#221C13;--ink-soft:#6E6455;
--ink-faint:#9A8E7B;--line:#E7DFD0;--line-strong:#D8CDB8;--accent:#A8480A;
--accent-bg:#FBEFE1;--ok:#1E6B54;--stop:#99271F;
--shadow:0 1px 2px rgba(34,28,19,.05),0 6px 20px -12px rgba(34,28,19,.18);
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Monaco,"Cascadia Mono",monospace;}
@media(prefers-color-scheme:dark){:root{--paper:#15110B;--surface:#1E180F;
--ink:#F1E9DA;--ink-soft:#AA9D88;--ink-faint:#7C7060;--line:#322818;
--line-strong:#43371F;--accent:#EA8B44;--accent-bg:#2A1D0E;--ok:#58B491;
--stop:#E68A80;--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px -14px rgba(0,0,0,.6);}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:760px;margin:0 auto;padding:34px 22px 72px}
header{border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:22px;
display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.brand .kicker{font-family:var(--mono);font-size:.68rem;letter-spacing:.15em;
text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-size:1.55rem;font-weight:800;letter-spacing:-.02em;margin:.15em 0 0}
.hright{display:flex;align-items:center;gap:14px;font-family:var(--mono);font-size:.72rem}
.updated{color:var(--ink-faint)}
.logout{color:var(--accent);font-weight:600}
.lead{color:var(--ink-soft);font-size:.92rem;margin:0 0 16px}
.lead b{color:var(--accent)}
.grouph{font-size:.8rem;font-family:var(--mono);letter-spacing:.12em;
text-transform:uppercase;color:var(--ink-faint);margin:30px 0 4px;
border-top:1px solid var(--line);padding-top:22px}
.tabs{display:flex;gap:2px;margin:0 0 20px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.tab{font-family:var(--mono);font-size:.76rem;font-weight:700;padding:8px 15px;
color:var(--ink-soft);border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.on{color:var(--accent);border-bottom-color:var(--accent)}
.tab:hover{color:var(--ink)}
/* interactive tools */
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 16px}
.toolbar input{flex:1;min-width:240px;padding:11px 13px;border:1px solid var(--line-strong);
border-radius:10px;background:var(--surface);color:var(--ink);font-size:1rem;font-family:var(--sans)}
.toolbar button{padding:11px 14px;border:1px solid var(--accent);border-radius:10px;
background:var(--surface);color:var(--accent);font-weight:700;font-size:.86rem;cursor:pointer;font-family:var(--sans)}
.toolbar button.primary{background:var(--accent);color:var(--paper)}
.toolbar button:hover{filter:brightness(1.06)}
.toolgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:10px}
.toolcard{display:flex;flex-direction:column;gap:3px;padding:14px 15px;border:1px solid var(--line);
border-radius:12px;background:var(--surface);box-shadow:var(--shadow);transition:border-color .12s,transform .12s}
.toolcard:hover{border-color:var(--accent);transform:translateY(-1px)}
.toolcard b{font-size:.95rem}.toolcard span{font-size:.79rem;color:var(--ink-soft)}
/* command center */
.cmdbar{background:var(--surface);border:1px solid var(--line-strong);
border-radius:14px;padding:16px;box-shadow:var(--shadow);margin:12px 0 18px}
.cmdbar .kwrow{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.cmdbar .kwrow input{flex:1;min-width:240px;padding:12px 14px;font-size:1.05rem;
border:1px solid var(--line-strong);border-radius:10px;background:var(--paper);color:var(--ink)}
.cmdopts{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));
gap:8px;margin-bottom:10px}
.cmdopts input,.cmdopts select{padding:9px 10px;border:1px solid var(--line);
border-radius:8px;background:var(--paper);color:var(--ink);font-size:.85rem}
.cmdbtns{display:flex;gap:8px;flex-wrap:wrap}
.cmdbtns button{padding:11px 15px;border:1px solid var(--accent);border-radius:10px;
background:var(--surface);color:var(--accent);font-weight:700;font-size:.88rem;cursor:pointer}
.cmdbtns button.primary{background:var(--accent);color:var(--paper)}
.cmdbtns button:hover{filter:brightness(1.06)}
/* demand sparkline + grade form */
.spark{font-family:var(--mono,ui-monospace,Menlo,Consolas,monospace);font-size:1.15rem;
letter-spacing:1px;color:var(--accent);background:transparent;padding:0}
.gradeform{display:flex;flex-direction:column;gap:12px;margin-top:14px}
.gradeform label{display:flex;flex-direction:column;gap:4px;font-weight:700;font-size:.85rem}
.gradeform input,.gradeform textarea{padding:11px 13px;border:1px solid var(--line-strong);
border-radius:10px;background:var(--paper);color:var(--ink);font-size:.95rem;
font-family:var(--sans);font-weight:400}
.gradeform textarea{resize:vertical}
.gradeform button.primary{align-self:flex-start;padding:11px 18px;border:1px solid var(--accent);
border-radius:10px;background:var(--accent);color:var(--paper);font-weight:700;cursor:pointer}
/* auto-pull bar + feed */
.pullbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;
background:var(--accent-bg);border:1px solid var(--accent);border-radius:12px;padding:13px 16px;margin:12px 0}
.pulltxt{display:flex;flex-direction:column;gap:2px}
.pulltxt b{font-size:.98rem}.pulltxt span{font-size:.8rem;color:var(--ink-soft)}
.pullbtns{display:flex;gap:8px;flex-wrap:wrap}
.pullbtn{padding:9px 14px;border:1px solid var(--accent);border-radius:9px;background:var(--surface);
color:var(--accent);font-weight:700;font-size:.85rem;text-decoration:none}
.pullbtn.primary{background:var(--accent);color:var(--paper)}
.pullbtn:hover{filter:brightness(1.06)}
.pullnote{background:#1E6B54;color:#fff;border-radius:10px;padding:10px 14px;margin:10px 0;font-size:.9rem}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{font-size:.74rem;font-weight:700;background:var(--surface);border:1px solid var(--line-strong);
border-radius:20px;padding:3px 10px;color:var(--ink);font-variant-numeric:tabular-nums}
.saveditem.auto{border-left:3px solid var(--accent)}
.pill.apill{background:var(--accent);color:var(--paper)}
.lrow{display:flex;gap:12px;align-items:flex-start;margin-top:6px}
.lthumb{width:84px;height:84px;object-fit:cover;border-radius:10px;border:1px solid var(--line);flex:none}
.learnbox{background:var(--accent-bg);border:1px solid var(--accent);border-radius:10px;
padding:10px 14px;margin:10px 0}
.learnbox b{color:var(--accent)}.learnbox ul{margin:6px 0 0;padding-left:18px}
.archive{margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
.archive summary{cursor:pointer;font-weight:700;color:var(--ink-soft);font-size:.9rem}
/* workspace */
.ws{background:var(--surface);border:1px solid var(--line);border-radius:14px;
padding:18px 20px;margin:14px 0;box-shadow:var(--shadow)}
.ws h2{font-size:1.15rem;margin:0 0 12px;border-bottom:1px solid var(--line);padding-bottom:8px}
.ws h3{font-size:.98rem;margin:16px 0 6px}
.verdict{border-radius:12px;padding:16px 18px;color:#fff}
.verdict .vbig{font-size:1.7rem;font-weight:800;letter-spacing:-.02em}
.verdict .vwhy{opacity:.92;margin:2px 0 12px}
.verdict .vgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
gap:10px;font-size:.85rem}
.verdict .vgrid b{display:block;text-transform:uppercase;font-size:.66rem;
letter-spacing:.08em;opacity:.8;margin-bottom:2px}
.v-design{background:#1E6B54}.v-validate{background:#B45309}.v-watch{background:#3B6E8F}
.v-skip{background:#6E6455}.v-avoid{background:#99271F}
.scoregrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:10px}
.score{border:1px solid var(--line);border-radius:10px;padding:11px 12px;background:var(--paper)}
.sname{font-size:.8rem;font-weight:700;color:var(--ink-soft)}
.est{font-size:.6rem;background:var(--accent-bg);color:var(--accent);padding:1px 4px;
border-radius:4px;font-weight:700;vertical-align:middle}
.snum{font-size:1.5rem;font-weight:800;font-variant-numeric:tabular-nums}
.snum i{font-size:.7rem;font-style:normal;color:var(--ink-faint)}
.sbar{height:6px;background:var(--line);border-radius:4px;overflow:hidden;margin:5px 0}
.sbar span{display:block;height:100%;background:var(--accent)}
.score.s4 .sbar span,.score.s5 .sbar span{background:var(--ok)}
.score.s0 .sbar span,.score.s1 .sbar span{background:var(--stop)}
.slabel{font-size:.72rem;font-weight:700;color:var(--ink-soft)}
.swhy{font-size:.76rem;color:var(--ink-soft);margin-top:4px}
.simp{font-size:.72rem;color:var(--ink-faint);margin-top:3px}
.lb .lbrow{display:flex;align-items:center;gap:10px;margin:12px 0 4px;font-size:.85rem}
.lb .lbrow b{font-size:.7rem;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-soft)}
.lbval{background:var(--paper);border:1px solid var(--line);border-radius:8px;
padding:9px 12px;font-size:.9rem;white-space:pre-wrap}
.note{font-size:.75rem;color:var(--ink-faint);margin:6px 0 0}
.cbtn{font-family:var(--mono);font-size:.68rem;font-weight:700;color:var(--accent);
background:var(--surface);border:1px solid var(--line-strong);border-radius:6px;
padding:4px 9px;cursor:pointer;text-decoration:none;display:inline-block}
.cbtn:hover{border-color:var(--accent)}
.facts,.check{margin:0;padding-left:18px;font-size:.87rem}.facts li,.check li{margin:4px 0}
.expbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.modetoggle{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:.85rem}
.modetoggle span{font-weight:700;color:var(--ink-soft);text-transform:uppercase;font-size:.66rem;letter-spacing:.08em}
.modetoggle label{border:1px solid var(--line-strong);border-radius:20px;padding:5px 12px;cursor:pointer;background:var(--paper)}
.modetoggle input{margin-right:4px}
.gate{border-radius:8px;padding:9px 12px;font-weight:800;font-size:.9rem;margin-bottom:8px}
.g-ok{background:var(--ok);color:#fff}.g-no{background:var(--stop);color:#fff}
.warn{background:var(--accent-bg);border:1px solid var(--line-strong);border-radius:8px;padding:8px 12px;font-size:.83rem;margin-bottom:8px}
.warn ul{margin:4px 0 0;padding-left:18px}
.runedit{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:10px;align-items:end}
.runedit .fld{display:flex;flex-direction:column;gap:3px}
.runedit label{font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-soft)}
.runedit input,.runedit select{padding:8px 10px;border:1px solid var(--line-strong);border-radius:8px;background:var(--paper);color:var(--ink);font-size:.88rem}
.runedit .fmeta{font-size:.67rem;color:var(--ink-faint)}
.runedit button{grid-column:1/-1;justify-self:start;padding:9px 16px;border:0;border-radius:9px;background:var(--accent);color:var(--paper);font-weight:700;cursor:pointer}
.savedform{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;margin:12px 0;padding:14px;border:1px solid var(--line-strong);border-radius:12px;background:var(--surface)}
.savedform input,.savedform select,.savedform textarea{padding:8px 10px;border:1px solid var(--line-strong);border-radius:8px;background:var(--paper);color:var(--ink);font-size:.86rem;font-family:var(--sans)}
.savedform textarea{grid-column:1/-1;min-height:46px}.savedform .note{grid-column:1/-1;margin:2px 0}
.savedform button{grid-column:1/-1;justify-self:start;padding:9px 16px;border:0;border-radius:9px;background:var(--accent);color:var(--paper);font-weight:700;cursor:pointer}
.scores{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:6px}
.sc{display:flex;flex-direction:column;font-size:.64rem;color:var(--ink-soft);gap:2px}
.sc input{padding:5px 7px;border:1px solid var(--line);border-radius:6px;background:var(--paper);color:var(--ink)}
.saveditem{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0;background:var(--surface)}
.sihead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:.95rem}
.pill{font-size:.64rem;font-weight:700;background:var(--accent-bg);color:var(--accent);padding:2px 8px;border-radius:10px;text-transform:uppercase}
.saveditem details{margin-top:6px;font-size:.85rem}.saveditem summary{cursor:pointer;font-weight:600;color:var(--accent)}
.hero{border:2px solid var(--accent)}
.glance{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.chip{background:var(--paper);border:1px solid var(--line-strong);border-radius:16px;padding:5px 12px;font-size:.8rem;color:var(--ink-soft)}
.chip b{color:var(--ink)}.chip.wide{flex:1;min-width:200px}
.chip.cg-ok{border-color:var(--ok)}.chip.cg-ok b{color:var(--ok)}
.chip.cg-no{border-color:var(--stop)}.chip.cg-no b{color:var(--stop)}
.wsnav{position:sticky;top:0;z-index:5;display:flex;gap:6px;flex-wrap:wrap;background:var(--paper);padding:9px 0;margin:8px 0 4px;border-bottom:1px solid var(--line)}
.wsnav a{font-family:var(--mono);font-size:.72rem;font-weight:700;color:var(--accent);border:1px solid var(--line-strong);border-radius:16px;padding:5px 11px;background:var(--surface)}
.wsnav a:hover{border-color:var(--accent);background:var(--accent-bg)}
.wsgroup{font-size:1.1rem;font-weight:800;margin:30px 0 2px;padding-top:12px;border-top:2px solid var(--accent);color:var(--ink);scroll-margin-top:56px}
.ws{scroll-margin-top:56px}
.inputsbox summary{cursor:pointer;font-weight:700;font-size:1rem;color:var(--accent)}
/* internal product preview */
.pv{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:16px;
border:1px solid var(--line-strong);border-radius:12px;padding:14px;background:var(--paper)}
.pvmain{aspect-ratio:1;background:repeating-linear-gradient(45deg,var(--line),var(--line) 10px,var(--surface) 10px,var(--surface) 20px);
border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--ink-faint);font-size:.8rem}
.pvthumbs{display:flex;gap:6px;margin-top:6px}.pvthumbs i{width:38px;height:38px;background:var(--line);border-radius:6px}
.pvshop{font-size:.78rem;color:var(--ink-soft)}
.pvtitle{font-size:1.02rem;font-weight:600;margin:4px 0}
.pvprice{font-size:1.35rem;font-weight:800;margin:6px 0}.pvprice small{font-size:.68rem;font-weight:400;color:var(--ink-faint)}
.pvpers{display:block;font-size:.75rem;color:var(--ink-soft);margin:8px 0}
.pvpers textarea{display:block;width:100%;min-height:42px;margin-top:3px;border:1px solid var(--line-strong);
border-radius:8px;padding:6px;background:var(--surface);color:var(--ink)}
.pvqty{font-size:.8rem;margin:6px 0}.pvqty select{margin-left:6px;padding:3px 6px;border-radius:6px}
.pvcart{width:100%;padding:11px;background:var(--accent);color:var(--paper);border:none;
border-radius:24px;font-weight:700;cursor:pointer;margin:8px 0}
.pvacc{border-top:1px solid var(--line);padding:6px 0;font-size:.82rem}
.pvacc summary{cursor:pointer;font-weight:600}
.pvtags{margin-top:8px;font-size:.68rem;color:var(--ink-faint)}
.pvtags span{display:inline-block;background:var(--accent-bg);color:var(--accent);
padding:1px 6px;border-radius:10px;margin:2px 3px 0 0}
@media(max-width:640px){.pv{grid-template-columns:1fr}}
/* report list */
.reports{display:grid;gap:10px}
.report{display:grid;grid-template-columns:44px 1fr auto;align-items:center;gap:16px;
background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:15px 16px;box-shadow:var(--shadow);transition:border-color .12s,transform .12s}
.report:hover{border-color:var(--accent);transform:translateY(-1px)}
.report:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.rid{font-family:var(--mono);font-weight:800;font-size:1.15rem;color:var(--accent);
font-variant-numeric:tabular-nums;text-align:center}
.rmeta{display:flex;flex-direction:column;gap:3px;min-width:0}
.rt{font-weight:700;font-size:1rem}
.rd{font-size:.82rem;color:var(--ink-soft)}
.ractions{display:flex;align-items:center;gap:8px;white-space:nowrap}
.btn{font-family:var(--mono);font-size:.72rem;font-weight:700;letter-spacing:.03em;
color:var(--paper);background:var(--accent);border:none;border-radius:7px;
padding:7px 11px;cursor:pointer}
.btn.ghost{color:var(--accent);background:transparent;border:1px solid var(--line-strong)}
.btn.ghost:hover{border-color:var(--accent)}
.empty{color:var(--ink-soft);background:var(--surface);border:1px dashed var(--line-strong);
border-radius:12px;padding:22px;text-align:center;font-size:.9rem}
/* single report */
.rbar{display:flex;align-items:center;justify-content:space-between;gap:12px;
margin-bottom:16px;flex-wrap:wrap}
.back{font-family:var(--mono);font-size:.78rem;color:var(--accent);font-weight:600}
.md{background:var(--surface);border:1px solid var(--line);border-radius:14px;
padding:26px 30px;box-shadow:var(--shadow);overflow-x:auto}
.md h1{font-size:1.5rem}.md h2{font-size:1.2rem;border-bottom:1px solid var(--line);
padding-bottom:.25em;margin-top:1.5em}.md h3{font-size:1rem;margin-top:1.3em}
.md a{color:var(--accent);text-decoration:underline}
.md code{font-family:var(--mono);font-size:.85em;background:var(--accent-bg);
padding:1px 5px;border-radius:4px}
.md pre{position:relative;background:var(--paper);border:1px solid var(--line-strong);
border-radius:9px;padding:13px 15px;margin:1em 0;overflow-x:auto;font-size:.82rem;line-height:1.55}
.md pre code{background:none;padding:0}
.md table{border-collapse:collapse;width:100%;font-size:.85rem;margin:1em 0}
.md th,.md td{border:1px solid var(--line);padding:6px 10px;text-align:left}
.md th{background:var(--accent-bg)}
.md blockquote{border-left:4px solid var(--line-strong);margin:1em 0;padding:.2em 1em;
color:var(--ink-soft)}
.copy{position:absolute;top:7px;right:7px;font-family:var(--mono);font-size:.64rem;
font-weight:700;color:var(--accent);background:var(--surface);border:1px solid var(--line-strong);
border-radius:6px;padding:3px 8px;cursor:pointer;opacity:.55;transition:opacity .12s}
.md pre:hover .copy{opacity:1}
/* login */
.login{max-width:340px;margin:15vh auto 0;text-align:center}
.login .kicker{font-family:var(--mono);font-size:.68rem;letter-spacing:.15em;
text-transform:uppercase;color:var(--accent);font-weight:700}
.login form{display:flex;flex-direction:column;gap:12px;margin-top:20px}
.login input{font:inherit;padding:11px 13px;border:1px solid var(--line-strong);
border-radius:9px;background:var(--surface);color:var(--ink)}
.login input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.login button{font:inherit;font-weight:700;padding:11px;border:none;border-radius:9px;
background:var(--accent);color:var(--paper);cursor:pointer}
.err{color:var(--stop);font-size:.85rem}
footer{margin-top:34px;font-family:var(--mono);font-size:.7rem;color:var(--ink-faint);
text-align:center}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

BASE = ("<!doctype html><html><head><meta charset=utf8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>{{TITLE}} · Etsy Product Manager</title><style>" + CSS +
        "</style></head><body>{{BODY}}</body></html>")

# Standalone print-ready page for the role reports -> browser Print/Save as PDF.
PRINT_BASE = (
    "<!doctype html><html><head><meta charset=utf8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>{{TITLE}}</title><style>"
    "body{font-family:-apple-system,Segoe UI,system-ui,sans-serif;max-width:800px;"
    "margin:0 auto;padding:32px 28px;color:#1a1a1a;line-height:1.5;background:#fff}"
    "h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.05rem;border-bottom:1px solid #ddd;"
    "padding-bottom:3px;margin:20px 0 8px;color:#b45309}h3{font-size:.95rem;margin:14px 0 4px}"
    ".meta{color:#666;font-size:.85rem;margin:0 0 12px}"
    ".warn{background:#fbe9d6;border:1px solid #e0c090;padding:6px 10px;border-radius:6px}"
    "table{border-collapse:collapse;width:100%;font-size:.85rem;margin:6px 0}"
    "th,td{border:1px solid #ddd;padding:4px 8px;text-align:left}th{background:#f5efe6}"
    "pre{background:#faf7f1;border:1px solid #e5ddcc;border-radius:6px;padding:10px;"
    "white-space:pre-wrap;font-size:.82rem}ul{margin:4px 0;padding-left:20px}"
    ".pbtn{position:fixed;top:14px;right:14px;background:#b45309;color:#fff;border:0;"
    "border-radius:8px;padding:9px 14px;font-weight:700;cursor:pointer}"
    "@media print{.pbtn{display:none}body{padding:0 10px}}"
    "</style></head><body>"
    "<button class=pbtn onclick='window.print()'>🖨️ Save as PDF</button>{{BODY}}"
    "<p style='margin-top:28px;color:#999;font-size:.75rem'>Etsy Product Manager — "
    "internal working document. Draft only; never auto-published. Do not copy "
    "competitor artwork, titles, or photos.</p></body></html>")

LOGIN = """
<div class="wrap"><div class="login">
  <div class="kicker">Etsy Product Manager</div>
  <h1>Team Reports</h1>
  {{ERROR}}
  <form method="post">
    <input type="password" name="password" placeholder="Password" autofocus>
    <button type="submit">Sign in</button>
  </form>
</div></div>
"""

PORTAL = """
<div class="wrap">
  <header>
    <div class="brand">
      <div class="kicker">Etsy Product Manager</div>
      <h1>Team Reports</h1>
    </div>
    <div class="hright">{{UPDATED}}<a class="logout" href="/cheatsheet">Cheat Sheet</a><a class="logout" href="/logout">Sign out</a></div>
  </header>
  {{BODY}}
  <footer>Reports are prepared on the research machine and synced here.</footer>
</div>
"""

PRIVACY = """
<div class="wrap">
  <header>
    <div class="brand">
      <div class="kicker">Etsy Product Manager</div>
      <h1>Privacy Policy</h1>
    </div>
    <div class="hright"><a class="logout" href="/">Home</a></div>
  </header>
  <article class="md">
    <p><em>Last updated: 7 July 2026</em></p>

    <h2>Who we are</h2>
    <p>This site is an internal market-research tool operated by The Global
    Service Team for our own Etsy print-on-demand shop. It is used by our small
    team to decide which products to design and list.</p>

    <h2>How we use the Pinterest API</h2>
    <p>Our application uses the Pinterest API v5 on a <strong>read-only</strong>
    basis. It requests <strong>aggregate trending-keyword data</strong> (for
    example, the top growing search keywords in a region) to cross-check demand
    for product ideas. We do <strong>not</strong> access, collect, or store any
    Pinterest user's personal information &mdash; no boards, pins, followers,
    messages, or private account data.</p>

    <h2>Data we store</h2>
    <p>We may cache the aggregate keyword and trend figures returned by the API
    on our own server so that reports load quickly. This is not personal data.
    Our API access token is kept privately in server configuration; it is never
    shared, sold, or exposed publicly.</p>

    <h2>How the data is used</h2>
    <p>Trend data is used solely to inform our own team's product research and
    listing decisions. We do <strong>not</strong> sell, rent, publish, or share
    Pinterest data with any third party.</p>

    <h2>Cookies</h2>
    <p>This site sets a single session cookie so team members stay signed in.
    It stores no personal or tracking information and is not shared with anyone.</p>

    <h2>Data retention &amp; deletion</h2>
    <p>Cached trend figures are overwritten on each new research run. To request
    deletion of any data, or revocation of our Pinterest access, contact us at
    the address below and we will action it promptly.</p>

    <h2>Contact</h2>
    <p>Questions about this policy:
    <a href="mailto:nvphilong@gmail.com">nvphilong@gmail.com</a></p>
  </article>
  <footer>Etsy Product Manager &middot; internal market-research tool</footer>
</div>
"""

COPY_JS = """
<script>
document.querySelectorAll('.md pre').forEach(pre=>{
  const b=document.createElement('button');
  b.className='copy';b.type='button';b.textContent='Copy';
  b.addEventListener('click',()=>{
    navigator.clipboard.writeText(pre.innerText.replace(/\\nCopy$/,'')).then(()=>{
      b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1200);});
  });
  pre.appendChild(b);
});
</script>
"""

WORKSPACE_JS = """
<script>
document.querySelectorAll('.cbtn[data-copy]').forEach(b=>{
  b.addEventListener('click',()=>{
    const el=document.getElementById(b.dataset.copy); if(!el) return;
    navigator.clipboard.writeText(el.innerText).then(()=>{
      const t=b.textContent; b.textContent='Copied \\u2713';
      setTimeout(()=>{b.textContent=t;},1200);});
  });
});
</script>
"""
