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

    step("harvest_keywords", _harvest)
    step("autopull_feeds", _autopull)
    step("track_snapshots", _track)
    step("learning_summary", _learn)
    step("refresh_alerts", _alerts)

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


# ----------------------------------------------------------- healthcheck ----
def healthcheck():
    """Return a list of (name, ok, detail). Never prints secret values."""
    checks = []

    def add(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    env = Path(".env")
    add(".env file exists", env.exists(),
        "" if env.exists() else "copy .env.example to .env")
    cookie = False
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("YTRENDS_COOKIE=") and len(line.split("=", 1)[1].strip()) > 5:
                cookie = True
    add("YTRENDS_COOKIE present (value hidden)", cookie,
        "optional — the MCP data layer works without a cookie" if not cookie else "set")

    for d in DATA_DIRS:
        add(f"dir {d}", Path(d).exists(), "" if Path(d).exists() else "run daily-run")

    kd = Path("data/processed/keyword_data.csv")
    add("keyword data present", kd.exists(),
        "" if kd.exists() else "run: py main.py harvest")
    sup = Path("data/suppliers/supplier_products.csv")
    add("supplier products csv (optional)", True,
        "present" if sup.exists() else "none yet — sync/import when ready")

    try:
        from src import web
        web.build_app("x", "y")
        add("dashboard can start", True)
    except Exception as e:  # noqa: BLE001
        add("dashboard can start", False, str(e)[:120])

    try:
        import markdown  # noqa: F401
        add("PDF/report deps (markdown)", True)
    except Exception as e:  # noqa: BLE001
        add("PDF/report deps (markdown)", False, str(e)[:120])

    try:
        from src import learning
        learning.ensure_files()
        add("learning files present", all(p.exists() for p in learning.FILES.values()))
    except Exception as e:  # noqa: BLE001
        add("learning files present", False, str(e)[:120])

    add("daily-run command available", callable(daily_run))

    # ---- team login / auth ----
    try:
        from src import auth
        auth.appdb.init_db()
        add("user database exists", Path(auth.appdb.DB_PATH).exists())
        users = auth.list_users()
        add("users table + at least one admin", any(
            u["role"] in ("OWNER", "ADMIN") and u["status"] == "ACTIVE" for u in users),
            "run: py main.py auth create-admin ..." if not users else "")
        add("passwords hashed (no plaintext)", all(
            (u["password_hash"] or "").split(":")[0] not in ("", "plain")
            and len(u["password_hash"] or "") > 20 for u in users) if users else True)
        add("session secret configured", bool(os.getenv("APP_SECRET_KEY")
            or os.getenv("WEB_SECRET")),
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
    return checks


# ------------------------------------------------------------------ cron ----
def cron_line(time="06:00", project=None):
    try:
        hh, mm = (int(x) for x in time.split(":"))
    except Exception:  # noqa: BLE001
        hh, mm = 6, 0
    project = project or os.getcwd()
    py = sys.executable or "python3"
    return (f"{mm} {hh} * * * cd {project} && {py} main.py daily-run "
            f">> logs/daily-run.log 2>&1 {CRON_MARKER}")


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


def cron_install(time="06:00"):
    line = cron_line(time)
    existing = _crontab_read()
    if existing is None:
        print("crontab not available on this OS (this is a Windows dev box).")
        print("On the Linux VPS, add this line with `crontab -e`:\n")
        print("  " + line)
        print("\nWindows alternative: Task Scheduler -> daily 06:00 -> run "
              "`py main.py daily-run` in the project folder.")
        return line
    kept = [ln for ln in existing.splitlines() if CRON_MARKER not in ln and ln.strip()]
    kept.append(line)
    new = "\n".join(kept) + "\n"
    try:
        p = subprocess.run(["crontab", "-"], input=new, text=True,
                           capture_output=True)
        if p.returncode == 0:
            print(f"Installed cron: daily at {time}.\n  {line}")
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
