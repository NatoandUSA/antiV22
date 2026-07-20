"""Daily flat-file backup (V33 CEO review: file loss = months of captures and
learning gone). One zip per day of the master CSV + import lanes + learning +
history; keeps the newest 10. Cheap guard: returns instantly when today's
backup already exists."""
import time
import zipfile
from datetime import date
from pathlib import Path

BK_DIR = Path("backups")
KEEP = 10
_MAX_FILE = 5_000_000        # skip anything over 5 MB (raw dumps)


def ensure_daily_backup():
    """Create backups/backup_YYYYMMDD.zip once per day. Never raises."""
    try:
        BK_DIR.mkdir(exist_ok=True)
        p = BK_DIR / f"backup_{date.today().strftime('%Y%m%d')}.zip"
        if p.exists():
            return str(p)
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            if Path("keyword_data.csv").is_file():
                z.write("keyword_data.csv")
            for root in ("data/imports", "data/learning", "data/history",
                         "config"):
                r = Path(root)
                if not r.is_dir():
                    continue
                for f in r.rglob("*"):
                    if f.is_file() and f.stat().st_size <= _MAX_FILE:
                        z.write(f)
        for old in sorted(BK_DIR.glob("backup_*.zip"))[:-KEEP]:
            old.unlink()
        return str(p)
    except Exception:  # noqa: BLE001 - backup must never break the app
        return None


def newest_age_days():
    """Age (days, float) of the newest backup, or None if none exist."""
    try:
        zips = sorted(BK_DIR.glob("backup_*.zip"))
        if not zips:
            return None
        return (time.time() - zips[-1].stat().st_mtime) / 86400.0
    except Exception:  # noqa: BLE001
        return None
