"""Operations: daily auto-run, health check, cron helpers, and logging.

Design rules:
- NEVER publishes to Etsy. daily-run only pulls data, refreshes feeds, and
  writes a summary + logs. There is no publish path anywhere in the tool.
- NEVER logs secrets. We check that YTRENDS_COOKIE exists but never print it.
- Cron is a Linux/VPS concept. On Windows we print the exact line + Task
  Scheduler hint instead of trying to install a crontab.
"""
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

LOG_DIR = Path("logs")
DATA_DIRS = [
    "data/raw", "data/raw/ytuong", "data/processed", "data/suppliers",
    "data/performance", "data/learning", "data/tracking", "data/alerts",
    "reports/latest/runs",
]
CRON_MARKER = "# etsy-agent-daily-run"


def get_logger(name, filename):
    LOG_DIR.mkdir(exist_ok=True)
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(logging.INFO)
        h = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
    return log


def ensure_dirs():
    for d in DATA_DIRS:
        Path(d).mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------ daily-run ----
def daily_run():
    """Pull fresh data + refresh feeds + write a summary. Never publishes."""
    # Preflight: every data step needs these. If we're on the wrong interpreter
    # (e.g. the VPS system `python3` instead of `.venv/bin/python`), fail fast with
    # a clear message BEFORE running/writing anything — otherwise all data steps
    # "fail" on the missing import and raise a scary CRITICAL alert.
    try:
        import dotenv, requests  # noqa: F401
    except ImportError as exc:
        print(f"Cannot run daily-run: missing dependency '{exc.name}'.")
        print("You're probably using the wrong Python. Use the project's venv:")
        print("  VPS:    .venv/bin/python main.py daily-run")
        print("  laptop: py main.py daily-run   (Windows)  /  python3 …  (Mac)")
        raise SystemExit(1)
    log = get_logger("daily-run", "daily-run.log")
    err = get_logger("errors", "errors.log")
    import json
    ensure_dirs()
    try:
        from src import learning
        learning.ensure_files()
    except Exception as e:  # noqa: BLE001
        err.error("learning.ensure_files failed: %s", e)

    log.info("=== daily-run start (no publishing) ===")
    try:
        from src import activity
        activity.log("DAILY_RUN_START", module="ops")
    except Exception:  # noqa: BLE001
        pass
    summary = {"date": str(date.today()), "published": False, "steps": {}}

    def step(name, fn):
        # Catch SystemExit too: the MCP layer raises it on network/429/401, and a
        # nightly run must keep going + still write its summary.
        try:
            res = fn()
            summary["steps"][name] = {"ok": True, "detail": res}
            log.info("%s OK: %s", name, res)
        except (SystemExit, Exception) as e:  # noqa: BLE001
            summary["steps"][name] = {"ok": False, "error": str(e)[:200]}
            log.error("%s FAILED: %s", name, e)
            err.error("daily-run %s failed: %s", name, e)

    def _harvest():
        from src.harvest import run_harvest
        run_harvest([])
        p = Path("data/processed/keyword_data.csv")
        return f"keyword data -> {p} ({'exists' if p.exists() else 'missing'})"

    def _autopull():
        from src import autopull, saved
        shops = autopull.pull_shops(limit=15)
        listings = autopull.pull_listings(limit=20)
        ns = saved.auto_save_shops(shops)
        nl = saved.auto_save_listings(listings)
        return f"shops +{ns}/{len(shops)}, listings +{nl}/{len(listings)}"

    def _learn():
        from src import learning
        return learning.summary()

    def _track():
        from src import tracking
        return tracking.daily_snapshot(limit=15)

    def _alerts():
        from src import alerts
        alerts.generate()          # re-scan state and raise/clear alerts
        return alerts.summary()

    def _warm():
        # Pre-fetch the paginated Trending/Opportunities/Gems surfaces into the
        # per-day cache so the team's first dashboard load is instant, not a
        # 10-page live pull. Mode-independent, so one pass covers every line.
        from src import interactive
        return interactive.warm_cache()

    step("harvest_keywords", _harvest)
    step("autopull_feeds", _autopull)
    step("track_snapshots", _track)
    step("learning_summary", _learn)
    step("refresh_alerts", _alerts)
    step("warm_keyword_cache", _warm)

    out = Path("data/processed") / f"daily_summary_{date.today()}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    try:
        from src import activity
        failed_steps = [k for k, v in summary["steps"].items() if not v.get("ok")]
        activity.log("DAILY_RUN_FAILED" if failed_steps else "DAILY_RUN_COMPLETE",
                     module="ops", success=not failed_steps,
                     summary=(", ".join(failed_steps) or "all steps ok"))
    except Exception:  # noqa: BLE001
        pass
    log.info("=== daily-run done -> %s ===", out)
    print(f"daily-run complete (no publishing). Summary -> {out}")
    for name, r in summary["steps"].items():
        print(f"  {'OK  ' if r['ok'] else 'FAIL'} {name}: "
              f"{r.get('detail', r.get('error'))}")
    return summary


# ------------------------------------------------------------------ clean ----
def clean(keep_runs=5):
    """Reclaim disk without touching live data. Trims old report archives, prunes
    stale keyword cache (+VACUUM), and drops regenerable __pycache__/.pytest_cache.
    Safe anytime, on the laptop or the VPS. Returns a list of what it did."""
    import shutil
    from src import db
    out = []

    runs_dir = Path("reports/runs")
    if runs_dir.exists():
        runs = sorted([p for p in runs_dir.iterdir() if p.is_dir()],
                      key=lambda p: p.name, reverse=True)
        old = runs[max(0, keep_runs):]
        for d in old:
            shutil.rmtree(d, ignore_errors=True)
        out.append(f"report archives: removed {len(old)}, kept newest "
                   f"{len(runs) - len(old)}")

    st = Path("reports/selftest")
    if st.exists():
        shutil.rmtree(st, ignore_errors=True)
        out.append("cleared reports/selftest (rebuilt on next selftest)")

    try:
        n = db.prune_cache(keep_days=3)
        db.vacuum()
        out.append(f"keyword cache: pruned {n} stale row(s) + vacuumed agent.db")
    except Exception as e:  # noqa: BLE001
        out.append(f"keyword cache prune skipped: {e}")

    # Only OUR __pycache__ (never walk .venv — huge and not ours).
    pyc = [p for base in ("src", "tests") for p in Path(base).rglob("__pycache__")]
    if Path("__pycache__").exists():
        pyc.append(Path("__pycache__"))
    for d in pyc:
        shutil.rmtree(d, ignore_errors=True)
    if Path(".pytest_cache").exists():
        shutil.rmtree(".pytest_cache", ignore_errors=True)
    out.append(f"removed {len(pyc)} __pycache__ dir(s) + .pytest_cache")

    for leftover in (Path("data/pdf_test.pdf"), Path("data/pdf_test.md")):
        if leftover.exists():
            leftover.unlink()
            out.append(f"removed leftover {leftover.name}")

    return out


# ----------------------------------------------------------- healthcheck ----
def _dep_ok(mod):
    """True if a runtime dependency imports cleanly on THIS interpreter."""
    import importlib
    try:
        importlib.import_module(mod)
        return True
    except Exception:  # noqa: BLE001
        return False


def run_pytest():
    """Run the test suite quietly. Returns (passed: bool, summary: str)."""
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                           capture_output=True, text=True, timeout=900)
        lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        summary = lines[-1] if lines else ((r.stderr or "").strip()[-160:] or "no output")
        return r.returncode == 0, summary
    except Exception as e:  # noqa: BLE001
        return False, f"could not run pytest: {e}"


def healthcheck(run_tests=False):
    """Return (checks, flags). Never prints secret values.

    checks: list of (name, ok, detail) — the detailed line-by-line report.
    flags:  the named readiness flags the audit reports. A flag is true ONLY when
            its dependency actually imports AND the functional check passes on THIS
            environment — so the audit can never claim ready in a deployment where
            Flask/Werkzeug/Markdown are missing or the tests fail. TESTS_PASS and
            SYSTEM_READY_FOR_TEAM_USE stay None ('unknown') until pytest is run.
    """
    checks = []

    def add(name, ok, detail=""):
        ok = bool(ok)
        checks.append((name, ok, detail))
        return ok

    env = Path(".env")
    add(".env file exists", env.exists(),
        "" if env.exists() else "copy .env.example to .env")

    def _env_set(key, minlen=5):
        """True if key is set (non-empty) in the environment OR in the .env file.
        The CLI doesn't load .env (only the web server does), so we check both —
        and never read or print the value itself."""
        if (os.getenv(key) or "").strip():
            return True
        if env.exists():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith(f"{key}=") \
                        and len(line.split("=", 1)[1].strip()) >= minlen:
                    return True
        return False

    add("YTRENDS_COOKIE present (value hidden)", _env_set("YTRENDS_COOKIE"),
        "optional — the MCP data layer works without a cookie")

    # ---- runtime dependencies (the audit-truth gate) ----
    flask_ok = _dep_ok("flask")
    werkzeug_ok = _dep_ok("werkzeug")
    markdown_ok = _dep_ok("markdown")
    pytest_ok = _dep_ok("pytest")
    autorun_ok = _dep_ok("dotenv") and _dep_ok("requests")
    add("dependency: Flask (dashboard)", flask_ok,
        "" if flask_ok else "pip install -r requirements.txt")
    add("dependency: Werkzeug (auth password hashing)", werkzeug_ok,
        "" if werkzeug_ok else "pip install -r requirements.txt")
    add("dependency: Markdown (PDF/report export)", markdown_ok,
        "" if markdown_ok else "pip install -r requirements.txt")
    add("dependency: pytest (test suite)", pytest_ok,
        "" if pytest_ok else "pip install -r requirements-dev.txt")

    for d in DATA_DIRS:
        add(f"dir {d}", Path(d).exists(), "" if Path(d).exists() else "run daily-run")

    kd = Path("data/processed/keyword_data.csv")
    add("keyword data present", kd.exists(),
        "" if kd.exists() else "run: py main.py harvest")
    sup = Path("data/suppliers/supplier_products.csv")
    add("supplier products csv (optional)", True,
        "present" if sup.exists() else "none yet — sync/import when ready")

    dashboard_starts = False
    try:
        from src import web
        web.build_app("x", "y")
        dashboard_starts = add("dashboard can start", True)
    except Exception as e:  # noqa: BLE001
        dashboard_starts = add("dashboard can start", False, str(e)[:120])

    add("PDF/report deps (markdown)", markdown_ok,
        "" if markdown_ok else "pip install -r requirements.txt")

    try:
        from src import learning
        learning.ensure_files()
        add("learning files present", all(p.exists() for p in learning.FILES.values()))
    except Exception as e:  # noqa: BLE001
        add("learning files present", False, str(e)[:120])

    add("daily-run command available", callable(daily_run))

    # ---- team login / auth ----
    user_db_ok = has_admin = pw_hashed = False
    try:
        from src import auth
        auth.appdb.init_db()
        user_db_ok = add("user database exists", Path(auth.appdb.DB_PATH).exists())
        users = auth.list_users()
        has_admin = add("users table + at least one admin", any(
            u["role"] in ("OWNER", "ADMIN") and u["status"] == "ACTIVE" for u in users),
            "run: py main.py auth create-admin ..." if not users else "")
        pw_hashed = add("passwords hashed (no plaintext)", all(
            (u["password_hash"] or "").split(":")[0] not in ("", "plain")
            and len(u["password_hash"] or "") > 20 for u in users) if users else True)
        add("session secret configured",
            _env_set("APP_SECRET_KEY", 8) or _env_set("WEB_SECRET", 8),
            "set APP_SECRET_KEY in .env so logins survive restarts")
        # activity + task tables present
        auth.appdb.q("SELECT 1 FROM activity_logs LIMIT 1")
        auth.appdb.q("SELECT 1 FROM tasks LIMIT 1")
        add("activity_log + task tables present", True)
        add("no publish automation (manual approval only)", True)
    except Exception as e:  # noqa: BLE001
        add("team login / auth", False, str(e)[:120])

    installed, when, _ = _cron_state()
    add("cron installed (Linux/VPS)", installed,
        f"scheduled {when}" if installed else "run: py main.py cron install --time 06:00")

    # ---- named readiness flags (the audit's source of truth) ----
    flags = {
        "DASHBOARD_READY": flask_ok and dashboard_starts,
        "AUTH_READY": werkzeug_ok and user_db_ok and has_admin and pw_hashed,
        "PDF_EXPORT_READY": markdown_ok,
        "DAILY_AUTORUN_READY": autorun_ok,
        "PUBLISH_AUTOMATION": False,   # always false — no publish path exists
        "TESTS_PASS": None,            # unknown until pytest runs
        "SYSTEM_READY_FOR_TEAM_USE": None,
    }
    if run_tests:
        passed, summary = run_pytest()
        add("pytest suite passes", passed, summary)
        flags["TESTS_PASS"] = passed
        flags["SYSTEM_READY_FOR_TEAM_USE"] = bool(
            passed and flags["DASHBOARD_READY"] and flags["AUTH_READY"]
            and flags["PDF_EXPORT_READY"] and flags["DAILY_AUTORUN_READY"])
    return checks, flags


# ------------------------------------------------------------------ cron ----
def cron_line(time="06:00", project=None, every_hours=None, command="daily-run"):
    """Build the crontab line. Default: `daily-run` once a day at `time`. Pass
    every_hours=N for a `0 */N * * *` interval, and command="warm" to run the
    lightweight cache warm (adds --fresh so each run pulls current data)."""
    project = project or os.getcwd()
    py = sys.executable or "python3"
    cmd = "warm" if str(command).lower() == "warm" else "daily-run"
    invoke = "warm --fresh" if cmd == "warm" else "daily-run"
    logf = "warm.log" if cmd == "warm" else "daily-run.log"
    if every_hours:
        try:
            n = max(1, min(24, int(every_hours)))
        except Exception:  # noqa: BLE001
            n = 6
        sched = f"0 */{n} * * *"
    else:
        try:
            hh, mm = (int(x) for x in time.split(":"))
        except Exception:  # noqa: BLE001
            hh, mm = 6, 0
        sched = f"{mm} {hh} * * *"
    return (f"{sched} cd {project} && {py} main.py {invoke} "
            f">> logs/{logf} 2>&1 {CRON_MARKER}")


def _crontab_read():
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return None   # crontab not available (e.g. Windows)


def _cron_state():
    """(installed, schedule_str, raw_line) — schedule read from our marker."""
    existing = _crontab_read()
    if not existing:
        return False, "", ""
    for line in existing.splitlines():
        if CRON_MARKER in line:
            parts = line.split()
            when = f"{parts[1]}:{parts[0].zfill(2)}" if len(parts) >= 2 else "?"
            return True, when, line
    return False, "", ""


def cron_install(time="06:00", every_hours=None, command="daily-run"):
    line = cron_line(time, every_hours=every_hours, command=command)
    when = f"every {every_hours}h" if every_hours else f"daily at {time}"
    existing = _crontab_read()
    if existing is None:
        print("crontab not available on this OS (this is a Windows dev box).")
        print(f"On the Linux VPS, add this line with `crontab -e`:\n")
        print("  " + line)
        print(f"\nWindows alternative: Task Scheduler -> {when} -> run "
              f"`py main.py {command}` in the project folder "
              "(or use deploy/schedule-warm.ps1).")
        return line
    kept = [ln for ln in existing.splitlines() if CRON_MARKER not in ln and ln.strip()]
    kept.append(line)
    new = "\n".join(kept) + "\n"
    try:
        p = subprocess.run(["crontab", "-"], input=new, text=True,
                           capture_output=True)
        if p.returncode == 0:
            print(f"Installed cron: {command} {when}.\n  {line}")
        else:
            print("Could not install crontab automatically. Add manually:\n  " + line)
    except Exception as e:  # noqa: BLE001
        print(f"Could not install crontab ({e}). Add manually:\n  " + line)
    return line


def cron_status():
    installed, when, line = _cron_state()
    log = LOG_DIR / "daily-run.log"
    last_run, last_line = "never", ""
    if log.exists():
        try:
            from datetime import datetime
            last_run = datetime.fromtimestamp(log.stat().st_mtime).isoformat(
                timespec="seconds")
            tail = [ln for ln in log.read_text(encoding="utf-8",
                    errors="replace").splitlines() if ln.strip()]
            last_line = tail[-1] if tail else ""
        except Exception:  # noqa: BLE001
            pass
    print(f"cron installed : {'yes' if installed else 'no'}")
    print(f"scheduled time : {when or '—'}")
    print(f"last run (log) : {last_run}")
    print(f"last log line  : {last_line or '—'}")
    print(f"log path       : {log}")
    if not installed:
        print("\nTo install:  py main.py cron install --time \"06:00\"")
    return {"installed": installed, "time": when, "last_run": last_run,
            "log": str(log)}
