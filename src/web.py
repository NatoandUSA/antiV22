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
        modes = _available_modes()
        if not modes:
            body = ('<p class="empty">No reports published yet. The operator '
                    'syncs them from the research machine — check back soon.</p>')
            return page("Reports", PORTAL.replace("{{UPDATED}}", "")
                        .replace("{{BODY}}", body))
        keys = [m[0] for m in modes]
        active = request.args.get("mode", "")
        if active not in keys:
            active = keys[0]
        sub = {m[0]: m[2] for m in modes}[active]
        mdir = LATEST / sub if sub else LATEST

        tabs = ""
        if len(modes) > 1:
            tabs = '<div class="tabs">' + "".join(
                f'<a class="tab{" on" if m[0] == active else ""}" '
                f'href="/?mode={m[0]}">{m[1]}</a>' for m in modes) + "</div>"

        daily = [_card(sub, f, rid, t, d) for rid, f, t, d in REPORTS
                 if (mdir / f).exists()]
        detail = [_card(sub, f, "&bull;", t, d) for f, t, d in DETAIL_REPORTS
                  if (mdir / f).exists()]
        active_label = {m[0]: m[1] for m in modes}.get(active, active)
        # --- interactive tools: live, self-serve, 24/7 (no operator needed) ---
        tools = (
            '<h2 class="grouph">🔎 Instant tools — live, anyone can use anytime</h2>'
            '<p class="lead">Type a keyword for an instant read — no waiting on '
            'the operator.</p>'
            '<form class="toolbar" method="get" action="/analyze">'
            '<input name="q" placeholder="Type a keyword, e.g. custom dad shirt" '
            'aria-label="keyword">'
            '<button class="primary" name="do" value="analyze">Analyze</button>'
            '<button name="do" value="expand">Expand</button>'
            '<button formaction="/should-sell">Should I sell?</button>'
            '<button formaction="/draft-listing">Draft listing</button>'
            '</form>'
            '<div class="toolgrid">'
            f'<a class="toolcard" href="/trending?mode={active}"><b>📈 Trending now'
            f'</b><span>Rising keywords in {active_label}</span></a>'
            f'<a class="toolcard" href="/opportunities?mode={active}"><b>💎 '
            'Opportunities</b><span>Low-competition sweet spots</span></a>'
            '<a class="toolcard" href="/calendar"><b>📅 Seasonal calendar</b>'
            '<span>What to launch next, timed</span></a>'
            '<a class="toolcard" href="/research"><b>🔬 Saved research</b>'
            '<span>Past keyword lookups</span></a>'
            '</div>')

        # --- read-only reports, built by the operator ---
        reports = '<h2 class="grouph">📊 Daily reports</h2>' + tabs
        if daily:
            reports += ('<p class="lead">The core reports — read in order from '
                        '<b>00</b>.</p><div class="reports">'
                        + "".join(daily) + "</div>")
        if detail:
            reports += ('<h2 class="grouph">All reports</h2><div class="reports">'
                        + "".join(detail) + "</div>")
        if not daily and not detail:
            reports += '<p class="empty">This set has no reports yet.</p>'
        body = tools + reports
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
            except Exception as exc:  # noqa: BLE001
                results = ('<article class="md"><p class="empty">Could not '
                           f'analyze "{val}": {_html.escape(str(exc)[:200])}'
                           '</p></article>')
        return page("Analyze a keyword", head + results)

    # ---- other live self-serve tools (all MCP-backed, run on the VPS 24/7) ----
    def _render_tool(title, txt):
        html = md.markdown(txt, extensions=["tables", "fenced_code",
                                            "sane_lists"])
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page(title, bar + f'<article class="md">{html}</article>' + COPY_JS)

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
        except Exception as exc:  # noqa: BLE001
            return _tool_error(title, exc)

    def _mode_tool(fn, title):
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        from src import interactive
        try:
            return _render_tool(title, fn(interactive, mode))
        except Exception as exc:  # noqa: BLE001
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
        from src import interactive
        try:
            return _render_tool("Seasonal calendar", interactive.calendar())
        except Exception as exc:  # noqa: BLE001
            return _tool_error("Seasonal calendar", exc)

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
