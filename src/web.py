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

    from datetime import timedelta
    from src import auth, activity
    app = Flask(__name__)
    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,       # JS can't read the cookie
        SESSION_COOKIE_SAMESITE="Lax",      # basic CSRF mitigation
        # Send the session cookie only over HTTPS. Enabled on the VPS by setting
        # WEB_SECURE_COOKIES=1 in .env; left off for local http://localhost dev.
        SESSION_COOKIE_SECURE=(os.getenv("WEB_SECURE_COOKIES", "").strip() == "1"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),   # session timeout
    )

    @app.after_request
    def _security_headers(resp):
        # Defense-in-depth: block framing (clickjacking), MIME sniffing, and
        # restrict where scripts/frames can come from. Inline script/style are
        # allowed (the app renders them); images come from anywhere (listing
        # thumbnails). This backstops the XSS-sink escaping in the routes.
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src * data: blob:; "
            "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        return resp

    auth.appdb.init_db()

    def _ip():
        return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or request.remote_addr or "")

    def _ua():
        return request.headers.get("User-Agent", "")[:200]

    def _no_tags(s):
        """Remove the HTML tag-injection characters. Used to neutralize XSS at
        input boundaries where the value later flows through markdown/raw HTML."""
        return (s or "").translate({ord("<"): "", ord(">"): "", ord('"'): ""})

    def _safe_url(u):
        """Only allow http(s) links; block javascript:/data: URI XSS. Returns '' if
        the scheme isn't safe, so the caller renders no href."""
        u = (u or "").strip()
        low = u.lower()
        if low.startswith("http://") or low.startswith("https://"):
            return u
        if low and "//" not in low and ":" not in low.split("/")[0]:
            return "https://" + u          # bare domain -> assume https
        return ""

    def current_user():
        uid = session.get("uid")
        return auth.get_user(uid) if uid else None

    def _log(event, **kw):
        activity.log(event, user=current_user(), ip=_ip(), user_agent=_ua(), **kw)

    def login_required(fn):
        @wraps(fn)
        def wrap(*a, **k):
            u = current_user()
            if not u or u.get("status") == "DISABLED":
                session.clear()
                return redirect(url_for("login"))
            return fn(*a, **k)
        return wrap

    def require_perm(perm):
        def deco(fn):
            @wraps(fn)
            def wrap(*a, **k):
                u = current_user()
                if not u:
                    return redirect(url_for("login"))
                if not auth.has_perm(u["role"], perm):
                    return page("Not allowed", '<div class="rbar"><a class="back" '
                                'href="/">&larr; Home</a></div><article class="md">'
                                '<h1>403 — not allowed</h1><p>Your role '
                                f'(<b>{u["role"]}</b>) can\'t access this page. Ask '
                                'an admin if you need it.</p></article>'), 403
                return fn(*a, **k)
            return wrap
        return deco

    def page(title, body):
        return Response(BASE.replace("{{TITLE}}", title)
                        .replace("{{BODY}}", body), mimetype="text/html")

    def _safe_report(name):
        """Return an existing file inside reports/latest, or None."""
        p = (LATEST / name).resolve()
        if LATEST.resolve() not in p.parents or not p.is_file():
            return None
        return p

    def _alerts_card():
        try:
            from src import alerts
            s = alerts.summary()
        except Exception:  # noqa: BLE001
            s = {"open": 0, "critical": 0}
        n, crit = s.get("open", 0), s.get("critical", 0)
        badge = (f' <span class="abadge {"crit" if crit else "warn"}">{n}</span>'
                 if n else "")
        return ('<a class="toolcard" href="/alerts"><b>🔔 Alerts' + badge + '</b>'
                '<span>What needs attention: reviews, kills, stale data</span></a>')

    # ---- auth (per-user login) ----
    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            pw = request.form.get("password") or ""
            u, why = auth.authenticate(email, pw, _ip())
            if u:
                session.clear()
                session["uid"] = u["user_id"]
                session.permanent = bool(request.form.get("remember"))
                activity.log("AUTH_LOGIN_SUCCESS", user=u, module="auth", ip=_ip(),
                             user_agent=_ua())
                return redirect(url_for("index"))
            activity.log("AUTH_LOGIN_FAILED", user={"email": email}, module="auth",
                         ip=_ip(), success=False, error=why)
            # One generic message for wrong-password AND disabled/unknown account,
            # so login can't be used to enumerate which emails exist.
            error = ('<p class="err">Account locked after too many attempts — '
                     'try again in 15 minutes.</p>' if why == "locked"
                     else '<p class="err">Wrong email or password.</p>')
        return page("Sign in", LOGIN.replace("{{ERROR}}", error))

    @app.route("/logout")
    def logout():
        _log("AUTH_LOGOUT", module="auth")
        session.clear()
        return redirect(url_for("login"))

    @app.route("/me")
    @login_required
    def me():
        import html as _h
        u = current_user()
        recent = activity.list_events(user_id=u["user_id"], limit=20)
        rows = "".join(f"<tr><td>{_h.escape(r['timestamp'])}</td>"
                       f"<td>{_h.escape(r['event_type'])}</td>"
                       f"<td>{_h.escape(r.get('keyword') or r.get('module') or '')}</td></tr>"
                       for r in recent)
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page("My profile", bar + '<article class="md"><h1>👤 My profile</h1>'
                    f'<p><b>{_h.escape(u["display_name"])}</b> · role '
                    f'<b>{u["role"]}</b> · {_h.escape(u["email"])}</p>'
                    f'<p class="note">Last login: {u.get("last_login_at") or "—"}</p>'
                    '<h2>My recent activity</h2><table><tr><th>When</th><th>Event</th>'
                    f'<th>Detail</th></tr>{rows}</table></article>')

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
            '<details class="cmdmore"><summary>＋ Quick single-step tools</summary>'
            '<p class="note">Jump straight to one tool instead of the full workspace. '
            '<b>Tip:</b> product type, niche, occasion, style &amp; personalization are '
            '<b>AI-filled from the live data inside the workspace</b> (the "📝 Run '
            'inputs" panel) — edit them there, no need to guess up front.</p>'
            '<div class="cmdbtns">'
            '<button formaction="/analyze" name="do" value="analyze">Analyze only</button>'
            '<button formaction="/analyze" name="do" value="expand">Expand keywords</button>'
            '<button formaction="/should-sell">Should I sell?</button>'
            '<button formaction="/draft-listing">Draft listing</button>'
            '</div></details></form>'
            # --- Section 1: find what to make (live market research) ---
            '<h2 class="grouph">🔍 Find opportunities — live market research</h2>'
            '<div class="toolgrid">'
            f'<a class="toolcard" href="/trending?mode={active}"><b>📈 Trending now'
            f'</b><span>Rising keywords in {active_label}</span></a>'
            f'<a class="toolcard" href="/opportunities?mode={active}"><b>💎 '
            'Opportunities</b><span>Low-competition sweet spots</span></a>'
            f'<a class="toolcard" href="/spy?mode={active}"><b>🕵️ Spy + Reverse Engine</b>'
            '<span>Decode each competitor\'s playbook + how to beat them</span></a>'
            f'<a class="toolcard" href="/calendar?mode={active}"><b>📅 Seasonal calendar</b>'
            '<span>Upcoming holidays + launch-by dates + keywords</span></a>'
            '</div>'
            # --- Section 2: saved intelligence you build up over time ---
            '<h2 class="grouph">📚 Your library — saved intelligence</h2>'
            '<div class="toolgrid">'
            '<a class="toolcard" href="/research"><b>🔬 Saved research</b>'
            '<span>Past keyword lookups</span></a>'
            '<a class="toolcard" href="/shops"><b>🏪 Saved shops</b>'
            '<span>Auto-pull new shops already selling (&lt; 1yr, high CR)</span></a>'
            '<a class="toolcard" href="/listings"><b>📌 Saved listings</b>'
            '<span>Auto-pull young winners (&lt; 3mo, high CR/views/favs)</span></a>'
            '<a class="toolcard" href="/suppliers"><b>🏭 Suppliers</b>'
            '<span>Catalogs + ShineOn/Embroidery CSV upload</span></a>'
            '</div>'
            # --- Section 3: ship it, then learn from results ---
            '<h2 class="grouph">🚀 Execute &amp; improve</h2>'
            '<div class="toolgrid">'
            '<a class="toolcard" href="/grade"><b>📋 Listing Analyzer</b>'
            '<span>SEO / Trust / Image scores + publish gate</span></a>'
            '<a class="toolcard" href="/feedback"><b>📉 Sales feedback</b>'
            '<span>Post-launch: keep / change / kill / scale</span></a>'
            + _alerts_card()
            + '<a class="toolcard" href="/launchpad"><b>🚀 Launchpad</b>'
            '<span>Launch board: idea → manager → Day-7 → scale/kill</span></a>'
            '<a class="toolcard" href="/trackers"><b>📊 Market &amp; keyword tracker</b>'
            '<span>Trends over time: rising / falling / stable</span></a>'
            '<a class="toolcard" href="/profit"><b>💰 Profit Center</b>'
            '<span>Real P&amp;L per product / supplier / mode</span></a>'
            '<a class="toolcard" href="/workflow"><b>📋 Workflow</b>'
            '<span>How the team works: find → collect → ship</span></a>'
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
        # Always-visible reminder: the member's open tasks, pinned at the top.
        mytask_strip = ""
        _mu = current_user()
        if _mu:
            from src import tasks as _tk
            mine = _tk.my_open(_mu["user_id"])
            if mine:
                od = sum(1 for t in mine if _tk.is_overdue(t))
                ds = sum(1 for t in mine if _tk.is_due_soon(t))
                chips = "".join(
                    f'<a class="tkchip pr-{t["priority"].lower()}'
                    + (" od" if _tk.is_overdue(t) else "") + '" href="/me/tasks">'
                    + _h_esc(t["title"][:32]) + '</a>' for t in mine[:3])
                more = (f'<a class="tkchip more" href="/me/tasks">+{len(mine)-3} more</a>'
                        if len(mine) > 3 else "")
                odtxt = f' · <b class="odtext">{od} overdue</b>' if od else ""
                odtxt += f' · <b class="dstext">{ds} due soon</b>' if ds else ""
                review = ""
                if auth.has_perm(_mu["role"], "tasks.review"):
                    rq = len(_tk.review_queue())
                    if rq:
                        review = f' · <a href="/admin/reviews"><b>{rq} to review</b></a>'
                mytask_strip = (
                    '<div class="mytasks"><div class="mtlabel">✅ My tasks: '
                    f'<b>{len(mine)}</b> open{odtxt}{review}</div>'
                    f'<div class="mtchips">{chips}{more}</div>'
                    '<a class="mtall" href="/me/tasks">Open →</a></div>')
        body = mytask_strip + tools + arch
        upd = _last_updated(mdir)
        updated = f'<span class="updated">Updated {upd}</span>' if upd else ""
        _u = current_user()
        uchip = (f'<a class="uchip" href="/me">{_h_esc(_u["display_name"])} · '
                 f'{_u["role"]}</a>' if _u else "")
        return page("Reports", PORTAL
                    .replace("{{UPDATED}}", updated)
                    .replace("{{USER}}", uchip)
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
        # theme-aware toolbar; the active view's button gets .primary (fixes the
        # bug where "Analyze" stayed highlighted even on the Expand view)
        form = (
            '<form method="get" action="/analyze" class="toolbar">'
            f'<input name="q" value="{val}" autofocus '
            'placeholder="Type a keyword, e.g. custom dad shirt">'
            '<button name="do" value="analyze"'
            + (' class="primary"' if do == "analyze" else "") + '>Analyze</button>'
            '<button name="do" value="expand"'
            + (' class="primary"' if do == "expand" else "") + '>Expand</button>'
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
                   "style", "personalization", "supplier_type",
                   # manager sign-off checkboxes (drive PUBLISH_READY)
                   "confirm_supplier", "confirm_competitor_audit", "confirm_material",
                   "confirm_image", "confirm_trademark")

    def _run_inputs():
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        # Strip tag-injection chars from the free-text option fields at the
        # boundary so no downstream markdown/HTML sink can be XSS'd (some render
        # sites escape, some don't — this makes every one safe).
        opts = {k: _no_tags((request.args.get(k) or "").strip()[:60])
                for k in _OPT_FIELDS}
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
        pr = bool(getattr(workspace.build_workspace, "_last", {}).get("publish_ready"))
        _log("WORKSPACE_BUILD", module="workspace", keyword=q,
             product_mode=opts.get("supplier_type"),
             summary=f"publish_ready={pr}")
        # Manager approval bar (only for OWNER/ADMIN/MANAGER; never publishes).
        approve = ""
        u = current_user()
        if u and auth.can_approve(u["role"]):
            if pr:
                approve = (
                    '<section class="ws"><h2>✅ Manager approval</h2>'
                    '<p>All checks pass and the manager sign-off is complete. You '
                    'may approve this listing <b>for manual publishing</b> — the '
                    'tool still never publishes; you list it yourself on Etsy.</p>'
                    '<form method="post" action="/run/approve" class="toolbar">'
                    f'<input type="hidden" name="q" value="{_html.escape(q)}">'
                    '<input name="note" placeholder="Approval note (optional)">'
                    '<button class="primary" name="decision" value="APPROVED">'
                    'Approve for manual publish</button>'
                    '<button name="decision" value="REJECTED">Reject</button>'
                    '</form><p class="note">MANAGER_APPROVED_FOR_MANUAL_PUBLISH is '
                    'recorded in the activity log. PUBLISH_AUTOMATION: false.</p></section>')
            else:
                approve = ('<section class="ws"><h2>✅ Manager approval</h2>'
                           '<p class="empty">Not approvable yet — PUBLISH_READY is '
                           'false. Complete the sign-off + failed checks above.</p>'
                           '</section>')
        # Assign a task for this product (managers+). One click, keyword pre-filled.
        assign = ""
        if u and auth.has_perm(u["role"], "tasks.assign"):
            from src import tasks as _tk
            types = "".join(f"<option>{x}</option>" for x in _tk.TASK_TYPES)
            assign = (
                '<section class="ws"><h2>👥 Assign a task for this product</h2>'
                '<form method="post" action="/admin/tasks/create" class="toolbar">'
                f'<input type="hidden" name="related_keyword" value="{_html.escape(q)}">'
                f'<input name="title" value="{_html.escape(q)} — " placeholder="Task" required>'
                f'<select name="assigned_to">{_user_options()}</select>'
                f'<select name="task_type">{types}</select>'
                '<select name="priority"><option>MEDIUM</option><option>HIGH</option>'
                '<option>URGENT</option><option>LOW</option></select>'
                '<button class="primary" type="submit">Assign →</button>'
                '</form><p class="note">Goes to Team Tasks + the assignee\'s My Tasks; '
                'logged in the activity log.</p></section>')
        head = (bar + f'<h1 style="margin:.1em 0 0">Keyword run — '
                f'{_html.escape(q)}</h1>')
        return page(f"Run: {q}", head + ws + approve + assign + WORKSPACE_JS)

    @app.route("/run/approve", methods=["POST"])
    @require_perm("listing.approve")
    def run_approve():
        import html as _html
        from src import workspace, appdb
        u = current_user()
        q = (request.form.get("q") or "").strip()[:80]
        decision = "APPROVED" if request.form.get("decision") == "APPROVED" else "REJECTED"
        note = (request.form.get("note") or "").strip()[:300]
        # Re-verify the gate server-side before recording an approval (never trust
        # the client). Approval requires a genuinely publish-ready run.
        ready = False
        try:
            workspace.build_workspace(q, _run_inputs()[1])
            ready = bool(workspace.build_workspace._last.get("publish_ready"))
        except (SystemExit, Exception):  # noqa: BLE001
            ready = False
        if decision == "APPROVED" and not ready:
            return page("Approval blocked", _bar() + '<article class="md"><h1>Blocked'
                        '</h1><p class="empty">Cannot approve: this run is not '
                        'PUBLISH_READY. Nothing was recorded.</p></article>')
        appdb.execute("INSERT INTO approvals (workspace_id, keyword, decision, "
                      "by_user_id, by_email, note, created_at) VALUES (?,?,?,?,?,?,?)",
                      ("", q, decision, u["user_id"], u["email"], note,
                       activity.datetime.utcnow().isoformat(timespec="seconds")))
        _log("MANAGER_APPROVE" if decision == "APPROVED" else "MANAGER_REJECT",
             module="workspace", keyword=q, summary=note or decision)
        return page("Decision recorded", _bar() + '<article class="md"><h1>'
                    f'{"✅ Approved for manual publish" if decision=="APPROVED" else "Rejected"}'
                    f'</h1><p>Keyword: <b>{_html.escape(q)}</b>. Recorded by '
                    f'{_html.escape(u["email"])}. <b>PUBLISH_AUTOMATION: false</b> — '
                    'publish it yourself on Etsy.</p></article>')

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
            _log("WORKSPACE_SAVE", module="workspace", keyword=q,
                 product_mode=opts.get("supplier_type"))
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
        if q:
            _log(f"PDF_EXPORT_{role.upper()}", module="export", keyword=q,
                 product_mode=opts.get("supplier_type"))
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
            url = _h.escape(_safe_url(r.get("shop_url")))
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
            url = _h.escape(_safe_url(r.get("listing_url")))
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
                _log("SUPPLIER_CSV_UPLOAD", module="suppliers", action=source)
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
                # 6 core fields cover the Day-3/7 call; the rest are optional detail.
                '<input name="listing_url" placeholder="Listing URL" required>'
                '<input name="keyword" placeholder="Main keyword (links the saved run)">'
                '<input name="price" type="number" step="any" placeholder="Price">'
                '<input name="day_7_views" type="number" placeholder="Day 7 views">'
                '<input name="orders" type="number" placeholder="Orders">'
                '<input name="revenue" type="number" step="any" placeholder="Revenue">'
                '<details class="fbmore"><summary>＋ More metrics (optional)</summary>'
                '<div class="fbgrid">'
                '<input name="publish_date" placeholder="Publish date (YYYY-MM-DD)">'
                '<input name="product_mode" placeholder="Mode (pod/embroidery)">'
                '<input name="supplier" placeholder="Supplier">'
                '<input name="product_cost" type="number" step="any" placeholder="Product cost">'
                '<input name="shipping_cost" type="number" step="any" placeholder="Shipping cost">'
                '<input name="title" placeholder="Title">'
                '<input name="main_image_version" placeholder="Main image version (e.g. v2)">'
                '<input name="mockup_style" placeholder="Mockup style (flat / lifestyle / gift)">'
                '<input name="personalization_offer" placeholder="Personalization offered">'
                '<input name="bundle_offer" placeholder="Bundle offered">'
                '<input name="day_1_impressions" type="number" placeholder="Day 1 impressions">'
                '<input name="day_3_views" type="number" placeholder="Day 3 views">'
                '<input name="favorites" type="number" placeholder="Favorites">'
                '<input name="carts" type="number" placeholder="Carts">'
                '<input name="profit" type="number" step="any" placeholder="Profit">'
                '<input name="refund_or_issue" placeholder="Refund / issue (or none)">'
                '</div></details>'
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
        d = {k: (request.form.get(k) or "").strip()[:300] for k in fb.FIELDS}
        fb.add(d)
        _ev = ("FEEDBACK_UPDATE_DAY7" if d.get("day_7_views") else
               "FEEDBACK_UPDATE_DAY3" if d.get("day_3_views") else "FEEDBACK_ADD")
        _log(_ev, module="feedback", keyword=d.get("keyword"),
             product_mode=d.get("product_mode"))
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

    def _risk_toggle(endpoint, mode, show_all):
        params = ([f"mode={mode}"] if mode else []) + ([] if show_all else ["show=all"])
        href = f"/{endpoint}" + ("?" + "&".join(params) if params else "")
        label = "✅ Show launch-ready only" if show_all else "🔎 Show risky / review items"
        return f'<div class="risktoggle"><a class="pullbtn" href="{href}">{label}</a></div>'

    def _mode_tool(fn, title, filterable=False):
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        endpoint = request.path.strip("/")
        show_all = request.args.get("show") == "all"
        from src import interactive
        try:
            switch = _mode_switch(endpoint, mode)
            if filterable:
                switch += _risk_toggle(endpoint, mode, show_all)
                out = fn(interactive, mode, show_all)
            else:
                out = fn(interactive, mode)
            return _render_tool(title, out, switch=switch)
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
        return _mode_tool(lambda iv, m, s: iv.trending(m, s), "Trending now", filterable=True)

    @app.route("/opportunities")
    @login_required
    def opportunities():
        return _mode_tool(lambda iv, m, s: iv.opportunities(m, s), "Opportunities", filterable=True)

    @app.route("/calendar")
    @login_required
    def calendar():
        from src import interactive, seasonal
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        rng = request.args.get("range") or "6mo"
        days = seasonal.RANGES.get(rng, 180)
        # range dropdown (links, keeps the current mode)
        mq = f"mode={mode}&" if mode else ""
        rlabels = [("30d", "30 days"), ("60d", "60 days"), ("90d", "90 days"),
                   ("6mo", "6 months"), ("year", "Full year")]
        rrow = "".join(
            f'<a class="pullbtn{" primary" if rng == rk else ""}" '
            f'href="/calendar?{mq}range={rk}">{rl}</a>' for rk, rl in rlabels)
        rangebar = ('<div class="pullbar"><div class="pulltxt"><b>Range</b>'
                    '<span>How far ahead to plan</span></div>'
                    f'<div class="pullbtns">{rrow}</div></div>')
        try:
            return _render_tool("Seasonal calendar", interactive.calendar(mode, days),
                                switch=_mode_switch("calendar", mode) + rangebar)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Seasonal calendar", exc)

    @app.route("/spy")
    @login_required
    def spy():
        from src import interactive
        raw = (request.args.get("q") or "").strip()[:200]   # room for a listing URL
        m = (request.args.get("supplier_type") or request.args.get("mode") or "").lower()
        mode = m if m in ("pod", "embroidery", "both") else None
        # Accept a keyword OR an Etsy listing URL. spy_target reads the URL's title
        # slug and broadens it to a keyword the index has data for. lid is None for a
        # plain keyword; lid set + empty q = a listing URL with no usable title slug.
        q, lid = interactive.spy_target(raw) if raw else ("", None)
        src_note = ""
        url_no_slug = (lid is not None and not q)
        if lid and q:
            src_note = (f'<p class="note">🔗 Decoded from Etsy listing <b>#{lid}</b> → '
                        f'market keyword "<b>{_h_esc(q)}</b>" (broadened from the title '
                        'so the market data isn\'t empty).</p>')
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        msel = "".join(
            f'<option value="{v}"{" selected" if v == (mode or "pod") else ""}>{lbl}</option>'
            for v, lbl in (("pod", "Print on Demand"), ("embroidery", "Embroidery"),
                           ("both", "Both")))
        form = ('<form method="get" action="/spy" class="toolbar">'
                f'<input name="q" value="{_h_esc(q if not src_note else raw)}" autofocus '
                'placeholder="Keyword  —  or paste an Etsy listing URL">'
                f'<select name="supplier_type" aria-label="Product mode">{msel}</select>'
                '<button class="primary" type="submit">🕵️ Decode competitors</button>'
                '</form>')
        intro = ('<h1>🕵️ Spy + Reverse Engine</h1><p>Give it a <b>keyword</b> or paste an '
                 '<b>Etsy listing URL</b> — Spy finds the competitors ranking for it, '
                 'decodes each one\'s playbook (title / tags / price / image angle), flags '
                 'who just launched, and shows the gaps to beat them. Learning only — '
                 'study structure, never copy.</p>'
                 '<p class="note">Decoding a whole <b>shop</b> isn\'t available — the '
                 'market data source is keyword-level, not per-shop.</p>')
        if not q:
            warn = ('<p class="empty">That Etsy link has no title in it (just the '
                    'listing number). Paste the <b>full</b> URL including the title '
                    'part — e.g. <code>etsy.com/listing/1234567890/personalized-photo-'
                    'badge-reel</code> — so Spy can read the keywords.</p>'
                    if url_no_slug else '')
            return page("Spy", bar + '<article class="md">' + intro + warn + form
                        + '</article>')
        _log("SPY_SEARCH", module="spy", keyword=q, product_mode=mode)
        try:
            body = md.markdown(interactive.spy(q, mode),
                               extensions=["tables", "fenced_code", "sane_lists"])
            return page(f"Spy: {q}", bar + '<article class="md">' + form + src_note
                        + body + '</article>' + COPY_JS)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Spy", exc)

    @app.route("/grade", methods=["GET", "POST"])
    @login_required
    def grade():
        import html as _html
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        # Strip tag-injection chars: the analysis RESULT echoes these back through
        # markdown (raw-HTML passthrough), so neutralize XSS at the boundary.
        title = _no_tags((request.form.get("title") or "").strip())
        tags = _no_tags((request.form.get("tags") or "").strip())
        desc = _no_tags((request.form.get("description") or "").strip())
        kw = _no_tags((request.form.get("keyword") or "").strip())
        img_ok = request.form.get("first_image_ready") == "on"
        sup_ok = request.form.get("supplier_ok") == "on"
        result_html = ""
        if request.method == "POST" and (title or tags or desc):
            from src import interactive
            try:
                out = interactive.analyze_listing(title, tags, desc, kw,
                                                  first_image_ready=img_ok,
                                                  supplier_ok=sup_ok)
                rendered = md.markdown(out, extensions=["tables", "fenced_code",
                                                        "sane_lists"])
                result_html = (f'<article class="md">{rendered}</article>' + COPY_JS)
            except (SystemExit, Exception) as exc:  # noqa: BLE001
                result_html = ('<p class="empty">Could not analyze: '
                               f'{_html.escape(str(exc)[:200])}</p>')
        ck = lambda on: " checked" if on else ""  # noqa: E731
        form = (
            '<article class="md"><h1>📋 Listing Analyzer</h1>'
            '<p class="lead">Paste a draft listing → <b>Listing / SEO / Trust / '
            'Image</b> scores + a hard <b>publish gate</b> with the exact failed '
            'checks. <b>Analysis only — never publishes.</b></p>'
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
            f'<label class="ckrow"><input type="checkbox" name="first_image_ready"'
            f'{ck(img_ok)}> First image confirmed ready (≥ 75 in First Image Battle)</label>'
            f'<label class="ckrow"><input type="checkbox" name="supplier_ok"'
            f'{ck(sup_ok)}> Supplier is SUPPLIER_CONFIRMED</label>'
            '<button class="primary" type="submit">Analyze listing →</button>'
            '</form></article>')
        return page("Listing Analyzer", bar + result_html + form)

    # ---- Alerts Center (internal only — no Etsy automation) ----
    @app.route("/alerts")
    @login_required
    def alerts_page():
        import html as _h
        from src import alerts
        alerts.generate()
        rows = alerts.load()
        order = {"critical": 0, "warn": 1, "info": 2}
        rows.sort(key=lambda r: order.get(r.get("level"), 3))
        items = ""
        for r in rows:
            items += ('<div class="saveditem"><div class="sihead">'
                      f'<span class="pill lvl-{r.get("level")}">{_h.escape(r.get("level",""))}</span> '
                      f'<b>{_h.escape(r.get("message",""))}</b> '
                      f'<a class="cbtn" href="/alerts/resolve/{r.get("id")}">resolve</a>'
                      f'</div><div class="note">{_h.escape(r.get("kind",""))} · '
                      f'{_h.escape(r.get("source",""))} · {r.get("updated_at","")}</div></div>')
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page("Alerts", bar + '<article class="md"><h1>🔔 Alerts Center</h1>'
                    '<p>Internal only — no Etsy automation, no publishing. Auto-refreshed '
                    'from system state + the 6 AM run.</p>'
                    + (items or '<p class="empty">✅ Nothing needs attention right now.</p>')
                    + '</article>')

    @app.route("/alerts/resolve/<int:aid>")
    @login_required
    def alerts_resolve(aid):
        from src import alerts
        alerts.resolve(aid)
        return redirect(url_for("alerts_page"))

    # ---- Launchpad (launch status board) ----
    @app.route("/launchpad")
    @login_required
    def launchpad_page():
        import html as _h
        from src import launchpad as lp
        u = current_user()
        can_assign = auth.has_perm(u["role"], "tasks.assign")
        b = lp.board()

        def _card_html(card):
            kw = _h.escape(str(card["keyword"])[:40])
            assign = (f'<a class="cbtn" href="/admin/tasks?keyword={_h.escape(str(card["keyword"]))}">'
                      '+ Assign task</a>' if can_assign else "")
            return ('<div class="lpcard"><b>' + kw + '</b>'
                    f'<span class="pill">{_h.escape(card.get("mode",""))}</span>'
                    f'<div class="note">{_h.escape(card.get("next_action",""))}</div>'
                    + assign + '</div>')

        cols = ""
        for c in lp.COLUMNS:
            cards = b.get(c, [])
            body = "".join(_card_html(card) for card in cards)
            cols += (f'<div class="lpcol"><h3>{_h.escape(c)} '
                     f'<span class="count">{len(cards)}</span></h3>{body or "<p class=note>—</p>"}</div>')
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        pulse = '<div class="tkstats">' + "".join(
            f'<div class="tkstat"><span class="n">{len(b.get(c, []))}</span>'
            f'<span class="l">{_h.escape(c)}</span></div>' for c in lp.COLUMNS) + '</div>'
        return page("Launchpad", bar + '<article class="md"><h1>🚀 Launchpad</h1>'
                    '<p class="tklead">Every idea, from spark to scale. Cards move '
                    'themselves as you save runs and log results — your job is to keep '
                    'them flowing right. <b>No auto-publishing</b>, ever.</p>'
                    + pulse + '</article><div class="lpboard">' + cols + '</div>')

    # ---- Market & keyword trackers ----
    @app.route("/trackers")
    @login_required
    def trackers_page():
        import html as _h
        from src import tracking as tk
        def tbl(rows, kind):
            if not rows:
                return ('<p class="empty">No ' + kind + ' tracked yet — the 6 AM '
                        'run fills this automatically, or track one below.</p>')
            head = ("<table><tr><th>Keyword</th><th>Trend</th><th>Demand/24h</th>"
                    "<th>Conv</th><th>Listings</th><th>Avg $</th><th>Snaps</th>"
                    "<th>Action</th></tr>") if kind == "keywords" else (
                    "<table><tr><th>Niche</th><th>Trend</th><th>Demand/24h</th>"
                    "<th>Listings</th><th>Sellers</th><th>Avg $</th><th>Snaps</th></tr>")
            out = [head]
            for r in rows:
                if kind == "keywords":
                    out.append(f"<tr><td>{_h.escape(r['keyword'])}</td>"
                               f"<td><b>{r['trend']}</b></td><td>{r.get('demand_24h','-')}</td>"
                               f"<td>{r.get('conversion','-')}</td><td>{r.get('listings','-')}</td>"
                               f"<td>${r.get('avg_price','-')}</td><td>{r['snapshots']}</td>"
                               f"<td>{r['action']}</td></tr>")
                else:
                    out.append(f"<tr><td>{_h.escape(r['niche'])}</td>"
                               f"<td><b>{r['trend']}</b></td><td>{r.get('demand_24h','-')}</td>"
                               f"<td>{r.get('listings','-')}</td><td>{r.get('sellers','-')}</td>"
                               f"<td>${r.get('avg_price','-')}</td><td>{r['snapshots']}</td></tr>")
            return "".join(out) + "</table>"
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        addf = ('<form method="post" action="/trackers/add" class="toolbar">'
                '<input name="keyword" placeholder="Track a keyword or niche now">'
                '<button class="primary" name="kind" value="keyword">Track keyword</button>'
                '<button name="kind" value="market">Track market</button></form>')
        return page("Trackers", bar + '<article class="md"><h1>📊 Market &amp; keyword '
                    'tracker</h1><p>Trends over time from the official index — rising / '
                    'falling / stable. The 6 AM run snapshots automatically.</p>' + addf
                    + '<h2>Keywords</h2>' + tbl(tk.keyword_rows(), "keywords")
                    + '<h2>Markets</h2>' + tbl(tk.market_rows(), "markets") + '</article>')

    @app.route("/trackers/add", methods=["POST"])
    @login_required
    def trackers_add():
        from src import tracking as tk
        q = (request.form.get("keyword") or "").strip()[:80]
        kind = request.form.get("kind")
        if q:
            try:
                if kind == "market":
                    tk.snapshot_market(q)
                else:
                    tk.snapshot_keyword(q)
            except (SystemExit, Exception):  # noqa: BLE001
                pass
        return redirect(url_for("trackers_page"))

    # ---- Profit Center ----
    @app.route("/profit", methods=["GET", "POST"])
    @login_required
    def profit_page():
        import html as _h
        from src import profit as pf
        if request.method == "POST":
            pf.add({k: (request.form.get(k) or "").strip() for k in
                    ("keyword", "product_mode", "supplier", "sale_price",
                     "product_cost", "shipping_cost", "offsite_ad",
                     "refund_or_issue", "notes")})
            return redirect(url_for("profit_page"))
        s = pf.summary()
        sup_rows = "".join(
            f"<tr><td>{_h.escape(k)}</td><td>{v['sales']}</td>"
            f"<td>${v['net']:.2f}</td><td>{v['avg_margin']*100:.0f}%</td></tr>"
            for k, v in s["by_supplier"].items())
        form = ('<form method="post" action="/profit" class="gradeform">'
                '<label>Keyword<input name="keyword"></label>'
                '<label>Mode<input name="product_mode" placeholder="pod/embroidery"></label>'
                '<label>Supplier<input name="supplier"></label>'
                '<label>Sale price<input name="sale_price" type="number" step="any"></label>'
                '<label>Product cost<input name="product_cost" type="number" step="any"></label>'
                '<label>Shipping cost<input name="shipping_cost" type="number" step="any"></label>'
                '<label class="ckrow"><input type="checkbox" name="offsite_ad" value="yes">'
                ' Came from an Etsy offsite ad (15% fee)</label>'
                '<label>Refund / issue<input name="refund_or_issue" placeholder="or none"></label>'
                '<button class="primary" type="submit">Log sale + compute profit</button></form>')
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        netcls = " good" if s["net_total"] > 0 else (" bad" if s["net_total"] < 0 else "")
        ptiles = [("Sales logged", str(s["sales"]), ""),
                  ("Net profit", f'${s["net_total"]:,.0f}', netcls),
                  ("Suppliers", str(len(s.get("by_supplier", {}))), ""),
                  ("Product lines", str(len(s.get("by_mode", {}))), "")]
        ppulse = '<div class="tkstats">' + "".join(
            f'<div class="tkstat{c}"><span class="n">{v}</span>'
            f'<span class="l">{l}</span></div>' for l, v, c in ptiles) + '</div>'
        return page("Profit Center", bar + '<article class="md"><h1>💰 Profit Center</h1>'
                    '<p class="tklead">Real money, not guesses. Every logged sale runs '
                    'through the Etsy fee model and sharpens your supplier scores — so '
                    'you double down on what actually pays.</p>' + ppulse
                    + ('<h2>By supplier</h2><table><tr><th>Supplier</th><th>Sales</th>'
                       f'<th>Net</th><th>Avg margin</th></tr>{sup_rows}</table>'
                       if sup_rows else '')
                    + form + '</article>')

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
        src = ('<p class="note">📌 A <b>saved snapshot</b> from a CLI '
               '<code>expand</code> run — the numbers are from the <b>YTrends index</b> '
               '(not a log of staff searches). For a <b>live</b> lookup use '
               '<a href="/">Command Center → Expand keywords</a>.</p>')
        return page("Keyword Research",
                    bar + f'<article class="md">{src}{html}</article>' + COPY_JS)

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

    # ---- team workflow guide (served from the repo's WORKFLOW.md) ----
    @app.route("/workflow")
    @login_required
    def workflow():
        p = ROOT / "WORKFLOW.md"
        if not p.is_file():
            abort(404)
        html = md.markdown(p.read_text(encoding="utf-8"),
                           extensions=["tables", "fenced_code", "sane_lists"])
        bar = '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'
        return page("Team Workflow",
                    bar + f'<article class="md">{html}</article>' + COPY_JS)

    # ======================= TEAM MANAGEMENT =======================
    def _bar():
        return '<div class="rbar"><a class="back" href="/">&larr; Home</a></div>'

    def _user_options(sel=None):
        from src import auth as _a
        return "".join(
            f'<option value="{u["user_id"]}"'
            + (" selected" if sel == u["user_id"] else "") + ">"
            f'{_h_esc(u["display_name"])} ({u["role"]})</option>'
            for u in _a.list_users() if u["status"] == "ACTIVE")

    def _h_esc(s):
        import html as _h
        return _h.escape(str(s or ""))

    @app.route("/team")
    @login_required
    def team_hub():
        u = current_user()
        cards = ['<a class="toolcard" href="/me/tasks"><b>✅ My Tasks</b>'
                 '<span>What you\'re assigned</span></a>',
                 '<a class="toolcard" href="/team/calendar"><b>📅 Team Calendar</b>'
                 '<span>Tasks by due date — today / week / overdue</span></a>']
        if auth.has_perm(u["role"], "tasks.assign"):
            cards.append('<a class="toolcard" href="/admin/tasks"><b>📋 Team Tasks</b>'
                         '<span>Assign + track everyone\'s work</span></a>')
        if auth.has_perm(u["role"], "tasks.review"):
            cards.append('<a class="toolcard" href="/admin/reviews"><b>🔍 Review Queue</b>'
                         '<span>Approve / reject submitted work</span></a>')
        if auth.has_perm(u["role"], "logs.view_all"):
            cards.append('<a class="toolcard" href="/admin/activity"><b>📈 Activity Log</b>'
                         '<span>Who did what in the dashboard</span></a>')
        if auth.has_perm(u["role"], "users.manage"):
            cards.append('<a class="toolcard" href="/admin/users"><b>👥 User Management</b>'
                         '<span>Create / edit / disable team members</span></a>')
        from src import toolfeedback as tfb
        if auth.has_perm(u["role"], "logs.view_all"):
            n = tfb.counts()["open"]
            badge = f' — {n} open' if n else ''
            cards.append('<a class="toolcard" href="/team/feedback"><b>💬 Tool Feedback</b>'
                         f'<span>Review what the team suggests{badge}</span></a>')
        else:
            cards.append('<a class="toolcard" href="/team/feedback"><b>💬 Tool Feedback</b>'
                         '<span>Suggest an improvement / report a bug</span></a>')
        cards.append('<a class="toolcard" href="/me"><b>👤 My Profile</b>'
                     '<span>Your role + recent activity</span></a>')
        return page("Team", _bar() + '<article class="md"><h1>👥 Team</h1>'
                    f'<p>Signed in as <b>{_h_esc(u["display_name"])}</b> ({u["role"]}).'
                    '</p></article><div class="toolgrid">' + "".join(cards) + '</div>')

    @app.route("/team/calendar")
    @login_required
    def team_calendar():
        from src import tasks as tk
        from datetime import date, timedelta
        u = current_user()
        view = request.args.get("view", "week")
        # managers see everyone; members see their own
        rows = (tk.list_tasks() if auth.has_perm(u["role"], "tasks.assign")
                else tk.list_tasks(assigned_to=u["user_id"]))
        by_id = {x["user_id"]: x for x in auth.list_users()}
        today = date.today().isoformat()
        wk = (date.today() + timedelta(days=7)).isoformat()

        def keep(t):
            due = (t.get("due_date") or "")[:10]
            open_ = t["status"] in tk.OPEN_STATUSES
            if view == "overdue":
                return tk.is_overdue(t)
            if view == "all":
                return True
            if not due:
                return False
            if view == "today":
                return due == today and open_
            if view == "week":
                return today <= due <= wk and open_
            if view == "upcoming":
                return due >= today and open_
            return True

        shown = sorted((t for t in rows if keep(t)),
                       key=lambda t: (t.get("due_date") or "9999-99-99"))
        views = [("today", "Today"), ("week", "This week"), ("overdue", "Overdue"),
                 ("upcoming", "Upcoming"), ("all", "All")]
        vrow = "".join(f'<a class="pullbtn{" primary" if view == vk else ""}" '
                       f'href="/team/calendar?view={vk}">{vl}</a>' for vk, vl in views)
        viewbar = ('<div class="pullbar"><div class="pulltxt"><b>View</b>'
                   '<span>Filter tasks by due date</span></div>'
                   f'<div class="pullbtns">{vrow}</div></div>')
        body = ""
        for t in shown:
            who = by_id.get(t["assigned_to_user_id"], {}).get("display_name", "—")
            odc = " od" if tk.is_overdue(t) else ""
            body += (f'<tr class="pr-{(t["priority"] or "medium").lower()}">'
                     f'<td class="{odc.strip()}">{_h_esc((t.get("due_date") or "—")[:10])}</td>'
                     f'<td>{_h_esc(t["title"])}</td><td>{_h_esc(who)}</td>'
                     f'<td>{_h_esc(t.get("related_keyword"))}</td>'
                     f'<td>{_h_esc(t["status"])}</td>'
                     f'<td><span class="pill pr-{(t["priority"] or "medium").lower()}">'
                     f'{_h_esc(t["priority"])}</span></td></tr>')
        table = ('<table><tr><th>Due</th><th>Task</th><th>Assignee</th><th>Keyword</th>'
                 '<th>Status</th><th>Priority</th></tr>'
                 + (body or '<tr><td colspan="6">No tasks in this view.</td></tr>')
                 + '</table>')
        return page("Team Calendar", _bar() + viewbar
                    + '<article class="md"><h1>📅 Team Calendar</h1>'
                    '<p class="note">Tasks by due date (overdue in red). Update status '
                    'in <a href="/me/tasks">My Tasks</a>; approve in the '
                    '<a href="/admin/reviews">Review Queue</a>.</p>' + table + '</article>')

    # ---- Tool Feedback (team suggestions ABOUT the tool) ----
    def _feedback_items(rows, is_mgr, show_author):
        out = ""
        for r in rows:
            resolved = r["status"] == "resolved"
            pill = ('<span class="pill apill">✓ Resolved</span>' if resolved
                    else '<span class="pill">Open</span>')
            who = f' — {_h_esc(r["author"])}' if show_author else ''
            meta = (f'resolved by {_h_esc(r["resolved_by"])}'
                    if resolved and r["resolved_by"] else '')
            btn = ""
            if is_mgr:
                to = "open" if resolved else "resolved"
                label = "Reopen" if resolved else "✓ Mark resolved"
                btn = (f'<form method="post" action="/team/feedback/resolve/{r["id"]}"'
                       ' style="display:inline;margin:0">'
                       f'<input type="hidden" name="to" value="{to}">'
                       '<button class="cbtn" type="submit" style="background:none;'
                       f'border:0;cursor:pointer">{label}</button></form>')
            out += ('<div class="saveditem"><div class="sihead">'
                    f'<b>[{_h_esc(r["category"])}]{who}</b> {pill} {btn}</div>'
                    f'<div style="margin:6px 0;white-space:pre-wrap">'
                    f'{_h_esc(r["message"])}</div>'
                    f'<div class="note">{_h_esc((r["created_at"] or "")[:16])} {meta}</div>'
                    '</div>')
        return out or '<p class="note">Nothing yet.</p>'

    @app.route("/team/feedback")
    @login_required
    def team_feedback():
        from src import toolfeedback as tfb
        u = current_user()
        is_mgr = auth.has_perm(u["role"], "logs.view_all")
        thanks = ('<p class="note">✅ Thanks — your feedback was sent to the owner.'
                  '</p>' if request.args.get("ok") else '')
        cats = "".join(f'<option value="{c}">{c.title()}</option>'
                       for c in tfb.CATEGORIES)
        form = ('<form class="savedform" method="post" action="/team/feedback/add">'
                f'<select name="category">{cats}</select>'
                '<textarea name="message" required placeholder="What should we '
                'improve, add, or fix? Be specific — the screen name + what happened '
                'helps."></textarea>'
                '<button type="submit">Send feedback</button></form>')
        if is_mgr:
            c = tfb.counts()
            listing = (f'<h2>Team feedback — {c["open"]} open · {c["resolved"]} '
                       f'resolved</h2>{_feedback_items(tfb.list_all(), True, True)}')
        else:
            listing = ('<h2>Your feedback</h2>'
                       + _feedback_items(tfb.list_by_user(u["user_id"]), False, False))
        return page("Tool Feedback", _bar() + '<article class="md">'
                    '<h1>💬 Tool Feedback</h1><p>Tell us what to improve, add, or fix '
                    'in this tool — bugs, ideas, anything confusing. The owner reviews '
                    'every note.</p>' + thanks + form + listing + '</article>')

    @app.route("/team/feedback/add", methods=["POST"])
    @login_required
    def team_feedback_add():
        from src import toolfeedback as tfb
        u = current_user()
        tfb.submit(u["user_id"], u["display_name"],
                   request.form.get("message"), request.form.get("category"))
        _log("TOOL_FEEDBACK_SUBMIT", module="team")
        return redirect(url_for("team_feedback", ok=1))

    @app.route("/team/feedback/resolve/<int:fid>", methods=["POST"])
    @require_perm("logs.view_all")
    def team_feedback_resolve(fid):
        from src import toolfeedback as tfb
        u = current_user()
        to_resolved = request.form.get("to") != "open"
        tfb.set_resolved(fid, to_resolved, resolver_name=u["display_name"])
        _log("TOOL_FEEDBACK_RESOLVE", module="team",
             summary=f"#{fid} {'resolved' if to_resolved else 'reopened'}")
        return redirect(url_for("team_feedback"))

    # ---- My Tasks ----
    @app.route("/me/tasks")
    @login_required
    def my_tasks():
        from src import tasks as tk
        u = current_user()
        rows = tk.list_tasks(assigned_to=u["user_id"])
        overdue = [t for t in rows if tk.is_overdue(t)]
        oid = {t["task_id"] for t in overdue}
        due_soon = [t for t in rows if tk.is_due_soon(t)
                    and t["status"] in ("TODO", "IN_PROGRESS", "BLOCKED")]
        skip = oid | {t["task_id"] for t in due_soon}
        buckets = [
            ("🔴 Overdue", overdue),
            ("🟠 Due soon", due_soon),
            ("⚪ To do", [t for t in rows if t["status"] == "TODO" and t["task_id"] not in skip]),
            ("🔵 In progress", [t for t in rows if t["status"] in ("IN_PROGRESS", "BLOCKED") and t["task_id"] not in skip]),
            ("🕓 Awaiting review", [t for t in rows if t["status"] == "READY_FOR_REVIEW" and t["task_id"] not in oid]),
        ]

        def card(t):
            actions = "".join(
                '<form method="post" action="/me/tasks/status" class="inlineform">'
                f'<input type="hidden" name="task_id" value="{t["task_id"]}">'
                f'<input type="hidden" name="status" value="{tgt}">'
                f'<button class="tkbtn{" primary" if prim else ""}" type="submit">{lbl}</button>'
                '</form>' for (lbl, tgt, prim) in tk.member_actions(t["status"]))
            due = (t.get("due_date") or "")[:10]
            duehtml = (f' · <span class="due{" od" if tk.is_overdue(t) else ""}">due {_h_esc(due)}</span>'
                       if due else "")
            guide = tk.TYPE_GUIDE.get(t["task_type"], "")
            rev = ""
            if t["review_status"] != "NOT_REVIEWED":
                rev = (f'<div class="note">Review: <b>{_h_esc(t["review_status"])}</b>'
                       + (f' — {_h_esc(t.get("review_notes"))}' if t.get("review_notes") else "")
                       + '</div>')
            return ('<div class="tkcard pr-' + (t["priority"] or "medium").lower() + '">'
                    '<div class="tkhead"><b>' + _h_esc(t["title"]) + '</b>'
                    f'<span class="pill pr-{(t["priority"] or "medium").lower()}">{_h_esc(t["priority"])}</span></div>'
                    f'<div class="note">{_h_esc(t.get("task_type") or "")}'
                    + (f' · {_h_esc(t.get("related_keyword"))}' if t.get("related_keyword") else "")
                    + duehtml + '</div>'
                    + (f'<div class="tkguide">🎯 {_h_esc(guide)}</div>' if guide else "")
                    + rev
                    + (f'<div class="tkactions">{actions}</div>' if actions else "")
                    + '</div>')

        body = ""
        for label, items in buckets:
            if items:
                body += (f'<h2 class="tkgroup">{label} <span class="count">{len(items)}'
                         '</span></h2>' + "".join(card(t) for t in items))
        if not body:
            body = '<p class="empty">No open tasks — you\'re all caught up. 🎉</p>'
        return page("My Tasks", _bar() + '<article class="md"><h1>✅ My Tasks</h1>'
                    '<p class="note">Your assigned work, most urgent first. Click '
                    '<b>Start</b> → <b>Submit for review</b> as you go.</p>'
                    + body + '</article>')

    @app.route("/me/tasks/status", methods=["POST"])
    @login_required
    def my_task_status():
        from src import tasks as tk
        u = current_user()
        tid = int(request.form.get("task_id") or 0)
        t = tk.get_task(tid)
        if t and t["assigned_to_user_id"] == u["user_id"]:
            tk.update_task(tid, status=request.form.get("status"))
            _log("TASK_STATUS_CHANGE", module="tasks", entity_type="task",
                 entity_id=tid, summary=request.form.get("status"))
        return redirect(url_for("my_tasks"))

    # ---- Team Tasks (assign) ----
    def _task_fields(task=None, pk="", ptype=""):
        """Shared form fields for New task + Edit task (keeps them identical)."""
        from src import tasks as tk
        sel = lambda cur, x: " selected" if x == cur else ""
        t = task or {}
        cur_title = _h_esc(t.get("title") or ((pk + " — ") if pk else ""))
        cur_kw = _h_esc(t.get("related_keyword") or pk)
        cur_type = t.get("task_type") or ptype
        cur_prio = t.get("priority") or "MEDIUM"
        due = (t.get("due_date") or "")[:16]
        if len(due) == 10:                 # old date-only value -> give the picker a time
            due += "T09:00"
        types = "".join(f'<option{sel(cur_type, x)}>{x}</option>' for x in tk.TASK_TYPES)
        prios = "".join(f'<option{sel(cur_prio, x)}>{x}</option>' for x in tk.PRIORITIES)
        return (
            f'<label>Title<input name="title" value="{cur_title}" required></label>'
            f'<label>Assign to<select name="assigned_to">'
            f'{_user_options(t.get("assigned_to_user_id"))}</select></label>'
            f'<label>Type<select name="task_type">{types}</select></label>'
            f'<label>Priority<select name="priority">{prios}</select></label>'
            f'<label>Keyword<input name="related_keyword" value="{cur_kw}"></label>'
            '<label>Due date &amp; time<input type="datetime-local" name="due_date" '
            f'value="{due}"></label>')

    @app.route("/admin/tasks")
    @require_perm("tasks.assign")
    def team_tasks():
        from src import tasks as tk
        rows = tk.list_tasks()
        by_id = {u["user_id"]: u for u in auth.list_users()}
        pk = _h_esc(request.args.get("keyword") or "")
        ptype = request.args.get("type") or ""

        # team pulse — the board at a glance (management feel)
        overdue = sum(1 for t in rows if tk.is_overdue(t))
        tiles = [("Active", sum(1 for t in rows if t["status"] in tk.OPEN_STATUSES), ""),
                 ("In progress", sum(1 for t in rows if t["status"] in ("IN_PROGRESS", "BLOCKED")), ""),
                 ("In review", sum(1 for t in rows if t["status"] == "READY_FOR_REVIEW"), ""),
                 ("Overdue", overdue, " bad" if overdue else ""),
                 ("Completed", sum(1 for t in rows if t["status"] in ("APPROVED", "DONE")), " good")]
        pulse = '<div class="tkstats">' + "".join(
            f'<div class="tkstat{c}"><span class="n">{n}</span><span class="l">{l}</span></div>'
            for l, n, c in tiles) + '</div>'

        form = ('<details class="tknew"' + (" open" if pk else "") + '>'
                '<summary>➕ New task</summary>'
                '<form method="post" action="/admin/tasks/create" class="gradeform">'
                + _task_fields(pk=pk, ptype=ptype)
                + '<button class="primary" type="submit">Create + assign task</button>'
                '</form></details>')

        board = [("⚪ To do", ("TODO",)), ("🔵 In progress", ("IN_PROGRESS", "BLOCKED")),
                 ("🕓 Awaiting review", ("READY_FOR_REVIEW",)),
                 ("✅ Done", ("APPROVED", "DONE", "REJECTED"))]
        cols = ""
        for label, statuses in board:
            cards = [t for t in rows if t["status"] in statuses]
            body = ""
            for t in cards:
                name = by_id.get(t["assigned_to_user_id"], {}).get("display_name") or "Unassigned"
                initials = ("".join(w[0] for w in name.split()[:2]).upper() or "•")
                od = tk.is_overdue(t)
                due = (t.get("due_date") or "")
                prio = (t["priority"] or "medium").lower()
                duebadge = (f'<span class="tkdue{" od" if od else ""}">🕒 '
                            f'{_h_esc(due[:16].replace("T", " "))}</span>' if due else '')
                body += (
                    f'<div class="tkcard pr-{prio}">'
                    f'<div class="tkwho"><span class="tkinit" title="{_h_esc(name)}">'
                    f'{_h_esc(initials)}</span>'
                    f'<span class="tkname">{_h_esc(name)}</span></div>'
                    f'<b class="tktitle">{_h_esc(t["title"][:52])}</b>'
                    f'<div class="tkmeta">{_h_esc(t.get("task_type") or "—")}'
                    f'<span class="pill pr-{prio}">{_h_esc(t["priority"])}</span></div>'
                    f'<div class="tkfoot">{duebadge}'
                    f'<a class="cbtn" href="/admin/tasks/{t["task_id"]}/edit">✏️ Edit</a>'
                    '</div></div>')
            cols += (f'<div class="lpcol"><h3>{label} <span class="count">{len(cards)}'
                     f'</span></h3>{body or "<p class=note>—</p>"}</div>')
        return page("Team Tasks", _bar()
                    + '<article class="md"><h1>📋 Team Tasks</h1>'
                    '<p class="tklead">Great products ship when everyone knows their next '
                    'move. Assign the work, watch it flow left → right, and clear the board '
                    'together — momentum is a team sport.</p>'
                    + pulse + form + '</article><div class="lpboard">' + cols + '</div>')

    @app.route("/admin/tasks/create", methods=["POST"])
    @require_perm("tasks.assign")
    def team_task_create():
        from src import tasks as tk
        u = current_user()
        assignee = int(request.form.get("assigned_to") or 0) or None
        t = tk.create_task(
            title=(request.form.get("title") or "").strip()[:200],
            assigned_to_user_id=assignee, assigned_by_user_id=u["user_id"],
            task_type=request.form.get("task_type"),
            priority=request.form.get("priority"),
            related_keyword=(request.form.get("related_keyword") or "").strip()[:120],
            due_date=(request.form.get("due_date") or "").strip()[:20])
        _log("TASK_CREATE", module="tasks", entity_type="task", entity_id=t["task_id"],
             summary=t["title"])
        _log("TASK_ASSIGN", module="tasks", entity_type="task", entity_id=t["task_id"],
             summary=f"-> user {assignee}")
        return redirect(url_for("team_tasks"))

    @app.route("/admin/tasks/<int:tid>/edit")
    @require_perm("tasks.assign")
    def team_task_edit(tid):
        from src import tasks as tk
        t = tk.get_task(tid)
        if not t:
            return redirect(url_for("team_tasks"))
        statuses = "".join(f'<option{" selected" if x == t["status"] else ""}>{x}</option>'
                           for x in tk.STATUSES)
        who = _h_esc(t.get("related_keyword") or t["title"])
        form = (f'<form method="post" action="/admin/tasks/{tid}/edit" class="gradeform">'
                + _task_fields(task=t)
                + f'<label>Status<select name="status">{statuses}</select></label>'
                + '<div class="tkactions"><button class="primary" type="submit">'
                'Save changes</button>'
                '<a class="tkbtn" href="/admin/tasks">Cancel</a></div></form>')
        return page("Edit task", _bar() + '<article class="md"><h1>✏️ Edit task</h1>'
                    f'<p class="note">Editing task #{tid} — {who}. Change the assignee, '
                    'priority, status, due date/time, or details.</p>' + form + '</article>')

    @app.route("/admin/tasks/<int:tid>/edit", methods=["POST"])
    @require_perm("tasks.assign")
    def team_task_edit_save(tid):
        from src import tasks as tk
        assignee = int(request.form.get("assigned_to") or 0) or None
        tk.update_task(
            tid, status=request.form.get("status"),
            priority=request.form.get("priority"), assigned_to_user_id=assignee,
            title=(request.form.get("title") or "").strip()[:200],
            task_type=request.form.get("task_type"),
            related_keyword=(request.form.get("related_keyword") or "").strip()[:120],
            due_date=(request.form.get("due_date") or "").strip()[:20])
        _log("TASK_UPDATE", module="tasks", entity_type="task", entity_id=tid,
             summary="edited")
        return redirect(url_for("team_tasks"))

    # ---- Review Queue ----
    @app.route("/admin/reviews")
    @require_perm("tasks.review")
    def reviews():
        from src import tasks as tk
        rows = tk.review_queue()
        items = ""
        for t in rows:
            items += ('<div class="saveditem"><div class="sihead">'
                      f'<b>{_h_esc(t["title"])}</b> '
                      f'<span class="pill">{_h_esc(t["task_type"])}</span></div>'
                      f'<div class="note">{_h_esc(t.get("related_keyword"))}</div>'
                      '<form method="post" action="/admin/reviews/act" class="toolbar">'
                      f'<input type="hidden" name="task_id" value="{t["task_id"]}">'
                      '<input name="notes" placeholder="Review notes">'
                      '<button class="primary" name="decision" value="APPROVED">Approve</button>'
                      '<button name="decision" value="NEEDS_FIX">Needs fix</button>'
                      '<button name="decision" value="REJECTED">Reject</button>'
                      '</form></div>')
        return page("Review Queue", _bar() + '<article class="md"><h1>🔍 Review Queue</h1>'
                    '<p>Work submitted as READY_FOR_REVIEW.</p>'
                    + (items or '<p class="empty">Nothing waiting for review.</p>')
                    + '</article>')

    @app.route("/admin/reviews/act", methods=["POST"])
    @require_perm("tasks.review")
    def reviews_act():
        from src import tasks as tk
        u = current_user()
        tid = int(request.form.get("task_id") or 0)
        decision = request.form.get("decision") or "APPROVED"
        tk.review_task(tid, u["user_id"], decision, request.form.get("notes") or "")
        _log("TASK_REVIEW_APPROVE" if decision == "APPROVED" else "TASK_REVIEW_REJECT",
             module="tasks", entity_type="task", entity_id=tid, summary=decision)
        return redirect(url_for("reviews"))

    # ---- User Management (OWNER/ADMIN) ----
    @app.route("/admin/users")
    @require_perm("users.manage")
    def admin_users():
        rows = ""
        for u in auth.list_users():
            role_sel = "".join(f'<option{" selected" if u["role"]==r else ""}>{r}</option>'
                               for r in auth.ROLES)
            rows += ('<tr><td>' + _h_esc(u["email"]) + '</td><td>' + _h_esc(u["display_name"])
                     + '</td><td><form method="post" action="/admin/users/role" class="inlineform">'
                     f'<input type="hidden" name="email" value="{_h_esc(u["email"])}">'
                     f'<select name="role" onchange="this.form.submit()">{role_sel}</select></form></td>'
                     '<td>' + _h_esc(u["status"]) + '</td><td>' + _h_esc(u.get("last_login_at") or "—")
                     + '</td><td>'
                     f'<a class="cbtn" href="/admin/users/disable?email={_h_esc(u["email"])}">disable</a>'
                     '</td></tr>')
        roles_opt = "".join(f"<option>{r}</option>" for r in auth.ROLES)
        form = ('<form method="post" action="/admin/users/create" class="gradeform">'
                '<label>Email<input name="email" type="email" required></label>'
                '<label>Display name<input name="display_name" required></label>'
                '<label>Temporary password<input name="password" required></label>'
                f'<label>Role<select name="role">{roles_opt}</select></label>'
                '<button class="primary" type="submit">Create user</button></form>')
        return page("User Management", _bar() + '<article class="md"><h1>👥 User Management</h1>'
                    + form + '<table><tr><th>Email</th><th>Name</th><th>Role</th>'
                    '<th>Status</th><th>Last login</th><th></th></tr>' + rows
                    + '</table><p class="note">Reset a password from the CLI: '
                    '<code>py main.py auth reset-password --email x --password New123!</code></p>'
                    '</article>')

    @app.route("/admin/users/create", methods=["POST"])
    @require_perm("users.manage")
    def admin_users_create():
        u = current_user()
        try:
            auth.create_user(request.form.get("email"), request.form.get("password"),
                             (request.form.get("display_name") or "").strip()[:80],
                             request.form.get("role") or "VIEWER",
                             created_by=u["email"], must_change=True)
            _log("TASK_CREATE", module="users", action="create_user",
                 summary=request.form.get("email"))
        except Exception:  # noqa: BLE001
            pass
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/role", methods=["POST"])
    @require_perm("users.manage")
    def admin_users_role():
        target = request.form.get("email")
        # only OWNER may change another OWNER
        tu = auth.get_user_by_email(target or "")
        if tu and tu["role"] == "OWNER" and current_user()["role"] != "OWNER":
            return redirect(url_for("admin_users"))
        try:
            auth.set_role(target, request.form.get("role"))
        except Exception:  # noqa: BLE001
            pass
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/disable")
    @require_perm("users.manage")
    def admin_users_disable():
        target = request.args.get("email") or ""
        tu = auth.get_user_by_email(target)
        if tu and tu["role"] == "OWNER":
            return redirect(url_for("admin_users"))   # never disable an OWNER here
        auth.disable_user(target)
        return redirect(url_for("admin_users"))

    # ---- Activity Log ----
    @app.route("/admin/activity")
    @require_perm("logs.view_all")
    def admin_activity():
        f_user = request.args.get("user") or None
        f_type = request.args.get("type") or None
        rows = activity.list_events(
            user_id=int(f_user) if (f_user or "").isdigit() else None,
            event_type=f_type, keyword=request.args.get("kw") or None, limit=300)
        body = "".join(
            '<tr><td>' + _h_esc(r["timestamp"]) + '</td><td>' + _h_esc(r["user_email"])
            + '</td><td>' + _h_esc(r["user_role"]) + '</td><td>' + _h_esc(r["event_type"])
            + '</td><td>' + _h_esc(r.get("keyword") or r.get("module") or "")
            + '</td><td>' + ("✓" if r["success"] else "✗") + '</td></tr>' for r in rows)
        return page("Activity Log", _bar() + '<article class="md"><h1>📈 Activity Log</h1>'
                    '<p><a class="cbtn" href="/admin/activity/export">Export CSV</a> · '
                    'showing the latest 300 events (dashboard actions only — no '
                    'keystrokes, screens, or private data).</p>'
                    '<table><tr><th>When</th><th>User</th><th>Role</th><th>Event</th>'
                    '<th>Detail</th><th>OK</th></tr>' + body + '</table></article>')

    @app.route("/admin/activity/export")
    @require_perm("logs.view_all")
    def admin_activity_export():
        path, n = activity.export_csv("data/exports/activity_log.csv")
        return page("Export", _bar() + '<article class="md"><h1>Activity exported</h1>'
                    f'<p>{n} events written to <code>{path}</code> on the server.</p>'
                    '</article>')

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

    secret = (os.getenv("APP_SECRET_KEY") or os.getenv("WEB_SECRET")
              or os.urandom(24).hex())
    # Per-user login now. Seed the first OWNER from .env on first run so nobody
    # is locked out; after that, manage users with `py main.py auth ...`.
    from src import auth
    auth.appdb.init_db()
    seeded = auth.seed_admin_from_env()
    if seeded:
        print(f"Seeded first OWNER account: {seeded['email']}")
    if auth.user_count() == 0:
        print("No users yet. Create the first admin:")
        print('  py main.py auth create-admin --email you@example.com '
              '--password "StrongPass123!" --name "You"')
        print("(or set ADMIN_EMAIL + ADMIN_PASSWORD_INITIAL in .env and restart)")

    if host == "0.0.0.0":
        print("WARNING: binding 0.0.0.0 exposes this on your network. Prefer "
              "the default 127.0.0.1 + a Cloudflare Tunnel for teams.")
    app = build_app(os.getenv("WEB_PASSWORD", ""), secret)
    print(f"Etsy Product Manager report portal -> http://{host}:{port}")
    print("Team members log in with their own email + password. Ctrl+C to stop.")
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
.risktoggle{margin:-4px 0 14px}
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
/* alerts + launchpad + trackers + profit */
.abadge{display:inline-block;min-width:18px;text-align:center;border-radius:20px;
padding:0 6px;font-size:.72rem;color:#fff;background:#B45309;vertical-align:middle}
.abadge.crit{background:#99271F}
.pill.lvl-critical{background:#99271F;color:#fff}.pill.lvl-warn{background:#B45309;color:#fff}
.pill.lvl-info{background:#3B6E8F;color:#fff}
.lpboard{display:flex;gap:12px;overflow-x:auto;padding-bottom:10px}
.lpcol{flex:0 0 220px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px}
.lpcol h3{font-size:.82rem;margin:0 0 8px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink-soft)}
.lpcol .count{background:var(--accent-bg);color:var(--accent);border-radius:10px;padding:0 6px;font-size:.72rem}
.lpcard{background:var(--paper);border:1px solid var(--line);border-radius:9px;padding:8px 10px;margin-bottom:8px}
.lpcard b{font-size:.86rem;display:block}
.ckrow{flex-direction:row!important;align-items:center;gap:8px;font-weight:400!important}
.ckrow input{width:auto!important}
/* team tasks */
.mytasks{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;
background:var(--accent-bg);border:1px solid var(--accent);border-radius:12px;
padding:11px 16px;margin:0 0 16px}
.mtlabel{font-size:.9rem}.mtlabel .odtext{color:#99271F}.mtlabel .dstext{color:#B45309}
.mtchips{display:flex;flex-wrap:wrap;gap:6px;flex:1}
.tkchip{font-size:.76rem;font-weight:700;background:var(--surface);border:1px solid var(--line-strong);
border-left:3px solid var(--ink-soft);border-radius:7px;padding:3px 9px;color:var(--ink);text-decoration:none}
.tkchip.more{border-left-color:var(--line-strong);color:var(--ink-soft)}
.tkchip.od{border-left-color:#99271F}
.tkchip.pr-urgent{border-left-color:#99271F}.tkchip.pr-high{border-left-color:#B45309}
.tkchip.pr-medium{border-left-color:#3B6E8F}.tkchip.pr-low{border-left-color:#6E6455}
.mtall{font-weight:700;color:var(--accent);text-decoration:none;font-size:.85rem}
.tkgroup{font-size:1.02rem;margin:20px 0 8px}.tkgroup .count{background:var(--accent-bg);
color:var(--accent);border-radius:10px;padding:0 7px;font-size:.72rem}
.tkcard{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--ink-soft);
border-radius:11px;padding:11px 14px;margin-bottom:9px;box-shadow:var(--shadow)}
.tkcard.pr-urgent{border-left-color:#99271F}.tkcard.pr-high{border-left-color:#B45309}
.tkcard.pr-medium{border-left-color:#3B6E8F}.tkcard.pr-low{border-left-color:#6E6455}
.tkhead{display:flex;justify-content:space-between;align-items:center;gap:8px}
.pill.pr-urgent{background:#99271F;color:#fff}.pill.pr-high{background:#B45309;color:#fff}
.pill.pr-medium{background:#3B6E8F;color:#fff}.pill.pr-low{background:#6E6455;color:#fff}
.tkguide{font-size:.82rem;color:var(--ink-soft);margin:6px 0}
.due.od,.note.od{color:#99271F;font-weight:700}
.tkactions{display:flex;gap:8px;margin-top:9px;flex-wrap:wrap}
.tkbtn{font:inherit;font-size:.82rem;font-weight:700;padding:7px 13px;border-radius:8px;
border:1px solid var(--line-strong);background:var(--surface);color:var(--ink);cursor:pointer}
.tkbtn.primary{background:var(--accent);color:var(--paper);border-color:var(--accent)}
.tknew{margin:6px 0 14px}.tknew summary{cursor:pointer;font-weight:700;color:var(--accent)}
.cmdmore{margin-top:8px}.cmdmore summary{cursor:pointer;font-weight:700;color:var(--accent);font-size:.9rem;padding:4px 0;list-style:revert}
.cmdmore .cmdopts,.cmdmore .cmdbtns{margin-top:8px}
.fbmore{grid-column:1/-1}.fbmore summary{cursor:pointer;font-weight:700;color:var(--accent);font-size:.86rem;padding:2px 0}
.fbgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;margin-top:8px}
.tklead{font-size:.96rem;color:var(--ink-soft);margin:6px 0 16px;max-width:64ch;line-height:1.5}
.tkstats{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 16px}
.tkstat{flex:1 1 96px;min-width:96px;background:var(--surface);border:1px solid var(--line);
border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:3px;box-shadow:var(--shadow)}
.tkstat .n{font-size:1.6rem;font-weight:800;color:var(--ink);line-height:1;font-variant-numeric:tabular-nums}
.tkstat .l{font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-faint);font-weight:700}
.tkstat.bad{border-color:var(--stop)}.tkstat.bad .n{color:var(--stop)}
.tkstat.good{border-color:var(--ok)}.tkstat.good .n{color:var(--ok)}
.tkwho{display:flex;align-items:center;gap:7px;margin-bottom:7px;padding-bottom:7px;
border-bottom:1px dashed var(--line)}
.tkname{font-size:.76rem;font-weight:700;color:var(--ink-soft);white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.tktitle{display:block;font-size:.92rem;line-height:1.28}
.tkinit{flex:0 0 auto;width:26px;height:26px;border-radius:50%;background:var(--accent);
color:var(--paper);font-size:.64rem;font-weight:800;display:flex;align-items:center;justify-content:center}
.tkmeta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:8px 0 0;
font-size:.72rem;color:var(--ink-faint);text-transform:uppercase;letter-spacing:.03em}
.tkfoot{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:9px}
.tkdue{font-size:.7rem;color:var(--ink-soft);font-variant-numeric:tabular-nums}
.tkdue.od{color:var(--stop);font-weight:700}
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
.rbar{position:sticky;top:0;z-index:80;display:flex;align-items:center;
justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 0 18px;
padding:10px 16px;background:var(--paper);border-bottom:1px solid var(--line-strong);
box-shadow:0 2px 8px rgba(0,0,0,.06)}
.back{display:inline-flex;align-items:center;gap:7px;font-family:var(--sans);
font-size:.92rem;font-weight:700;color:var(--paper);background:var(--accent);
border:1px solid var(--accent);border-radius:10px;padding:9px 16px;text-decoration:none;
line-height:1}
.back:hover{filter:brightness(1.08)}
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
.login .remember{display:flex;align-items:center;gap:8px;font-size:.85rem;color:var(--ink-soft)}
.login .remember input{width:auto}
.lognote{margin-top:18px;font-size:.72rem;color:var(--ink-soft);line-height:1.5;text-align:left}
.uchip{background:var(--accent-bg);color:var(--accent);border-radius:20px;padding:3px 11px;
font-weight:700;font-size:.72rem;text-decoration:none}
.inlineform{display:inline}
.inlineform select{font:inherit;font-size:.8rem;padding:3px 6px;border-radius:6px;
border:1px solid var(--line);background:var(--surface);color:var(--ink)}
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
  <h1>Team Sign in</h1>
  {{ERROR}}
  <form method="post">
    <input type="email" name="email" placeholder="Email" autofocus autocomplete="username">
    <input type="password" name="password" placeholder="Password" autocomplete="current-password">
    <label class="remember"><input type="checkbox" name="remember"> Remember me</label>
    <button type="submit">Sign in</button>
  </form>
  <p class="lognote">This dashboard records work activity inside the Etsy Product
  Manager system for team workflow, quality review, and task management. It does
  not track keystrokes, screens, browser history, or anything outside this tool.</p>
</div></div>
"""

PORTAL = """
<div class="wrap">
  <header>
    <div class="brand">
      <div class="kicker">Etsy Product Manager</div>
      <h1>Team Reports</h1>
    </div>
    <div class="hright">{{UPDATED}}{{USER}}<a class="logout" href="/team">Team</a><a class="logout" href="/cheatsheet">Cheat Sheet</a><a class="logout" href="/logout">Sign out</a></div>
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
