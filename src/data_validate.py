"""Data + schema validation — `py main.py validate data|run|suppliers|feedback`.

Separate from src/validators.py (which validates listing titles/tags). This checks
STORED DATA. No hard dependency: built-in checks always run; if the optional
`jsonschema` package is installed AND src/schemas/<name>.schema.json exists, it
also validates records against that JSON Schema. Catches the things that hurt:
invalid JSON, missing CSV headers/fields, <13 tags, an invalid status, a missing
supplier cost, a missing source timestamp, and the critical safety invariant —
PUBLISH_READY=true must never coexist with failed checks.
"""
import csv
import json
from pathlib import Path

SCHEMA_DIR = Path("src/schemas")
VALID_DECISIONS = {"NEW", "KEEP", "NEEDS_MORE_DATA", "CHANGE_MAIN_PHOTO",
                   "CHANGE_TITLE", "CHANGE_TAGS", "RAISE_PRICE", "LOWER_PRICE",
                   "MAKE_VARIANTS", "KILL_LISTING", "SCALE_PRODUCT_LINE"}


def _load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _schema_check(name, records, issues):
    """Optional JSON-Schema validation (only if jsonschema is installed)."""
    try:
        from jsonschema import Draft7Validator
    except Exception:  # noqa: BLE001
        return
    sp = SCHEMA_DIR / f"{name}.schema.json"
    if not sp.exists():
        return
    schema = _load_json(sp)
    item = schema.get("items", schema)
    v = Draft7Validator(item)
    for i, rec in enumerate(records or []):
        for err in v.iter_errors(rec):
            issues.append(f"{name}[{i}] schema: {err.message}")


def validate_feedback(issues):
    p = Path("data/performance/listing_feedback.json")
    if not p.exists():
        return
    try:
        rows = _load_json(p)
    except Exception as e:  # noqa: BLE001
        issues.append(f"feedback json invalid: {e}")
        return
    for i, r in enumerate(rows):
        if not r.get("listing_url") and not r.get("keyword"):
            issues.append(f"feedback[{i}] missing listing_url/keyword")
        if not (r.get("created_at") or r.get("added_at")):
            issues.append(f"feedback[{i}] missing source timestamp")
        dec = r.get("decision") or r.get("day7_action")
        if dec and dec not in VALID_DECISIONS:
            issues.append(f"feedback[{i}] invalid decision '{dec}'")
    _schema_check("feedback", rows, issues)


def validate_suppliers(issues):
    p = Path("data/suppliers/supplier_products.csv")
    if not p.exists():
        return
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        required = {"supplier_id", "product_name", "production_mode",
                    "base_cost", "supplier_status"}
        if required - headers:
            issues.append(f"suppliers CSV missing headers: {sorted(required - headers)}")
            return
        for i, r in enumerate(reader):
            if r.get("supplier_status") == "SUPPLIER_CONFIRMED":
                if not (r.get("base_cost") or "").strip():
                    issues.append(f"suppliers[{i}] CONFIRMED but base_cost empty")
                if not (r.get("product_url") or "").strip():
                    issues.append(f"suppliers[{i}] CONFIRMED but product_url empty")


REQUIRED_RUN_FILES = ["workspace.json", "publish_gate.json", "listing_draft.json"]


def validate_run(path, issues):
    d = Path(path)
    if not d.is_dir():
        issues.append(f"run folder not found: {path}")
        return
    for fn in REQUIRED_RUN_FILES:
        fp = d / fn
        if not fp.exists():
            issues.append(f"run {d.name}: missing {fn}")
            continue
        try:
            data = _load_json(fp)
        except Exception as e:  # noqa: BLE001
            issues.append(f"run {d.name}: {fn} invalid JSON ({e})")
            continue
        if fn == "publish_gate.json":
            if bool(data.get("publish_ready")) and (data.get("failed_checks") or []):
                issues.append(f"run {d.name}: PUBLISH_READY=true WITH failed checks "
                              "(UNSAFE — must never happen)")
        if fn == "listing_draft.json":
            tags = data.get("tags") or []
            if tags and len(tags) != 13:
                issues.append(f"run {d.name}: {len(tags)} tags (need exactly 13)")


def validate_all_runs(issues):
    base = Path("reports/latest/runs")
    if base.exists():
        for d in sorted(base.iterdir()):
            if d.is_dir():
                validate_run(d, issues)


def _validate_json_store(name, path, issues):
    p = Path(path)
    if not p.exists():
        return
    try:
        _load_json(p)
    except Exception as e:  # noqa: BLE001
        issues.append(f"{name}: invalid JSON ({e})")


def run(target="data", path=None):
    issues = []
    target = (target or "data").lower()
    if target == "feedback":
        validate_feedback(issues)
    elif target == "suppliers":
        validate_suppliers(issues)
    elif target == "run":
        if not path:
            print("validate run needs --path reports/latest/runs/<folder>")
            return False
        validate_run(path, issues)
    else:
        validate_feedback(issues)
        validate_suppliers(issues)
        for n, pth in (("profit", "data/performance/profit_center.json"),
                       ("alerts", "data/alerts/alerts.json"),
                       ("keyword_tracker", "data/tracking/keyword_tracker.json"),
                       ("market_tracker", "data/tracking/market_tracker.json")):
            _validate_json_store(n, pth, issues)
        validate_all_runs(issues)

    print(f"VALIDATE {target}: "
          + ("PASS — no issues" if not issues else f"{len(issues)} issue(s)"))
    for msg in issues:
        print(f"  ✗ {msg}")
    return not issues
