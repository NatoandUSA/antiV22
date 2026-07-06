"""Team web dashboard for the Etsy Product Manager.

  python main.py web            -> serves http://127.0.0.1:8000

Login uses WEB_PASSWORD from .env. The app REFUSES to start without one, so it
is never exposed unauthenticated. To share with your team, keep this running
and put a Cloudflare Tunnel / ngrok in front of the local port — the login
gates access. Never open the raw port straight to the internet, and always set
a strong WEB_PASSWORD first (your .env holds live API secrets).

Design note: reuses the burnt-amber "Command Card" palette so the web UI and
the printed cheat sheet feel like one tool.
"""
import os
import subprocess
import sys
import threading
import uuid
from functools import wraps
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "reports" / "latest"

# Allowlist: button id -> (label, argv, one-line help, needs-live-data?).
# Only these fixed argv lists can run; no user-supplied arguments are executed.
COMMANDS = {
    "daily":        ("Build daily reports", ["daily"],
                     "The 5-report team set — your main command.", True),
    "discover":     ("Discover niches", ["discover"],
                     "Rank rising, low-competition FOCUS niches.", True),
    "discover_pod": ("Discover · POD", ["discover", "pod"],
                     "Print-on-demand keywords only.", True),
    "discover_emb": ("Discover · Embroidery", ["discover", "embroidery"],
                     "Embroidery keywords only.", True),
    "ideas":        ("Best ideas", ["ideas"],
                     "Product clusters + verdicts + 7-day plan.", True),
    "grow":         ("Grow keywords", ["grow"],
                     "Auto-add viral & best-selling keywords.", True),
    "images":       ("Preview AI prompts", ["images"],
                     "List report-04 design prompts (no API calls).", False),
    "selftest":     ("Self-test", ["selftest"],
                     "Health check — no network needed.", False),
}

# In-memory job store. Fine for a small team on one instance.
JOBS = {}
JOBS_LOCK = threading.Lock()
MAX_OUTPUT = 12000


def _run_job(job_id, argv):
    try:
        proc = subprocess.Popen(
            [sys.executable, "main.py", *argv], cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1)
        buf = []
        for line in proc.stdout:
            buf.append(line)
            joined = "".join(buf)
            if len(joined) > MAX_OUTPUT:
                joined = "...(truncated)...\n" + joined[-MAX_OUTPUT:]
            with JOBS_LOCK:
                JOBS[job_id]["output"] = joined
        proc.wait()
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done" if proc.returncode == 0 else "error"
            JOBS[job_id]["code"] = proc.returncode
    except Exception as exc:  # launcher-level failure
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["output"] = JOBS[job_id].get("output", "") + \
                f"\n[could not launch] {exc}"


def build_app(password, secret):
    from flask import (Flask, session, request, redirect, url_for,
                       jsonify, abort, send_from_directory, Response)
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

    # ---- dashboard ----
    @app.route("/")
    @login_required
    def index():
        cards = []
        for cid, (label, _argv, help_, live) in COMMANDS.items():
            tag = ('<span class="tag live">live data</span>' if live
                   else '<span class="tag">offline</span>')
            cards.append(
                f'<button class="cmd" data-job="{cid}">'
                f'<span class="cl">{label}</span>{tag}'
                f'<span class="ch">{help_}</span></button>')
        reports = _report_rows()
        return page("Dashboard", DASH
                    .replace("{{CARDS}}", "".join(cards))
                    .replace("{{REPORTS}}", reports))

    # ---- run a command (background) ----
    @app.route("/run/<job>", methods=["POST"])
    @login_required
    def run(job):
        if job not in COMMANDS:
            abort(404)
        job_id = uuid.uuid4().hex
        argv = COMMANDS[job][1]
        with JOBS_LOCK:
            JOBS[job_id] = {"cmd": " ".join(argv), "status": "running",
                            "output": "", "code": None}
        threading.Thread(target=_run_job, args=(job_id, argv),
                         daemon=True).start()
        return jsonify({"job_id": job_id, "cmd": " ".join(argv)})

    @app.route("/status/<job_id>")
    @login_required
    def status(job_id):
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if not j:
                abort(404)
            return jsonify(dict(j))

    # ---- reports ----
    def _safe_report(name):
        """Return an existing file inside reports/latest, or None."""
        p = (LATEST / name).resolve()
        if LATEST.resolve() not in p.parents or not p.is_file():
            return None
        return p

    @app.route("/report/<name>")
    @login_required
    def report(name):
        p = _safe_report(name)
        if not p or p.suffix != ".md":
            abort(404)
        html = md.markdown(p.read_text(encoding="utf-8"),
                           extensions=["tables", "fenced_code", "sane_lists"])
        return page(name, f'<a class="back" href="/">&larr; Dashboard</a>'
                    f'<article class="md">{html}</article>')

    @app.route("/pdf/<name>")
    @login_required
    def pdf(name):
        p = _safe_report(name)
        if not p or p.suffix != ".pdf":
            abort(404)
        return send_from_directory(str(LATEST), p.name)

    def _report_rows():
        if not LATEST.exists():
            return ('<p class="muted">No reports yet — run '
                    '<b>Build daily reports</b> first.</p>')
        mds = sorted(LATEST.glob("[0-9][0-9]_*.md"))
        if not mds:
            return ('<p class="muted">No reports yet — run '
                    '<b>Build daily reports</b> first.</p>')
        rows = []
        for m in mds:
            rid = m.name[:2]
            title = m.stem[3:].replace("_", " ").title()
            pdf = m.with_suffix(".pdf")
            pdf_link = (f'<a href="/pdf/{pdf.name}" target="_blank">PDF</a>'
                        if pdf.exists() else "")
            rows.append(
                f'<div class="rrow"><span class="rid">{rid}</span>'
                f'<a class="rt" href="/report/{m.name}">{title}</a>'
                f'<span class="rp">{pdf_link}</span></div>')
        return "".join(rows)

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
        print("The web dashboard needs Flask and Markdown.")
        print("Fix: py -m pip install flask markdown")
        sys.exit(1)

    password = os.getenv("WEB_PASSWORD", "").strip()
    if not password:
        print("WEB_PASSWORD is not set — refusing to start without a login.")
        print("Fix: add a line to your .env file:")
        print("  WEB_PASSWORD=choose-a-strong-password")
        sys.exit(1)
    secret = os.getenv("WEB_SECRET") or os.urandom(24).hex()

    if host == "0.0.0.0":
        print("WARNING: binding 0.0.0.0 exposes this on your network. Prefer "
              "the default 127.0.0.1 + a Cloudflare Tunnel / ngrok for teams.")
    app = build_app(password, secret)
    print(f"Etsy Product Manager web dashboard -> http://{host}:{port}")
    print("Log in with your WEB_PASSWORD. Ctrl+C to stop.")
    app.run(host=host, port=port, threaded=True)


# --------------------------- templates ---------------------------
CSS = """
:root{--paper:#FBFAF6;--surface:#FFF;--ink:#221C13;--ink-soft:#6E6455;
--ink-faint:#9A8E7B;--line:#E7DFD0;--line-strong:#D8CDB8;--accent:#A8480A;
--accent-bg:#FBEFE1;--ok:#1E6B54;--ok-bg:#E4F0EA;--stop:#99271F;--stop-bg:#F6E5E2;
--shadow:0 1px 2px rgba(34,28,19,.05),0 6px 20px -12px rgba(34,28,19,.18);
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,Roboto,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Monaco,"Cascadia Mono",monospace;}
@media(prefers-color-scheme:dark){:root{--paper:#15110B;--surface:#1E180F;
--ink:#F1E9DA;--ink-soft:#AA9D88;--ink-faint:#7C7060;--line:#322818;
--line-strong:#43371F;--accent:#EA8B44;--accent-bg:#2A1D0E;--ok:#58B491;
--ok-bg:#17281F;--stop:#E68A80;--stop-bg:#2C1714;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px -14px rgba(0,0,0,.6);}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:920px;margin:0 auto;padding:32px 22px 64px}
header{border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:24px;
display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.kicker{font-family:var(--mono);font-size:.7rem;letter-spacing:.14em;
text-transform:uppercase;color:var(--accent);font-weight:600}
h1{font-size:1.7rem;font-weight:800;letter-spacing:-.02em;margin:.2em 0 0}
a{color:var(--accent)}
.eyebrow{font-family:var(--mono);font-size:.72rem;letter-spacing:.13em;
text-transform:uppercase;color:var(--ink-faint);margin:0 0 12px;display:flex;
align-items:center;gap:10px}.eyebrow::after{content:"";flex:1;height:1px;background:var(--line)}
.eyebrow b{color:var(--accent);font-weight:700}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}
.cmd{text-align:left;background:var(--surface);border:1px solid var(--line);
border-radius:12px;padding:14px 15px;box-shadow:var(--shadow);cursor:pointer;
display:flex;flex-direction:column;gap:6px;font:inherit;color:inherit}
.cmd:hover{border-color:var(--accent)}
.cmd:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.cmd .cl{font-weight:700;font-size:.95rem}
.cmd .ch{font-size:.8rem;color:var(--ink-soft)}
.tag{font-family:var(--mono);font-size:.6rem;letter-spacing:.06em;
text-transform:uppercase;color:var(--ink-faint);border:1px solid var(--line);
border-radius:4px;padding:2px 6px;font-weight:600;align-self:flex-start}
.tag.live{color:var(--accent);border-color:var(--accent)}
section{margin-top:30px}
.panel{background:var(--surface);border:1px solid var(--line-strong);
border-radius:10px;margin-top:10px;overflow:hidden}
.panel .bar{display:flex;align-items:center;gap:10px;padding:9px 13px;
border-bottom:1px solid var(--line);font-family:var(--mono);font-size:.78rem}
.dot{width:9px;height:9px;border-radius:50%;background:var(--ink-faint)}
.dot.running{background:var(--accent);animation:pulse 1s infinite}
.dot.done{background:var(--ok)}.dot.error{background:var(--stop)}
@keyframes pulse{50%{opacity:.3}}
@media(prefers-reduced-motion:reduce){.dot.running{animation:none}}
pre{margin:0;padding:12px 14px;font-family:var(--mono);font-size:.78rem;
line-height:1.55;white-space:pre-wrap;word-break:break-word;max-height:340px;
overflow:auto;color:var(--ink)}
.rrow{display:grid;grid-template-columns:34px 1fr auto;align-items:center;gap:12px;
background:var(--surface);border:1px solid var(--line);border-radius:10px;
padding:10px 14px;margin-bottom:8px}
.rid{font-family:var(--mono);font-weight:800;color:var(--accent)}
.rt{font-weight:700;font-size:.9rem;text-decoration:none}.rt:hover{text-decoration:underline}
.rp a{font-family:var(--mono);font-size:.74rem}
.muted{color:var(--ink-soft);font-size:.88rem}
.back{font-family:var(--mono);font-size:.78rem;display:inline-block;margin-bottom:16px}
.md{background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:22px 26px;box-shadow:var(--shadow);overflow-x:auto}
.md h1,.md h2,.md h3{letter-spacing:-.01em}.md h2{border-bottom:1px solid var(--line);
padding-bottom:.2em;margin-top:1.4em}.md code{font-family:var(--mono);font-size:.86em;
background:var(--accent-bg);padding:1px 5px;border-radius:4px}
.md pre{background:var(--paper);border:1px solid var(--line-strong);border-radius:8px;margin:1em 0}
.md pre code{background:none;padding:0}
.md table{border-collapse:collapse;width:100%;font-size:.86rem;margin:1em 0}
.md th,.md td{border:1px solid var(--line);padding:6px 10px;text-align:left}
.md th{background:var(--accent-bg)}
.logout{font-family:var(--mono);font-size:.72rem}
.login{max-width:340px;margin:14vh auto 0;text-align:center}
.login form{display:flex;flex-direction:column;gap:12px;margin-top:20px}
.login input{font:inherit;padding:11px 13px;border:1px solid var(--line-strong);
border-radius:8px;background:var(--surface);color:var(--ink)}
.login button{font:inherit;font-weight:700;padding:11px;border:none;border-radius:8px;
background:var(--accent);color:var(--paper);cursor:pointer}
.err{color:var(--stop);font-size:.85rem}
"""

BASE = ("<!doctype html><html><head><meta charset=utf8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>{{TITLE}} · Etsy Product Manager</title><style>" + CSS +
        "</style></head><body>{{BODY}}</body></html>")

LOGIN = """
<div class="wrap"><div class="login">
  <div class="kicker">Etsy Product Manager</div>
  <h1>Team Dashboard</h1>
  {{ERROR}}
  <form method="post">
    <input type="password" name="password" placeholder="Password" autofocus>
    <button type="submit">Sign in</button>
  </form>
</div></div>
"""

DASH = """
<div class="wrap">
  <header>
    <div><div class="kicker">Etsy Product Manager · Team Dashboard</div>
    <h1>Run &amp; review</h1></div>
    <a class="logout" href="/logout">Sign out</a>
  </header>

  <section>
    <div class="eyebrow"><b>Run a command</b> · results appear below</div>
    <div class="grid">{{CARDS}}</div>
    <div class="panel" id="panel" style="display:none">
      <div class="bar"><span class="dot" id="dot"></span>
        <span id="jobcmd">—</span><span id="jobstate" style="margin-left:auto"></span></div>
      <pre id="out"></pre>
    </div>
  </section>

  <section>
    <div class="eyebrow"><b>Latest reports</b> · read 00 &rarr; 04</div>
    {{REPORTS}}
  </section>
</div>
<script>
const panel=document.getElementById('panel'),dot=document.getElementById('dot'),
out=document.getElementById('out'),jc=document.getElementById('jobcmd'),
js=document.getElementById('jobstate');let timer=null;
document.querySelectorAll('.cmd').forEach(b=>b.addEventListener('click',async()=>{
  const job=b.dataset.job;
  panel.style.display='block';dot.className='dot running';js.textContent='running…';
  out.textContent='Starting…';jc.textContent='python main.py '+job.replace('_',' ');
  const r=await fetch('/run/'+job,{method:'POST'});const {job_id,cmd}=await r.json();
  jc.textContent='python main.py '+cmd;
  if(timer)clearInterval(timer);
  timer=setInterval(async()=>{
    const s=await(await fetch('/status/'+job_id)).json();
    out.textContent=s.output||'(no output yet)';out.scrollTop=out.scrollHeight;
    if(s.status!=='running'){clearInterval(timer);dot.className='dot '+s.status;
      js.textContent=s.status==='done'?'done ✓':'failed (exit '+s.code+')';
      if(s.status==='done')setTimeout(()=>location.reload(),1200);}
  },1000);
}));
</script>
"""
