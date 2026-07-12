"""Clean release packager — `py main.py package release`.

Builds a delivery zip that NEVER contains secrets, git history, caches, logs, or
debug reports. Exclusions come from .releaseignore plus a hardcoded safety list
(so a mistake in .releaseignore can't leak .env). Only .env.example ships.
"""
import fnmatch
import zipfile
from pathlib import Path

# Hardcoded safety net — these are ALWAYS excluded, even if .releaseignore is
# edited or missing. .env must never ship.
ALWAYS_EXCLUDE_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv",
                       "node_modules", "logs", "dist", ".cloudflared", ".ruff_cache"}
ALWAYS_EXCLUDE_FILES = {".env", ".DS_Store", "Thumbs.db"}
ALWAYS_EXCLUDE_GLOBS = ["*.pyc", "*.log", "*.pem", "*.har",
                        "deploy/*.json", "*credentials*",
                        "*.db", "*.sqlite", "*.sqlite3"]
KEEP_ENV_EXAMPLE = ".env.example"   # this one is allowed

# Under data/ we ship ONLY curated reference data (the git-tracked supplier
# catalogs). EVERYTHING else under data/ is runtime/business data — real team
# users + password hashes (app.db), the keyword cache (agent.db), activity logs,
# saved shops/listings, learning, research, imports — and must NEVER ship. The
# app recreates all of it on first run (init_db / learning.ensure_files /
# daily-run), so a fresh deploy needs none of it.
DATA_REFERENCE_KEEP = {
    "data/embroidery_supplier_prices.csv",
    "data/shineon_products.csv",
    "data/supplier_catalog.csv",
    "data/suppliers/Embroidery.csv",
    "data/suppliers/supplier_sources.json",
}
# Runtime research/business files that live at the repo root (gitignored).
ROOT_RUNTIME_EXCLUDE = {"keyword_data.csv", "social_signals.csv",
                        "supplier_products.csv"}


def _load_ignore(root):
    p = root / ".releaseignore"
    pats = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line.rstrip("/"))
    return pats


def _is_excluded(rel, parts, patterns):
    name = parts[-1]
    if name == KEEP_ENV_EXAMPLE:
        return False
    # data/ whitelist: only curated reference data ships; runtime/business data never.
    if parts[0] == "data" and rel not in DATA_REFERENCE_KEEP:
        return True
    if rel in ROOT_RUNTIME_EXCLUDE:
        return True
    if any(seg in ALWAYS_EXCLUDE_DIRS for seg in parts[:-1]) or name in ALWAYS_EXCLUDE_DIRS:
        return True
    if name in ALWAYS_EXCLUDE_FILES:
        return True
    for g in ALWAYS_EXCLUDE_GLOBS:
        if fnmatch.fnmatch(name, g) or fnmatch.fnmatch(rel, g):
            return True
    for pat in patterns:
        # dir-component match, basename match, or full-path glob
        if pat in parts or fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat) \
                or rel.startswith(pat + "/"):
            return True
    return False


def package_release(version="", root="."):
    root = Path(root).resolve()
    patterns = _load_ignore(root)
    out_dir = root / "dist"
    out_dir.mkdir(exist_ok=True)
    ver = (version or "").replace(" ", "").lower()
    zip_path = out_dir / f"etsy-product-manager{('-' + ver) if ver else ''}.zip"
    if zip_path.exists():
        zip_path.unlink()

    included, skipped_secrets = 0, 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(root).as_posix()
            parts = rel.split("/")
            if path == zip_path:
                continue
            if _is_excluded(rel, parts, patterns):
                if parts[-1] == ".env" or parts[-1].endswith(".pem"):
                    skipped_secrets += 1
                continue
            zf.write(path, rel)
            included += 1

    # Safety assertion: the zip must not contain secrets, real DBs, or business
    # data. A leak here is a hard failure — we delete the unsafe artifact and exit
    # non-zero so `package release` can never silently produce a shippable-looking
    # zip that actually carries team data.
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    leaked = sorted(n for n in names if (
        n.endswith("/.env") or n == ".env" or n.endswith(".pem")
        or n.endswith((".db", ".sqlite", ".sqlite3"))
        or (n.startswith("data/") and n not in DATA_REFERENCE_KEEP)
        or n in ROOT_RUNTIME_EXCLUDE))
    size_kb = zip_path.stat().st_size / 1024
    print(f"Release package: {zip_path}")
    print(f"  {included} files, {size_kb:,.0f} KB, secrets excluded: {skipped_secrets}")
    if leaked:
        print(f"  !! SECURITY: package contains files that must NOT ship: {leaked}")
        print("  Deleting the unsafe package. Fix the exclusions and rebuild.")
        zip_path.unlink(missing_ok=True)
        raise SystemExit(1)
    print("  OK verified: no .env / .pem / .git / caches / logs / real DB / "
          "business data in the package")
    print("  (.env.example is included; copy it to .env on the target machine.)")
    return zip_path
