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
import hmac
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


def _data_degraded():
    """Empty string when fresh; else a short reason. YTrends is a single primary
    source, so when its data is stale/missing we say so loudly instead of serving
    old numbers as if they were live."""
    from datetime import datetime
    fuel = Path("keyword_data.csv")
    if not fuel.exists():
        return "no keyword data on file yet — run a harvest / daily build"
    try:
        age_h = (datetime.now().timestamp() - fuel.stat().st_mtime) / 3600
    except Exception:  # noqa: BLE001
        return ""
    if age_h > 48:
        return (f"primary data is ~{int(age_h)}h old (auto-refresh runs ~every "
                "6h) — YTrends may be down; verify before acting")
    return ""


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
        # Cap request bodies. /api/import is public and its body is buffered
        # before the token check, so without this an anonymous POST can chew
        # through VPS memory. 8MB is far above any real YTrends table export.
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
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

    @app.before_request
    def _csrf_guard():
        # Blanket CSRF backstop: every POST must carry the per-session token.
        # Login is exempt (its token is seeded by the GET that renders the form,
        # but we never want the very first POST to /login to hard-fail on it).
        # Per-route _check_csrf() calls remain as a harmless double-check.
        if request.method == "POST" and request.endpoint not in ("login", "api_import"):
            if request.form.get("_csrf") != session.get("_csrf"):
                abort(403)

    @app.after_request
    def _inject_csrf(resp):
        # Universal "tokenize every form": inject the per-session CSRF token into
        # every method="post" form in an HTML response, so no hand-built form can
        # ship unprotected and the guard above can stay strict. Also seeds
        # session["_csrf"] on the GET that first renders a form. Never fatal.
        try:
            if ("text/html" in resp.headers.get("Content-Type", "")
                    and resp.direct_passthrough is False):
                import re as _re
                field = f'<input type="hidden" name="_csrf" value="{_csrf()}">'
                body = resp.get_data(as_text=True)
                new = _re.sub(r'(<form\b[^>]*\bmethod=["\']post["\'][^>]*>)',
                              lambda m: m.group(1) + field, body,
                              flags=_re.IGNORECASE)
                if new != body:
                    resp.set_data(new)
        except Exception:  # noqa: BLE001 - CSRF injection must never break a page
            pass
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
        bar = _bar()
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
        try:                      # daily flat-file backup (V33 CEO review)
            from src import backupper as _bk
            _bk.ensure_daily_backup()
        except Exception:  # noqa: BLE001
            pass
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

        # === Workflow-first pipeline rail (the hero of the home): the real
        # fast-lane spine CSV -> analyze -> winner -> launch -> learn, styled with
        # the portal's own theme vars so it matches light + dark automatically. ===
        _plcss = (
            '<style>'
            # --- V37.9 workflow rail: one instruction, then a compact map ---
            '.nowcard{background:var(--accent-bg);border:1px solid var(--accent);'
            'border-radius:16px;padding:20px 22px;margin:6px 0 18px}'
            '.now-k{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;'
            'text-transform:uppercase;color:var(--accent);font-weight:700}'
            '.now-h{font-size:1.45rem;font-weight:800;letter-spacing:-.02em;'
            'margin:5px 0 0;line-height:1.2}'
            '.now-s{font-size:.9rem;color:var(--ink-soft);margin:6px 0 0;max-width:62ch}'
            '.now-a{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:14px}'
            '.now-go{background:var(--accent);color:var(--paper);font-weight:700;'
            'font-size:.95rem;padding:12px 20px;border-radius:11px;text-decoration:none}'
            '.now-go:hover{filter:brightness(1.08)}'
            '.now-nx{font-size:.8rem;color:var(--ink-soft)}'
            '.wsrail-h{display:flex;align-items:baseline;gap:10px;margin:0 0 8px}'
            '.wsrail-h b{font-size:.78rem;letter-spacing:.1em;text-transform:uppercase;'
            'color:var(--ink-faint);font-family:var(--mono)}'
            '.wsrail-h span{font-size:.78rem;color:var(--ink-faint)}'
            '.wsrail-h a{margin-left:auto;font-size:.78rem;color:var(--accent);font-weight:700}'
            # A slim keyword bar INSIDE the "do this next" card, so home has one
            # instruction instead of three competing ones.
            '.now-kw{display:flex;gap:8px;margin:14px 0 0;flex-wrap:wrap}'
            '.now-kw input{flex:1;min-width:220px;font-size:13px;padding:9px 12px;'
            'border:1px solid var(--line);border-radius:9px;background:var(--paper);'
            'color:var(--ink)}'
            '.now-kw button{font-size:12.5px;font-weight:700;padding:9px 15px;'
            'border:1px solid var(--accent);border-radius:9px;background:transparent;'
            'color:var(--accent);cursor:pointer;white-space:nowrap}'
            '.now-kw button:hover{background:var(--accent);color:var(--paper)}'
            # Five full-width ROWS, not a 5-column grid: the cards now carry
            # named tool links and a status line, which a 1/5-width column
            # cannot hold without truncating everything to uselessness.
            '.phgrid{display:flex;flex-direction:column;gap:7px;margin-bottom:20px}'
            '.phc{border:1px solid var(--line);border-left:3px solid var(--line-strong);'
            'border-radius:11px;background:var(--surface);overflow:hidden;'
            'transition:border-color .12s}'
            '.phc:hover{border-color:var(--accent)}'
            '.phc.ready{border-left-color:var(--ok)}'
            '.phc.todo{border-left-color:#B45309}'
            '.phc.unknown{border-left-color:var(--line-strong)}'
            '.phc.here{border-color:var(--accent);background:var(--accent-bg)}'
            '.phc-main{display:flex;align-items:center;gap:11px;padding:11px 14px 9px;'
            'text-decoration:none;color:inherit}'
            '.phc-i{font-size:19px;line-height:1;flex:none}'
            '.phc-body{display:flex;flex-direction:column;gap:1px;min-width:0;flex:1}'
            '.phc-t{font-size:14px;font-weight:800;letter-spacing:-.01em;'
            'color:var(--ink);line-height:1.25}'
            '.phc-w{font-size:11.5px;color:var(--ink-soft);line-height:1.35}'
            '.phc-c{flex:none;font-family:var(--mono);font-size:11px;font-weight:700;'
            'color:var(--ink-faint);font-variant-numeric:tabular-nums;text-align:right}'
            '.phc-c em{display:block;font-style:normal;font-size:9px;letter-spacing:.09em;'
            'text-transform:uppercase;color:var(--accent);margin-top:2px}'
            '.phc-tools{display:flex;flex-wrap:wrap;align-items:center;gap:6px;'
            'padding:0 14px 11px 44px}'
            '.phc-sub{font-size:10.5px;color:var(--ink-faint);margin-right:4px;'
            'white-space:nowrap}'
            '.phtool{font-size:11.5px;font-weight:700;padding:3px 10px;border-radius:20px;'
            'border:1px solid var(--line);background:var(--paper);color:var(--accent);'
            'text-decoration:none;white-space:nowrap}'
            '.phtool:hover{border-color:var(--accent);background:var(--accent-bg)}'
            '.supwrap{margin:0 0 20px}'
            '.supwrap summary{cursor:pointer;font-size:.8rem;font-weight:700;'
            'color:var(--ink-soft)}'
            '.supg{margin:8px 0;font-size:11.5px}'
            '.supg b{display:block;color:var(--ink-soft);margin-bottom:2px}'
            '.supg a{color:var(--accent);margin-right:9px;white-space:nowrap}'
            '@media(max-width:620px){.now-h{font-size:1.2rem}'
            '.phc-w{display:none}.phc-tools{padding-left:14px}}'
            # (Six orphaned declaration blocks used to sit here - the bodies of
            # the deleted 9-step rail's rules, with their selectors removed.
            # CSS error recovery swallows everything up to the next "{", so the
            # ENTIRE .plnudge rule below was being discarded by the browser and
            # the "Start here" banner rendered unstyled on every home load.)
            '.plnudge{display:flex;align-items:center;gap:12px;margin:14px 0 8px;'
            'background:var(--accent-bg);border:1px solid var(--line);border-radius:12px;padding:11px 14px}'
            '.plnudge .t{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;'
            'color:var(--accent);white-space:nowrap}'
            '.plnudge .x{font-size:13px;color:var(--ink-soft);flex:1}.plnudge .x b{color:var(--ink)}'
            '.plcapbar{display:flex;gap:10px;align-items:center;margin:0 0 4px;flex-wrap:wrap}'
            '.plcapbar .plkind{width:auto;min-width:180px;margin:0}'
            '.plcapbar .pldz{flex:1;min-width:220px;margin:0}'
            '.plcapbar .capbtn{font-size:12.5px;font-weight:700;color:#fff;background:var(--accent);'
            'border:0;border-radius:8px;padding:10px 16px;cursor:pointer;white-space:nowrap}'
            '.pldz{border:1.5px dashed var(--line-strong);border-radius:9px;padding:11px 8px;'
            'text-align:center;cursor:pointer;background:var(--surface);transition:border-color .15s}'
            '.pldz:hover,.pldz.drag{border-color:var(--accent)}'
            '.pldz .plch{font-size:11px;color:var(--ink-soft);line-height:1.35}'
            '.pldz .plfn{display:block;font-size:11px;color:var(--accent);font-weight:600;'
            'margin-top:4px;word-break:break-all}'
            '.plmeta{font-size:10.5px;color:var(--ink-faint);margin:0 0 8px;line-height:1.3}'
            '.plmeta b{color:var(--ink-soft)}'
            '.plkind{width:100%;font-size:11px;padding:8px 6px;border:1px solid var(--line);'
            'border-radius:7px;background:var(--surface);color:var(--ink);margin-bottom:6px}'
            '</style>')
        _csrf_tok = _csrf()
        try:   # newest import: powers both the next-step nudge and the "last
            from src import shortlister_integration as _si   # import" status line
            _imp_info = _si.latest_import_info()
        except Exception:  # noqa: BLE001
            _imp_info = None
        _has_imp = bool(_imp_info)

        def _ago(s):
            if s is None:
                return ""
            if s < 60:
                return "just now"
            if s < 3600:
                return f"{s // 60}m ago"
            if s < 86400:
                return f"{s // 3600}h ago"
            return f"{s // 86400}d ago"

        # Prefer the structured import diagnostics (lane + files + rows, flags an
        # empty parse loudly); fall back to the ytrends-only info.
        _li = None
        try:
            import json as _json
            import time as _time
            _lip = Path("data/imports/last_import.json")
            if _lip.is_file():
                _li = _json.loads(_lip.read_text(encoding="utf-8"))
                _li["age_seconds"] = max(0, int(_time.time() - _li.get("ts", 0)))
        except Exception:  # noqa: BLE001
            _li = None
        if _li:
            if _li.get("empty"):
                _hd = ", ".join(_li.get("headers", [])[:6]) or "no headers found"
                _implabel_html = ('<div class="plmeta">⚠️ <b>Last import parsed 0 '
                                  f'rows</b> (lane: {_h_esc(str(_li.get("lane")))}) — '
                                  f'columns seen: {_h_esc(_hd)}. Check the file type '
                                  'or pick the source manually.</div>')
            else:
                _kwn = _li.get("kw_new")
                _kwbit = ""
                if _kwn is not None and "keywords" in str(_li.get("lanes") or {}):
                    _kwbit = (f' · <b>+{_kwn} new keywords</b>' if _kwn
                              else ' · <b>0 new</b> (all duplicates — rank unchanged)')
                _implabel_html = ('<div class="plmeta">Last import: '
                                  f'<b>{_li.get("rows")} rows</b> from '
                                  f'{_li.get("files")} file(s) → '
                                  f'<b>{_h_esc(str(_li.get("lane")))}</b> lane'
                                  f'{_kwbit} · '
                                  f'{_ago(_li.get("age_seconds"))}</div>')
        elif _imp_info:
            _v = _imp_info.get("view") or ""
            _implabel_html = ('<div class="plmeta">Last import: '
                              f'<b>{_imp_info["rows"]} rows</b> · '
                              f'{_ago(_imp_info.get("age_seconds"))}'
                              + (f' · {_h_esc(_v)}' if _v else '') + '</div>')
        else:
            _implabel_html = '<div class="plmeta">No imports yet — drop your first file.</div>'
        # Keyword-base growth: how fast the base updates + where it comes from
        try:
            from src import import_ledger as _ilg
            _g = _ilg.stats()
            _chan = " · ".join(
                f"{_h_esc(k)} <b>{v}</b>" for k, v in
                sorted(_g["by_channel_total"].items(), key=lambda kv: -kv[1]))
            _implabel_html += (
                '<div class="plmeta">\U0001F4C8 Keyword base: '
                f'<b>{_g["total"]}</b> total · <b>+{_g["today"]}</b> today · '
                f'<b>+{_g["last7"]}</b> 7d · <b>+{_g.get("last30", 0)}</b> 30d '
                f'&nbsp;|&nbsp; {_chan} '
                f'&nbsp;·&nbsp; <a href="/kw-history">who added what →</a></div>')
        except Exception:  # noqa: BLE001
            pass
        # Pipeline Health strip (V32): build + freshness self-evident on the home
        try:
            from src import pipeline_status as _ps
            _s = _ps.snapshot(active if active in ("pod", "embroidery") else None)
            _c0 = _s.get("counts", {})
            _wtxt = (f' · <b style="color:#c0392b">⚠ {len(_s["warnings"])} '
                     'warning(s)</b>' if _s.get("warnings") else " · ✓ healthy")
            _implabel_html += (
                '<div class="plmeta">\U0001FA7A '
                f'<b>V{_h_esc(_s["version"])}</b> build '
                f'<b>{_h_esc(_s["git_sha"])}</b> · started {_h_esc(_s["started_ago"] or "?")} '
                f'· master {_h_esc(_s["age"]["master"] or "never")} '
                f'· captures {_h_esc(_s["age"]["captures"] or "never")} '
                f'· \U0001F5C4 {_c0.get("archived", 0)} archived '
                f'· \U0001F50C {_c0.get("needs_enrichment", 0)} to enrich'
                f'{_wtxt} · <a href="/status">full status →</a></div>')
        except Exception:  # noqa: BLE001
            pass
        # This used to render "▶ Start here" / "▶ Import ready" as a second
        # instruction, sitting under the "Do this next" card that already told
        # staff what to do — two answers to the same question, disagreeing.
        # The import block is now a disclosure, so the line inside it states
        # what the data says without claiming to be the starting point.
        if _has_imp:
            _nx, _nh, _nl = (
                "Fresh imports are loaded — the Opportunity Inbox has them "
                "deduped into ONE ranked list.",
                f"/inbox?mode={active}", "Open Opportunity Inbox →")
        else:
            _nx, _nh, _nl = (
                "No import yet — capture keywords from YTrends/Etsy with the "
                "browser extension, then drop the file below.",
                "/imports", "Import Center →")
        _plnudge = (f'<div class="plnudge"><span class="x">{_nx}</span>'
                    f'<a class="pullbtn primary" href="{_nh}">{_nl}</a></div>')
        _plrail = (
            # (The "Feed the machine" heading was removed: this block now lives
            # inside a disclosure whose summary says the same thing.)
            _plnudge +
            # ① Capture drop — a compact full-width bar (the quick entry point)
            '<form class="pldrop plcapbar" method="post" action="/import-file" '
            'enctype="multipart/form-data">'
            f'<input type="hidden" name="_csrf" value="{_csrf_tok}">'
            f'<input type="hidden" name="mode" value="{active}">'
            '<select class="plkind" name="kind">'
            '<option value="auto">Auto-detect source</option>'
            '<option value="keywords">Etsy / YTrends keywords</option>'
            '<option value="supplier">Supplier — Alibaba/AliExpress/1688</option>'
            '<option value="pinterest">Pinterest — pins &amp; saves</option>'
            '<option value="etsy">Etsy listings / spy — competitor intel</option>'
            '<option value="proof">Alura / EverBee products — real sales proof</option>'
            '<option value="amazon">Amazon Xray — reference</option>'
            '</select>'
            '<label class="pldz" id="pldz">'
            '<input type="file" name="file" accept=".csv,.json,.txt" id="plfile" multiple hidden>'
            '<span class="plch">⬆ Drop keyword CSV / JSON (one or many) or click to choose</span>'
            '<span class="plfn" id="plfn"></span></label>'
            '<button class="capbtn" type="submit">Import → rank</button></form>'
            + _implabel_html +
            # drag-drop + auto-submit: drop or choose a file and it goes straight in
            '<script>(function(){'
            'var dz=document.getElementById("pldz"),fi=document.getElementById("plfile"),'
            'fn=document.getElementById("plfn");if(!dz||!fi)return;'
            'function go(){if(fi.files&&fi.files.length){fn.textContent=fi.files.length>1?'
            '(fi.files.length+" files"):fi.files[0].name;dz.closest("form").submit();}}'
            'fi.addEventListener("change",go);'
            '["dragenter","dragover"].forEach(function(e){dz.addEventListener(e,function(ev){'
            'ev.preventDefault();dz.classList.add("drag");});});'
            '["dragleave","drop"].forEach(function(e){dz.addEventListener(e,function(ev){'
            'ev.preventDefault();dz.classList.remove("drag");});});'
            'dz.addEventListener("drop",function(ev){if(ev.dataTransfer&&ev.dataTransfer.files'
            '&&ev.dataTransfer.files.length){fi.files=ev.dataTransfer.files;go();}});'
            '})();</script>')
        pipeline_html = _plcss + _plrail

        # --- Opportunity action queue: pull the actionable rows straight from the
        # Inbox so the home says WHAT TO DO NOW, not just "here are tools" (V29 CF005).
        _oppq = ""
        try:
            from urllib.parse import quote_plus as _uq
            from src import opportunity_inbox as _oi
            _idata = _oi.build_inbox(active if active in ("pod", "embroidery") else None,
                                     limit=6)
            _ic = _idata["counts"]
            _qcss = (
                '<style>'
                '.oppq{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:2px 0 10px}'
                '.oppq .qc{border:1px solid var(--line);border-radius:11px;padding:11px 13px;'
                'background:var(--surface);text-decoration:none;display:block}'
                '.oppq .qc:hover{border-color:var(--accent)}'
                '.oppq .qn{font-size:22px;font-weight:800;letter-spacing:-.5px}'
                '.oppq .ql{font-size:11.5px;color:var(--ink-soft);font-weight:600;margin-top:2px}'
                '.oppq .qc.go .qn{color:var(--ok)}.oppq .qc.warn .qn{color:#c07a00}'
                '.oppq .qc.bad .qn{color:#c0392b}'
                '.opprows{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-bottom:6px}'
                '.opprow{display:flex;align-items:center;gap:10px;padding:9px 13px;'
                'border-top:1px solid var(--line);font-size:13px;text-decoration:none;color:var(--ink)}'
                '.opprow:first-child{border-top:0}.opprow:hover{background:var(--accent-bg)}'
                '.opprow .ok{flex:1;font-weight:600}.opprow .oa{font-size:11px;font-weight:700;'
                'padding:2px 8px;border-radius:20px;background:var(--accent-bg);color:var(--accent);white-space:nowrap}'
                '.opprow .om{font-size:11px;color:var(--ink-faint);white-space:nowrap}'
                '</style>')
            _act_label = {"BUILD_NOW": "Build now", "CONFIRM_FIRST": "Confirm first",
                          "REVIEW": "Review", "WATCH": "Watch", "SKIP": "Skip",
                          "BLOCKED": "Blocked"}
            _act_href = {"build": "/launch-kit", "pattern": "/pattern-miner",
                         "review": "/should-sell", "analyze": "/should-sell",
                         "watch": "/should-sell", "skip": "/inbox", "blocked": "/inbox"}
            _rowhtml = ""
            for _r in _idata["rows"][:5]:
                _href = _act_href.get(_r.get("route"), "/inbox")
                _rowhtml += (
                    f'<a class="opprow" href="{_href}?q={_uq(_r["keyword"])}">'
                    f'<span class="ok">{_h_esc(_r["keyword"])}</span>'
                    f'<span class="om">{_h_esc(_r.get("fit_label") or "")}</span>'
                    f'<span class="oa">{_act_label.get(_r["action"], _r["action"])}</span></a>')
            _oppq = (
                _qcss + '<h2 class="grouph">🎯 Today\'s opportunities — act on these</h2>'
                '<div class="oppq">'
                f'<a class="qc go" href="/inbox?mode={active}"><div class="qn">{_ic["build"]}</div>'
                '<div class="ql">🚀 Build now</div></a>'
                f'<a class="qc" href="/pattern-miner?mode={active}"><div class="qn">{_ic["confirm"]}</div>'
                '<div class="ql">🔍 Confirm / Pattern Miner</div></a>'
                f'<a class="qc warn" href="/inbox?mode={active}"><div class="qn">{_ic["review"] + _ic["watch"]}</div>'
                '<div class="ql">🚩 Review / watch</div></a>'
                f'<a class="qc bad" href="/inbox?mode={active}"><div class="qn">{_ic["blocked"]}</div>'
                '<div class="ql">🚫 Blocked (trademark)</div></a>'
                '</div>'
                + (f'<div class="opprows">{_rowhtml}</div>' if _rowhtml else '')
                + f'<p class="note" style="margin:0 0 4px">Straight from the '
                f'<a href="/inbox?mode={active}">Opportunity Inbox</a> — '
                f'{_ic["total"]} keywords ranked through the risk gate → market '
                'signal → final action.</p>')
        except (SystemExit, Exception):  # noqa: BLE001 - never break the home
            _oppq = ""

        # --- Instant Product Command Center: one keyword -> the WHOLE pipeline.
        # The 9-stage workflow board lives INSIDE the form as submit buttons, so
        # the typed keyword + product mode travel with EVERY step click — no
        # going back to the homepage between steps (owner directive).
        _mchk = {"embroidery": "", "pod": "", "both": ""}
        _mchk[active if active in ("pod", "embroidery") else "both"] = " checked"
        # --- THE WORKFLOW SPINE (V37.7) -------------------------------------
        # 104 routes with no ordering is why staff could not say what step they
        # were in. src/workflow_spine.py is the single definition of the owner's
        # real 12-step Etsy process; WORKFLOW.md renders from the same module, so
        # the page and the doc cannot drift. Support routes stay collapsed —
        # showing all 104 equally is what caused the confusion.
        spine = ""
        support_html = ""      # the raw support-route list, shown under All tools
        try:
            from src import workflow_spine as _ws
            _st = _ws.status()
            _here = _ws.current_step(_st)
            _dot = {"ready": ("✅", "ok"), "todo": ("⬜", "warn"),
                    "unknown": ("❔", "")}
            # ONE focused instruction, then a compact rail. The first cut of this
            # rendered all 12 steps as tall cards carrying Needs/Creates/route —
            # ~11 screens of text on the page staff open every morning, stacked on
            # top of the older 9-step pipeline. Detail moved to /workflow; home now
            # answers only "what do I do next" and "where is everything else".
            # V37.10: five PHASES on screen, the twelve steps living inside them.
            # Twelve tiles read as a project plan; several were the same sitting-
            # down job on one route, and 9/10 became one button once the loop was
            # closed. Guide text is Vietnamese (team-facing); listing OUTPUT stays
            # English because the buyers are American.
            _ps = _ws.phase_status(_st)
            _curph = _ws.current_phase(_st)
            cur = next(s for s in _ws.STEPS if s["n"] == _here)
            cstat = _st.get(cur["key"]) or {}
            clabel, chref = cur["action"]
            done = sum(1 for s in _ws.STEPS
                       if (_st.get(s["key"]) or {}).get("state") == "ready")
            # Five full-width rows, each NAMING its tools as direct links.
            # The previous version was a 5-column grid of chips showing step
            # NAMES, which meant Pattern Miner and Keyword Lab appeared nowhere
            # a human could find: Keyword Lab existed only as the bare string
            # "/keyword-lab" inside a collapsed list of raw URLs, and Pattern
            # Miner had no card at all. Naming the tools inside the phase that
            # uses them is the whole point of having phases.
            _cards = []
            for ph in _ws.PHASES:
                x = _ps[ph["key"]]
                here = ph["key"] == _curph["key"]
                tools_row = " ".join(
                    f'<a class="phtool" href="{_r}{"?mode=" + active if active else ""}">'
                    f'{_h_esc(_n)}</a>' for _n, _r in ph.get("tools", ()))
                nxt = x.get("next_step")
                # What is actually outstanding in this phase, in plain words -
                # this is the "what is the team doing" signal, and it replaces
                # a row of step-name chips that only restated the phase title.
                sub = (f'⬜ next: {_h_esc(nxt["name"])}' if nxt
                       else '✅ every step done')
                _cards.append(
                    f'<div class="phc {x["state"]}{" here" if here else ""}">'
                    f'<a class="phc-main" href="{ph["route"]}">'
                    f'<span class="phc-i">{ph["icon"]}</span>'
                    f'<span class="phc-body"><span class="phc-t">Phase {ph["p"]} · '
                    f'{_h_esc(ph["en"])}</span>'
                    f'<span class="phc-w">{_h_esc(ph["en_do"])}</span></span>'
                    f'<span class="phc-c">{x["done"]}/{x["total"]}'
                    + ('<em>here</em>' if here else '') + '</span></a>'
                    f'<div class="phc-tools"><span class="phc-sub">{sub}</span>'
                    f'{tools_row}</div></div>')
            support_html = "".join(
                f'<div class="supg"><b>{_h_esc(g)}</b><span>' + " ".join(
                    f'<a href="{r}">{_h_esc(r)}</a>' for r in rs)
                + '</span></div>' for g, rs in _ws.SUPPORT_ROUTES)
            # ONE instruction on the page. The old home also carried a "Start
            # here / Import ready" banner above the import dropzone AND a
            # "Work one keyword" section header - three competing answers to
            # "where do I begin?". The keyword box survives as a slim bar
            # attached to this card; the dropzone moved into a disclosure.
            spine = (
                '<section class="nowcard">'
                f'<div class="now-k">Do this next · phase {_curph["p"]} of 5'
                f' · {_h_esc(cur["owner"])}</div>'
                f'<h2 class="now-h">{_h_esc(cur["name"])}</h2>'
                f'<p class="now-s">{_h_esc(cstat.get("detail") or "")}</p>'
                '<div class="now-a">'
                f'<a class="now-go" href="{chref}">{_h_esc(clabel)} →</a>'
                f'<span class="now-nx">Creates: {_h_esc(_curph["en_out"])}</span>'
                '</div>'
                # type once, and the keyword + product line travel with every
                # step from here on (every tool page now carries both).
                '<form class="now-kw" method="get" action="/run">'
                f'<input type="hidden" name="mode" value="{active}">'
                '<input name="q" aria-label="keyword" placeholder="…or jump '
                'straight to a keyword, e.g. patchwork usa tee">'
                '<button type="submit">Open workspace →</button></form>'
                '</section>'
                '<div class="wsrail-h"><b>Workflow · 5 phases</b>'
                f'<span>{done} of 12 steps done</span>'
                '<a href="/workflow">quy trình đầy đủ →</a></div>'
                f'<div class="phgrid">{"".join(_cards)}</div>')
        except Exception:  # noqa: BLE001 — the spine is additive, never breaks home
            spine = ""

        # The home page's ONE job: what is my team doing, what do I do next,
        # where is everything else. In that order, and nothing else open.
        #   status (focus) -> Do this next -> 5 phases -> today's actions
        #   -> [Import data] [All tools] [Reports], all collapsed.
        # What used to sit here open: a second "Work one keyword" section with
        # its own product-mode radios (the mode selector now lives on every
        # tool page), a "More single-step tools" button row, and the import
        # dropzone under a "▶ Start here" banner that contradicted the
        # "Do this next" card directly above it.
        tools = (
            spine
            + _oppq +
            '<details class="archive advtools"><summary>📥 Import data — drop '
            'captures from the extension (YTrends / Etsy / Pinterest / supplier '
            '/ Alura)</summary>' + pipeline_html + '</details>'
            + '<details class="archive advtools"><summary>⚡ Work one keyword — '
            'single-step tools</summary>'
            '<form class="cmdbar" method="get" action="/run">'
            '<div class="modetoggle"><span>Product mode</span>'
            f'<label><input type="radio" name="mode" value="embroidery"{_mchk["embroidery"]}>'
            ' Embroidery</label>'
            f'<label><input type="radio" name="mode" value="pod"{_mchk["pod"]}>'
            ' Print on Demand</label>'
            f'<label><input type="radio" name="mode" value="both"{_mchk["both"]}>'
            ' Both</label></div>'
            '<div class="kwrow">'
            '<input name="q" aria-label="keyword" '
            'placeholder="Main keyword, e.g. patchwork usa tee">'
            '<button class="primary" type="submit">Build full workspace →</button>'
            '</div>'
            '<div class="cmdbtns">'
            '<button formaction="/should-sell">Should I sell?</button>'
            '<button formaction="/analyze" name="do" value="analyze">Analyze only</button>'
            '<button formaction="/draft-listing">Draft listing</button>'
            '<button formaction="/edge">Beat competitors</button>'
            '</div></form></details>' +
            # --- TOOLS: the default-visible shelf. Exactly what staff need to
            # read alongside the pipeline — trend feeds, ranked views, execution
            # helpers. Everything else lives under Advanced (owner directive:
            # "what staff need to read only, not a bunch of reports"). ---
            # SECTION 1 — TREND FEEDS: find what's rising (read these first).
            # Three always-open grids (Trend Feeds + Execution Helpers + Guides =
            # 19 cards) sat above a 13-card Advanced block. All of it is reachable
            # from the rail's canonical routes, so it now opens on demand instead
            # of pushing the day's actual work off-screen.
            '<details class="archive advtools"><summary>🧭 All tools — trend feeds, '
            'execution helpers &amp; guides</summary>'
            '<h2 class="grouph">📈 Trend Feeds — tìm cái đang lên</h2>'
            '<div class="toolgrid">'
            '<a class="toolcard" href="/build-queue"><b>🎯 Build Queue</b>'
            '<span>Make these next: proven keywords from your base, ranked + TM-checked → 1-click Design/Kit</span></a>'
            f'<a class="toolcard" href="/winners?mode={active}"><b>🏆 Winner Finder</b>'
            '<span>High-demand × low-competition sweet spot — the fastest pick, ranked</span></a>'
            f'<a class="toolcard" href="/supplier-trends?mode={active}"><b>🏭 Supplier Trend Finder</b>'
            '<span>Reverse signal: Alibaba/AliExpress/1688 heat → keyword demand leads</span></a>'
            f'<a class="toolcard" href="/pinterest-trends?mode={active}"><b>📌 Pinterest Trend Finder</b>'
            '<span>Leading signal: pin saves → rising keyword demand leads</span></a>'
            f'<a class="toolcard" href="/trending?mode={active}"><b>📈 Trending now'
            f'</b><span>Rising keywords in {active_label} (YTuong data)</span></a>'
            f'<a class="toolcard" href="/opportunities?mode={active}"><b>💎 '
            'Opportunities</b><span>Low-competition sweet spots</span></a>'
            f'<a class="toolcard" href="/gems?mode={active}"><b>💠 Hidden gems</b>'
            '<span>High-conversion, low-competition niches (full table)</span></a>'
            f'<a class="toolcard" href="/newest?mode={active}"><b>🆕 Newest winners</b>'
            '<span>Brand-new listings already outselling their niche</span></a>'
            f'<a class="toolcard" href="/calendar?mode={active}"><b>📅 Seasonal calendar</b>'
            '<span>Upcoming holidays + launch-by dates + keywords</span></a>'
            '</div>'
            # SECTION 2 — EXECUTION HELPERS: turn one pick into a listing.
            '<h2 class="grouph">🛠 Execution Helpers — biến 1 pick thành listing</h2>'
            '<div class="toolgrid">'
            '<a class="toolcard" href="/design-skill-bridge"><b>🎨 Design Skill Bridge</b>'
            '<span>Ảnh + evidence → chạy ChatGPT Skill (V8.1) → import RESULT_JSON → owner duyệt → listing_seeds</span></a>'
            f'<a class="toolcard" href="/launch-kit?mode={active}"><b>🚀 Launch Kit</b>'
            '<span>One winner → verdict, edge, listing, photos &amp; ads on one page</span></a>'
            f'<a class="toolcard" href="/photo-brief?mode={active}"><b>📸 Photo prompt set</b>'
            '<span>Every listing image + a ready AI prompt (real-photo honesty rule)</span></a>'
            f'<a class="toolcard" href="/edge?mode={active}"><b>🥊 Beat competitors</b>'
            '<span>Measured gaps in the ranking listings, biggest weakness first</span></a>'
            '<a class="toolcard" href="/grade"><b>📋 Listing Analyzer</b>'
            '<span>SEO / Trust / Image scores + publish gate</span></a>'
            f'<a class="toolcard" href="/ads-plan?mode={active}"><b>📣 Etsy Ads plan</b>'
            '<span>Manual starter: budget, breakeven ACOS, tag coverage, kill rules</span></a>'
            '<a class="toolcard" href="/training"><b>📚 Hướng dẫn nhân viên</b>'
            '<span>5 giai đoạn / 12 bước — dạy nhân viên (Tiếng Việt)</span></a>'
            '</div>'
            # --- ADVANCED: everything else — research library, team surfaces,
            # analytics — one click away so the home stays calm. ---
            '<details class="archive advtools"><summary>🧰 Advanced tools — research '
            'library, team &amp; analytics (open when you need them)</summary>'
            '<div class="toolgrid">'
            f'<a class="toolcard" href="/daily-brief?mode={active}"><b>🌅 Daily brief</b>'
            '<span>Today\'s scored build-list (Opportunity Score) — read first</span></a>'
            f'<a class="toolcard" href="/score-import?mode={active}"><b>🎯 Score latest import</b>'
            '<span>Rank your last YTrends extension import by Opportunity Score</span></a>'
            f'<a class="toolcard" href="/spy?mode={active}"><b>🕵️ Spy + Reverse Engine</b>'
            '<span>Decode each competitor\'s playbook + how to beat them</span></a>'
            '<a class="toolcard" href="/categories"><b>🗂️ Category intel</b>'
            '<span>Underserved whole categories (demand vs supply)</span></a>'
            '<a class="toolcard" href="/research"><b>🔬 Saved research</b>'
            '<span>Past keyword lookups</span></a>'
            '<a class="toolcard" href="/shops"><b>🏪 Saved shops</b>'
            '<span>Auto-pull new shops already selling (&lt; 1yr, high CR)</span></a>'
            '<a class="toolcard" href="/listings"><b>📌 Saved listings</b>'
            '<span>Auto-pull young winners (&lt; 3mo, high CR/views/favs)</span></a>'
            '<a class="toolcard" href="/feedback"><b>📉 Sales feedback</b>'
            '<span>Post-launch: keep / change / kill / scale</span></a>'
            + _alerts_card()
            + '<a class="toolcard" href="/launchpad"><b>🚀 Launchpad</b>'
            '<span>Launch board: idea → manager → Day-7 → scale/kill</span></a>'
            '<a class="toolcard" href="/trackers"><b>📊 Market &amp; keyword tracker</b>'
            '<span>Trends over time: rising / falling / stable</span></a>'
            '<a class="toolcard" href="/profit"><b>💰 Profit Center</b>'
            '<span>Real P&amp;L per product / supplier / mode</span></a>'
            '<a class="toolcard" href="/shortlist"><b>🎯 Shortlist</b>'
            '<span>Top opportunities ranked → GO/CONDITIONAL → one-click Confirm</span></a>'
            '</div></details>'
            # --- Guides: always one click away ---
            '<h2 class="grouph">📖 Guides</h2>'
            '<div class="toolgrid">'
            '<a class="toolcard" href="/how-to-use"><b>📖 How to Use (Tiếng Việt)</b>'
            '<span>Hướng dẫn đầy đủ cho nhân viên: mọi mục + điểm số + thuật ngữ</span></a>'
            '<a class="toolcard" href="/workflow"><b>📋 Workflow</b>'
            '<span>How the team works: find → collect → ship</span></a>'
            '<a class="toolcard" href="/cheatsheet"><b>📖 Cheat Sheet</b>'
            '<span>Every command + workflow, in plain English</span></a>'
            '</div>'
            # The raw support-route index used to sit directly under the phase
            # cards, where its bare "/keyword-lab" text was the ONLY mention of
            # Keyword Lab on the whole page. The phase cards name their tools
            # now, so this belongs here: a complete index, not the front door.
            '<h2 class="grouph">🗂 Every other route</h2>' + support_html
            + '</details>')

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
        # Role-aware FOCUS PANEL — the hero of the home. Staff see their work;
        # managers see the review/decision desk. (Research tools stay below, so a
        # task that needs research is one click away, but the default is action.)
        focus = ""
        _mu = current_user()
        try:                        # never let the task/research desk 500 the home
         if _mu:
            from src import tasks as _tk, research as rs
            mine = _tk.my_open(_mu["user_id"])
            od = sum(1 for t in mine if _tk.is_overdue(t))
            ds = sum(1 for t in mine if _tk.is_due_soon(t))
            cc = rs.counts_by_status()
            day37 = cc.get("DAY_3_CHECK", 0) + cc.get("DAY_7_DECISION", 0)
            is_mgr = (auth.has_perm(_mu["role"], "tasks.assign")
                      or auth.has_perm(_mu["role"], "tasks.review"))
            if is_mgr:
                blocked = len(_tk.list_tasks(status="BLOCKED")) + cc.get("BLOCKED", 0)
                # "In flight" = the team is actively working, even if nothing has
                # reached the manager's own queue yet (keeps the desk from reading
                # as empty while staff have tasks in progress).
                inflight = len(_tk.list_tasks(status="IN_PROGRESS"))
                tiles = [("Imported today", len(rs.imported_today()), "/imports"),
                         ("In flight", inflight, "/admin/tasks"),
                         ("To review", len(_tk.review_queue()), "/admin/reviews"),
                         ("Ready to publish", cc.get("READY_FOR_MANUAL_PUBLISH", 0), "/research-queue"),
                         ("Blocked", blocked, "/research-queue"),
                         ("Day 3 / 7 due", day37, "/research-queue"),
                         ("My tasks", len(mine), "/me/tasks")]
                title, acts = "🧑‍💼 Manager desk — review &amp; decide", [
                    ("✅ Review submitted listings", "/admin/reviews"),
                    ("👥 Team", "/team")]
            else:
                tiles = [("My tasks", len(mine), "/me/tasks"),
                         ("Overdue", od, "/me/tasks"), ("Due soon", ds, "/me/tasks"),
                         ("My research", len(rs.list_candidates(assigned_to=_mu["user_id"])), "/research-queue"),
                         ("Day 3 / 7 due", day37, "/research-queue")]
                title, acts = "✅ My work today", [
                    ("✅ My Tasks", "/me/tasks"), ("🧭 Research Queue", "/research-queue"),
                    ("📥 Import Center", "/imports")]
            tilehtml = "".join(
                f'<a class="tkstat{" bad" if (lbl in ("Overdue", "Blocked") and n) else ""}" '
                f'href="{href}"><span class="n">{n}</span>'
                f'<span class="l">{_h_esc(lbl)}</span></a>' for lbl, n, href in tiles)
            actbtns = "".join(f'<a class="tkbtn" href="{href}">{lbl}</a>' for lbl, href in acts)
            focus = (f'<section class="focus"><h2 class="grouph">{title}</h2>'
                     f'<div class="tkstats">{tilehtml}</div>'
                     f'<div class="tkactions">{actbtns}</div></section>')
        except (SystemExit, Exception):  # noqa: BLE001 - one bad panel can't break home
            focus = ""
        _deg = _data_degraded()
        deg_banner = ('<div class="notice warn">⚠️ <b>DATA DEGRADED:</b> '
                      f'{_h_esc(_deg)}</div>' if _deg else "")
        body = _bar() + deg_banner + focus + tools + arch
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
        # `mode` is an accepted alias for `supplier_type`, so links from the
        # Research Queue / Import Center can carry a candidate's product mode as
        # /run?q=...&mode=pod|embroidery and it flows straight into the workspace.
        if not opts.get("supplier_type"):
            m = (request.args.get("mode") or "").strip().lower()
            if m in ("pod", "embroidery", "both"):
                opts["supplier_type"] = m
        return q, opts

    @app.route("/run")
    @login_required
    def run():
        import html as _html
        q, opts = _run_inputs()
        bar = _bar()
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
            # Self-diagnosing: log the full traceback to journalctl AND surface the
            # exact src file:line to the operator, so a data-shaped failure is
            # fixable in one shot instead of a bare error message.
            import traceback as _tb
            app.logger.exception("workspace build failed for %r", q)
            _loc = ""
            for _fr in reversed(_tb.extract_tb(exc.__traceback__) or []):
                _fp = _fr.filename.replace("\\", "/")
                if "/src/" in _fp:
                    _loc = f" [{_fp.split('/src/')[-1]}:{_fr.lineno} in {_fr.name}()]"
                    break
            return page("Keyword Run", bar + '<article class="md"><p class="empty">'
                        f'Could not build the workspace for "{_html.escape(q)}": '
                        f'{_html.escape(type(exc).__name__)}: '
                        f'{_html.escape(str(exc)[:120])}{_html.escape(_loc)}</p>'
                        '</article>')
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
                + ' ' + _post_btn(f'/shops/del/{r["id"]}', "delete",
                                  confirm="Delete this saved shop?") + '</div>'
                + f'<div class="note">{_h.escape(r.get("category",""))} · '
                f'{_h.escape(r.get("niche",""))} · '
                + ("new-shop proxy (listing age)" if is_auto
                   else f'learning score {ov if ov is not None else "—"}/100')
                + f' · saved {r.get("last_analyzed_at","")}</div>'
                + chips
                + (f'<p>{_h.escape(r.get("notes",""))}</p>' if r.get("notes") else "")
                + '<details><summary>Analysis rubric — what to examine</summary>'
                f'<ul class="facts">{fw}</ul><p class="note">{saved.DO_NOT_COPY}</p>'
                '</details></div>')
        bar = _bar()
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

    @app.route("/shops/del/<int:sid>", methods=["POST"])
    @login_required
    def shops_del(sid):
        _check_csrf()
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
                + ' ' + _post_btn(f'/listings/del/{r["id"]}', "delete",
                                  confirm="Delete this saved listing?") + '</div>'
                + f'<div class="note">{_h.escape(r.get("shop_name",""))} · '
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
        bar = _bar()
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

    @app.route("/listings/del/<int:lid>", methods=["POST"])
    @login_required
    def listings_del(lid):
        _check_csrf()
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

        # --- product -> supplier match panel (was terminal-only: `supplier match`)
        mq = (request.args.get("match") or "").strip()[:80]
        mmode = request.args.get("mode") if request.args.get("mode") in ("embroidery", "pod") else ""
        modeopts = "".join(
            f'<option value="{m}"{" selected" if mmode == m else ""}>{m}</option>'
            for m in ("embroidery", "pod"))
        match_html = (
            '<h2>🔎 Match a product to a supplier</h2>'
            '<form class="savedform" method="get" action="/suppliers">'
            f'<input name="match" value="{_h.escape(mq)}" placeholder="Product '
            'keyword, e.g. chenille name bag" required>'
            f'<select name="mode"><option value="">Auto mode</option>{modeopts}</select>'
            '<button class="primary" type="submit">Find supplier →</button></form>')
        if mq:
            # Drop the zeros: since V37.12 a 0 means "this supplier does not make
            # this product family / cannot work in this mode", so listing eight
            # do-not-use rows just buries the real answer, which is "nobody".
            scored = [x for x in so.match(mq, mmode or None, verbose=False)
                      if x[0] > 0]
            if scored:
                mr = ['<table><tr><th>Fit</th><th>Supplier</th><th>Product</th>'
                      '<th>Mode</th><th>Base cost</th><th>Status</th><th>URL</th></tr>']
                for sc, r in scored[:8]:
                    band = ("strong" if sc >= 90 else "usable" if sc >= 70
                            else "weak" if sc >= 50 else "do-not-use")
                    url = r.get("product_url") or ""
                    ucell = (f'<a href="{_h.escape(url)}" target="_blank" '
                             'rel="noopener">open ↗</a>' if url.startswith("http") else "—")
                    mr.append(
                        f'<tr><td><b>{sc}</b>/100 {band}</td>'
                        f'<td>{_h.escape(r.get("supplier_name",""))}</td>'
                        f'<td>{_h.escape((r.get("product_name") or "")[:44])}</td>'
                        f'<td>{_h.escape(r.get("production_mode",""))}</td>'
                        f'<td>{_h.escape(str(r.get("base_cost","") or "—"))}</td>'
                        f'<td>{_h.escape(r.get("supplier_status",""))}</td>'
                        f'<td>{ucell}</td></tr>')
                mr.append("</table>")
                match_html += ("".join(mr) + '<p class="note">Pick a strong/usable '
                               'match, confirm its product URL + base/shipping cost, '
                               'then tick <b>Supplier confirmed</b> on the run. '
                               'PUBLISH_READY stays false until a supplier is confirmed.</p>')
            else:
                match_html += ('<p class="note">No supplier products on file for that '
                               'yet — upload a CSV or sync a catalog below, then match '
                               'again.</p>')
        match_html += "<hr>"

        # Step 3 of the workflow, and it had NO phase strip either. The page
        # already owns a keyword box (the ?match= form above), so the shared
        # header contributes the phase strip + Back/Next + product line only.
        bar = _bar() + _stage_nav("supplier", mq, mmode) + _mode_switch(
            "suppliers", mmode, mq)
        return page("Suppliers", bar + '<article class="md"><h1>🏭 Supplier panel</h1>'
                    + match_html
                    + '<h2>Supplier library</h2>'
                    '<p>POD catalogs (open + pull manually) and CSV suppliers '
                    '(ShineOn / Embroidery — upload to normalize into the library). '
                    'Nothing is scraped; uploaded CSVs are the truth. A product is '
                    'only publish-ready once a supplier reaches SUPPLIER_CONFIRMED.'
                    '</p>' + "".join(rows) + '<p class="note">CLI still works too: '
                    '<code>py main.py supplier import-csv --source shineon --file '
                    '&lt;csv&gt;</code></p></article>')

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

        def _pf(name, maxlen=200):
            return _h.escape((request.args.get(name) or "").strip()[:maxlen], quote=True)

        prefilled = bool(request.args.get("keyword") or request.args.get("title"))
        prebanner = ('<p class="note" style="border-left:3px solid var(--accent,#1baf7a);'
                     'padding-left:10px">Pre-filled from your <b>Launch Kit</b> — add the '
                     'metrics when it sells, then submit to teach the tool.</p>'
                     if prefilled else '')
        form = (f'<form class="savedform" method="post" action="/feedback/add">'
                # 6 core fields cover the Day-3/7 call; the rest are optional detail.
                f'<input name="listing_url" value="{_pf("listing_url", 300)}" placeholder="Listing URL" required>'
                f'<input name="keyword" value="{_pf("keyword", 80)}" placeholder="Main keyword (links the saved run)">'
                f'<input name="price" type="number" step="any" value="{_pf("price", 12)}" placeholder="Price">'
                f'<input name="day_7_views" type="number" placeholder="Day 7 views">'
                f'<input name="orders" type="number" placeholder="Orders">'
                f'<input name="revenue" type="number" step="any" placeholder="Revenue">'
                f'<details class="fbmore"{" open" if prefilled else ""}><summary>＋ More metrics (optional)</summary>'
                f'<div class="fbgrid">'
                f'<input name="publish_date" value="{_pf("publish_date", 20)}" placeholder="Publish date (YYYY-MM-DD)">'
                f'<input name="product_mode" value="{_pf("product_mode", 20)}" placeholder="Mode (pod/embroidery)">'
                f'<input name="supplier" value="{_pf("supplier", 80)}" placeholder="Supplier">'
                f'<input name="product_cost" type="number" step="any" placeholder="Product cost">'
                f'<input name="shipping_cost" type="number" step="any" placeholder="Shipping cost">'
                f'<input name="title" value="{_pf("title", 140)}" placeholder="Title">'
                f'<input name="tags" value="{_pf("tags", 300)}" placeholder="Tags (comma-separated — folds into learning)">'
                f'<input name="main_image_version" placeholder="Main image version (e.g. v2)">'
                f'<input name="mockup_style" placeholder="Mockup style (flat / lifestyle / gift)">'
                f'<input name="personalization_offer" value="{_pf("personalization_offer", 80)}" placeholder="Personalization offered">'
                f'<input name="bundle_offer" placeholder="Bundle offered">'
                f'<input name="day_1_impressions" type="number" placeholder="Day 1 impressions">'
                f'<input name="day_3_views" type="number" placeholder="Day 3 views">'
                f'<input name="favorites" type="number" placeholder="Favorites">'
                f'<input name="carts" type="number" placeholder="Carts">'
                f'<input name="profit" type="number" step="any" placeholder="Profit">'
                f'<input name="refund_or_issue" placeholder="Refund / issue (or none)">'
                f'</div></details>'
                f'<textarea name="notes" placeholder="Notes"></textarea>'
                f'<button class="primary" type="submit">Log + get Day-3/7 recommendation</button>'
                f'</form>')
        items = ""
        for r in reversed(fb.load()):
            a7 = r.get("day7_action") or r.get("recommendation", "")
            v = r.get("day_7_views") or r.get("views", 0)
            items += ('<div class="saveditem"><div class="sihead">'
                      f'<b>{_h.escape((r.get("title") or r.get("listing_url") or "")[:58])}</b> '
                      f'<span class="pill apill">{_h.escape(a7)}</span> '
                      + _post_btn(f'/feedback/del/{r["id"]}', "delete",
                                  confirm="Delete this feedback entry?") + '</div>'
                      + f'<div class="note">{_h.escape(r.get("product_mode",""))} · '
                      f'{v} views · {r.get("favorites",0)} favs · '
                      f'{r.get("carts",0)} carts · {r.get("orders",0)} orders · '
                      f'logged {r.get("added_at","")}</div>'
                      f'<p><b>Day 3 → {_h.escape(r.get("day3_action",""))}:</b> '
                      f'{_h.escape(r.get("day3_reason",""))}</p>'
                      f'<p><b>Day 7 → {_h.escape(a7)}:</b> '
                      f'{_h.escape(r.get("day7_reason") or r.get("rec_reason",""))}</p></div>')
        _lq = (request.args.get("q") or "").strip()[:80]
        bar = (_bar() + _stage_nav("learn", _lq, request.args.get("mode") or "")
               + _teamops_strip(
                   [("DAY3_FOLLOWUP", "Day 3 check"), ("DAY7_FOLLOWUP", "Day 7 check"),
                    ("FIX_REQUEST", "Assign fix")], keyword=_lq,
                   lead="Schedule the follow-up checks"))
        return page("Sales feedback", bar + '<article class="md"><h1>Sales feedback '
                    'loop</h1><p>After you MANUALLY publish, log the listing\'s real '
                    'numbers to get a Day-3/7 <b>KEEP / CHANGE / KILL / SCALE</b> '
                    'recommendation. This private performance data is your edge — every '
                    'logged order feeds the learning loop that lifts proven niches in '
                    'your Winner Finder.</p>' + prebanner
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

    @app.route("/feedback/del/<int:fid>", methods=["POST"])
    @login_required
    def feedback_del(fid):
        _check_csrf()
        from src import feedback as fb
        fb.delete(fid)
        return redirect(url_for("feedback"))

    # ---- other live self-serve tools (all MCP-backed, run on the VPS 24/7) ----
    def _mode_switch(endpoint, current, q=""):
        """One-click POD / Embroidery / All toggle for mode-aware tool pages.
        Reuses the pullbar styling; the active line is highlighted.
        Carries the typed keyword, so switching product line no longer throws
        away what you were looking at."""
        from urllib.parse import quote_plus as _qp
        row = []
        for val, label in (("pod", "Print on Demand"),
                           ("embroidery", "Embroidery"), ("", "All lines")):
            qs = ([f"mode={val}"] if val else []) + ([f"q={_qp(q)}"] if q else [])
            href = f"/{endpoint}" + ("?" + "&".join(qs) if qs else "")
            cls = "pullbtn primary" if (current or "") == val else "pullbtn"
            row.append(f'<a class="{cls}" href="{href}">{label}</a>')
        return ('<div class="pullbar"><div class="pulltxt"><b>Product line</b>'
                '<span>Switch POD &#8646; Embroidery for this tool</span></div>'
                '<div class="pullbtns">' + "".join(row) + '</div></div>')

    def _tool_head(endpoint, q="", mode="", stage=None, action=None,
                   button="Search →", next_href=None, next_label=None):
        """The SAME header on every tool page: phase strip + Back/Next, a
        keyword box, and the POD/Embroidery switch.

        These three used to be mutually exclusive. `_mode_tool` pages
        (/trending, /opportunities, /gems) got the product-line switch but no
        keyword box; `_kw_mode_tool` pages (/pattern-miner, /keyword-lab,
        /inbox) got the keyword box but no product-line switch; and three step
        routes (/pinterest-trends, /suppliers, /team/ops) got neither, so they
        were dead ends that forced a trip back to the home page."""
        head = ""
        if stage:
            head += _stage_nav(stage, q, mode)
        head += _stage_kwbar(action or f"/{endpoint.strip('/')}", q, button,
                             next_href, next_label, mode=mode)
        head += _mode_switch(endpoint.strip("/"), mode if mode in
                             ("pod", "embroidery") else "", q)
        return head

    def _render_tool(title, txt, switch=""):
        html = md.markdown(txt, extensions=["tables", "fenced_code",
                                            "sane_lists"])
        bar = _bar()
        return page(title, bar + switch
                    + f'<article class="md">{html}</article>' + COPY_JS)

    def _tool_error(title, exc):
        import html as _html
        bar = _bar()
        return page(title, bar + f'<article class="md"><h1>{title}</h1>'
                    f'<p class="empty">The live data source is unavailable right '
                    f'now: {_html.escape(str(exc)[:200])}</p></article>')

    def _kw_tool(fn, title):
        import html as _html
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        if not q:
            bar = _bar()
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

    def _source_toggle(endpoint, mode, source):
        """Live YTrends market data  |  Local Capture Index. The local index is
        your accumulated + listing-mined keywords — useful for exploration, but
        it can be stale/partial and its mined rows are supply-side PROXIES, not
        buyer demand. Labelled explicitly (senior-review W06) so it's never read
        as equal to live market data."""
        from urllib.parse import urlencode
        base = {}
        if mode:
            base["mode"] = mode
        def _lnk(val, label):
            q = dict(base)
            if val:
                q["source"] = val
            on = "on" if (source == val or (not source and not val)) else ""
            return (f'<a class="stgn {on}" href="/{endpoint}?{urlencode(q)}">'
                    f'{label}</a>')
        bar = ('<div class="stgnav" style="margin-top:6px">'
               '<span style="font-size:11px;color:var(--ink-faint);'
               'align-self:center;margin-right:4px">Source:</span>'
               + _lnk(None, "\U0001F310 Live YTrends market")
               + _lnk("mine", "\U0001F5C3️ Local Capture Index") + '</div>')
        if source == "mine":
            try:
                from src import data_store as _ds
                s = _ds.stats()
                bar += (
                    '<div class="warn" style="margin-top:6px;font-size:.8rem">'
                    '🗃️ <b>Local Capture Index</b> — your captured/mined data, '
                    'not live market data. '
                    f'<b>{s.get("keywords", 0)}</b> keywords '
                    f'(<b>{s.get("mined", 0)}</b> mined proxies, '
                    f'{s.get("proxy_pct", 0)}%), '
                    f'{s.get("listings", 0)} listings · newest capture '
                    f'{str(s.get("newest_capture") or "—")[:10]} · '
                    f'freshness <b>{s.get("freshness", "unknown")}</b>. '
                    'Mined rows are <b>supply-side proxies</b> (listing-tag &amp; '
                    'shop counts, not search demand) — capped at '
                    '<b>Confirm-first</b>, never Build-Now.</div>')
            except Exception:  # noqa: BLE001
                pass
        return bar

    def _mode_tool(fn, title, filterable=False, stage=None):
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        endpoint = request.path.strip("/")
        show_all = request.args.get("show") == "all"
        source = request.args.get("source")
        source = source if source in ("mine", "live") else None
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        from src import interactive
        try:
            # These are BROWSE feeds - they list a market, they do not take a
            # keyword. So the box sends the typed keyword to the step that DOES
            # rank it, and the button says so outright rather than looking like
            # an on-page filter that silently navigates away.
            switch = _tool_head(endpoint, q, m or "", stage=stage,
                                action="/inbox", button="🏆 Rank this keyword →")
            if filterable:
                switch += _risk_toggle(endpoint, mode, show_all)
                switch += _source_toggle(endpoint, mode, source)
                out = fn(interactive, mode, show_all, source)
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

    def _kw_mode():
        """(cleaned keyword, mode) from ?q= plus ?mode= or the command bar's
        supplier_type radio (embroidery/pod/both)."""
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        m = request.args.get("mode") or request.args.get("supplier_type")
        mode = m if m in ("pod", "embroidery") else None
        return q, mode

    def _kw_mode_tool(fn, title, path=None, stage=None, button="Run →"):
        q, mode = _kw_mode()
        m = request.args.get("mode") or request.args.get("supplier_type") or ""
        # the workflow strip + an on-page keyword box + the product-line
        # switch: every stage page is self-serve, and the next step is one
        # click with the same keyword. The switch used to be missing here (it
        # only appeared on _mode_tool pages), so staff could not change POD /
        # Embroidery without going back to the home page.
        head = _tool_head(path or request.path, q, m, stage=stage,
                          action=path, button=button) if path else (
            _stage_nav(stage, q, m) if stage else "")
        if not q:
            return page(title, _bar() + head + f'<article class="md"><h1>{title}'
                        '</h1><p class="empty">Type a keyword in the box above '
                        '(or click a step in the strip — it carries your keyword).'
                        '</p></article>')
        from src import interactive
        try:
            return _render_tool(f"{title}: {q}", fn(interactive, q, mode),
                                switch=head)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error(title, exc)

    @app.route("/photo-brief")
    @login_required
    def photo_brief():
        return _kw_mode_tool(lambda iv, q, m: iv.photo_prompts(q, m),
                             "Photo prompt set", path="/photo-brief",
                             stage="images", button="\U0001F4F8 Generate prompts")

    @app.route("/ads-plan")
    @login_required
    def ads_plan():
        return _kw_mode_tool(lambda iv, q, m: iv.ads_plan(q, m),
                             "Etsy Ads starter plan", path="/ads-plan",
                             stage="ads", button="\U0001F4E3 Build ads plan")

    @app.route("/edge")
    @login_required
    def edge():
        return _kw_mode_tool(lambda iv, q, m: iv.edge_finder(q, m),
                             "Beat the competition", path="/edge",
                             stage="build", button="\U0001F94A Find the edge")

    @app.route("/launch-kit")
    @login_required
    def launch_kit():
        # V35: dedicated HTML page (marketplace copy-paste layout), not the
        # markdown pipeline - the markdown kit remains available to other
        # callers via interactive.launch_kit().
        q, mode = _kw_mode()
        m = request.args.get("mode") or request.args.get("supplier_type") or ""
        head = (_stage_nav("build", q, m)
                + _stage_kwbar("/launch-kit", q,
                               "\U0001F680 Build Launch Kit", mode=m)
                + _mode_switch("launch-kit", m if m in ("pod", "embroidery") else "", q))
        if not q:
            return page("Launch Kit", _bar() + head
                        + '<article class="md"><h1>Launch Kit</h1>'
                        '<p class="empty">Type a keyword in the box above '
                        '(or click a step in the strip — it carries your '
                        'keyword).</p></article>')
        from src import launch_kit_page
        try:
            sent = request.args.get("sent") == "1"
            return page(f"Launch Kit: {q}", _bar() + head
                        + launch_kit_page.build(q, mode, sent=sent)
                        + WORKSPACE_JS)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Launch Kit", exc)

    @app.route("/launch-kit/submit", methods=["POST"])
    @login_required
    def launch_kit_submit():
        # V35.1: "Send FINAL to manager" - drops the kit into the EXISTING
        # review queue (/admin/reviews) as a READY_FOR_REVIEW task with an
        # auto-summary + the seller's note. Approval never publishes anything.
        _check_csrf()
        from src import interactive, launch_kit_page
        from src import tasks as tk
        u = current_user()
        raw = (request.form.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        m = request.form.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        if not q:
            return redirect("/launch-kit")
        mode = interactive._mode_for(q, mode)
        note = _no_tags((request.form.get("note") or "").strip())[:1000]
        try:
            ev = interactive.kit_evidence(q, mode)
            price, _b, _s, _c = interactive._price_cost_for(q, mode)
            tags = interactive._tags_for(q, mode=mode)
            summary = launch_kit_page.summary_for_manager(q, mode, ev, price,
                                                         tags)
        except (SystemExit, Exception):  # noqa: BLE001 - summary is best-effort
            summary = f"LISTING APPROVAL REQUEST - {q} [{mode}]"
        if note:
            summary += f"\nSeller note: {note}"
        t = tk.create_task(
            f"List approval: {q}", assigned_by_user_id=u["user_id"],
            assigned_to_user_id=u["user_id"], task_type="MANAGER_REVIEW",
            priority="HIGH", role_target="MANAGER", related_keyword=q,
            description="Launch Kit final review - List / Fix / Decline.")
        tk.update_task(t["task_id"], status="READY_FOR_REVIEW",
                       work_report=summary)
        _log("TASK_CREATE", module="tasks", entity_type="task",
             entity_id=t["task_id"], summary=f"launch-kit submit: {q}")
        from urllib.parse import quote_plus as _qp2
        return redirect(f"/launch-kit?q={_qp2(q)}&mode={mode}&sent=1")

    @app.route("/design-skill-bridge", methods=["GET"])
    @app.route("/design-analyzer", methods=["GET"])   # V37 legacy alias
    @login_required
    def design_skill_bridge():
        # V37: manual ChatGPT bridge for Etsy POD Redesign V8.1. Replaces the
        # retired Gemini Design Analyzer. No model API on this path.
        from src import design_skill_bridge as dsb
        q, _m = _kw_mode()
        try:
            runs = dsb.list_runs()
        except Exception:  # noqa: BLE001
            runs = []
        return page("Design Skill Bridge",
                    _bar() + _teamops_strip(
                        [("DESIGN", "Assign Design"), ("MOCKUP", "Assign Mockup"),
                         ("PHOTO_STUDIO", "Assign Photo Studio"),
                         ("REVIEW_QA", "Submit to Review Queue")],
                        keyword=q or "", lead="Assign the image work")
                    + dsb.form_html(_csrf(), prefill_q=q or "", runs=runs))

    @app.route("/design-skill-bridge/run/<run_id>")
    @login_required
    def design_skill_bridge_run(run_id):
        from src import design_skill_bridge as dsb
        run = dsb.get_run((run_id or "").strip()[:60])
        return page("Design Skill Bridge", _bar() + dsb.run_view_html(run, _csrf()))

    @app.route("/design-skill-bridge/pack", methods=["POST"])
    @login_required
    def design_skill_bridge_pack():
        _check_csrf()
        from src import design_skill_bridge as dsb
        _u = current_user() or {}
        data = dict(request.form)
        if not data.get("launched_by"):
            data["launched_by"] = (_u.get("display_name") or _u.get("email")
                                   or "owner")
        try:
            inp = dsb.create_pack(data)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Design Skill Bridge", exc)
        return page("Design Skill Bridge", _bar() + dsb.pack_html(inp, _csrf()))

    @app.route("/design-skill-bridge/import", methods=["POST"])
    @login_required
    def design_skill_bridge_import():
        _check_csrf()
        from src import design_skill_bridge as dsb
        raw = (request.form.get("raw") or "")[:20000]
        keyword = (request.form.get("keyword") or "")[:120]
        _u = current_user() or {}
        operator = _u.get("display_name") or _u.get("email") or ""
        try:
            run_id, v = dsb.import_pasted(raw, operator=operator, keyword=keyword)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Design Skill Bridge", exc)
        if not run_id:
            return page("Design Skill Bridge",
                        _bar() + dsb.result_html(v, "-", _csrf()))
        return page("Design Skill Bridge", _bar() + dsb.result_html(v, run_id, _csrf()))

    @app.route("/design-skill-bridge/approve", methods=["POST"])
    @login_required
    def design_skill_bridge_approve():
        _check_csrf()
        from src import design_skill_bridge as dsb
        run_id = (request.form.get("run_id") or "").strip()[:60]
        _u = current_user() or {}
        # owner/manager only — reuse the review permission as the approval gate
        if not auth.has_perm(_u.get("role", ""), "tasks.review"):
            return _tool_error("Design Skill Bridge",
                               ValueError("Chỉ Manager/Owner mới được duyệt."))
        res = dsb.approve(run_id, owner=_u.get("display_name") or _u.get("email") or "")
        if not res.get("ok"):
            return _tool_error("Design Skill Bridge", ValueError(res.get("error", "")))
        seeds = dsb.listing_seeds(run_id)
        return page("Design Skill Bridge",
                    _bar() + dsb.approved_html(run_id, seeds, _csrf()))

    @app.route("/design-skill-bridge/reject", methods=["POST"])
    @login_required
    def design_skill_bridge_reject():
        _check_csrf()
        from src import design_skill_bridge as dsb
        run_id = (request.form.get("run_id") or "").strip()[:60]
        _u = current_user() or {}
        if not auth.has_perm(_u.get("role", ""), "tasks.review"):
            return _tool_error("Design Skill Bridge",
                               ValueError("Chỉ Manager/Owner mới được reject."))
        dsb.reject(run_id, owner=_u.get("display_name") or _u.get("email") or "")
        return redirect("/design-skill-bridge")

    @app.route("/design-skill-bridge/send-to-launchkit", methods=["POST"])
    @login_required
    def design_skill_bridge_send():
        _check_csrf()
        from src import design_skill_bridge as dsb
        run_id = (request.form.get("run_id") or "").strip()[:60]
        out = dsb.send_to_launchkit(run_id)
        if not out.get("ok"):
            return _tool_error("Design Skill Bridge", ValueError(out.get("error", "")))
        from urllib.parse import quote_plus as _qpl
        return redirect(f"/launch-kit?q={_qpl(out.get('keyword', ''))}")

    @app.route("/design-skill-bridge/delete", methods=["POST"])
    @login_required
    def design_skill_bridge_delete():
        _check_csrf()
        from src import design_skill_bridge as dsb
        run_id = (request.form.get("run_id") or "").strip()[:60]
        _u = current_user() or {}
        # owner/manager only — same gate as approve/reject
        if not auth.has_perm(_u.get("role", ""), "tasks.review"):
            return _tool_error("Design Skill Bridge",
                               ValueError("Chỉ Manager/Owner mới được xoá."))
        dsb.delete_run(run_id)
        return redirect("/design-skill-bridge")

    @app.route("/design-skill-bridge/set-keyword", methods=["POST"])
    @login_required
    def design_skill_bridge_set_keyword():
        _check_csrf()
        from src import design_skill_bridge as dsb
        run_id = (request.form.get("run_id") or "").strip()[:60]
        keyword = (request.form.get("keyword") or "")[:120]
        dsb.set_keyword(run_id, keyword)
        return redirect(f"/design-skill-bridge/run/{run_id}")


    @app.route("/training")
    @login_required
    def training():
        # V35.9: serve the Vietnamese staff walkthrough as a full page.
        #
        # This guide teaches the RETIRED 9-stage flow (Build Queue · Feed ·
        # Rank · Pattern Miner · Keyword Lab · Re-rank · Build · Photo · Ads ·
        # Learn). It is a good TOOL reference and a wrong PROCESS map: it has
        # no Pinterest step, no supplier-feasibility step and no HeyEtsy
        # evidence step, so it contradicts both the home page and WORKFLOW.md.
        # Rather than silently leave that, or fabricate 34KB of replacement
        # Vietnamese, we prepend a banner GENERATED FROM workflow_spine so the
        # mapping can never drift, and say plainly what the guide omits.
        from pathlib import Path as _P
        from flask import Response as _Resp
        _CH2PH = {"find": ["FEED"], "rank": ["BUILD QUEUE", "RANK"],
                  "learn": ["PATTERN MINER"],
                  "newkw": ["KEYWORD LAB", "RE-RANK"],
                  "ship": ["BUILD", "PHOTO STUDIO", "ADS TEST", "LEARN"]}
        for _p in (_P("staff_guide_vn.html"), _P("docs/staff_guide_vn.html")):
            if _p.is_file():
                _doc = _p.read_text(encoding="utf-8")
                try:
                    from src import workflow_spine as _wsg
                    _rows = "".join(
                        f'<tr><td><b>{ph["p"]} {ph["icon"]} {_h_esc(ph["vi"])}</b>'
                        f'</td><td>{_h_esc(" · ".join(_CH2PH.get(ph["key"], [])) or "—")}'
                        f'</td><td><a href="{ph["route"]}">{ph["route"]}</a></td></tr>'
                        for ph in _wsg.PHASES)
                    _missing = ", ".join(
                        s["name"] for s in _wsg.STEPS
                        if s["key"] in ("pinterest", "supplier", "evidence"))
                    _ban = (
                        '<div style="max-width:1000px;margin:14px auto;padding:14px 18px;'
                        'border:1px solid #d9822b;border-left:5px solid #d9822b;'
                        'border-radius:11px;background:#fff8ef;color:#222;'
                        'font:14px/1.5 system-ui,sans-serif">'
                        '<b>⚠️ Đây là tài liệu HƯỚNG DẪN TỪNG CÔNG CỤ, không phải quy '
                        'trình chính thức.</b><br>Nó viết theo <b>9 bước cũ</b>. Quy '
                        'trình đang dùng là <b>5 giai đoạn</b> — xem '
                        '<a href="/workflow"><b>/workflow</b></a> hoặc trang chủ.'
                        '<table style="width:100%;margin-top:10px;border-collapse:collapse;'
                        'font-size:13px"><tr style="text-align:left">'
                        '<th>Giai đoạn (đúng)</th><th>Chương trong tài liệu này</th>'
                        '<th>Route</th></tr>' + _rows + '</table>'
                        f'<p style="margin:9px 0 0;font-size:12.5px"><b>Tài liệu này '
                        f'THIẾU:</b> {_h_esc(_missing)} — ba bước đó chỉ có trong '
                        '<a href="/workflow">/workflow</a>.</p></div>')
                    _doc = (_doc.replace("<body>", "<body>" + _ban, 1)
                            if "<body>" in _doc else _ban + _doc)
                except Exception:  # noqa: BLE001 - never break the guide
                    pass
                return _Resp(_doc, mimetype="text/html")
        return page("Huong dan", _bar() + '<article class="md"><p>Chua cai tai '
                    'lieu (staff_guide_vn.html).</p></article>')


    @app.route("/trending")
    @login_required
    def trending():
        return _mode_tool(lambda iv, m, s, src: iv.trending(m, s, src),
                          "Trending now", filterable=True, stage="feed")

    @app.route("/opportunities")
    @login_required
    def opportunities():
        return _mode_tool(lambda iv, m, s, src: iv.opportunities(m, s, src),
                          "Opportunities", filterable=True, stage="feed")

    @app.route("/gems")
    @login_required
    def gems():
        return _mode_tool(lambda iv, m, s, src: iv.gems(m, s, src),
                          "Hidden gems", filterable=True, stage="feed")

    @app.route("/newest")
    @login_required
    def newest():
        return _mode_tool(lambda iv, m, s, src: iv.newest(m, s),
                          "Newest fresh winners", filterable=True, stage="feed")

    @app.route("/categories")
    @login_required
    def categories():
        from src import interactive
        sort = request.args.get("sort") or "opportunity"
        labels = [("opportunity", "Opportunity"), ("revenue", "Revenue"),
                  ("conversion", "Conversion"), ("sellers", "Fewest sellers")]
        srow = "".join(
            f'<a class="pullbtn{" primary" if sort == sk else ""}" '
            f'href="/categories?sort={sk}">{sl}</a>' for sk, sl in labels)
        sortbar = ('<div class="pullbar"><div class="pulltxt"><b>Sort</b>'
                   '<span>Rank whole categories by</span></div>'
                   f'<div class="pullbtns">{srow}</div></div>')
        try:
            return _render_tool("Category intelligence",
                                interactive.category_intel(sort), switch=sortbar)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Category intelligence", exc)

    @app.route("/daily-brief")
    @login_required
    def daily_brief():
        return _mode_tool(lambda iv, m: iv.daily_brief(m), "Daily brief")

    @app.route("/score-import")
    @login_required
    def score_import():
        from src import interactive
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        source = (request.args.get("source") or "").strip() or None
        enrich = request.args.get("enrich") == "1"
        gtrends = request.args.get("gt") == "1"
        try:
            return _render_tool("Score latest import",
                                interactive.score_import(source, mode, enrich,
                                                         gtrends))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Score latest import", exc)

    @app.route("/inbox")
    @login_required
    def inbox():
        from src import interactive
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        # sanitize like _kw_mode does (audit fix: raw q reached the markdown
        # renderer, so [x](javascript:...) injected a live link - XSS)
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        show_all = request.args.get("show") == "all"
        bar = (_stage_nav("rank", q, m or "")
               + _stage_kwbar("/inbox", q, "\U0001F3C6 Rank / focus keyword",
                              mode=m or "")
               + _mode_switch("inbox", mode or "", q))
        # Needs-Enrichment queue (V32): one-click MCP enrich for lane leads
        try:
            from src import opportunity_inbox as _oi2
            _ne = _oi2.build_inbox(mode, limit=1)["counts"].get(
                "needs_enrichment", 0)
            if _ne:
                bar += (f'<form method="post" action="/enrich-leads" '
                        'style="margin:0 0 10px">'
                        f'<input type="hidden" name="_csrf" value="{_csrf()}">'
                        f'<input type="hidden" name="mode" value="{m or ""}">'
                        '<button class="pullbtn primary" type="submit">'
                        f'\U0001F50C Enrich {min(_ne, 12)} capture-lane leads via '
                        'MCP → re-rank</button> <span style="font-size:.78rem;'
                        'color:var(--ink-soft)">fills market data for '
                        'Pinterest/supplier leads · honest-nulls until data '
                        'arrives</span></form>')
        except Exception:  # noqa: BLE001
            pass
        bar += _teamops_strip(
            [("RESEARCH", "Create Task"), ("PATTERN_MINER", "Assign Pattern Miner"),
             ("SUPPLIER_CHECK", "Assign Supplier Check"),
             ("TRADEMARK_CHECK", "Assign Trademark Check")],
            keyword=q, opportunity=q)
        try:
            return _render_tool("Opportunity Inbox",
                                interactive.inbox(mode, q,
                                                  show_archived=show_all),
                                switch=bar)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Opportunity Inbox", exc)

    @app.route("/rerank")
    @login_required
    def rerank_page():
        # V37.5 Phase D: Re-rank is now its OWN decision page over the GENERATED
        # candidates (Keyword Lab / lane leads), not a second link to /inbox.
        from src import interactive
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        bar = (_stage_nav("rerank", q, m or "")
               + _stage_kwbar("/rerank", q,
                              "\U0001F3AF Re-rank generated candidates", mode=m or "")
               + _mode_switch("rerank", mode or "", q))
        bar += _teamops_strip(
            [("LISTING_DRAFT", "Assign Listing Draft"), ("DESIGN", "Assign Design"),
             ("PHOTO_STUDIO", "Assign Photo Studio"),
             ("REVIEW_QA", "Assign Manager Review")], keyword=q)
        # Confirmation for a winner->Inbox push (step 10 -> 11). Without this the
        # staff member clicks "Send to Re-rank" and lands on a page that looks
        # unchanged, which is exactly the "what just happened?" the loop was
        # meant to remove.
        pushed = (request.args.get("pushed") or "").strip()
        if pushed.isdigit():
            n = int(pushed)
            if request.args.get("pusherr"):
                bar += ('<div class="warn">Nothing was pushed — no candidates '
                        'matched. Import a HeyEtsy Detail / Reviews export for '
                        'that listing first.</div>')
            elif n:
                bar += (f'<div class="ok">✅ {n} winner-derived keyword(s) added '
                        'to the master and ranked below — tagged with the source '
                        'listing. No retyping needed.</div>')
            else:
                bar += ('<div class="ok">Already in the master — nothing '
                        'duplicated. The existing rows are ranked below.</div>')
        try:
            return _render_tool("Re-rank", interactive.rerank(mode, q), switch=bar)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Re-rank", exc)

    @app.route("/longtail")
    @login_required
    def longtail_page():
        """The long-tail lane: evidence-backed phrases a small shop can win.
        A view over the same ranked rows — no scoring/verdict change anywhere."""
        from src import longtail as lt
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        try:
            mw = max(2, min(6, int(request.args.get("words") or lt.MIN_WORDS)))
        except ValueError:
            mw = lt.MIN_WORDS
        bar = (_stage_nav("rank", q, m or "")
               + _stage_kwbar("/longtail", q, "\U0001F48E Filter this niche",
                              mode=m or "")
               + _mode_switch("longtail", mode or "", q))
        # the _csrf hidden field is injected app-wide by _inject_csrf
        bar += ('<form method="post" action="/longtail/pull" class="toolbar">'
                + f'<input type="hidden" name="mode" value="{_h_esc(m or "")}">'
                f'<input name="seeds" placeholder="Seeds to expand (blank = your '
                f'best sellers), e.g. embroidered hat, dad shirt">'
                '<button class="primary" type="submit">\U0001F53D Pull more '
                'long-tails from YTrends</button></form>')
        try:
            return _render_tool("Long-tail lane", lt.page(mode, q, min_words=mw),
                                switch=bar)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Long-tail lane", exc)

    @app.route("/longtail/pull", methods=["POST"])
    @login_required
    def longtail_pull():
        """Supply: ask YTrends for the long-tails related to a seed. They arrive
        WITH per-tag revenue + conversion, so they can be judged immediately."""
        _check_csrf()
        from src import longtail as lt
        m = request.form.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        raw = (request.form.get("seeds") or "").strip()[:300]
        seeds = [s.strip() for s in raw.split(",") if s.strip()][:8]
        if not seeds:
            seeds = [s["keyword"] for s in
                     lt.shortlist(mode, limit=6)["rows"]][:6]
        if not seeds:
            return redirect("/longtail")
        try:
            rows = lt.pull(seeds, per_seed=10)
            added = lt.save_rows(rows)
            activity.log("longtail_pull", module="longtail",
                         action=f"{len(seeds)} seed(s) -> {added} new long-tail(s)")
            try:
                from src import import_ledger as _il
                _u = current_user()
                _il.record(user=(_u or {}).get("display_name")
                           or (_u or {}).get("email"),
                           channel="longtail", view="long-tail pull",
                           rows=len(rows), kw_new=added)
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            return _tool_error("Long-tail pull", exc)
        return redirect(f"/longtail{'?mode=' + m if mode else ''}")

    @app.route("/enrich-leads", methods=["POST"])
    @login_required
    def enrich_leads():
        _check_csrf()
        m = request.form.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        from src import opportunity_inbox as oi
        from src import keyword_lab as kl
        leads = oi.lead_keywords(mode, limit=12)
        if not leads:
            return redirect(f"/inbox{'?mode=' + m if mode else ''}")
        try:
            added, enriched = kl.save_candidates(
                leads, mode, enrich=True, limit=12, source="lane-enrich")
            activity.log("enrich_leads", module="opportunity_inbox",
                         action=f"enriched {enriched}/{added} lane leads")
            try:
                from src import import_ledger as _il
                _u = current_user()
                _il.record(user=(_u or {}).get("display_name")
                           or (_u or {}).get("email"),
                           channel="lane-enrich", view="needs-enrichment queue",
                           rows=len(leads), kw_new=added)
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            return _tool_error("Enrich leads", exc)
        return redirect(f"/inbox{'?mode=' + m if mode else ''}")

    @app.route("/status")
    @login_required
    def pipeline_status_page():
        import html as _h
        from src import pipeline_status as ps
        s = ps.snapshot()
        c = s.get("counts", {})
        src = s.get("sources", {})
        lanes = "".join(
            f"<tr><td><b>{_h.escape(name)}</b></td><td>{v['files']}</td>"
            f"<td>{_h.escape(ps._age(v['newest']) or '—')}</td></tr>"
            for name, v in s["lanes"].items())
        li = s.get("last_import") or {}
        warns = "".join(f'<div class="notice warn">⚠ {_h.escape(w)}</div>'
                        for w in s.get("warnings", []))
        content = (
            '<article class="md"><h1>\U0001FA7A Pipeline Health</h1>'
            f'<p><b>V{_h.escape(s["version"])}</b> · build '
            f'<code>{_h.escape(s["git_sha"])}</code> · service started '
            f'{_h.escape(s["started_ago"] or "?")} — if this SHA does not match '
            'your latest <code>git push</code>, the VPS is running a STALE '
            'build.</p>' + warns +
            '<h2>Data freshness</h2><table>'
            f'<tr><th>Master keyword CSV</th><td>{src.get("master_rows", "?")} rows'
            f'</td><td>{_h.escape(s["age"]["master"] or "never")}</td></tr>'
            f'<tr><th>Proof (Alura + captures)</th><td>'
            f'{src.get("proof_listings", 0)} listings</td>'
            f'<td>{_h.escape(s["age"]["proof"] or "never")}</td></tr>'
            f'<tr><th>Your sales learning file</th><td>—</td>'
            f'<td>{_h.escape(s["age"]["learning"] or "never")}</td></tr></table>'
            '<h2>Capture lanes</h2><table><tr><th>Lane</th><th>Files</th>'
            f'<th>Newest</th></tr>{lanes}</table>'
            '<h2>Ranking right now</h2>'
            f'<p>{c.get("total", "?")} active keywords — \U0001F3C6 '
            f'{c.get("proven", 0)} proven · \U0001F7E2 {c.get("selling", 0)} '
            f'selling · \U0001F680 {c.get("build", 0)} build · '
            f'\U0001F5C4 {c.get("archived", 0)} archived (stale WATCH) · '
            f'\U0001F50C {c.get("needs_enrichment", 0)} need enrichment.</p>'
            '<h2>Last file import</h2>'
            + (f'<p>{li.get("rows", 0)} rows from {li.get("files", 0)} file(s) '
               f'→ lanes: {_h.escape(str(li.get("lanes", {})))}</p>'
               if li else '<p class="empty">No file imports yet.</p>')
            + '<p class="note">Keyword growth &amp; who added what: '
            '<a href="/kw-history">/kw-history</a>.</p></article>')
        return page("Pipeline Health", _bar() + content)

    @app.route("/kw-history")
    @login_required
    def kw_history():
        """Keyword-base growth + attribution: daily adds by channel, per-person
        totals (from the import ledger), and the recent import events."""
        import html as _h
        from src import import_ledger as il
        g = il.stats(days=14)
        chan_cols = sorted({c for d in g["daily"] for c in d["by_channel"]})
        chead = "".join(f"<th>{_h.escape(c)}</th>" for c in chan_cols)
        drows = ""
        for d in g["daily"]:
            cells = "".join(f"<td>{d['by_channel'].get(c, '') or ''}</td>"
                            for c in chan_cols)
            drows += (f"<tr><td><b>{_h.escape(d['date'])}</b></td>"
                      f"<td><b>+{d['added']}</b></td>{cells}</tr>")
        if not drows:
            drows = ('<tr><td colspan="9">No dated additions yet — dates start '
                     'recording correctly from this deploy.</td></tr>')
        urows = "".join(
            f"<tr><td><b>{_h.escape(str(u['user']))}</b></td><td>+{u['today']}</td>"
            f"<td>+{u['last7']}</td><td>+{u.get('last30', 0)}</td>"
            f"<td><b>+{u['total']}</b></td>"
            f"<td>{u['rows']}</td><td>{u['events']}</td></tr>"
            for u in g["by_user"]) or (
            '<tr><td colspan="7">No import events recorded yet. Staff names '
            'appear here once they set "Your name" in the extension popup, or '
            'when they drop files while logged in.</td></tr>')
        # RECONCILING table: distinct keywords per channel, sums to the base.
        # This is the honest "where did my keywords come from" view — unlike the
        # per-person cumulative counts, these add up to your real total.
        crows = "".join(
            f"<tr><td><b>{_h.escape(str(c['channel']))}</b></td>"
            f"<td><b>{c['count']}</b></td><td>{c['pct']}%</td></tr>"
            for c in g.get("base_by_channel", [])) or (
            '<tr><td colspan="3">Base is empty.</td></tr>')
        def _evt_result(e):
            new = int(e.get("kw_new", 0) or 0)
            upd = int(e.get("kw_updated", 0) or 0)
            leads = int(e.get("leads", 0) or 0)
            lanes = e.get("lanes") or {}
            ltype = next(iter(lanes), "") if lanes else ""
            # retro-fill leads for events logged before this column existed, so
            # the older listing sends also stop reading as a bare "+0".
            if (not leads and new == 0 and upd == 0 and ltype
                    and ltype not in ("keywords", "categories", "empty")):
                leads = int(e.get("rows", 0) or 0)
            parts = []
            if new:
                parts.append(f'<b style="color:#15803d">+{new} new kw</b>')
            if upd:
                parts.append(f'<span style="color:#2563eb">{upd} updated</span>')
            if leads:
                parts.append(f'<span style="color:#a16207">{leads} leads</span>')
            return " · ".join(parts) if parts else '<span style="color:#999">—</span>'
        erows = "".join(
            f"<tr><td>{_h.escape(str(e.get('date', '')))}</td>"
            f"<td>{_h.escape(str(e.get('user', '')))}</td>"
            f"<td>{_h.escape(str(e.get('channel', '')))}</td>"
            f"<td>{_h.escape(str(e.get('view', ''))[:40])}</td>"
            f"<td>{e.get('rows', 0)}</td><td>{_evt_result(e)}</td></tr>"
            for e in g["recent_events"]) or '<tr><td colspan="6">—</td></tr>'
        # honest date warning when first-seen dates all collapse onto one day
        _date_warn = ""
        if g.get("single_day"):
            _date_warn = (
                '<p class="note" style="background:#fef3c7;padding:8px 12px;'
                'border-radius:6px">⚠️ Almost all keywords share one '
                f'first-seen date ({_h.escape(str(g["single_day"]))}), so '
                '"today / 7 days / 30 days" below are not meaningful yet — an '
                'earlier bug re-stamped the date on every import. Genuine daily '
                'tracking starts from now on.</p>')
        content = (
            '<article class="md"><h1>\U0001F4C8 Keyword base — growth &amp; '
            'who added what</h1>'
            f'<p style="font-size:1.15em"><b>You have {g["total"]} keywords</b> '
            'in your base right now. That is the real number — everything below '
            'is import <i>activity</i>, which can be higher because the same '
            'keywords get re-pulled.</p>'
            f'{_date_warn}'
            '<h2>Where your keywords came from</h2>'
            '<p class="note">Distinct keywords by channel. These add up to your '
            'total base — the honest breakdown of your ' f'{g["total"]}'
            ' keywords.</p>'
            '<table><tr><th>Channel</th><th>Keywords</th><th>Share</th></tr>'
            f'{crows}</table>'
            f'<p><b>+{g["today"]}</b> today · <b>+{g["last7"]}</b> last 7 days · '
            f'<b>+{g.get("last30", 0)}</b> last 30 days '
            '<span class="note">(from first-seen dates; reliable going '
            'forward).</span></p>'
            '<h2>Daily additions (last 14 days, by channel)</h2>'
            f'<table><tr><th>Date</th><th>New keywords</th>{chead}</tr>{drows}</table>'
            '<h2>By person — import activity</h2>'
            '<p class="note">Counted from the import ledger: extension sends '
            '(with the staff name set in the popup), homepage file drops '
            '(logged-in user), Keyword Lab adds, and the MCP auto-pull. '
            '<b>"New-kw imports" counts every import’s new keywords added '
            'up over time</b> — if someone re-pulls the same list, those '
            'keywords are counted again each pull, so this can be far larger '
            'than your actual base. It measures work done, not base size.</p>'
            '<table><tr><th>Who</th><th>Today</th><th>7 days</th><th>30 days</th>'
            '<th>New-kw imports (cumulative)</th><th>Rows imported</th>'
            '<th>Imports</th></tr>'
            f'{urows}</table>'
            '<h2>Recent import events</h2>'
            '<p class="note">Result key: <b style="color:#15803d">new kw</b> = '
            'brand-new keyword phrases · <span style="color:#2563eb">updated</span> '
            '= existing keywords whose market numbers were refreshed by a resend · '
            '<span style="color:#a16207">leads</span> = listing/spy rows captured '
            '(Etsy, Amazon, Pinterest, Alibaba, ytuong) — useful, but not keywords.</p>'
            '<table><tr><th>Date</th><th>Who</th><th>Channel</th><th>View</th>'
            f'<th>Rows</th><th>Result</th></tr>{erows}</table>'
            f'<p class="note">{_h.escape(g["note"])}</p></article>')
        return page("Keyword base history", _bar()
                    + _stage_nav("feed", "", request.args.get("mode") or "")
                    + content)

    # V37.11: the strip on every tool page used to show a NINE-stage model
    # (Feed/Rank/Pattern/Keywords/Re-rank/Build/Images/Ads/Learn) while home
    # showed the five phases. Clicking a phase card landed you on a page telling
    # you a different workflow with different numbers — the single worst
    # inconsistency in the app, and invisible from the home page alone. Both now
    # render from workflow_spine.PHASES, so there is exactly one model.
    # The old stage keys stay valid so all 8 call sites keep working.
    #
    # CAREFUL: "learn" here is the LEGACY 9-stage key meaning post-launch
    # learning (/feedback), which is phase 5 — NOT phase 3 "Learn from
    # winners". Step keys from workflow_spine.STEPS are mapped explicitly so
    # pages can name their phase without colliding with that.
    _STAGE_TO_PHASE = {"feed": "find", "rank": "rank", "pattern": "learn",
                       "lab": "newkw", "rerank": "newkw", "build": "ship",
                       "images": "ship", "ads": "ship", "learn": "ship",
                       # step keys -> phase keys
                       "pinterest": "find", "supplier": "find",
                       "evidence": "learn", "openers": "learn",
                       "extract": "learn", "candidates": "newkw",
                       "team": "ship"}

    _STGNAV_CSS = (
        '<style>.stgnav{display:flex;gap:4px;flex-wrap:wrap;margin:0 0 10px;'
        'align-items:center}'
        '.stgn{font-size:11px;font-weight:700;padding:4px 10px;'
        'border:1px solid var(--line);border-radius:20px;text-decoration:none;'
        'color:var(--ink-soft);background:var(--surface);white-space:nowrap}'
        '.stgn:hover{border-color:var(--accent);color:var(--accent)}'
        '.stgn.on{background:var(--accent);border-color:var(--accent);color:#fff}'
        '.stgstep{font-size:11px;color:var(--ink-faint);margin-left:auto;'
        'white-space:nowrap}'
        '.stgpn{display:flex;gap:6px;margin:0 0 10px;flex-wrap:wrap}'
        '.stgpn a{font-size:11.5px;font-weight:700;padding:5px 12px;'
        'border:1px solid var(--line);border-radius:8px;text-decoration:none;'
        'color:var(--ink-soft);background:var(--surface)}'
        '.stgpn a:hover{border-color:var(--accent);color:var(--accent)}'
        '.stgpn .nx{margin-left:auto;border-color:var(--accent);color:var(--accent)}'
        '</style>')

    def _phase_tail(q="", mode=""):
        """?q=&mode= querystring so every jump carries the keyword + product line."""
        from urllib.parse import quote_plus as _qp
        qs = []
        if q:
            qs.append("q=" + _qp(q))
        if mode in ("pod", "embroidery", "both"):
            qs.append("mode=" + _qp(mode))
        return ("?" + "&".join(qs)) if qs else ""

    def _stage_nav(current, q="", mode=""):
        """The workflow strip ON every stage page: every phase one click away,
        carrying the SAME keyword + mode — never round-trip to the home page.
        Followed by explicit Back / Next buttons, because a strip of five pills
        does not tell staff which way the process flows."""
        tail = _phase_tail(q, mode)
        try:
            from src import workflow_spine as _ws2
            phases = _ws2.PHASES
        except Exception:  # noqa: BLE001 - nav is never allowed to break a page
            return ""
        here = _STAGE_TO_PHASE.get(current, current)
        cur = next((p for p in phases if p["key"] == here), None)
        items = "".join(
            f'<a class="stgn{" on" if ph["key"] == here else ""}"'
            f' href="{ph["route"]}{tail}">{ph["p"]} {ph["icon"]} '
            f'{_h_esc(ph["en"])}</a>'
            for ph in phases)
        if cur:
            items += (f'<span class="stgstep">Phase {cur["p"]} of {len(phases)}'
                      f' · steps {"·".join(str(n) for n in cur["steps"])}</span>')
        # Back / Next: the owner had to return to the home page between every
        # step because no tool page said where the process went next.
        pn = ""
        if cur:
            prev, nxt = _ws2.neighbours(cur["key"])
            btns = ""
            if prev:
                btns += (f'<a href="{prev["route"]}{tail}">◀ Back · {prev["p"]} '
                         f'{_h_esc(prev["en"])}</a>')
            if nxt:
                btns += (f'<a class="nx" href="{nxt["route"]}{tail}">Next · '
                         f'{nxt["p"]} {_h_esc(nxt["en"])} ▶</a>')
            if btns:
                pn = f'<nav class="stgpn">{btns}</nav>'
        return _STGNAV_CSS + '<nav class="stgnav">' + items + "</nav>" + pn

    def _stage_kwbar(action, q, button, next_href=None, next_label=None, mode=""):
        """A keyword box ON the stage page itself (no round-trip to the home) +
        a next-step button that carries the same keyword down the pipeline.
        Carries the POD/Embroidery mode too (audit fix: submitting the box used
        to silently reset the mode filter to 'all')."""
        import html as _h
        qe = _h.escape(q or "", quote=True)
        mfield = (f'<input type="hidden" name="mode" '
                  f'value="{_h.escape(mode, quote=True)}">'
                  if mode in ("pod", "embroidery", "both") else "")
        nxt = (f'<a class="pullbtn" style="white-space:nowrap" href="{next_href}">'
               f'{next_label}</a>' if next_href else "")
        return (f'<form class="toolbar" method="get" action="{action}">{mfield}'
                f'<input name="q" value="{qe}" placeholder="Keyword, e.g. '
                f'patchwork usa tee">'
                f'<button class="primary" type="submit">{button}</button>'
                f'{nxt}</form>')

    @app.route("/pattern-miner")
    @login_required
    def pattern_miner():
        from src import interactive
        from urllib.parse import quote_plus as _uq2
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        bar = (_stage_nav("pattern", q, m or "")
               + _stage_kwbar("/pattern-miner", q, "\U0001F52C Mine pattern",
                              f"/keyword-lab?q={_uq2(q)}" if q else "/keyword-lab",
                              "Next: \U0001F4A1 Keyword Lab →", mode=m or "")
               + _mode_switch("pattern-miner", mode or "", q))
        bar += _teamops_strip(
            [("DESIGN", "Assign Designer"), ("LISTING_DRAFT", "Assign Seller"),
             ("KEYWORD_RERANK", "Send candidates to Re-rank"),
             ("LISTING_UPLOAD", "Create Build Listing task")], keyword=q)
        # Step 10 -> 11. The team-ops strip above only files a TASK saying
        # "send candidates to re-rank"; this actually sends them. Candidates come
        # from the imported winners joined to this keyword by the CF007-guarded
        # bridge, so they can never attach to an unrelated keyword.
        candform = ""
        if q:
            try:
                from src import feed_evidence_router as _fer3
                cands = _fer3.candidates_for_keyword(q)
                if cands:
                    boxes = []
                    for c in cands[:25]:
                        k = _h_esc(c.get("keyword") or "")
                        conf = c.get("match_confidence") or 0
                        mt = _h_esc(str(c.get("match_type") or "").replace("_", " "))
                        src = _h_esc(str(c.get("source_listing_id") or ""))
                        boxes.append(
                            '<label style="display:inline-block;margin:2px 10px 2px 0;'
                            'font-size:12.5px">'
                            f'<input type="checkbox" name="cand" value="{k}" checked> '
                            f'<b>{k}</b> <span style="color:var(--ink-faint)">'
                            f'({mt} · {conf:.2f} · listing {src})</span></label>')
                    candform = (
                        '<form method="post" action="/send-to-rerank" '
                        'style="margin:10px 0 4px">'
                        f'<input type="hidden" name="_csrf" value="{_csrf()}">'
                        f'<input type="hidden" name="q" value="{_h_esc(q)}">'
                        f'<input type="hidden" name="mode" value="{_h_esc(m or "")}">'
                        '<details open style="border:1px solid var(--line);'
                        'border-radius:10px;padding:8px 12px;margin-bottom:8px">'
                        '<summary style="font-size:12.5px;font-weight:700;'
                        f'cursor:pointer">💡 {len(cands)} keyword candidate(s) from '
                        'the winners you imported — pick and send</summary>'
                        f'<div style="margin:8px 0">{"".join(boxes)}</div></details>'
                        '<button class="pullbtn primary" type="submit">➡ Send to '
                        'Re-rank / Inbox</button> '
                        '<span style="font-size:.78rem;color:var(--ink-soft)">'
                        'no retyping · tagged with the source listing · capped at '
                        'CONFIRM_FIRST</span></form>')
            except Exception:  # noqa: BLE001 - additive, never blocks mining
                candform = ""
        try:
            return _render_tool("Pattern Miner",
                                interactive.pattern_miner(q, mode),
                                switch=bar + candform)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Pattern Miner", exc)

    @app.route("/keyword-lab")
    @login_required
    def keyword_lab():
        from src import interactive
        from urllib.parse import quote_plus as _uq3
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        bar = (_stage_nav("lab", q, m or "")
               + _stage_kwbar("/keyword-lab", q, "\U0001F4A1 Generate keywords",
                              f"/rerank?q={_uq3(q)}" if q else "/rerank",
                              "Next: \U0001F3AF Re-rank →", mode=m or "")
               + _mode_switch("keyword-lab", mode or "", q))
        # "Add all to Inbox" form: the save that makes RE-RANK real - candidates
        # are appended to keyword_data.csv (best-effort MCP enrich) and the Inbox
        # re-ranks them through the full layered engine.
        addform = ""
        try:
            from src import keyword_lab as kl
            g = kl.generate(q or None, mode=mode)
            if g["candidates"]:
                import html as _h
                boxes = "".join(
                    '<label style="display:flex;gap:7px;align-items:center;'
                    'font-size:12.5px;padding:3px 0">'
                    f'<input type="checkbox" name="kw" value='
                    f'"{_h.escape(c["keyword"], quote=True)}"'
                    + (" checked" if c.get("bucket") == "build" else "")
                    + f'> {_h.escape(c["keyword"])}'
                    '<span style="color:var(--ink-faint);font-size:11px">'
                    f'{_h.escape(c["angle"].split("·")[-1].strip())}</span>'
                    '</label>' for c in g["candidates"])
                addform = (
                    '<form method="post" action="/keyword-lab/add" '
                    'style="margin:10px 0 4px">'
                    f'<input type="hidden" name="_csrf" value="{_csrf()}">'
                    f'<input type="hidden" name="mode" value="{m or ""}">'
                    f'<input type="hidden" name="q" value="{_h.escape(q, quote=True)}">'
                    '<details open style="border:1px solid var(--line);'
                    'border-radius:10px;padding:8px 12px;margin-bottom:8px">'
                    '<summary style="font-size:12.5px;font-weight:700;'
                    'cursor:pointer">☑ Choose which keywords to add '
                    '(build-ready pre-checked)</summary>'
                    f'{boxes}</details>'
                    '<button class="pullbtn primary" type="submit">➕ Add '
                    'SELECTED to the Inbox & re-rank →</button> '
                    '<span style="font-size:.78rem;color:var(--ink-soft)">'
                    'saves into keyword_data.csv · MCP-enriched when reachable · '
                    'ranked by the layered engine</span></form>')
        except (SystemExit, Exception):  # noqa: BLE001
            addform = ""
        try:
            return _render_tool("Keyword Lab",
                                interactive.keyword_lab(q, mode),
                                switch=bar + addform)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Keyword Lab", exc)

    @app.route("/keyword-lab/add", methods=["POST"])
    @login_required
    def keyword_lab_add():
        _check_csrf()
        from src import keyword_lab as kl
        m = request.form.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        kws = [k.strip() for k in request.form.getlist("kw") if k.strip()]
        if not kws:                       # legacy textarea fallback
            kws = [k.strip() for k in
                   (request.form.get("kws") or "").splitlines() if k.strip()]
        kws = kws[:20]
        try:
            added, enriched = kl.save_candidates(kws, mode)
            activity.log("keyword_lab_add", module="keyword_lab",
                         action=f"added {added} (enriched {enriched})")
            try:
                from src import import_ledger as _il
                _u = current_user()
                _il.record(user=(_u or {}).get("display_name")
                           or (_u or {}).get("email"),
                           channel="keyword-lab",
                           view=(request.form.get("q") or "")[:60],
                           rows=len(kws), kw_new=added)
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            return _tool_error("Keyword Lab", exc)
        # land on the RE-RANK decision page (V37.5), where the freshly generated
        # candidates live — the button promises "& re-rank", so go there, not to Rank.
        from urllib.parse import quote_plus as _uq3
        qkw = (request.form.get("q") or "").strip()[:80]
        parts = []
        if qkw:
            parts.append("q=" + _uq3(qkw))
        if mode:
            parts.append(f"mode={m}")
        tail = ("?" + "&".join(parts)) if parts else ""
        return redirect(f"/rerank{tail}")

    @app.route("/send-to-rerank", methods=["POST"])
    @login_required
    def send_to_rerank():
        """Workflow step 10 -> 11: push a mined winner's keywords into the Inbox.

        Before V37.7 the keyword map was built on every import and then read by
        nobody, so staff retyped candidates by hand. This is the one action that
        closes that loop; it reuses keyword_lab.save_candidates so keywords enter
        the master through a single path, and records the source listing, reason
        and evidence summary for the audit trail. Promotes nothing: candidates
        are capped at CONFIRM_FIRST and the frozen engine still ranks them.
        """
        _check_csrf()
        from src import feed_evidence_router as _fer
        from urllib.parse import quote_plus as _uq4
        u = current_user() or {}
        m = request.form.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        lid = (request.form.get("listing_id") or "").strip()[:32] or None
        kw = (request.form.get("q") or "").strip()[:80] or None
        picked = [k.strip() for k in request.form.getlist("cand") if k.strip()][:25]
        res = _fer.send_to_rerank(
            listing_id=lid, keyword=kw, keywords=picked or None, mode=mode,
            actor=(u.get("display_name") or u.get("email") or "unknown"))
        try:
            activity.log("send_to_rerank", module="feed_evidence_router",
                         action=(f"{res.get('added', 0)} keyword(s) from "
                                 f"listing {lid or '-'}"))
        except Exception:  # noqa: BLE001
            pass
        parts = []
        if kw:
            parts.append("q=" + _uq4(kw))
        if mode:
            parts.append("mode=" + mode)
        parts.append("pushed=" + str(res.get("added", 0)))
        if not res.get("ok"):
            parts.append("pusherr=1")
        return redirect("/rerank?" + "&".join(parts))

    @app.route("/winners")
    @login_required
    def winners():
        from src import interactive
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        source = request.args.get("source")
        source = source if source in ("mine", "live") else None
        try:
            switch = _source_toggle("winners", mode, source)
            return _render_tool("Winner Finder",
                                interactive.winners(mode, source), switch=switch)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Winner Finder", exc)

    @app.route("/supplier-trends")
    @login_required
    def supplier_trends():
        from src import interactive
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        try:
            return _render_tool("Supplier Trend Finder",
                                interactive.supplier_trends(mode))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Supplier Trend Finder", exc)

    @app.route("/pinterest-trends")
    @login_required
    def pinterest_trends():
        from src import interactive
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        raw = (request.args.get("q") or "").strip()[:80]
        q = "".join(c for c in raw if c.isalnum() or c in " '&-.").strip()
        # Step 2 of the workflow, and it had NO phase strip - a dead end that
        # forced a trip back to the home page.
        head = _tool_head("pinterest-trends", q, m or "", stage="pinterest",
                          action="/inbox", button="🏆 Rank this keyword →")
        try:
            return _render_tool("Pinterest Trend Finder",
                                interactive.pinterest_trends(mode), switch=head)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Pinterest Trend Finder", exc)

    @app.route("/etsy-spy")
    @login_required
    def etsy_spy():
        from src import interactive
        m = request.args.get("mode")
        mode = m if m in ("pod", "embroidery") else None
        try:
            return _render_tool("Etsy Spy", interactive.etsy_spy(mode))
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Etsy Spy", exc)

    # ---- YTrends Exporter extension ingest (token-gated, CORS, no session) ----
    ALLOWED_IMPORT_ORIGINS = {"https://trends.ytuong.ai", "https://ytuong.me",
                              "https://heyetsy.com", "https://www.etsy.com",
                              "https://www.pinterest.com", "https://www.amazon.com",
                              "https://www.alibaba.com",
                              "https://chatgpt.com", "https://chat.openai.com"}
    # regional subdomains (vn.pinterest.com, m.alibaba.com...) share the capture UX
    ALLOWED_IMPORT_SUFFIXES = (".pinterest.com", ".alibaba.com", ".amazon.com")

    def _origin_ok(origin):
        if origin in ALLOWED_IMPORT_ORIGINS:
            return True
        try:
            host = origin.split("://", 1)[1]
        except IndexError:
            return False
        return origin.startswith("https://") and \
            any(host.endswith(sfx) for sfx in ALLOWED_IMPORT_SUFFIXES)

    def _json_resp(obj, code=200):
        import json as _j
        return Response(_j.dumps(obj), status=code, mimetype="application/json")

    def _cors(resp, origin):
        allow = origin if _origin_ok(origin) else "https://trends.ytuong.ai"
        resp.headers["Access-Control-Allow-Origin"] = allow
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Import-Token"
        resp.headers["Access-Control-Max-Age"] = "86400"
        return resp

    @app.route("/api/import", methods=["POST", "OPTIONS"])
    def api_import():
        origin = request.headers.get("Origin", "")
        if request.method == "OPTIONS":               # CORS preflight
            return _cors(Response(status=204), origin)
        token = os.getenv("YTX_IMPORT_TOKEN", "").strip()
        if not token:
            return _cors(_json_resp(
                {"ok": False, "error": "import disabled: set YTX_IMPORT_TOKEN in .env"},
                503), origin)
        # compare_digest, not != : this is the only auth on a session-less public
        # endpoint, and str != leaks the token byte-by-byte via timing.
        if not hmac.compare_digest(request.headers.get("X-Import-Token", ""), token):
            return _cors(_json_resp(
                {"ok": False, "error": "bad or missing X-Import-Token"}, 401), origin)
        payload = request.get_json(force=True, silent=True)
        if payload is None:
            return _cors(_json_resp({"ok": False, "error": "invalid JSON body"}, 400), origin)
        try:
            # Route by COLUMNS with the same lane precedence as /import-file, so a
            # Pinterest / Alibaba / ytuong-Hot / Etsy-search capture from the
            # extension lands in its proper lane instead of the keyword ingester.
            from src import ytx_import
            from src import supplier_trend as _st
            from src import feed_evidence_router as _fer
            hdrs = payload.get("headers") or []
            n_rows = len(payload.get("rows") or [])
            lane = None
            # V37.4 Feed Center Evidence Router: the granular v3.4.0 exports go to
            # their own validated lanes FIRST (before the generic etsy detector),
            # so raw Detail never lands in proof and reviews never land in spy.
            # Search results FIRST: it carries he_sold (would else be grabbed by
            # the HeyEtsy-detail check) but is uniquely marked by rank_position /
            # keyword_match_type. It feeds the Pattern Miner pool, not proof.
            if _st.looks_like_etsy_search_results(hdrs):
                lane = "etsy_search"
            elif _fer.looks_like_heyetsy_detail(hdrs):
                lane = "listing_detail"
            elif _fer.looks_like_etsy_reviews(hdrs):
                lane = "listing_reviews"
            elif _fer.looks_like_etsy_listing_structure(hdrs):
                lane = "listing_structure"
            elif _st.looks_like_supplier(hdrs):
                lane = "supplier"
            elif _st.looks_like_pinterest(hdrs):
                lane = "pinterest"
            elif (not _st.has_keyword_col(hdrs)
                  and _st.looks_like_etsy_listings(hdrs)):
                lane = "etsy"
            if lane == "listing_detail":
                _fer.save_detail(hdrs, payload.get("rows") or [],
                                 source_hint=payload.get("view"))
                summary = {"type": lane, "view": str(payload.get("view") or lane),
                           "rows_received": n_rows}
            elif lane == "listing_reviews":
                _fer.save_reviews(hdrs, payload.get("rows") or [],
                                  source_hint=payload.get("view"))
                summary = {"type": lane, "view": str(payload.get("view") or lane),
                           "rows_received": n_rows}
            elif lane == "listing_structure":
                _fer.save_listing_structure(hdrs, payload.get("rows") or [],
                                            source_hint=payload.get("view"))
                summary = {"type": lane, "view": str(payload.get("view") or lane),
                           "rows_received": n_rows}
            elif lane:
                _st.save_payload(payload, source=lane)
                summary = {"type": lane, "view": str(payload.get("view") or lane),
                           "rows_received": n_rows}
                # Option C hybrid: ALSO index Etsy SERP listings into the clean
                # SQLite layer (files stay for the frozen ranking readers; the DB
                # gives Pattern Miner keyword-keyed queries). Never blocks ingest.
                if lane in ("etsy", "etsy_search"):
                    try:
                        from src import data_store as _ds
                        _ds.index_capture(payload.get("view"), hdrs,
                                          payload.get("rows") or [],
                                          "etsy_vn" if "vietnam" in
                                          str(payload.get("view") or "").lower()
                                          else "etsy")
                    except Exception:  # noqa: BLE001
                        pass
            else:
                summary = ytx_import.ingest(payload)
            # V37.5 Phase A (capture-only, ZERO ranking effect): if the extension
            # tagged this send with a Focus Keyword, record the pulled listings into
            # the exact-keyword evidence lane. Nothing reads this into Rank yet
            # (Phase B, behind an owner decision + config flag).
            try:
                _focus = _fer.clean_text(payload.get("focusKeyword")
                                         or payload.get("focus_keyword"))
                if _focus and (payload.get("rows") or []):
                    _fer.record_focus_evidence(_focus, hdrs,
                                               payload.get("rows") or [],
                                               source_hint=payload.get("view"))
            except Exception:  # noqa: BLE001 - capture is additive, never blocks ingest
                pass
        except ValueError as exc:
            return _cors(_json_resp({"ok": False, "error": str(exc)}, 400), origin)
        except Exception:  # noqa: BLE001
            # Traceback to the server log, not to the caller: the message can
            # carry paths / internals and this endpoint faces the public net.
            app.logger.exception("ytx_import.ingest failed")
            return _cors(_json_resp({"ok": False, "error": "ingest failed"}, 500), origin)
        try:
            activity.log("ytrends_import", module="ytx_import",
                         action=f'{summary["type"]}:{summary["view"]} '
                                f'{summary["rows_received"]} rows')
        except Exception:  # noqa: BLE001
            pass
        # WHO/HOW-MANY ledger: extension sends an optional `operator` (staff
        # name from the popup); without it the event is honestly 'extension'.
        try:
            from src import import_ledger as _il
            _op = str(payload.get("operator") or "").strip()[:60]
            _typ = summary.get("type", "?")
            _rows = summary.get("rows_received", 0)
            _knew = summary.get("keywords_new", 0)
            _kupd = summary.get("keywords_updated", 0)
            # non-keyword lanes (etsy/pinterest/supplier/generic listings) are
            # leads: real captured rows, just not keywords -> count them so a
            # listing send never reads as "+0" and looks like a failure.
            _leads = 0 if _typ in ("keywords", "categories", "empty") else _rows
            _il.record(user=_op or "extension (no name set)",
                       channel="extension", view=summary.get("view", ""),
                       lanes={_typ: _rows},
                       files=1, rows=_rows,
                       kw_new=_knew, kw_updated=_kupd, leads=_leads)
        except Exception:  # noqa: BLE001
            pass
        return _cors(_json_resp({"ok": True, **summary}), origin)

    @app.route("/api/design-result", methods=["POST", "OPTIONS"])
    def api_design_result():
        # V37: the 22Etsy Exporter posts a pasted/extracted RESULT_JSON straight
        # from the ChatGPT skill. We read the bridge_run_id OUT of the JSON and
        # route to the Design Skill Bridge importer (validate + CANDIDATE). Owner
        # approval still happens inside 22etsy — this only saves the copy-paste.
        origin = request.headers.get("Origin", "")
        if request.method == "OPTIONS":
            return _cors(Response(status=204), origin)
        token = os.getenv("YTX_IMPORT_TOKEN", "").strip()
        if not token:
            return _cors(_json_resp(
                {"ok": False, "error": "import disabled: set YTX_IMPORT_TOKEN"}, 503), origin)
        if not hmac.compare_digest(request.headers.get("X-Import-Token", ""), token):
            return _cors(_json_resp(
                {"ok": False, "error": "bad or missing X-Import-Token"}, 401), origin)
        body = request.get_json(force=True, silent=True) or {}
        raw = body.get("raw") or body.get("result") or ""
        if isinstance(raw, dict):
            import json as _j
            raw = _j.dumps(raw)
        from src import design_skill_bridge as dsb
        try:
            run_id, v = dsb.import_pasted(raw)
        except Exception:  # noqa: BLE001
            app.logger.exception("design-result import failed")
            return _cors(_json_resp({"ok": False, "error": "import failed"}, 500), origin)
        if not run_id:
            return _cors(_json_resp(
                {"ok": False, "error": "no RESULT_JSON found in payload"}, 400), origin)
        return _cors(_json_resp(
            {"ok": v["ok"], "run_id": run_id, "errors": v["errors"],
             "warnings": v["warnings"], "state": v["state"]}), origin)

    @app.route("/import-file", methods=["POST"])
    @login_required
    def import_file():
        # Manual CSV/JSON upload straight from the homepage -> same ingest path as
        # the extension -> jump to the Winner Finder. Session-authed + CSRF (unlike
        # the token-gated public /api/import). Pure local parse; no MCP, no network.
        _check_csrf()
        m = request.form.get("mode")
        modeq = f"?mode={m}" if m in ("pod", "embroidery") else ""
        # One OR many files (drop several exports -> one merged, ranked list).
        uploads = [(f.filename, f.read()) for f in request.files.getlist("file")
                   if f and f.filename]   # total bounded by MAX_CONTENT_LENGTH (8 MB)
        if not uploads:
            return _tool_error("Import file", ValueError(
                "No file chosen. Pick one or more .csv / .json exports and try again."))
        try:
            from src import ytx_import
            from src import supplier_trend as st
            from src import feed_evidence_router as fer
            kind_req = (request.form.get("kind") or "auto").lower()

            def _looks_amazon(h):
                blob = " ".join(str(x).lower() for x in (h or []))
                return any(k in blob for k in ("search volume", "competing products",
                                               "asin", "cerebro", "title density"))

            def _looks_product(h):
                # Alura Product Research / EverBee Product Analytics export: per-listing
                # rows with a title + real revenue + sales + an age or reviews column,
                # and NO keyword column. Requiring age/reviews keeps a plain Etsy Spy
                # listings export (title/price/shop, no age) in the Pattern-Miner lane
                # instead of hijacking it here.
                cells = [str(x).lower() for x in (h or [])]
                blob = " ".join(cells)
                has_title = any(k in c for c in cells
                                for k in ("title", "product", "listing", "item"))
                has_rev = "revenue" in blob
                has_sales = any(k in blob for k in ("sales", "sold", "orders"))
                has_age_or_reviews = ("age" in blob or "review" in blob
                                      or "rating" in blob)
                has_kw = any("keyword" in c or "phrase" in c for c in cells)
                return (has_title and has_rev and has_sales
                        and has_age_or_reviews and not has_kw)
            # PER-FILE routing (fix: a multi-drop used to be MERGED first and then
            # routed to ONE lane, so a mixed drop - Etsy search + Pinterest +
            # YTrends Spy - all landed in whichever lane the merged header union
            # happened to look like. Now each file is detected and routed alone.)
            mode_p = m if m in ("pod", "embroidery") else None
            lanes = {}
            headers_seen = []
            parsed_any = False
            kw_new_total = 0
            for fn, raw in uploads:
                try:
                    p1, _n1 = ytx_import.parse_uploads([(fn, raw)])
                except ValueError:
                    lanes["unreadable"] = lanes.get("unreadable", 0)
                    continue
                parsed_any = True
                hf = p1.get("headers") or []
                nrows = len(p1.get("rows") or [])
                headers_seen = hf
                kf = kind_req
                if kf == "auto":
                    # V37.4 evidence lanes first: granular HeyEtsy Detail / Etsy
                    # Reviews (v3.4.0) route to validated lanes, not proof/spy.
                    if st.looks_like_etsy_search_results(hf):
                        kf = "etsy_search"         # ranking listings -> Pattern Miner
                    elif fer.looks_like_heyetsy_detail(hf):
                        kf = "listing_detail"
                    elif fer.looks_like_etsy_reviews(hf):
                        kf = "listing_reviews"
                    elif _looks_product(hf):
                        kf = "proof"               # Alura/EverBee product export
                    elif st.looks_like_supplier(hf):
                        kf = "supplier"
                    elif st.looks_like_pinterest(hf):
                        kf = "pinterest"
                    elif _looks_amazon(hf):
                        kf = "amazon"
                    elif st.has_keyword_col(hf):
                        kf = "keywords"            # YTrends keyword table
                    elif st.looks_like_etsy_listings(hf):
                        kf = "etsy"                # listings/spy -> Pattern Miner + proof
                    else:
                        kf = "keywords"
                if kf == "listing_detail":
                    fer.save_detail(hf, p1.get("rows") or [], source_hint=fn)
                elif kf == "listing_reviews":
                    fer.save_reviews(hf, p1.get("rows") or [], source_hint=fn)
                elif kf == "proof":
                    from src import etsy_proof as ep
                    ep.save_export(hf, p1.get("rows") or [], mode_p,
                                   source="product-export")
                    try:
                        st.save_payload(p1, source="etsy")
                    except Exception:  # noqa: BLE001
                        pass
                elif kf in ("supplier", "pinterest", "etsy", "etsy_search"):
                    st.save_payload(p1, source=kf)
                    if kf in ("etsy", "etsy_search"):
                        try:
                            from src import data_store as _ds
                            _ds.index_capture(p1.get("view") or fn, hf,
                                              p1.get("rows") or [], "etsy")
                        except Exception:  # noqa: BLE001
                            pass
                else:
                    if kf == "amazon":
                        p1["view"] = "amazon-xray"
                    try:
                        _s1 = ytx_import.ingest(p1)
                        kw_new_total += int(_s1.get("keywords_new") or 0)
                    except ValueError:
                        kf = "unreadable"
                lanes[kf] = lanes.get(kf, 0) + nrows
            if not parsed_any:
                raise ValueError("no usable files - pick .csv/.json exports")
            # destination: ranking lanes go to the Inbox; single-lane drops go to
            # their own page
            if any(k in lanes for k in ("proof", "keywords", "etsy", "amazon")):
                dest = f"/inbox{modeq}"
            elif "supplier" in lanes:
                dest = f"/supplier-trends{modeq}"
            elif "pinterest" in lanes:
                dest = f"/pinterest-trends{modeq}"
            elif any(k in lanes for k in ("listing_detail", "listing_reviews")):
                dest = "/imports"   # evidence lanes -> Feed/Import Center, not Inbox
            else:
                dest = f"/inbox{modeq}"
            act = " · ".join(f"{k}:{v}" for k, v in lanes.items())
        except ValueError as exc:
            return _tool_error("Import file", exc)
        except Exception as exc:  # noqa: BLE001
            app.logger.exception("import_file failed")
            return _tool_error("Import file", exc)
        try:
            activity.log("ytrends_import", module="ytx_import",
                         action=f"upload {act}")
        except Exception:  # noqa: BLE001
            pass
        # Import diagnostics: per-lane record shown on the home capture bar so a
        # mis-detected or empty import is never silent.
        try:
            import json as _json
            import time as _time
            Path("data/imports").mkdir(parents=True, exist_ok=True)
            total_rows = sum(lanes.values())
            Path("data/imports/last_import.json").write_text(_json.dumps({
                "ts": _time.time(), "lane": act, "files": len(uploads),
                "rows": total_rows, "lanes": lanes,
                "filenames": [u[0] for u in uploads][:6],
                "headers": [str(h) for h in (headers_seen or [])][:15],
                "empty": total_rows == 0,
                "kw_new": kw_new_total,
            }), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        # WHO/HOW-MANY ledger: file drops are session-authed, so we know the user
        try:
            from src import import_ledger as _il
            _u = current_user()
            _lead_rows = sum(v for k, v in (lanes or {}).items()
                             if str(k).lower() not in ("keywords", "categories", "empty"))
            _il.record(user=(_u or {}).get("display_name") or (_u or {}).get("email"),
                       channel="file-drop", view=act, lanes=lanes,
                       files=len(uploads), rows=sum(lanes.values()),
                       kw_new=kw_new_total, leads=_lead_rows)
        except Exception:  # noqa: BLE001
            pass
        return redirect(dest)

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
        bar = _bar()
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
        bar = _bar()
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
                      + _post_btn(f'/alerts/resolve/{r.get("id")}', "resolve")
                      + f'</div><div class="note">{_h.escape(r.get("kind",""))} · '
                      f'{_h.escape(r.get("source",""))} · {r.get("updated_at","")}</div></div>')
        bar = _bar()
        return page("Alerts", bar + '<article class="md"><h1>🔔 Alerts Center</h1>'
                    '<p>Internal only — no Etsy automation, no publishing. Auto-refreshed '
                    'from system state + the 6 AM run.</p>'
                    + (items or '<p class="empty">✅ Nothing needs attention right now.</p>')
                    + '</article>')

    @app.route("/alerts/resolve/<int:aid>", methods=["POST"])
    @login_required
    def alerts_resolve(aid):
        _check_csrf()
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
        bar = _bar()
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
        bar = _bar()
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
        bar = _bar()
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

    # ---- Vietnamese staff guide (served from the repo's HOW_TO_USE.md) ----
    @app.route("/how-to-use")
    @login_required
    def how_to_use():
        p = ROOT / "HOW_TO_USE.md"
        if not p.is_file():
            abort(404)
        html = md.markdown(p.read_text(encoding="utf-8"),
                           extensions=["tables", "fenced_code", "sane_lists", "toc"])
        bar = _bar()
        return page("How to Use",
                    bar + f'<article class="md">{html}</article>' + COPY_JS)

    # ---- team workflow guide (served from the repo's WORKFLOW.md) ----
    @app.route("/workflow")
    @login_required
    def workflow():
        p = ROOT / "WORKFLOW.md"
        if not p.is_file():
            abort(404)
        html = md.markdown(p.read_text(encoding="utf-8"),
                           extensions=["tables", "fenced_code", "sane_lists", "toc"])
        bar = _bar()
        return page("Team Workflow",
                    bar + f'<article class="md">{html}</article>' + COPY_JS)

    # ============ YTUONG IMPORT CENTER + RESEARCH QUEUE ============
    # YTuong/HeyEtsy is the RESEARCH engine; this dashboard is the EXECUTION engine.
    # We import YTuong findings here and turn them into candidates -> tasks -> drafts
    # -> manager review -> MANUAL publish. No cloning of YTuong pages, no auto-publish.
    FIT_LABELS = {
        "POD_FIT": "POD product", "EMBROIDERY_FIT": "Embroidery product",
        "JEWELRY_FIT": "Jewelry product", "ACRYLIC_FIT": "Acrylic product",
        "THEME_FIT_READY": "Design theme — launch-ready",
        "THEME_FIT_NEEDS_PRODUCT": "Good design theme, but choose a product first",
        "AMBIGUOUS_PHRASE": "Ambiguous — needs a clearer angle",
        "LOW_BUYER_INTENT": "Low buyer intent — unlikely to convert",
        "BROAD_SEED_ONLY": "Too broad — a seed, not a product",
        "SHOP_NAME_LIKELY": "Shop / brand name", "POLICY_RISK": "Policy risk",
        "TRADEMARK_RISK": "Trademark / brand", "DIGITAL_FIT": "Digital only",
    }

    def _fit_pill(status, launchable):
        cls = "apill" if launchable else ""
        label = FIT_LABELS.get(status, status)
        return (f'<span class="pill {cls}" title="{_h_esc(status)}">'
                f'{_h_esc(label)}</span>')

    # ============ CONFIRM & ASSIGN — the simple daily loop ============
    # Paste a YTuong niche -> confirm (fit + trademark + optional Google Trends)
    # -> hand it to a staff member in Embroidery mode. Never publishes.
    def _confirm_verdict(fit, risk, google):
        st = fit["status"]
        if risk == "HIGH" or st in ("POLICY_RISK", "TRADEMARK_RISK", "SHOP_NAME_LIKELY"):
            return "NO", "Not safe or not a real product — skip it."
        if fit["launchable"] and risk == "OK" and (
                not google or google.get("direction") != "falling"):
            return "GO", "Safe, makeable, and buyer intent is clear. Assign it."
        reasons = []
        if not fit["launchable"]:
            reasons.append(fit["reason"])
        if risk == "CAUTION":
            reasons.append("verify the trademark on USPTO first")
        if google and google.get("direction") == "falling":
            reasons.append("Google Trends is falling")
        return "CHECK", "; ".join(reasons) or "Double-check before committing."

    def _xcheck_rows(xc):
        """Render the 3-source demand cross-check + Google rising suggestions.
        Returns (table_rows_html, suggestions_html). Each source is non-blocking:
        live sources show a number, off sources show how to turn them on."""
        from src import crosscheck
        g, p, x = xc.get("google") or {}, xc.get("pinterest"), xc.get("x")
        st = crosscheck.status()
        if g.get("status") == "ok":
            arrow = {"rising": "↑ rising", "flat": "→ flat",
                     "falling": "↓ falling"}.get(g.get("direction"), "?")
            g_html = (f'<b>{arrow}</b> <span class="note">'
                      f'({g.get("momentum_pct")}% vs 3 months ago)</span>')
        else:
            g_html = f'<span class="note">{_h_esc(g.get("note") or g.get("status") or "no data")}</span>'
        if p is None:
            p_html = f'<span class="note">off — {_h_esc(st["Pinterest"])}</span>'
        elif p.get("status") == "ok":
            p_html = ('<b>on growing list ✓</b>' if p.get("on_growing_list")
                      else '<span class="note">not on the growing list right now</span>')
        else:
            p_html = f'<span class="note">{_h_esc(p.get("note") or p.get("status"))}</span>'
        if x is None:
            x_html = f'<span class="note">off — {_h_esc(st["X / Twitter"])}</span>'
        elif x.get("status") == "ok":
            n = x.get("tweets_7d")
            x_html = f'<b>{n if n is not None else "?"}</b> <span class="note">tweets / 7 days</span>'
        else:
            x_html = f'<span class="note">{_h_esc(x.get("note") or x.get("status"))}</span>'
        rd = xc.get("reddit") or {}
        if rd.get("status") == "ok":
            subs = ", ".join(f"r/{s}" for s in (rd.get("top_subreddits") or [])[:3])
            rd_html = (f'<b>{_h_esc(rd.get("buzz", "?"))} buzz</b> '
                       f'<span class="note">({rd.get("posts_30d")} posts · '
                       f'{rd.get("upvotes_30d")} upvotes / 30d'
                       + (f' · {_h_esc(subs)}' if subs else '') + ')</span>')
        else:
            rd_html = ('<span class="note">'
                       f'{_h_esc(rd.get("note") or rd.get("status") or "no data")}</span>')
        rows = (f'<tr><td>Google Trends</td><td>{g_html}</td></tr>'
                f'<tr><td>Pinterest</td><td>{p_html}</td></tr>'
                f'<tr><td>Reddit</td><td>{rd_html}</td></tr>'
                f'<tr><td>X / Twitter</td><td>{x_html}</td></tr>')
        rising = [str(r) for r in (g.get("rising") or [])][:3]
        sug = ""
        if rising:
            chips = " ".join(f'<a class="cbtn" href="/confirm?q={_h_esc(r)}">{_h_esc(r)}</a>'
                             for r in rising)
            sug = (f'<p class="note">💡 Also rising on Google (worth a look, click to '
                   f'confirm): {chips}</p>')
        return rows, sug

    @app.route("/confirm")
    @login_required
    def confirm_niche():
        from src import product_fit as pf, trademark, crosscheck
        raw = (request.args.get("q") or "").strip()[:80]
        kw = "".join(ch for ch in raw if ch.isalnum() or ch in " '&-.").strip()
        want_xcheck = request.args.get("google") == "1"
        form = ('<form class="savedform" method="get" action="/confirm">'
                f'<input name="q" value="{_h_esc(kw)}" '
                'placeholder="Paste a niche/keyword from YTuong, e.g. monogram tote bag" '
                'required><button class="primary" type="submit">Confirm →</button></form>')
        body = ('<article class="md"><h1>✅ Confirm &amp; Assign</h1>'
                '<p class="tklead">Confirm a YTuong niche in one glance — product fit, '
                'trademark, and (optional) demand cross-check (Google Trends · Pinterest '
                '· Reddit · X) — then hand it to a staff member in <b>Embroidery</b> mode. '
                'Never publishes.</p>' + form)
        if kw:
            fit = pf.classify(kw, "embroidery")
            risk, why = trademark.check(kw)
            xc = crosscheck.confirm(kw) if want_xcheck else None
            google = xc.get("google") if xc else None
            verdict, note = _confirm_verdict(fit, risk, google)
            badge = {"GO": "✅ GO", "CHECK": "⚠️ CHECK", "NO": "⛔ NO"}[verdict]
            noticecls = "notice" if verdict == "GO" else "notice warn"
            if xc is None:
                xrows = ('<tr><td>Demand cross-check</td><td>'
                         f'<a class="cbtn" href="/confirm?q={_h_esc(kw)}&amp;google=1">'
                         'Run cross-check (Google · Pinterest · Reddit · X) →</a></td></tr>')
                xsug = ""
            else:
                xrows, xsug = _xcheck_rows(xc)
            card = (
                f'<div class="{noticecls}"><h2 style="margin:.2em 0">{badge} — {_h_esc(kw)}</h2>'
                f'<p>{_h_esc(note)}</p></div>'
                '<table><tr><th>Check</th><th>Result</th></tr>'
                f'<tr><td>Product fit (Embroidery)</td><td>{_fit_pill(fit["status"], fit["launchable"])} '
                f'<span class="note">{_h_esc(fit["reason"])}</span></td></tr>'
                f'<tr><td>Trademark</td><td><b>{_h_esc(risk)}</b> '
                f'<span class="note">{_h_esc(why)}</span></td></tr>'
                f'{xrows}</table>' + xsug +
                '<h2>Assign to a staff member</h2>'
                '<form class="toolbar" method="post" action="/confirm/assign">'
                f'<input type="hidden" name="q" value="{_h_esc(kw)}">'
                f'<select name="assigned_to"><option value="">— pick staff —</option>'
                f'{_user_options()}</select>'
                '<button class="primary" type="submit">Assign in Embroidery mode →</button>'
                '</form>'
                f'<p class="note"><a href="/run?q={_h_esc(kw)}&amp;mode=embroidery">'
                'Or open the full workspace →</a></p>')
            body += card
        return page("Confirm & Assign", _bar() + body + '</article>')

    @app.route("/confirm/assign", methods=["POST"])
    @login_required
    def confirm_assign():
        from src import research as rs, tasks as tk
        u = current_user()
        kw = _no_tags((request.form.get("q") or "").strip())[:80]
        if not kw:
            return redirect(url_for("confirm_niche"))
        c = rs.import_candidate("product_idea", "confirm", kw, mode="embroidery",
                                note="Confirmed via Confirm & Assign",
                                by=u["display_name"])
        assignee = (request.form.get("assigned_to") or "").strip()
        if assignee.isdigit():
            aid = int(assignee)
            due = tk.default_due()            # 24h default deadline (editable later)
            rs.update_candidate(c["id"], assigned_to=aid, status="SUPPLIER_CHECK",
                                next_action="Supplier check + competitor audit",
                                due_date=due)
            tk.create_task(title=f"{kw} — supplier check + competitor audit",
                           assigned_to_user_id=aid, task_type="SUPPLIER_CHECK",
                           related_keyword=kw, due_date=due)
        _log("CONFIRM_ASSIGN", module="research", entity_type="candidate",
             entity_id=c["id"], keyword=kw, product_mode="embroidery",
             summary=f"assigned={assignee or 'unassigned'}")
        return redirect(url_for("research_queue"))

    @app.route("/shortlist")
    @login_required
    def shortlist_page():
        from src import interactive as iv
        m = (request.args.get("supplier_type") or request.args.get("mode")
             or "embroidery").lower()
        mode = m if m in ("pod", "embroidery") else "embroidery"
        err, rows = "", []
        try:
            rows = iv.shortlist(mode, limit=10)
        except SystemExit as exc:
            err = str(exc).splitlines()[0][:200]
        except Exception as exc:  # noqa: BLE001
            err = str(exc)[:200]
        vlabel = {"GO": "🔥 PURSUE NOW", "CONDITIONAL": "⚠️ VALIDATE FIRST",
                  "WATCH": "👀 WATCH / SAVE", "SKIP": "⛔ SKIP"}

        def _row(i, r):
            sc = r["score"] if isinstance(r.get("score"), (int, float)) else "pending"
            cls = "apill" if r.get("verdict") == "GO" else ""
            return (
                f'<tr><td>{i}</td>'
                f'<td><b>{_h_esc(r["keyword"])}</b><br>'
                f'<span class="note">→ {_h_esc(r.get("next_action", ""))}</span></td>'
                f'<td>{_h_esc(r.get("product_type", ""))}</td><td><b>{sc}</b></td>'
                f'<td><span class="pill {cls}">'
                f'{vlabel.get(r.get("verdict"), r.get("verdict", ""))}</span></td>'
                f'<td><span class="note">{_h_esc(r.get("reason", ""))}</span></td>'
                f'<td><a class="tkbtn primary" href="/confirm?q={_h_esc(r["keyword"])}">'
                'Confirm →</a></td></tr>')

        def _tbl(items, start=1):
            return ('<table><tr><th>#</th><th>Keyword / next step</th><th>Fit</th>'
                    '<th>Score</th><th>Verdict</th><th>Why it matters</th><th></th></tr>'
                    + "".join(_row(start + n, r) for n, r in enumerate(items))
                    + '</table>')

        if rows:
            top5, rest = rows[:5], rows[5:]
            table = ('<h2>🔝 Top 5 today</h2>' + _tbl(top5)
                     + (('<h2>More shortlist</h2>' + _tbl(rest, start=6)) if rest else ''))
        else:
            table = ('<p class="empty">' + (_h_esc(err) if err else
                     'No launch-ready opportunities cached yet — run <code>warm</code> on '
                     'the laptop (the VPS reads that cache).') + '</p>')
        sw = ('<div class="pullbar"><div class="pulltxt"><b>Mode</b></div>'
              '<div class="pullbtns">'
              f'<a class="pullbtn{" primary" if mode == "embroidery" else ""}" '
              'href="/shortlist?mode=embroidery">Embroidery</a>'
              f'<a class="pullbtn{" primary" if mode == "pod" else ""}" '
              'href="/shortlist?mode=pod">POD</a></div></div>')
        return page("Shortlist", _bar()
                    + '<article class="md"><h1>🎯 Shortlist — top opportunities</h1>'
                    '<p class="tklead">The current YTuong opportunities, ranked by their '
                    'real YTrends opportunity score and product-fit filtered for '
                    f'<b>{mode.title()}</b>. GO = launch now. One click sends it to '
                    'Confirm &amp; Assign. Never fabricated — a missing score shows as '
                    '"pending".</p>' + sw + table + '</article>')

    @app.route("/build-queue")
    @login_required
    def build_queue():
        # V36: base-driven "make these next" — proven/buildable keywords ranked,
        # TM-flagged, routed to Design Analyzer + Launch Kit. Works straight from
        # keyword_data.csv (no warm cache needed, unlike /shortlist).
        from src import build_shortlist as bq
        source = request.args.get("source")
        source = source if source in ("mine", "live") else None
        try:
            data = bq.analyze(source=source)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Build Queue", exc)
        return page("Build Queue", _bar()
                    + _source_toggle("build-queue", None, source)
                    + _teamops_strip(
                        [("LISTING_DRAFT", "Assign Listing Draft"),
                         ("DESIGN", "Assign Design"),
                         ("REVIEW_QA", "Submit to Review Queue")],
                        lead="Hand a build to the team")
                    + bq.render_html(data, _csrf()))

    @app.route("/build-queue/done", methods=["POST"])
    @login_required
    def build_queue_done():
        _check_csrf()
        from src import build_shortlist as bq
        _u = current_user() or {}
        bq.mark_done(request.form.get("keyword", ""),
                     _u.get("display_name") or _u.get("email") or "")
        return redirect("/build-queue")

    @app.route("/build-queue/archive-empties", methods=["POST"])
    @login_required
    def build_queue_archive():
        _check_csrf()
        from src import build_shortlist as bq
        try:
            moved, kept = bq.archive_empties()
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Archive empties", exc)
        return page("Build Queue", _bar() +
                    '<article class="md"><h1>\U0001F9F9 Archived</h1><p>Moved '
                    f'<b>{moved}</b> empty keywords to the archive (reversible). '
                    f'Base now holds <b>{kept}</b> keywords with real signal.</p>'
                    '<p><a class="tkbtn primary" href="/build-queue">'
                    '← Back to Build Queue</a></p></article>')

    @app.route("/imports")
    @login_required
    def imports_center():
        from src import research as rs, deeplinks as dl
        kinds = "".join(f'<option value="{k}">{v}</option>'
                        for k, v in rs.IMPORT_KINDS.items())
        srcs = "".join(f'<option>{s}</option>' for s in rs.SOURCES)
        openbar = ('<div class="dlrow"><b>Open the research engine:</b> '
                   + dl.render([("YTuong Trending", f"{dl.YTUONG}/trending"),
                                ("Hidden Gems", f"{dl.YTUONG}/hidden-gems"),
                                ("YTuong Spy", f"{dl.YTUONG}/spy"),
                                ("Categories", f"{dl.YTUONG}/categories"),
                                ("Calendar", f"{dl.YTUONG}/calendar"),
                                ("HeyEtsy Hot", f"{dl.HEYETSY}/hot"),
                                ("Best sellers", f"{dl.HEYETSY}/best-seller"),
                                ("Shop inspirations", f"{dl.HEYETSY}/shop-inspirations?filterTotalSold=shuffle")])
                   + '</div>')
        form = ('<form class="savedform" method="post" action="/imports/add">'
                f'<select name="kind">{kinds}</select>'
                f'<select name="source">{srcs}</select>'
                '<select name="mode"><option value="embroidery" selected>Embroidery</option>'
                '<option value="pod">POD</option><option value="">Auto mode</option></select>'
                '<input name="value" placeholder="Paste a YTuong/Etsy URL, or type a keyword" required>'
                '<textarea name="note" placeholder="Note (why this is interesting, screenshot ref, pasted data)"></textarea>'
                '<button type="submit">Import → create candidate</button></form>')
        by_id = {x["user_id"]: x for x in auth.list_users()}
        recent = rs.list_candidates()[:8]

        def _imp_row(c):
            who = by_id.get(c.get("assigned_to"), {}).get("display_name") or "— unassigned"
            return (f'<tr><td><b>{_h_esc(c["title"])}</b></td>'
                    f'<td>{_h_esc(c["source"])}</td>'
                    f'<td>{_h_esc(c["product_mode"])}</td>'
                    f'<td>{_fit_pill(c["fit_status"], c["launchable"])}</td>'
                    f'<td>{_h_esc(c["status"])}</td>'
                    f'<td>{_h_esc(who)}</td>'
                    f'<td><a class="cbtn" href="/research-queue">open queue →</a></td></tr>')
        rows = "".join(_imp_row(c) for c in recent)
        table = ('<h2>Recently imported</h2><table><tr><th>Idea</th><th>Source</th>'
                 '<th>Mode</th><th>Product fit</th><th>Status</th><th>Assigned</th>'
                 '<th></th></tr>'
                 + (rows or '<tr><td colspan="7">Nothing imported yet.</td></tr>')
                 + '</table>') if recent else ""
        notice = ""
        if request.args.get("notice") == "kw_manual":
            notice = ('<div class="notice warn">Could not extract a keyword from that '
                      'URL automatically. Please enter the product keyword/title '
                      'manually below, then import.</div>')
        # V37.4 evidence card: read-only view of the HeyEtsy Detail / Etsy Reviews
        # lanes. Capped evidence only — never a publish or ranking action here.
        evcard = ""
        try:
            from src import feed_evidence_router as _fer
            ev = _fer.recent_evidence(12)

            def _money(n):
                if n is None:
                    return "n/a"
                return f"${n/1000:.1f}K" if n >= 1000 else f"${n:.0f}"

            def _num(n):
                return "n/a" if n is None else f"{n:,.0f}"

            def _act_pill(a):
                cls = {"CONFIRM_FIRST": "lvl-warn", "REVIEW": "lvl-info",
                       "WATCH": "pr-low"}.get(a, "pr-low")
                return f'<span class="pill {cls}">{_h_esc(a)}</span>'

            def _ev_row(r):
                title = _h_esc((r.get("title") or r.get("listing_id") or "?")[:70])
                shop = _h_esc(r.get("shop") or "—")
                conv = ("n/a" if r.get("conversion_rate") is None
                        else f'{r["conversion_rate"] * 100:.1f}%')
                buys = _h_esc(r.get("top_recipient") or "—")
                revn = r.get("review_count") or 0
                # step 7: open the REAL Etsy listing. This used to be the HeyEtsy
                # shop page because of a header-matching bug.
                url = r.get("etsy_url") or ""
                link = (f' · <a href="{_h_esc(url)}" target="_blank" '
                        'rel="noopener noreferrer">open listing ↗</a>'
                        if url.startswith("http") else "")
                rating = r.get("shop_rating")
                trust = (f' · ★{rating:.1f}' if isinstance(rating, (int, float))
                         else "")
                nimg = r.get("image_count")
                photos = f' · {int(nimg)} photos' if nimg else ""
                thumb = ""
                if (r.get("main_image") or "").startswith("http"):
                    thumb = (f'<img src="{_h_esc(r["main_image"])}" alt="" '
                             'style="width:40px;height:40px;object-fit:cover;'
                             'border-radius:6px;margin-right:8px;vertical-align:middle" '
                             'loading="lazy">')
                return (f'<tr><td>{thumb}<b>{title}</b><br><span style="color:var(--ink-faint);'
                        f'font-size:11px">{shop}{trust} · id '
                        f'{_h_esc(r.get("listing_id"))}{photos}{link}</span></td>'
                        f'<td>{_num(r.get("estimated_sold"))}</td>'
                        f'<td>{_money(r.get("estimated_revenue_usd"))}</td>'
                        f'<td>{conv}</td>'
                        f'<td>{revn}</td>'
                        f'<td>{buys}</td>'
                        f'<td>{_act_pill(r.get("max_action"))}</td></tr>')
            def _cand_block(lid):
                """Step 10 -> 11: the winner's derived keywords, pickable, with a
                one-click push into the Inbox. This is what staff used to retype."""
                cands = _fer.candidates_for_rerank(lid)
                if not cands:
                    return ""
                boxes = []
                for c in cands[:25]:
                    k = _h_esc(c.get("keyword") or "")
                    conf = c.get("match_confidence") or 0
                    mt = _h_esc(str(c.get("match_type") or "").replace("_", " "))
                    boxes.append(
                        '<label style="display:inline-block;margin:2px 10px 2px 0;'
                        'font-size:12.5px">'
                        f'<input type="checkbox" name="cand" value="{k}" checked> '
                        f'<b>{k}</b> <span style="color:var(--ink-faint)">'
                        f'({mt} · {conf:.2f})</span></label>')
                return (
                    f'<tr><td colspan="7" style="background:var(--bg-soft)">'
                    '<form method="post" action="/send-to-rerank">'
                    f'<input type="hidden" name="_csrf" value="{_csrf()}">'
                    f'<input type="hidden" name="listing_id" value="{_h_esc(lid)}">'
                    '<details style="margin:2px 0"><summary style="cursor:pointer;'
                    'font-size:12.5px;font-weight:700">💡 '
                    f'{len(cands)} keyword candidate(s) derived from this winner '
                    '— pick and send</summary>'
                    f'<div style="margin:8px 0">{"".join(boxes)}</div>'
                    '<button class="pullbtn primary" type="submit">➡ Send to '
                    'Re-rank / Inbox</button> '
                    '<span style="font-size:.78rem;color:var(--ink-soft)">'
                    'saves to keyword_data.csv tagged '
                    f'<code>winner:{_h_esc(lid)}</code> · capped at CONFIRM_FIRST '
                    '· the layered engine still ranks them</span>'
                    '</details></form></td></tr>')

            if ev:
                evrows = "".join(_ev_row(r) + _cand_block(r.get("listing_id"))
                                 for r in ev)
                evcard = (
                    '<h2>🗣 Listing evidence (v3.4.0 lanes)</h2>'
                    '<p class="tklead">HeyEtsy Detail &amp; Etsy Reviews land here as '
                    '<b>validated, capped</b> evidence. Single-listing evidence is '
                    '<b>CONFIRM_FIRST</b> — strong competitor proof, not keyword-market '
                    'proof; PROVEN needs 2+ shops. Reviews feed Pattern Miner / Keyword '
                    'Lab and never change the market score.</p>'
                    '<table><tr><th>Listing</th><th>Est. sold</th><th>Est. rev</th>'
                    '<th>Conv</th><th>Reviews</th><th>Buys&nbsp;for</th>'
                    '<th>Max action</th></tr>' + evrows + '</table>'
                    '<p style="font-size:11px;color:var(--ink-faint)">Estimates are '
                    'third-party (HeyEtsy), not Etsy internal sales.</p>')
        except Exception:  # noqa: BLE001 — the card is additive, never breaks the page
            evcard = ""
        # /imports is where phase 3's EVIDENCE lands (steps 6/7) - it is not
        # phase 1. Passing "feed" here highlighted "1 Find & filter", so a
        # click on the phase-3 card landed on a page insisting you were in
        # phase 1. That mismatch, not the route, is what read as "wrong page".
        return page("YTuong Import Center", _bar()
                    + _stage_nav("evidence", (request.args.get("q") or "").strip()[:80],
                                 request.args.get("mode") or "")
                    + '<article class="md"><h1>📥 YTuong Import Center</h1>'
                    '<p class="tklead">YTuong &amp; HeyEtsy do the market research. '
                    'Import a finding here and the dashboard turns it into an '
                    'execution plan — product-fit check, product mode, and a spot in '
                    'the Research Queue. Nothing is auto-published.</p>'
                    + notice + openbar + form + table + evcard + '</article>')

    @app.route("/imports/add", methods=["POST"])
    @login_required
    def imports_add():
        from src import research as rs
        u = current_user()
        value = _no_tags((request.form.get("value") or "").strip())
        # A URL was pasted but no keyword could be decoded from it: don't create a
        # junk candidate titled with the raw URL — send the user back with a clear
        # message to type the keyword/title manually.
        if value.lower().startswith("http") and not rs.kw_from_url(value):
            return redirect(url_for("imports_center", notice="kw_manual"))
        c = rs.import_candidate(
            kind=request.form.get("kind") or "product_idea",
            source=request.form.get("source") or "YTuong",
            value=value,
            mode=(request.form.get("mode") or None),
            note=_no_tags((request.form.get("note") or "").strip())[:1000],
            by=u["display_name"])
        _log("YTUONG_IMPORT", module="research", entity_type="candidate",
             entity_id=c["id"], keyword=c.get("keyword"),
             product_mode=c.get("product_mode"), summary=c["title"])
        return redirect(url_for("research_queue"))

    @app.route("/research-queue")
    @login_required
    def research_queue():
        from src import research as rs, deeplinks as dl
        u = current_user()
        by_id = {x["user_id"]: x for x in auth.list_users()}
        counts = rs.counts_by_status()
        pulse = '<div class="tkstats">' + "".join(
            f'<div class="tkstat"><span class="n">{counts.get(s, 0)}</span>'
            f'<span class="l">{_h_esc(s.replace("_", " ").title())}</span></div>'
            for s in ("NEW_IDEA", "RESEARCHING", "LISTING_DRAFT", "MANAGER_REVIEW",
                      "READY_FOR_MANUAL_PUBLISH", "BLOCKED")) + '</div>'
        cards = ""
        for c in rs.list_candidates():
            who = by_id.get(c.get("assigned_to"), {}).get("display_name", "—")
            kw = c.get("keyword") or c.get("title")
            links = dl.for_keyword(kw)
            if c.get("source_url"):
                links = dl.for_listing(c["source_url"]) + links[:2]
            statopts = "".join(
                f'<option{" selected" if s == c["status"] else ""}>{s}</option>'
                for s in rs.STATUSES)
            cards += (
                '<div class="tkcard pr-medium"><div class="tkhead">'
                f'<b>{_h_esc(c["title"])}</b> {_fit_pill(c["fit_status"], c["launchable"])}'
                f'<span class="pill">{_h_esc(c["product_mode"])}</span></div>'
                f'<div class="note">Source: {_h_esc(c["source"])} · Assigned: '
                f'{_h_esc(who)} · Next: {_h_esc(c.get("next_action") or "—")}</div>'
                f'<div class="dlrow">{dl.render(links)}</div>'
                '<div class="tkactions">'
                f'<a class="tkbtn primary" href="/run?q={_h_esc(str(kw))}'
                f'&mode={_h_esc(c.get("product_mode") or "")}">Build workspace</a>'
                f'<a class="tkbtn" href="/admin/tasks?keyword={_h_esc(str(kw))}">Assign task</a>'
                '</div>'
                '<form method="post" action="/research-queue/update" class="toolbar">'
                f'<input type="hidden" name="id" value="{c["id"]}">'
                f'<select name="status">{statopts}</select>'
                f'<select name="assigned_to"><option value="">— assign —</option>{_user_options(c.get("assigned_to"))}</select>'
                '<input name="due_date" type="datetime-local" placeholder="Due">'
                '<button class="primary" type="submit">Update</button>'
                '</form>'
                + _post_btn(f'/research-queue/del/{c["id"]}', "delete",
                            confirm="Delete this candidate?")
                + '</div>')
        return page("Research Queue", _bar()
                    + '<article class="md"><h1>🧭 Research Queue</h1>'
                    '<p class="tklead">Every imported idea, moving from spark to '
                    'manager-approved manual publish. Assign it, research it, draft it, '
                    'review it — the pipeline keeps the team honest.</p>'
                    + pulse + '</article><div class="lpboard" style="flex-direction:column">'
                    + (cards or '<p class="empty">No candidates yet — import one from the '
                       '<a href="/imports">YTuong Import Center</a>.</p>') + '</div>')

    @app.route("/research-queue/update", methods=["POST"])
    @login_required
    def research_queue_update():
        from src import research as rs
        cid = int(request.form.get("id") or 0)
        assignee = request.form.get("assigned_to")
        rs.update_candidate(
            cid, status=request.form.get("status"),
            assigned_to=(int(assignee) if assignee else None),
            due_date=(request.form.get("due_date") or None))
        _log("RESEARCH_UPDATE", module="research", entity_type="candidate",
             entity_id=cid, summary=request.form.get("status"))
        return redirect(url_for("research_queue"))

    @app.route("/research-queue/del/<int:cid>", methods=["POST"])
    @login_required
    def research_queue_del(cid):
        _check_csrf()
        from src import research as rs
        rs.delete_candidate(cid)
        _log("RESEARCH_DELETE", module="research", entity_type="candidate", entity_id=cid)
        return redirect(url_for("research_queue"))

    # ======================= TEAM MANAGEMENT =======================
    def _bar():
        # Global top nav — jump straight between the main sections from any page,
        # no round-trip through Home. Role-aware; current section is highlighted.
        u = current_user()
        is_mgr = bool(u and (auth.has_perm(u["role"], "tasks.assign")
                             or auth.has_perm(u["role"], "tasks.review")))
        cur = request.path
        # Trimmed per owner: Research, Review and the old Team board removed from
        # the top bar. Review is still reachable from the Manager Desk on Home;
        # team work now lives entirely under Team Ops.
        links = [("/", "🏠 Home"), ("/longtail", "💎 Long-tail"),
                 ("/build-queue", "🎯 Build"),
                 ("/design-skill-bridge", "🎨 Design"), ("/launch-kit", "🚀 Launch Kit")]
        links += ([] if is_mgr else [("/me/tasks", "✅ My work")])
        links += [("/team/ops", "🛠️ Team Ops"), ("/training", "📚 Guide")]
        # Longest match wins, so /team/ops doesn't also light up /team.
        matches = [h for h, _ in links
                   if cur == h or (h != "/" and cur.startswith(h + "/"))]
        best = max(matches, key=len) if matches else None
        items = ""
        for h, l in links:
            on = " on" if h == best else ""
            items += f'<a class="navbtn{on}" href="{h}">{l}</a>'
        return f'<nav class="rbar">{items}</nav>'

    def _rollout_note():
        """Shown on the OLD boards so nobody confuses them with the new Team Ops
        board. Both systems run side by side; nothing is migrated automatically."""
        return ('<div class="rolloutnote"><b>Legacy task system remains active '
                'during rollout.</b> <span>The new Team Ops task system is at '
                '<a href="/team/ops/board">/team/ops/board</a> and '
                '<a href="/team/ops/my-tasks">/team/ops/my-tasks</a>. Tasks are not '
                'copied between the two.</span></div>')

    def _teamops_strip(pairs, keyword="", opportunity="", listing="", store="",
                       lead="Assign this to the team"):
        """Hand work from a workflow module to the Team Ops board.

        Each button deep-links to the Create Task form with the type and the
        opportunity/keyword/listing already filled in. Internal only — it never
        touches Etsy, it just puts the next move on someone's board. Managers
        only, since staff can't assign.
        """
        u = current_user()
        if not (u and auth.has_perm(u["role"], "tasks.assign")):
            return ""
        from src import team_ops as _to
        btns = ""
        for ttype, label in pairs:
            title = label
            if keyword:
                title = f"{label} — {keyword}"
            href = _to.new_task_url(ttype, title=title, keyword=keyword,
                                    opportunity_id=opportunity,
                                    listing_id=listing, store=store)
            btns += f'<a class="tostrip-b" href="{href}">{_h_esc(label)}</a>'
        return (f'<div class="tostrip"><b>👥 {_h_esc(lead)}</b>{btns}'
                '<a class="tostrip-b" href="/team/ops/board">Open board →</a></div>')

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

    # ---- CSRF: destructive actions are POST-only + carry a per-session token ----
    def _csrf():
        tok = session.get("_csrf")
        if not tok:
            tok = os.urandom(16).hex()
            session["_csrf"] = tok
        return tok

    def _csrf_field():
        return f'<input type="hidden" name="_csrf" value="{_csrf()}">'

    def _check_csrf():
        if request.form.get("_csrf") != session.get("_csrf"):
            abort(403)

    def _post_btn(action, label, hidden=None, confirm=None):
        """A small inline POST form styled like the old .cbtn link — for
        destructive actions (delete/resolve/disable) so they can't be triggered
        by a cross-site GET."""
        onsub = (f' onsubmit="return confirm(&#39;{_h_esc(confirm)}&#39;)"'
                 if confirm else "")
        extra = "".join(
            f'<input type="hidden" name="{_h_esc(k)}" value="{_h_esc(v)}">'
            for k, v in (hidden or {}).items())
        return (f'<form method="post" action="{action}" class="pf"{onsub}>'
                f'{_csrf_field()}{extra}'
                f'<button class="cbtn" type="submit">{label}</button></form>')

    # ---- Team Command Center (V37.4) --------------------------------------
    # Maps task_type -> the workflow stage it belongs to, for the pipeline strip.
    _TCC_STAGE_MAP = {
        "KEYWORD_RESEARCH": "RESEARCH", "SPY_RESEARCH": "PATTERN",
        "COMPETITOR_AUDIT": "PATTERN", "TRADEMARK_CHECK": "BUILD",
        "SUPPLIER_CHECK": "BUILD", "LISTING_DRAFT": "BUILD", "PDF_EXPORT": "BUILD",
        "DESIGN_BRIEF": "DESIGN", "FIRST_IMAGE": "PHOTO", "MOCKUP": "PHOTO",
        "FEEDBACK_DAY3": "LEARN", "FEEDBACK_DAY7": "LEARN",
        "MANAGER_REVIEW": "REVIEW", "FIX_REQUIRED": "REVIEW",
    }
    _TCC_STAGES = ["FEED", "RESEARCH", "RANK", "PATTERN", "KEYWORD", "BUILD",
                   "DESIGN", "PHOTO", "ADS", "LEARN", "REVIEW"]

    @app.route("/team")
    @app.route("/team/command-center")
    @login_required
    def team_hub():
        from datetime import date as _date, datetime as _dt
        from src import tasks as tk, activity as av, toolfeedback as tfb
        u = current_user()
        is_mgr = auth.has_perm(u["role"], "tasks.assign")
        by_id = {x["user_id"]: x for x in auth.list_users()}
        # scope: managers see everyone's tasks; members see their own
        all_tasks = (tk.list_tasks() if is_mgr
                     else tk.list_tasks(assigned_to=u["user_id"]))
        mine = tk.my_open(u["user_id"])
        today = _date.today().isoformat()

        def _due_today(t):
            return ((t.get("due_date") or "")[:10] == today
                    and t["status"] in tk.OPEN_STATUSES)
        overdue = [t for t in all_tasks if tk.is_overdue(t)]
        due_today = [t for t in all_tasks if _due_today(t)]
        blocked = [t for t in all_tasks if t["status"] == "BLOCKED"]
        researching = [t for t in all_tasks if t["status"] == "IN_PROGRESS"]
        review_q = tk.review_queue()
        my_overdue = [t for t in mine if tk.is_overdue(t)]
        my_today = [t for t in mine if _due_today(t)]
        try:
            fb_open = tfb.counts().get("open", 0)
        except Exception:  # noqa: BLE001
            fb_open = 0
        try:
            active_today = av.summary_today().get("active_users", 0)
        except Exception:  # noqa: BLE001
            active_today = 0
        try:
            from src.timestamp import tz as _tz
            now_str = _dt.now(_tz()).strftime("%a %d %b %Y · %H:%M ICT")
        except Exception:  # noqa: BLE001
            now_str = today

        def _esc(s):
            return _h_esc("" if s is None else str(s))

        # ---- header ----
        header = (
            '<article class="md"><h1>🛰️ Team Command Center</h1>'
            f'<p class="tklead">Signed in as <b>{_esc(u["display_name"])}</b> '
            f'· <b>{_esc(u["role"])}</b> · {_esc(now_str)}. '
            'One control room: who owns what, what is due or stuck, and the next '
            'action. Nothing here auto-publishes.</p></article>')

        # ---- KPI strip ----
        kpis = [("My open", len(mine), "/me/tasks"),
                ("My due today", len(my_today), "/me/tasks"),
                ("My overdue", len(my_overdue), "/me/tasks")]
        if is_mgr:
            kpis += [("Team overdue", len(overdue), "/admin/tasks"),
                     ("Needs review", len(review_q), "/admin/reviews"),
                     ("Blocked", len(blocked), "/admin/tasks"),
                     ("Active today", active_today, "/admin/activity"),
                     ("Feedback open", fb_open, "/team/feedback")]
        kpi_html = "".join(
            f'<a href="{href}" style="flex:1 1 120px;min-width:110px;text-decoration:none;'
            'border:1px solid var(--line);border-radius:12px;padding:10px 12px;'
            'background:var(--paper)">'
            f'<div style="font-size:22px;font-weight:800;color:var(--ink)">{val}</div>'
            f'<div style="font-size:11px;color:var(--ink-soft);text-transform:uppercase;'
            f'letter-spacing:.03em">{_esc(label)}</div></a>'
            for label, val, href in kpis)
        kpi_strip = ('<div style="display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 14px">'
                     + kpi_html + '</div>')

        # ---- Today Control Board ----
        def _task_line(t, tag=""):
            who = by_id.get(t.get("assigned_to_user_id"), {}).get("display_name", "—")
            kw = t.get("related_keyword") or t.get("task_type") or ""
            od = ' style="color:#99271F;font-weight:700"' if tk.is_overdue(t) else ""
            due = (t.get("due_date") or "")[:10] or "—"
            return (f'<li{od}>{_esc(t["title"])} '
                    f'<span style="color:var(--ink-faint);font-size:11px">· {_esc(who)} '
                    f'· {_esc(kw)} · due {_esc(due)} · {_esc(t["status"])}</span></li>')

        def _board_col(title, items, href, empty):
            body = ("".join(_task_line(t) for t in items[:6])
                    if items else f'<li style="color:var(--ink-faint)">{empty}</li>')
            return (f'<div style="flex:1 1 240px;min-width:220px;border:1px solid '
                    'var(--line);border-radius:12px;padding:10px 12px">'
                    f'<div style="font-weight:700;font-size:13px;margin-bottom:4px">'
                    f'{_esc(title)} <a href="{href}" style="font-size:11px;'
                    f'font-weight:500">open →</a></div>'
                    f'<ul style="margin:0;padding-left:16px;font-size:12.5px">{body}</ul></div>')
        board_cols = [
            _board_col("🔴 Overdue", overdue if is_mgr else my_overdue,
                       "/admin/tasks" if is_mgr else "/me/tasks", "None overdue."),
            _board_col("📌 Due today", due_today if is_mgr else my_today,
                       "/me/tasks", "Nothing due today."),
        ]
        if is_mgr:
            board_cols.append(_board_col("🔍 Needs review", review_q,
                                         "/admin/reviews", "Review queue clear."))
        board_cols.append(_board_col("⛔ Blocked", blocked if is_mgr else
                                     [t for t in mine if t["status"] == "BLOCKED"],
                                     "/admin/tasks" if is_mgr else "/me/tasks",
                                     "Nothing blocked."))
        board = ('<h2>Today control board</h2>'
                 '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">'
                 + "".join(board_cols) + '</div>')

        # ---- Process pipeline (open task counts by stage) ----
        pcount = {s: 0 for s in _TCC_STAGES}
        for t in all_tasks:
            if t["status"] in tk.OPEN_STATUSES:
                stg = _TCC_STAGE_MAP.get(t.get("task_type"))
                if stg:
                    pcount[stg] += 1
        chips = "".join(
            '<span style="border:1px solid var(--line);border-radius:9px;'
            'padding:3px 9px;font-size:11.5px;'
            + ("background:var(--accent-bg);color:var(--accent);font-weight:700"
               if pcount[s] else "color:var(--ink-faint)") + '">'
            f'{s} {pcount[s]}</span>' for s in _TCC_STAGES)
        pipeline = ('<h2>Process pipeline</h2>'
                    '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px">'
                    + chips + '</div>'
                    '<p style="font-size:11px;color:var(--ink-faint)">Open tasks by '
                    'workflow stage. Feed / Rank / Keyword / Ads have no task type yet.</p>')

        # ---- Activity timeline ----
        try:
            events = (av.list_events(limit=12) if is_mgr
                      else av.list_events(user_id=u["user_id"], limit=12))
        except Exception:  # noqa: BLE001
            events = []
        ev_rows = "".join(
            f'<tr><td style="white-space:nowrap;font-size:11px">{_esc((e.get("timestamp") or "")[:16].replace("T"," "))}</td>'
            f'<td>{_esc(e.get("user_email"))}</td>'
            f'<td>{_esc(e.get("event_type"))}</td>'
            f'<td>{_esc(e.get("action") or e.get("keyword") or "")}</td></tr>'
            for e in events)
        timeline = ('<h2>Team activity</h2><table><tr><th>When</th><th>Who</th>'
                    '<th>Action</th><th>Detail</th></tr>'
                    + (ev_rows or '<tr><td colspan="4">No recent activity.</td></tr>')
                    + '</table>') if is_mgr or events else ""

        # ---- module cards (all 10 destinations kept; counts added) ----
        def _card(href, title, sub):
            return (f'<a class="toolcard" href="{href}"><b>{title}</b>'
                    f'<span>{sub}</span></a>')
        cards = [
            _card("/team/ops", "🛠️ Team Operations",
                  "Role-based board, review queue, work log, KPI + bottlenecks"),
            _card("/me/tasks", "✅ My Tasks",
                  f"{len(mine)} open · {len(my_overdue)} overdue"),
            _card("/research-queue", "🧭 Research Queue",
                  "Ideas from import → review → manual publish"),
            _card("/imports", "📥 Feed / Import Center",
                  "Turn a YTuong/HeyEtsy finding into a candidate"),
            # literal href kept (selftest greps web.py source for href="/team/calendar")
            ('<a class="toolcard" href="/team/calendar"><b>📅 Team Calendar</b>'
             f'<span>{len(due_today)} due today · {len(overdue)} overdue</span></a>'),
        ]
        if is_mgr:
            cards.append(_card("/admin/tasks", "📋 Team Tasks",
                               f"{len(researching)} in flight · {len(blocked)} blocked"))
        if auth.has_perm(u["role"], "tasks.review"):
            cards.append(_card("/admin/reviews", "🔍 Review Queue",
                               f"{len(review_q)} awaiting owner review"))
        if auth.has_perm(u["role"], "logs.view_all"):
            cards.append(_card("/admin/activity", "📈 Activity Log",
                               f"{active_today} active today"))
        if auth.has_perm(u["role"], "users.manage"):
            cards.append(_card("/admin/users", "👥 User Management",
                               f"{len(by_id)} team members"))
        # literal href kept (selftest greps web.py source for href="/team/feedback")
        cards.append('<a class="toolcard" href="/team/feedback"><b>💬 Tool Feedback</b>'
                     f'<span>{fb_open} open</span></a>' if fb_open else
                     '<a class="toolcard" href="/team/feedback"><b>💬 Tool Feedback</b>'
                     '<span>Suggest an improvement</span></a>')
        cards.append(_card("/me", "👤 My Profile", "Your role + recent activity"))
        grid = '<div class="toolgrid">' + "".join(cards) + '</div>'

        return page("Team Command Center", _bar()
                    + header + '<article class="md">' + kpi_strip + board
                    + pipeline + timeline + '</article>' + grid)

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
        mo = (date.today() + timedelta(days=30)).isoformat()

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
            if view == "month":
                return today <= due <= mo and open_
            if view == "upcoming":
                return due >= today and open_
            return True

        shown = sorted((t for t in rows if keep(t)),
                       key=lambda t: (t.get("due_date") or "9999-99-99"))
        views = [("today", "Today"), ("week", "This week"), ("month", "This month"),
                 ("overdue", "Overdue"), ("upcoming", "Upcoming"), ("all", "All")]
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
        from datetime import date as _date, timedelta as _td
        u = current_user()
        by_id = {x["user_id"]: x for x in auth.list_users()}
        rows = tk.list_tasks(assigned_to=u["user_id"])
        today = _date.today().isoformat()
        week_end = (_date.today() + _td(days=7)).isoformat()

        def _dd(t):
            return (t.get("due_date") or "")[:10]
        # Each task lands in exactly ONE group (first match wins, in this order).
        seen = set()

        def take(pred):
            out = []
            for t in rows:
                if t["task_id"] in seen:
                    continue
                if pred(t):
                    out.append(t)
                    seen.add(t["task_id"])
            return out
        # submitted work is grouped as "waiting" first — it's out of the member's
        # hands, so it must not fall into Today/This-week just because it has a due
        # date (READY_FOR_REVIEW is itself an OPEN status).
        awaiting = take(lambda t: t["status"] == "READY_FOR_REVIEW")
        overdue = take(tk.is_overdue)
        today_b = take(lambda t: t["status"] in tk.OPEN_STATUSES and _dd(t) == today)
        week_b = take(lambda t: t["status"] in tk.OPEN_STATUSES
                      and today < _dd(t) <= week_end)
        open_rest = take(lambda t: t["status"] in ("TODO", "IN_PROGRESS", "BLOCKED"))
        done_recent = [t for t in rows if t["status"] in ("DONE", "APPROVED")][:8]
        buckets = [
            ("🔴 Overdue", overdue),
            ("📌 Today", today_b),
            ("🗓 This week", week_b),
            ("🕓 Awaiting review", awaiting),
            ("⚪ Open (no date)", open_rest),
            ("✅ Recently done", done_recent),
        ]

        def card(t):
            acts = tk.member_actions(t["status"])
            report_val = _h_esc(t.get("work_report") or "")
            due = (t.get("due_date") or "")[:10]
            duehtml = (f' · <span class="due{" od" if tk.is_overdue(t) else ""}">due {_h_esc(due)}</span>'
                       if due else "")
            guide = tk.TYPE_GUIDE.get(t["task_type"], "")
            rev = ""
            if t["review_status"] != "NOT_REVIEWED":
                rev = (f'<div class="note">Review: <b>{_h_esc(t["review_status"])}</b>'
                       + (f' — {_h_esc(t.get("review_notes"))}' if t.get("review_notes") else "")
                       + '</div>')
            # ONE form: a report textarea (pre-filled) + the status buttons + "Save
            # report" (saves the note without changing status). Staff describe what
            # they did; the reviewer sees it in the Review Queue.
            if acts:
                btns = "".join(
                    f'<button class="tkbtn{" primary" if prim else ""}" name="status" '
                    f'value="{tgt}" type="submit">{_h_esc(lbl)}</button>'
                    for (lbl, tgt, prim) in acts)
                btns += ('<button class="tkbtn" name="status" value="__KEEP__" '
                         'type="submit">💾 Save report</button>')
                report = ('<form method="post" action="/me/tasks/status" class="tkreport">'
                          f'<input type="hidden" name="task_id" value="{t["task_id"]}">'
                          '<label>📝 What did you do? <span class="note">(links, findings, '
                          'shortlist — your reviewer sees this)</span></label>'
                          '<textarea name="work_report" rows="3" placeholder="e.g. '
                          'Shortlisted 5 keywords (demand vs competition), verified '
                          f'trademarks, noted 5 rival shops…">{report_val}</textarea>'
                          f'<div class="tkactions">{btns}</div></form>')
            elif report_val:
                report = f'<div class="tkreported"><b>📝 Reported:</b> {report_val}</div>'
            else:
                report = ""
            return ('<div class="tkcard pr-' + (t["priority"] or "medium").lower() + '">'
                    '<div class="tkhead"><b>' + _h_esc(t["title"]) + '</b>'
                    f'<span class="pill pr-{(t["priority"] or "medium").lower()}">{_h_esc(t["priority"])}</span></div>'
                    f'<div class="note">{_h_esc(t.get("task_type") or "")}'
                    + (f' · stage {_h_esc(_TCC_STAGE_MAP.get(t.get("task_type")))}'
                       if _TCC_STAGE_MAP.get(t.get("task_type")) else "")
                    + (f' · {_h_esc(t.get("related_keyword"))}' if t.get("related_keyword") else "")
                    + (f' · from {_h_esc(by_id.get(t.get("assigned_by_user_id"), {}).get("display_name"))}'
                       if by_id.get(t.get("assigned_by_user_id")) else "")
                    + duehtml + '</div>'
                    + (f'<div class="tkguide">🎯 {_h_esc(guide)}</div>' if guide else "")
                    + rev + report + '</div>')

        body = ""
        for label, items in buckets:
            if items:
                body += (f'<h2 class="tkgroup">{label} <span class="count">{len(items)}'
                         '</span></h2>' + "".join(card(t) for t in items))
        if not body:
            body = '<p class="empty">No open tasks — you\'re all caught up. 🎉</p>'
        return page("My Tasks", _bar() + '<article class="md"><h1>✅ My Tasks '
                    '<span class="legacytag">Legacy task system</span></h1>'
                    + _rollout_note()
                    + '<p class="note">Your assigned work, most urgent first. Click '
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
            report = _no_tags((request.form.get("work_report") or "").strip())[:4000]
            raw_status = request.form.get("status")
            # "__KEEP__" (the Save-report button) leaves status unchanged
            status = raw_status if raw_status in tk.STATUSES else None
            tk.update_task(tid, status=status, work_report=report)
            _log("TASK_STATUS_CHANGE" if status else "TASK_REPORT_SAVED",
                 module="tasks", entity_type="task", entity_id=tid,
                 summary=(status or "report saved"))
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

        # who's on what — per-staff open workload, so a manager can see at a glance
        # which task each person is on without scanning all four board columns.
        staff = {}
        for t in rows:
            if t["status"] not in tk.OPEN_STATUSES:
                continue
            nm = by_id.get(t["assigned_to_user_id"], {}).get("display_name") or "Unassigned"
            s = staff.setdefault(nm, {"todo": 0, "prog": 0, "od": 0, "rev": 0, "n": 0})
            s["n"] += 1
            if t["status"] == "TODO":
                s["todo"] += 1
            elif t["status"] in ("IN_PROGRESS", "BLOCKED"):
                s["prog"] += 1
            elif t["status"] == "READY_FOR_REVIEW":
                s["rev"] += 1
            if tk.is_overdue(t):
                s["od"] += 1
        whos = ""
        if staff:
            def _staff_row(nm, s):
                od = (f'<b style="color:var(--stop)">{s["od"]}</b>'
                      if s["od"] else "0")
                return (f'<tr><td><b>{_h_esc(nm)}</b></td>'
                        f'<td>{s["todo"]}</td><td>{s["prog"]}</td>'
                        f'<td>{od}</td><td>{s["rev"]}</td></tr>')
            body_rows = "".join(
                _staff_row(nm, s) for nm, s in
                sorted(staff.items(), key=lambda kv: (kv[0] == "Unassigned", -kv[1]["n"])))
            whos = ('<h3 class="whosh">👥 Who\'s on what</h3>'
                    '<table class="whos"><thead><tr><th>Staff</th><th>To do</th>'
                    '<th>In progress</th><th>Overdue</th><th>Awaiting review</th>'
                    f'</tr></thead><tbody>{body_rows}</tbody></table>')

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
                    + '<article class="md"><h1>📋 Team Tasks '
                    '<span class="legacytag">Legacy task system</span></h1>'
                    + _rollout_note()
                    + '<p class="tklead">Great products ship when everyone knows their next '
                    'move. Assign the work, watch it flow left → right, and clear the board '
                    'together — momentum is a team sport.</p>'
                    + pulse + whos + form + '</article><div class="lpboard">' + cols + '</div>')

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
        by_id = {u["user_id"]: u for u in auth.list_users()}

        def _urg(t):
            # overdue first, then priority, then soonest due
            return (0 if tk.is_overdue(t) else 1,
                    {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(t.get("priority"), 2),
                    (t.get("due_date") or "9999-99-99"))
        rows = sorted(tk.review_queue(), key=_urg)
        items = ""
        from urllib.parse import quote_plus as _qp_r
        for t in rows:
            who = by_id.get(t["assigned_to_user_id"], {}).get("display_name", "—")
            prio = (t.get("priority") or "medium").lower()
            due = (t.get("due_date") or "")[:10]
            meta = (f'<span class="pill pr-{prio}">{_h_esc(t.get("priority") or "MEDIUM")}</span>'
                    + (f' · <span class="due{" od" if tk.is_overdue(t) else ""}">due '
                       f'{_h_esc(due)}</span>' if due else ""))
            rep = (t.get("work_report") or "").strip()
            report_html = (f'<div class="tkreported"><b>📝 {_h_esc(who)} reported:</b> '
                           f'{_h_esc(rep)}</div>' if rep else
                           '<div class="note">— no report submitted —</div>')
            kw = (t.get("related_keyword") or "").strip()
            # a launch-kit approval: keyword links to the full kit, and the
            # decisions read List / Fix / Decline (same underlying statuses)
            is_listing = ((t.get("task_type") or "") == "MANAGER_REVIEW"
                          and str(t.get("title", "")).startswith("List approval"))
            kw_html = (f'<a href="/launch-kit?q={_qp_r(kw)}">{_h_esc(kw)}</a>'
                       if kw and is_listing else _h_esc(kw))
            b_ok, b_fix, b_no = (("✅ List", "🔧 Fix", "⛔ Decline")
                                 if is_listing
                                 else ("Approve", "Needs fix", "Reject"))
            items += (f'<div class="saveditem pr-{prio}"><div class="sihead">'
                      f'<b>{_h_esc(t["title"])}</b> '
                      f'<span class="pill">{_h_esc(t["task_type"])}</span></div>'
                      f'<div class="note">{_h_esc(who)} · {kw_html} · {meta}</div>'
                      + report_html
                      + '<form method="post" action="/admin/reviews/act" class="toolbar">'
                      f'<input type="hidden" name="task_id" value="{t["task_id"]}">'
                      '<input name="notes" placeholder="Review notes / what to fix">'
                      f'<button class="primary" name="decision" value="APPROVED">{b_ok}</button>'
                      f'<button name="decision" value="NEEDS_FIX">{b_fix}</button>'
                      f'<button name="decision" value="REJECTED">{b_no}</button>'
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
                     + _post_btn('/admin/users/disable', "disable",
                                 hidden={"email": u["email"]},
                                 confirm="Disable this user?")
                     + '</td></tr>')
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
        new_role = request.form.get("role")
        actor = current_user()
        tu = auth.get_user_by_email(target or "")
        # nobody may change their own role (no self-escalation)
        if (target or "").strip().lower() == (actor["email"] or "").strip().lower():
            return redirect(url_for("admin_users"))
        # only OWNER may change an existing OWNER
        if tu and tu["role"] == "OWNER" and actor["role"] != "OWNER":
            return redirect(url_for("admin_users"))
        # only an OWNER may GRANT the OWNER role (blocks ADMIN->OWNER escalation)
        if new_role == "OWNER" and actor["role"] != "OWNER":
            return redirect(url_for("admin_users"))
        try:
            auth.set_role(target, new_role)
        except Exception:  # noqa: BLE001
            pass
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/disable", methods=["POST"])
    @require_perm("users.manage")
    def admin_users_disable():
        _check_csrf()
        target = request.form.get("email") or ""
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
        f_kw = request.args.get("kw") or ""
        rows = activity.list_events(
            user_id=int(f_user) if (f_user or "").isdigit() else None,
            event_type=f_type, keyword=f_kw or None, limit=300)
        # filter form (the params already worked; this exposes them in the UI)
        uopts = '<option value="">All users</option>' + "".join(
            f'<option value="{x["user_id"]}"'
            + (" selected" if str(x["user_id"]) == (f_user or "") else "")
            + f'>{_h_esc(x["display_name"])}</option>' for x in auth.list_users())
        topts = '<option value="">All events</option>' + "".join(
            f'<option{" selected" if et == (f_type or "") else ""}>{et}</option>'
            for et in sorted(activity.EVENT_TYPES))
        filt = ('<form method="get" action="/admin/activity" class="toolbar">'
                f'<select name="user">{uopts}</select>'
                f'<select name="type">{topts}</select>'
                f'<input name="kw" placeholder="keyword contains…" value="{_h_esc(f_kw)}">'
                '<button class="primary" type="submit">Filter</button> '
                '<a class="cbtn" href="/admin/activity">Clear</a> '
                '<a class="cbtn" href="/admin/activity/export">⬇ Export CSV</a></form>')
        body = "".join(
            '<tr><td>' + _h_esc(r["timestamp"]) + '</td><td>' + _h_esc(r["user_email"])
            + '</td><td>' + _h_esc(r["user_role"]) + '</td><td>' + _h_esc(r["event_type"])
            + '</td><td>' + _h_esc(r.get("keyword") or r.get("module") or "")
            + '</td><td>' + ("✓" if r["success"] else "✗") + '</td></tr>' for r in rows)
        return page("Activity Log", _bar() + '<article class="md"><h1>📈 Activity Log</h1>'
                    + filt +
                    '<p class="note">Latest 300 matching events (dashboard actions '
                    'only — no keystrokes, screens, or private data).</p>'
                    '<table><tr><th>When</th><th>User</th><th>Role</th><th>Event</th>'
                    '<th>Detail</th><th>OK</th></tr>'
                    + (body or '<tr><td colspan="6">No events match.</td></tr>')
                    + '</table></article>')

    @app.route("/admin/activity/export")
    @require_perm("logs.view_all")
    def admin_activity_export():
        path, n = activity.export_csv("data/exports/activity_log.csv")
        return page("Export", _bar() + '<article class="md"><h1>Activity exported</h1>'
                    f'<p>{n} events written to <code>{path}</code> on the server.</p>'
                    '</article>')

    # ---- Team Operations OS (/team/ops/*) ---------------------------------
    # The role-based execution board: task workflow, review queue, proactive
    # work log with the 48h KPI lock, bottleneck alerts and analytics. Lives in
    # src/team_ui.py so this file stays navigable; it reuses the helpers above.
    from src import team_ui
    team_ui.register(app, page, login_required, current_user, _log, _h_esc,
                     _safe_url, _csrf, stage_nav=_stage_nav)

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

    secret = os.getenv("APP_SECRET_KEY") or os.getenv("WEB_SECRET")
    if not secret:
        # Pin a STABLE key so sessions + CSRF tokens survive a restart. A random
        # per-boot key logs the whole team out and invalidates every CSRF token
        # on every deploy. Persist one under data/ (gitignored) if no env key.
        keyfile = Path("data/.secret_key")
        try:
            secret = keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""
            if not secret:
                secret = os.urandom(24).hex()
                keyfile.parent.mkdir(parents=True, exist_ok=True)
                keyfile.write_text(secret, encoding="utf-8")
        except Exception:  # noqa: BLE001 - fall back to an ephemeral key
            secret = os.urandom(24).hex()
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
--accent-bg:#FBEFE1;--ok:#1E6B54;--stop:#99271F;--row:#F6F0E6;
--shadow:0 1px 2px rgba(34,28,19,.05),0 6px 20px -12px rgba(34,28,19,.18);
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Monaco,"Cascadia Mono",monospace;}
@media(prefers-color-scheme:dark){:root{--paper:#15110B;--surface:#1E180F;
--ink:#F1E9DA;--ink-soft:#AA9D88;--ink-faint:#7C7060;--line:#322818;
--line-strong:#43371F;--accent:#EA8B44;--accent-bg:#2A1D0E;--ok:#58B491;
--stop:#E68A80;--row:#231B10;--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px -14px rgba(0,0,0,.6);}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.wrap{max-width:880px;margin:0 auto;padding:34px 22px 72px}
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
/* rollout labels: old board vs new Team Ops board */
.legacytag{display:inline-block;font-size:.62rem;font-weight:800;letter-spacing:.05em;
text-transform:uppercase;background:var(--ink-faint);color:var(--paper);
border-radius:20px;padding:2px 9px;vertical-align:middle}
.rolloutnote{background:var(--accent-bg);border:1px solid var(--accent);
border-radius:10px;padding:9px 13px;margin:0 0 12px;font-size:.82rem}
.rolloutnote b{color:var(--accent)}
.rolloutnote span{color:var(--ink-soft)}
/* hand-off strip: workflow module -> Team Ops board */
.tostrip{display:flex;flex-wrap:wrap;gap:7px;align-items:center;background:var(--surface);
border:1px solid var(--line-strong);border-radius:11px;padding:9px 13px;margin:0 0 12px}
.tostrip b{font-size:.83rem;margin-right:4px}
.tostrip-b{font-size:.78rem;font-weight:700;padding:5px 10px;border-radius:7px;
border:1px solid var(--line-strong);background:var(--paper);color:var(--ink);text-decoration:none}
.tostrip-b:hover{border-color:var(--accent);color:var(--accent)}
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
.focus{background:var(--surface);border:1px solid var(--line-strong);border-radius:16px;padding:16px 18px;margin:0 0 20px}
.focus .grouph{margin-top:0}
a.tkstat{text-decoration:none;transition:border-color .15s}a.tkstat:hover{border-color:var(--accent)}
.dlrow{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:8px 0;font-size:.82rem}
.dlbtn{font-size:.74rem;font-weight:700;padding:5px 10px;border:1px solid var(--line-strong);
border-radius:999px;background:var(--paper);color:var(--accent);text-decoration:none;white-space:nowrap}
.dlbtn:hover{background:var(--accent-bg)}
.tkreport{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.tkreport label{font-size:.82rem;font-weight:700}
.tkreport textarea{width:100%;padding:9px 11px;border:1px solid var(--line-strong);
border-radius:9px;background:var(--paper);color:var(--ink);font:inherit;font-size:.86rem;resize:vertical}
.tkreported{margin-top:9px;padding:9px 11px;border-left:3px solid var(--ok);
background:var(--surface);border-radius:8px;font-size:.86rem;white-space:pre-wrap}
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
.pf{display:inline;margin:0}.pf .cbtn{vertical-align:middle}
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
/* workspace tables — base table CSS is scoped to .md, so style .ws tables here */
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;margin:10px 0;background:var(--surface)}
.ws table{border-collapse:collapse;width:100%;font-size:.85rem}
.ws th,.ws td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
.ws thead th{background:var(--paper);font-size:.68rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-faint);white-space:nowrap}
.ws tbody tr:last-child td{border-bottom:none}
.ws tbody tr:hover{background:var(--paper)}
.edge{font-size:.86rem;color:var(--ink);background:var(--accent-bg);border-radius:8px;padding:10px 12px;margin-top:10px}
.edge b{color:var(--accent)}
/* collapsible detail groups — decision-first: detail is one click away */
.wsgrp{background:var(--surface);border:1px solid var(--line);border-radius:14px;margin:12px 0;box-shadow:var(--shadow);scroll-margin-top:56px;overflow:hidden}
.wsgrp>summary{cursor:pointer;list-style:none;padding:15px 18px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.wsgrp>summary::-webkit-details-marker{display:none}
.wsgrp>summary .gt{font-size:1.05rem;font-weight:800}
.wsgrp>summary .gh{font-size:.75rem;color:var(--ink-faint)}
.wsgrp>summary .chev{margin-left:auto;color:var(--ink-faint);transition:transform .18s}
.wsgrp[open]>summary .chev{transform:rotate(90deg)}
.wsgrp[open]>summary{border-bottom:1px solid var(--line)}
.wsgrpbody{padding:2px 16px 10px}
.wsgrpbody .ws{box-shadow:none;border:0;border-top:1px solid var(--line);border-radius:0;margin:0;padding:16px 0}
.wsgrpbody .ws:first-child{border-top:0;padding-top:8px}
@media(prefers-reduced-motion:reduce){.wsgrp>summary .chev{transition:none}}
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
gap:8px;flex-wrap:wrap;margin:0 0 18px;
padding:9px 14px;background:var(--paper);border-bottom:1px solid var(--line-strong);
box-shadow:0 2px 8px rgba(0,0,0,.06)}
.back{display:inline-flex;align-items:center;gap:7px;font-family:var(--sans);
font-size:.92rem;font-weight:700;color:var(--paper);background:var(--accent);
border:1px solid var(--accent);border-radius:10px;padding:9px 16px;text-decoration:none;
line-height:1}
.back:hover{filter:brightness(1.08)}
.navbtn{display:inline-flex;align-items:center;gap:6px;font-family:var(--sans);
font-size:.85rem;font-weight:700;color:var(--ink-soft);background:var(--surface);
border:1px solid var(--line-strong);border-radius:9px;padding:8px 13px;
text-decoration:none;line-height:1;white-space:nowrap}
.navbtn:hover{border-color:var(--accent);color:var(--accent);background:var(--accent-bg)}
.navbtn.on{color:var(--paper);background:var(--accent);border-color:var(--accent)}
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
.md table{border-collapse:separate;border-spacing:0;width:100%;font-size:.85rem;
margin:1.1em 0;display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;
border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}
.md th,.md td{padding:9px 12px;text-align:left;white-space:nowrap;
border-bottom:1px solid var(--line)}
.md th{background:var(--accent-bg);font-family:var(--mono);font-size:.7rem;
letter-spacing:.04em;text-transform:uppercase;color:var(--ink-soft);font-weight:700;
position:sticky;top:0}
.md td{font-variant-numeric:tabular-nums}
.md tbody tr:nth-child(even){background:var(--row)}
.md tbody tr:hover{background:var(--accent-bg)}
.md tbody tr:last-child td{border-bottom:0}
.md td strong{font-variant-numeric:tabular-nums}
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
    <div class="hright">{{UPDATED}}{{USER}}<a class="logout" href="/team">Team</a><a class="logout" href="/how-to-use">How to Use</a><a class="logout" href="/cheatsheet">Cheat Sheet</a><a class="logout" href="/logout">Sign out</a></div>
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
