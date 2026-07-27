"""Design Skill Bridge (V37) — manual ChatGPT bridge for Etsy POD Redesign V8.1.

Replaces the fragile Gemini Design Analyzer. There is NO model API call here: the
staff run the ChatGPT Skill by hand and paste the RESULT_JSON back. 22etsy owns
the workflow, validation, storage, owner approval, and the Launch Kit handoff.
The Skill owns creative reasoning. PUBLISH_AUTOMATION stays false.

Flow:  DRAFT_INPUT → PACK_CREATED → RUN_IN_CHATGPT → RESULT_IMPORTED
       → VALIDATED_CANDIDATE → OWNER_APPROVED → SENT_TO_LAUNCHKIT   (or REJECTED)

Invariants preserved from Etsy POD Redesign V8.1:
  - three normal inputs (main design, HeyEtsy evidence, Etsy URL)
  - three private concepts, one auto-selected; never ask the user V1/V2/V3
  - evidence quality is separate from input completeness
  - missing metrics are n/a, never zero
  - production route comes from the TARGET product, not the reference
  - POD gets no stitch/digitizer language; embroidery stitch counts are estimates
  - no DST/PES/EXP/JEF/VP3 or machine-ready claims before CÓ ĐƠN
  - the Skill returns listing_seeds, NOT a finished Etsy listing (Launch Kit owns that)
"""
import json
import re
import time
from pathlib import Path

SKILL_URL = ("https://chatgpt.com/skills?skill_id="
             "6a65e9caee008191ab382aa6398c0534")
BASE = Path("data/design_skill_bridge")
INDEX = BASE / "index.jsonl"

SCHEMA_VERSION = "0.1"
RESULT_SOURCE = "etsy-pod-redesign-v8.1-chatgpt-skill"

STATES = ("DRAFT_INPUT", "PACK_CREATED", "RUN_IN_CHATGPT", "RESULT_IMPORTED",
          "VALIDATED_CANDIDATE", "OWNER_APPROVED", "SENT_TO_LAUNCHKIT",
          "REJECTED")

MODES = ("POD", "EMBROIDERY", "OTHER", "DIGITAL_EMBROIDERY")
_ROUTE_BY_MODE = {
    "POD": "PRINTED POD",
    "EMBROIDERY": "PHYSICAL EMBROIDERY",
    "OTHER": "OTHER PHYSICAL PRODUCT",
    "DIGITAL_EMBROIDERY": "DIGITAL EMBROIDERY FILE",
}
# machine-file / production-ready tokens that must NOT appear before CÓ ĐƠN
_MACHINE_TOKENS = ("dst", "pes", "exp", "jef", "vp3", "machine-ready",
                   "machine ready", "production-approved", "production approved",
                   "production-ready", "production ready", "digitizer handoff")
DRAFT_STAMP = "DRAFT ONLY — DO NOT PUBLISH"


# ---- ids / io ---------------------------------------------------------------
def new_run_id():
    # app runtime (not a workflow script) so time is available and fine here
    return "BR-" + time.strftime("%Y%m%d-%H%M%S")


def _run_dir(run_id):
    return BASE / re.sub(r"[^A-Za-z0-9._-]", "_", run_id)


def _write(run_id, name, text):
    d = _run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def _append_index(evt):
    BASE.mkdir(parents=True, exist_ok=True)
    with INDEX.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(evt, ensure_ascii=False) + "\n")


def _load_run(run_id):
    d = _run_dir(run_id)
    if not d.is_dir():
        return None
    out = {"run_id": run_id}
    for name in ("input", "result", "validation", "approval", "rejection"):
        p = d / f"{name}.json"
        if p.is_file():
            try:
                out[name] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                out[name] = None
    out["_has_result_file"] = (d / "result.json").is_file()
    out["_has_raw"] = (d / "raw_result.txt").is_file()
    return out


def _sent_run_ids():
    """Run ids that were handed to Launch Kit (recorded only in the index)."""
    ids = set()
    if not INDEX.is_file():
        return ids
    try:
        for line in INDEX.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("state") == "SENT_TO_LAUNCHKIT" and e.get("run_id"):
                ids.add(e["run_id"])
    except OSError:
        pass
    return ids


def _derive_state(run, sent_ids):
    """Single source of truth for a run's management state. WS1.1: a pack with no
    result is WAITING_FOR_RESULT (never REJECTED); a failed import is
    IMPORT_FAILED; an owner rejection is REJECTED."""
    rid = run.get("run_id")
    if rid in sent_ids:
        return "SENT_TO_LAUNCHKIT"
    if (run.get("approval") or {}).get("state") == "OWNER_APPROVED":
        return "OWNER_APPROVED"
    if (run.get("rejection") or {}).get("state") == "REJECTED":
        return "REJECTED"
    val = run.get("validation")
    if val is not None:                       # an import was attempted
        return "VALIDATED_CANDIDATE" if val.get("ok") else "IMPORT_FAILED"
    if run.get("_has_raw") or run.get("_has_result_file"):
        return "IMPORT_FAILED"                # raw came in but no validation record
    return "WAITING_FOR_RESULT"               # pack exists, GPT result not back yet


_MODE_LABEL = {"POD": "POD", "EMBROIDERY": "Embroidery", "OTHER": "Other",
               "DIGITAL_EMBROIDERY": "Digital Embroidery",
               "PHYSICAL EMBROIDERY": "Embroidery", "PRINTED POD": "POD",
               "OTHER PHYSICAL PRODUCT": "Other", "DIGITAL EMBROIDERY FILE":
               "Digital Embroidery"}


def _mode_label(inp, res):
    m = (inp or {}).get("mode")
    if m and m in _MODE_LABEL:
        return _MODE_LABEL[m]
    route = ((res or {}).get("selected_concept") or {}).get("production_route")
    if route and route.upper() in _MODE_LABEL:
        return _MODE_LABEL[route.upper()]
    return "—"


def _human_time(inp, mtime):
    ca = (inp or {}).get("created_at")
    if ca:
        return ca                    # already "YYYY-MM-DD HH:MM"
    if mtime:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
    return "—"


def list_runs(limit=200):
    """Every bridge run with full management metadata (9 columns). State comes
    from _derive_state (WS1.1: pack-with-no-result = WAITING, never REJECTED)."""
    if not BASE.is_dir():
        return []
    sent = _sent_run_ids()
    out = []
    for d in BASE.iterdir():
        if not d.is_dir():
            continue
        run = _load_run(d.name)
        if not run:
            continue
        inp = run.get("input") or {}
        res = run.get("result") or {}
        seeds = res.get("listing_seeds") or {}
        appr = run.get("approval") or {}
        rej = run.get("rejection") or {}
        try:
            mtime = d.stat().st_mtime
        except OSError:
            mtime = 0
        launched = (inp.get("launched_by") or appr.get("owner")
                    or rej.get("owner") or "unknown")
        try:
            prompt = build_prompt(inp) if inp.get("bridge_run_id") else ""
        except Exception:  # noqa: BLE001
            prompt = ""
        out.append({
            "run_id": d.name,
            "state": _derive_state(run, sent),
            "prompt": prompt,
            "keyword": inp.get("keyword") or seeds.get("main_keyword")
            or res.get("keyword") or "",
            "batch": inp.get("batch") or "single-run",
            "created": _human_time(inp, mtime),
            "target": seeds.get("target_product") or inp.get("target_product") or "—",
            "mode": _mode_label(inp, res),
            "launched_by": launched or "unknown",
            "mtime": mtime,
        })
    out.sort(key=lambda r: r["mtime"], reverse=True)
    return out[:limit]


def get_run(run_id):
    """Full run for the review page: {input, result, validation, approval}."""
    return _load_run(run_id)


# ---- 1) pack ----------------------------------------------------------------
def _clean(s, n=400):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def create_pack(form):
    """Build the Skill Pack from the input form. Returns the run dict."""
    mode = (form.get("mode") or "POD").strip().upper()
    if mode not in MODES:
        mode = "POD"
    inp = {
        "schema_version": SCHEMA_VERSION,
        "bridge_run_id": new_run_id(),
        "keyword": _clean(form.get("keyword"), 120),
        "project_id": _clean(form.get("project_id"), 60),
        "title": _clean(form.get("title"), 300),
        "etsy_url": _clean(form.get("etsy_url"), 500),
        "heyetsy_evidence": _clean(form.get("heyetsy"), 2000),
        "target_product": _clean(form.get("target_product"), 120),
        "mode": mode,
        "production_route": _ROUTE_BY_MODE[mode],
        "placement": _clean(form.get("placement"), 120),
        "personalization": _clean(form.get("personalization"), 300),
        "image_ref": _clean(form.get("image_ref"), 300),
        "batch": _clean(form.get("batch"), 60),
        "launched_by": _clean(form.get("launched_by"), 60),
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "state": "PACK_CREATED",
    }
    prompt = build_prompt(inp)
    brief = build_brief(inp)
    _write(inp["bridge_run_id"], "input.json",
           json.dumps(inp, ensure_ascii=False, indent=2))
    _write(inp["bridge_run_id"], "prompt.txt", prompt)
    _write(inp["bridge_run_id"], "brief.md", brief)
    _append_index({"ts": time.time(), "run_id": inp["bridge_run_id"],
                   "state": "PACK_CREATED", "keyword": inp["keyword"]})
    inp["_prompt"] = prompt
    inp["_brief"] = brief
    return inp


def build_prompt(inp):
    """The compact SEED to paste into the ChatGPT skill (V8.2.1 bridge-aware).

    We do NOT re-type the whole workflow here — the skill already holds the
    rules. 22etsy only emits a one-line SEED (so the result can be matched back)
    plus a short output contract. The staff attach the main design image + Etsy
    URL + HeyEtsy DIRECTLY in ChatGPT — no image is uploaded into 22etsy."""
    seed = (f"SEED · run_id={inp['bridge_run_id']} · "
            f"keyword={inp['keyword'] or 'n/a'} · "
            f"target={inp['target_product'] or 'n/a'} · "
            f"mode={inp['mode']} · etsy={inp['etsy_url'] or 'n/a'}")
    lines = [
        seed,
        f"HeyEtsy: {inp['heyetsy_evidence'] or 'n/a (third-party, directional)'}",
        "",
        "Mở ChatGPT Skill (Etsy POD Redesign V8.2.1). Trong 1 tin nhắn: dán dòng "
        "SEED trên, ĐÍNH KÈM ảnh thiết kế chính, dán Etsy URL + HeyEtsy. Gõ Start.",
        "",
        "OUTPUT: kết thúc bằng ĐÚNG 1 khối fenced RESULT_JSON theo hợp đồng V8.1 —"
        f' echo bridge_run_id="{inp["bridge_run_id"]}"; gồm selected_concept'
        " (ip_status GREEN|YELLOW) + listing_seeds + safety. KHÔNG viết title/tag/"
        "mô tả Etsy cuối (đó là việc của Launch Kit). KHÔNG claim DST/PES/máy trước "
        "khi CÓ ĐƠN.",
    ]
    return "\n".join(lines)


def build_brief(inp):
    return (
        f"# DESIGN SKILL BRIEF — {inp['bridge_run_id']}\n\n"
        f"- **Keyword:** {inp['keyword'] or 'n/a'}\n"
        f"- **Target product:** {inp['target_product'] or 'n/a'}\n"
        f"- **Production route:** {inp['production_route']}\n"
        f"- **Placement:** {inp['placement'] or 'n/a'}\n"
        f"- **Personalization:** {inp['personalization'] or 'n/a'}\n"
        f"- **Etsy URL:** {inp['etsy_url'] or 'n/a'}\n"
        f"- **HeyEtsy evidence:** {inp['heyetsy_evidence'] or 'n/a'} "
        "(third-party, directional only)\n\n"
        "Run the prompt in the ChatGPT Skill, then paste the RESULT_JSON back "
        "into 22etsy. The result is a CANDIDATE until the owner approves it. "
        f"{DRAFT_STAMP}.\n"
    )


# ---- 2) import + validate ---------------------------------------------------
def extract_json(text):
    """Safely pull the JSON object out of pasted text. Never eval/exec.
    Prefers a ```RESULT_JSON fenced block, then any fenced block, then the first
    balanced {...} span."""
    if not text:
        return None
    # fenced ```RESULT_JSON ... ``` or ```json ... ```
    for pat in (r"```[ \t]*RESULT_JSON\s*(.*?)```",
                r"```[ \t]*json\s*(.*?)```",
                r"```\s*(.*?)```"):
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except ValueError:
                continue
    # first balanced brace span
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    return None


def _machine_claim_present(obj):
    blob = json.dumps(obj, ensure_ascii=False).lower()
    return any(tok in blob for tok in _MACHINE_TOKENS)


def validate_result(raw_text, inp):
    """Validate a pasted RESULT_JSON against the run's input. Returns a dict:
    {ok, errors[], warnings[], result, state}. Never raises on bad input."""
    errors, warnings = [], []
    obj = extract_json(raw_text)
    if obj is None:
        return {"ok": False, "errors": ["No valid JSON found in the pasted text."],
                "warnings": [], "result": None, "state": "RESULT_IMPORTED"}

    def g(d, k):
        return (d or {}).get(k)

    if g(obj, "schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}.")
    if RESULT_SOURCE not in str(g(obj, "source") or ""):
        errors.append(f"source must be {RESULT_SOURCE}.")
    # bridge_run_id: required only for a 22etsy-INITIATED run (inp present, SEED
    # flow). An EXTENSION-INITIATED result (Etsy page → ChatGPT → send back) has
    # no pre-created run, so a null/absent run id is fine — the importer mints one.
    if inp:
        if not g(obj, "bridge_run_id"):
            errors.append("bridge_run_id is missing.")
        elif g(obj, "bridge_run_id") != inp.get("bridge_run_id"):
            errors.append("bridge_run_id does not match this run — wrong paste.")
    if inp and inp.get("project_id") and g(obj, "project_id_or_opportunity_id") \
            and g(obj, "project_id_or_opportunity_id") != inp["project_id"]:
        errors.append("project/opportunity id mismatch.")

    sc = g(obj, "selected_concept") or {}
    for f in ("name", "buyer", "hook", "production_route", "ip_status"):
        if not g(sc, f):
            errors.append(f"selected_concept.{f} is required.")
    ip = str(g(sc, "ip_status") or "").upper()
    safety_ip = str(g(g(obj, "safety") or {}, "ip_status") or "").upper()
    if "RED" in (ip, safety_ip):
        errors.append("RED IP risk — concept is blocked.")
    if ip == "YELLOW" or safety_ip == "YELLOW":
        warnings.append("YELLOW IP — CONFIRM FIRST / manager review before build.")

    seeds = g(obj, "listing_seeds") or {}
    for f in ("target_product", "selected_concept", "buyer", "main_keyword",
              "evidence_classification"):
        if not g(seeds, f):
            errors.append(f"listing_seeds.{f} is required.")

    # route must match the target mode we packed
    if inp:
        want = inp.get("production_route")
        got = g(sc, "production_route") or g(seeds, "target_product")
        if want and g(sc, "production_route") and want.lower() not in \
                str(g(sc, "production_route")).lower():
            warnings.append(
                f"production_route '{g(sc, 'production_route')}' differs from the "
                f"packed target route '{want}' — confirm the target product.")

    # machine-ready / DST-PES claims before CÓ ĐƠN are rejected
    if _machine_claim_present(obj):
        errors.append("Machine-ready / DST-PES-EXP-JEF-VP3 / production-approved "
                      "claim present — rejected before CÓ ĐƠN.")

    ok = not errors
    return {"ok": ok, "errors": errors, "warnings": warnings, "result": obj,
            "state": "VALIDATED_CANDIDATE" if ok else "RESULT_IMPORTED"}


def import_result(run_id, raw_text):
    inp = (_load_run(run_id) or {}).get("input")
    v = validate_result(raw_text, inp)
    _write(run_id, "raw_result.txt", raw_text or "")
    if v["result"] is not None:
        _write(run_id, "result.json",
               json.dumps(v["result"], ensure_ascii=False, indent=2))
    _write(run_id, "validation.json",
           json.dumps({k: v[k] for k in ("ok", "errors", "warnings", "state")},
                      ensure_ascii=False, indent=2))
    _append_index({"ts": time.time(), "run_id": run_id, "state": v["state"],
                   "ok": v["ok"]})
    return v


def import_pasted(raw):
    """Import a pasted/POSTed RESULT_JSON with no pre-created run: read the
    bridge_run_id out of the JSON, or mint one. Returns (run_id, validation)."""
    obj = extract_json(raw)
    if not isinstance(obj, dict):
        return None, {"ok": False, "errors": ["No RESULT_JSON found in the text."],
                      "warnings": [], "result": None, "state": "RESULT_IMPORTED"}
    run_id = str(obj.get("bridge_run_id") or new_run_id())[:60]
    return run_id, import_result(run_id, raw)


# ---- 3) approve + handoff ---------------------------------------------------
def approve(run_id, owner=""):
    run = _load_run(run_id)
    if not run or not run.get("result"):
        return {"ok": False, "error": "No validated result to approve."}
    val = run.get("validation") or {}
    if not val.get("ok"):
        return {"ok": False, "error": "Result did not pass validation."}
    appr = {"owner": (owner or "")[:60], "at": time.strftime("%Y-%m-%d %H:%M"),
            "state": "OWNER_APPROVED"}
    _write(run_id, "approval.json", json.dumps(appr, ensure_ascii=False, indent=2))
    _append_index({"ts": time.time(), "run_id": run_id, "state": "OWNER_APPROVED",
                   "owner": appr["owner"]})
    return {"ok": True, "approval": appr}


def reject(run_id, owner=""):
    """Owner rejects a candidate. Marks the run rejected (a stored decision, not
    an import failure) so it drops out of the pending queue."""
    run = _load_run(run_id)
    if not run:
        return {"ok": False, "error": "Run not found."}
    rej = {"owner": (owner or "")[:60], "at": time.strftime("%Y-%m-%d %H:%M"),
           "state": "REJECTED"}
    _write(run_id, "rejection.json", json.dumps(rej, ensure_ascii=False, indent=2))
    _append_index({"ts": time.time(), "run_id": run_id, "state": "REJECTED",
                   "owner": rej["owner"]})
    return {"ok": True, "rejection": rej}


def listing_seeds(run_id):
    """The approved listing_seeds packet for Launch Kit (never a finished listing)."""
    run = _load_run(run_id)
    if not run or not run.get("result"):
        return None
    if not (run.get("approval") or {}).get("state") == "OWNER_APPROVED":
        return None
    return (run["result"] or {}).get("listing_seeds")


def send_to_launchkit(run_id):
    seeds = listing_seeds(run_id)
    if seeds is None:
        return {"ok": False, "error": "Not approved yet — cannot hand off."}
    _append_index({"ts": time.time(), "run_id": run_id,
                   "state": "SENT_TO_LAUNCHKIT"})
    return {"ok": True, "seeds": seeds,
            "keyword": (seeds or {}).get("main_keyword", "")}


# ---- HTML render (web.py stays a thin route) --------------------------------
def _esc(s):
    return (str(s if s is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _draft_banner():
    return ('<div style="background:#FDF2F0;border:2px solid #B91C1C;'
            'border-radius:10px;padding:8px 12px;margin:8px 0;color:#B91C1C;'
            f'font-weight:800">🔒 {DRAFT_STAMP}</div>')


# state -> (label, colour, next-action hint)
_STATE_META = {
    "WAITING_FOR_RESULT": ("Waiting for GPT result", "#64748b",
                           "Run in GPT → import RESULT_JSON"),
    "PACK_CREATED": ("Skill Pack ready", "#64748b",
                     "Run in GPT → import RESULT_JSON"),
    "IMPORT_FAILED": ("Import failed", "#B45309", "View error → retry import"),
    "REJECTED": ("Import failed", "#B45309", "Rejected — no action"),
    "VALIDATED_CANDIDATE": ("Candidate ready", "#2563EB", "Owner review & approve"),
    "OWNER_APPROVED": ("Owner approved", "#15803D", "Send to Launch Kit"),
    "SENT_TO_LAUNCHKIT": ("Sent to Launch Kit", "#7C3AED", "Open Launch Kit"),
}


def _state_pill(state):
    label, color, _ = _STATE_META.get(state, (state, "#777", ""))
    return f'<span class="pill" style="background:{color};color:#fff">{label}</span>'


def _btn(label, href, cls="tkbtn"):
    return (f'<a class="{cls}" href="{href}" style="padding:3px 8px;font-size:11.5px;'
            f'margin:1px">{label}</a>')


def _post_btn(label, action, run_id, csrf, cls="tkbtn"):
    return (f'<form method="post" action="{action}" style="display:inline;margin:1px">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<input type="hidden" name="run_id" value="{_esc(run_id)}">'
            f'<button class="{cls}" style="padding:3px 8px;font-size:11.5px">'
            f'{label}</button></form>')


def _row_actions(r, csrf):
    st = r["state"]
    rid = _esc(r["run_id"])
    run_url = f"/design-skill-bridge/run/{rid}"
    if st in ("PACK_CREATED", "WAITING_FOR_RESULT"):
        return (_btn("Open Pack", run_url)
                + f'<button class="tkbtn" style="padding:3px 8px;font-size:11.5px;'
                f'margin:1px" onclick=" dsbCopy(\'p-{rid}\');return false;">Copy Prompt</button>'
                + _btn("Open GPT Skill", SKILL_URL, "tkbtn")
                + _btn("Import RESULT_JSON", run_url + "#import")
                + f'<textarea id="p-{rid}" style="display:none">{_esc(r.get("prompt",""))}</textarea>')
    if st in ("IMPORT_FAILED", "REJECTED"):
        return (_btn("View Error", run_url)
                + _btn("Retry Import", run_url + "#import")
                + _btn("Open Pack", run_url))
    if st == "VALIDATED_CANDIDATE":
        return (_btn("Review", run_url)
                + _post_btn("Approve", "/design-skill-bridge/approve", rid, csrf, "tkbtn primary")
                + _post_btn("Reject", "/design-skill-bridge/reject", rid, csrf)
                + _post_btn("Send to Launch Kit", "/design-skill-bridge/send-to-launchkit", rid, csrf))
    if st == "OWNER_APPROVED":
        return (_btn("View Result", run_url)
                + _post_btn("Send to Launch Kit", "/design-skill-bridge/send-to-launchkit", rid, csrf, "tkbtn primary"))
    if st == "SENT_TO_LAUNCHKIT":
        from urllib.parse import quote_plus as _q
        return (_btn("Open Launch Kit", f"/launch-kit?q={_q(r.get('keyword',''))}", "tkbtn primary")
                + _btn("View Result", run_url))
    return _btn("Open", run_url)


def management_table_html(runs, csrf):
    """The Design Skill Bridge management table: 9 columns + filters + per-state
    actions. Pure render — no network calls. Filtering is client-side JS."""
    states = sorted({r["state"] for r in runs})
    batches = sorted({r["batch"] for r in runs})
    users = sorted({r["launched_by"] for r in runs})

    def opts(vals):
        return "".join(f'<option value="{_esc(v)}">{_esc(v)}</option>' for v in vals)

    filters = (
        '<div class="dsb-filters" style="display:flex;flex-wrap:wrap;gap:8px;'
        'margin:8px 0;font-size:12.5px">'
        '<input id="dsb-q" placeholder="🔎 Search keyword / run ID" '
        'oninput="dsbFilter()" style="flex:1;min-width:180px">'
        f'<select id="dsb-state" onchange="dsbFilter()"><option value="">State: all</option>{opts(states)}</select>'
        f'<select id="dsb-batch" onchange="dsbFilter()"><option value="">Batch: all</option>{opts(batches)}</select>'
        f'<select id="dsb-user" onchange="dsbFilter()"><option value="">Launched by: all</option>{opts(users)}</select>'
        '<input id="dsb-date" type="date" onchange="dsbFilter()" title="Created on/after">'
        '</div>')

    def row(r):
        rid = _esc(r["run_id"])
        _, _, nexthint = _STATE_META.get(r["state"], ("", "", ""))
        return (
            f'<tr data-kw="{_esc((r["keyword"] or "").lower())}" '
            f'data-rid="{rid.lower()}" data-state="{_esc(r["state"])}" '
            f'data-batch="{_esc(r["batch"])}" data-user="{_esc(r["launched_by"])}" '
            f'data-date="{_esc((r["created"] or "")[:10])}">'
            f'<td><a href="/design-skill-bridge/run/{rid}">{rid}</a></td>'
            f'<td>{_esc(r["keyword"]) or "—"}</td>'
            f'<td>{_esc(r["batch"])}</td>'
            f'<td class="note">{_esc(r["created"])}</td>'
            f'<td>{_esc(r["target"])}</td>'
            f'<td>{_esc(r["mode"])}</td>'
            f'<td>{_state_pill(r["state"])}</td>'
            f'<td>{_esc(r["launched_by"])}</td>'
            f'<td class="note">{_esc(nexthint)}</td>'
            f'<td>{_row_actions(r, csrf)}</td></tr>')

    if runs:
        body = "".join(row(r) for r in runs)
    else:
        body = ('<tr><td colspan="10" class="note">Chưa có run nào. Bấm '
                '"➕ Bắt đầu 1 thiết kế" ở trên để tạo prompt.</td></tr>')

    js = (
        '<script>'
        'function dsbCopy(id){var t=document.getElementById(id);if(!t)return;'
        't.style.display="block";t.select();document.execCommand("copy");'
        't.style.display="none";}'
        'function dsbFilter(){'
        'var q=(document.getElementById("dsb-q").value||"").toLowerCase();'
        'var st=document.getElementById("dsb-state").value;'
        'var ba=document.getElementById("dsb-batch").value;'
        'var us=document.getElementById("dsb-user").value;'
        'var dt=document.getElementById("dsb-date").value;'
        'var rows=document.querySelectorAll("#dsb-table tbody tr");'
        'rows.forEach(function(r){'
        'if(!r.dataset.rid)return;'
        'var ok=true;'
        'if(q&&!(r.dataset.kw.indexOf(q)>-1||r.dataset.rid.indexOf(q)>-1))ok=false;'
        'if(st&&r.dataset.state!==st)ok=false;'
        'if(ba&&r.dataset.batch!==ba)ok=false;'
        'if(us&&r.dataset.user!==us)ok=false;'
        'if(dt&&r.dataset.date<dt)ok=false;'
        'r.style.display=ok?"":"none";});}'
        '</script>')

    return (
        '<h2>📋 Bảng quản lý runs (' + str(len(runs)) + ')</h2>'
        + filters +
        '<div style="overflow-x:auto"><table id="dsb-table"><thead><tr>'
        '<th>Run ID</th><th>Keyword</th><th>Batch</th><th>Created</th>'
        '<th>Target</th><th>Mode</th><th>State</th><th>Launched by</th>'
        '<th>Next action</th><th>Actions</th></tr></thead><tbody>'
        + body + '</tbody></table></div>' + js)


def keyword_context(kw):
    """Pull the keyword's market data from the base so the copy block carries
    useful (third-party, directional) numbers. Returns a compact line or ''."""
    kw = (kw or "").strip()
    if not kw:
        return ""
    try:
        import csv
        from pathlib import Path as _P
        p = _P("keyword_data.csv")
        if not p.is_file():
            return ""
        with p.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("keyword") or "").strip().lower() == kw.lower():
                    def n(k):
                        return (r.get(k) or "").strip()
                    parts = []
                    if n("etsy_listings"):
                        parts.append(f"etsy_listings={n('etsy_listings')}")
                    if n("views_24h"):
                        parts.append(f"views_24h={n('views_24h')}")
                    if n("avg_price"):
                        parts.append(f"avg_price=${n('avg_price')}")
                    if n("conversion_rate"):
                        parts.append(f"conversion={n('conversion_rate')}")
                    if n("momentum"):
                        parts.append(f"momentum={n('momentum')}")
                    if n("tm_risk"):
                        parts.append(f"tm_risk={n('tm_risk')}")
                    return " · ".join(parts)
    except Exception:  # noqa: BLE001
        pass
    return ""


def _copy_text(kw, data):
    kw = (kw or "").strip() or "<gõ keyword vào ô trên>"
    return ("ETSY POD REDESIGN V8.2 — new case.\n"
            f"Keyword: {kw}\n"
            f"Market data (third-party, directional): {data or 'n/a'}\n"
            "Đính kèm ngay dưới tin nhắn này: ảnh thiết kế chính + Etsy listing "
            "URL + HeyEtsy. Start.")


def form_html(csrf, prefill_q="", runs=None):
    # V37.1: this page IS the manual Design Workspace. The browser extension is
    # now an evidence exporter only (it has NO "Open in V8.2" / "Send RESULT"
    # buttons anymore). A design is started HERE: enter keyword + evidence → get
    # a prompt → run the ChatGPT Skill by hand → paste RESULT_JSON back below.
    pf = _esc(prefill_q or "")
    return (
        '<article class="md"><h1>🎨 Design Skill Bridge — Xưởng thiết kế</h1>'
        '<p class="tklead">Nơi làm thiết kế <b>thủ công</b> với ChatGPT Skill '
        '(Etsy POD Redesign V8.2). <b>①</b> nhập keyword + bằng chứng → lấy prompt · '
        '<b>②</b> mở GPT Skill, dán prompt + đính <b>ảnh thật</b> + Etsy URL/HeyEtsy, '
        'chạy · <b>③</b> dán <b>RESULT_JSON</b> trả về vào ô Import. Owner duyệt → '
        '<b>listing_seeds</b> sang Launch Kit.</p>'
        # 1) START A DESIGN — manual entry, replaces the old extension "Open in V8.2"
        '<details class="archive" open><summary>➕ Bắt đầu 1 thiết kế</summary>'
        '<form method="post" action="/design-skill-bridge/pack">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        f'<p><label><b>Keyword</b><br><input name="keyword" value="{pf}" '
        'placeholder="vd: nurse embroidery sweatshirt" '
        'style="width:100%;padding:7px;border:1px solid #ddd;border-radius:8px">'
        '</label></p>'
        '<p><label><b>Etsy listing URL</b> (tuỳ chọn)<br><input name="etsy_url" '
        'placeholder="https://www.etsy.com/listing/..." '
        'style="width:100%;padding:7px;border:1px solid #ddd;border-radius:8px">'
        '</label></p>'
        '<p><label><b>HeyEtsy evidence</b> (tuỳ chọn — dán số liệu thật)<br>'
        '<textarea name="heyetsy" rows="2" style="width:100%;padding:7px;border:1px '
        'solid #ddd;border-radius:8px"></textarea></label></p>'
        '<p><label><b>Mode</b> '
        '<select name="mode" style="padding:6px;border:1px solid #ddd;border-radius:8px">'
        '<option value="POD">POD (in / printed)</option>'
        '<option value="EMBROIDERY">Embroidery (thêu vật lý)</option>'
        '<option value="DIGITAL_EMBROIDERY">Digital embroidery file</option>'
        '<option value="OTHER">Other physical product</option>'
        '</select></label></p>'
        '<p><button class="tkbtn primary">Tạo prompt →</button> '
        f'<a class="tkbtn" href="{SKILL_URL}" target="_blank" rel="noopener">'
        'Mở GPT Skill ↗</a></p></form></details>'
        # 2) the management table (dashboard)
        + management_table_html(runs or [], csrf) +
        # 3) manual import (paste the JSON GPT returned)
        '<details class="archive" open><summary>📥 Dán RESULT_JSON từ GPT vào đây'
        '</summary>'
        '<form method="post" action="/design-skill-bridge/import">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<textarea name="raw" rows="6" style="width:100%;font-family:ui-monospace,'
        'monospace;font-size:12px" placeholder="Dán nguyên khối RESULT_JSON GPT trả '
        'về (echo bridge_run_id để khớp đúng run)."></textarea>'
        '<p><button class="tkbtn primary">Import &amp; validate →</button></p></form>'
        '</details>'
        # 4) the clean manual process
        '<details class="archive"><summary>▶ Quy trình thủ công (3 bước)</summary>'
        '<ol class="tklead">'
        '<li><b>Tạo prompt:</b> nhập keyword (+ Etsy URL/HeyEtsy nếu có) ở trên → '
        '<b>Tạo prompt</b>. Trang Pack hiện SEED để copy.</li>'
        '<li><b>Chạy GPT thủ công:</b> mở <b>GPT Skill</b>, dán SEED, <b>đính ảnh '
        'thiết kế thật</b> + Etsy URL + HeyEtsy, gõ Start. Thiếu bằng chứng → '
        '<b>INTAKE BLOCKED</b>, KHÔNG bịa.</li>'
        '<li><b>Nhập kết quả:</b> copy khối <b>RESULT_JSON</b> GPT trả về → dán vào '
        'ô Import ở trên → run hiện trong bảng.</li>'
        '<li>Owner mở run → <b>duyệt</b> → Launch Kit.</li></ol>'
        '<p class="note">Extension nay chỉ để <b>xuất bằng chứng</b> (CSV / JSON / '
        'Send to agent) — không còn mở GPT hay gửi RESULT. Mọi thao tác GPT làm thủ '
        'công tại trang này.</p></details>'
        '<p class="note">🔒 ' + DRAFT_STAMP + ' — mọi kết quả là CANDIDATE cho tới khi '
        'owner duyệt.</p></article>')


def pack_html(inp, csrf):
    rid = inp["bridge_run_id"]
    return (
        '<article class="md"><h1>🎨 Skill Pack — ' + _esc(rid) + '</h1>'
        + _draft_banner() +
        '<ol class="tklead"><li>Copy <b>SEED</b> bên dưới.</li>'
        f'<li><a class="tkbtn primary" href="{SKILL_URL}" target="_blank" '
        'rel="noopener">Open ChatGPT Skill ↗</a> — trong GPT: dán SEED, <b>đính kèm '
        'ảnh thiết kế</b>, dán Etsy URL + HeyEtsy, gõ Start. (Ảnh chỉ upload ở GPT, '
        'KHÔNG upload vào 22etsy.)</li>'
        '<li>Copy khối <b>RESULT_JSON</b> GPT trả về → dán vào ô <b>Import</b> bên '
        'dưới (hoặc ô Import ở trang Bảng quản lý).</li></ol>'
        '<h2>SEED để dán vào ChatGPT (copy)</h2>'
        '<textarea readonly rows="7" style="width:100%;font-family:ui-monospace,monospace;'
        f'font-size:12px">{_esc(inp["_prompt"])}</textarea>'
        '<h2>Import RESULT_JSON</h2>'
        '<form method="post" action="/design-skill-bridge/import">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        f'<input type="hidden" name="run_id" value="{_esc(rid)}">'
        '<textarea name="raw" rows="10" style="width:100%;font-family:ui-monospace,'
        'monospace;font-size:12px" placeholder="Dán toàn bộ câu trả lời hoặc khối '
        'RESULT_JSON vào đây"></textarea>'
        '<p><button class="tkbtn primary">Import &amp; validate →</button></p>'
        '</form></article>')


def result_html(v, run_id, csrf):
    parts = ['<article class="md"><h1>🎨 Bridge result — ' + _esc(run_id) + '</h1>']
    if v["ok"]:
        parts.append('<div style="background:#EDF7F0;border:1px solid #A6DBB9;'
                     'border-radius:10px;padding:8px 12px;color:#15803d;'
                     'font-weight:700">✅ Validated — CANDIDATE. Chờ owner duyệt.</div>')
    else:
        parts.append('<div style="background:#FDF2F0;border:1px solid #F3B7AE;'
                     'border-radius:10px;padding:8px 12px;color:#B91C1C;'
                     'font-weight:700">❌ Rejected — chưa import được.</div>')
    parts.append(_draft_banner())
    if v["errors"]:
        parts.append('<h3>Lỗi</h3><ul>' + "".join(
            f'<li style="color:#B91C1C">{_esc(e)}</li>' for e in v["errors"]) + '</ul>')
    if v["warnings"]:
        parts.append('<h3>Cảnh báo</h3><ul>' + "".join(
            f'<li style="color:#a16207">{_esc(w)}</li>' for w in v["warnings"]) + '</ul>')
    res = v.get("result") or {}
    sc = res.get("selected_concept") or {}
    if sc:
        parts.append(
            '<h3>Selected concept</h3><table>'
            f'<tr><td>Name</td><td><b>{_esc(sc.get("name"))}</b></td></tr>'
            f'<tr><td>Buyer</td><td>{_esc(sc.get("buyer"))}</td></tr>'
            f'<tr><td>Hook</td><td>{_esc(sc.get("hook"))}</td></tr>'
            f'<tr><td>Route</td><td>{_esc(sc.get("production_route"))}</td></tr>'
            f'<tr><td>IP</td><td>{_esc(sc.get("ip_status"))}</td></tr></table>')
    if v["ok"]:
        parts.append(
            _post_btn("✅ Owner approve", "/design-skill-bridge/approve", run_id, csrf, "tkbtn primary")
            + _post_btn("✖ Reject", "/design-skill-bridge/reject", run_id, csrf)
            + _post_btn("🚀 Send to Launch Kit", "/design-skill-bridge/send-to-launchkit", run_id, csrf))
    else:
        # IMPORT_FAILED: offer a retry import box right here (WS1.2 routing)
        parts.append(
            '<h3 id="import">Retry import</h3>'
            '<form method="post" action="/design-skill-bridge/import">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            '<textarea name="raw" rows="6" style="width:100%;font-family:ui-monospace,'
            'monospace;font-size:12px" placeholder="Dán lại RESULT_JSON đã sửa"></textarea>'
            '<p><button class="tkbtn primary">Import &amp; validate →</button></p></form>')
    parts.append('</article>')
    return "".join(parts)


def approved_html(run_id, seeds, csrf):
    kv = "".join(f'<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>'
                 for k, v in (seeds or {}).items()
                 if not isinstance(v, (list, dict)))
    return (
        '<article class="md"><h1>✅ Approved — ' + _esc(run_id) + '</h1>'
        '<p>listing_seeds sẵn sàng cho Launch Kit (KHÔNG phải listing cuối).</p>'
        f'<table>{kv}</table>'
        '<form method="post" action="/design-skill-bridge/send-to-launchkit">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        f'<input type="hidden" name="run_id" value="{_esc(run_id)}">'
        '<button class="tkbtn primary">🚀 Send listing_seeds to Launch Kit →</button>'
        '</form></article>')


def work_html(run, csrf):
    """PACK / WAITING_FOR_RESULT work page — the SEED + Open GPT + Import box.
    WS1.1: a pack with no result opens HERE, never on the rejected result page."""
    inp = run.get("input") or {}
    rid = run["run_id"]
    try:
        prompt = build_prompt(inp) if inp.get("bridge_run_id") else ""
    except Exception:  # noqa: BLE001
        prompt = ""
    return (
        '<article class="md"><h1>🎨 Skill Pack — ' + _esc(rid) + '</h1>'
        '<div style="background:#EEF2FF;border:1px solid #C7D0F5;border-radius:10px;'
        'padding:8px 12px;color:#3730A3;font-weight:700;margin:8px 0">'
        '⏳ Waiting for GPT result — chạy skill rồi import RESULT_JSON.</div>'
        + _draft_banner() +
        '<h2>SEED để dán vào ChatGPT (copy)</h2>'
        '<textarea id="dsb-seed" readonly rows="7" style="width:100%;'
        f'font-family:ui-monospace,monospace;font-size:12px">{_esc(prompt)}</textarea>'
        '<p><button class="tkbtn" onclick="var t=document.getElementById(\'dsb-seed\');'
        't.select();document.execCommand(\'copy\');this.textContent=\'✓ Copied\';return false;">'
        '📋 Copy Prompt</button> '
        f'<a class="tkbtn primary" href="{SKILL_URL}" target="_blank" rel="noopener">'
        'Open GPT Skill ↗</a></p>'
        '<h2 id="import">Import RESULT_JSON</h2>'
        '<form method="post" action="/design-skill-bridge/import">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<textarea name="raw" rows="8" style="width:100%;font-family:ui-monospace,'
        'monospace;font-size:12px" placeholder="Dán RESULT_JSON từ ChatGPT vào đây"></textarea>'
        '<p><button class="tkbtn primary">Import &amp; validate →</button></p></form>'
        '</article>')


def error_html(run, csrf):
    """IMPORT_FAILED / REJECTED page — View Error + Retry Import + Open Pack."""
    rid = run["run_id"]
    val = run.get("validation") or {}
    rej = run.get("rejection") or {}
    if rej.get("state") == "REJECTED":
        head = ('<div style="background:#FDF2F0;border:1px solid #F3B7AE;border-radius:10px;'
                'padding:8px 12px;color:#B91C1C;font-weight:700">✖ Rejected by owner '
                f'({_esc(rej.get("owner") or "owner")}, {_esc(rej.get("at") or "")}).</div>')
    else:
        head = ('<div style="background:#FDF6EC;border:1px solid #F3D9A6;border-radius:10px;'
                'padding:8px 12px;color:#B45309;font-weight:700">⚠ Import failed — '
                'chưa validate được. Sửa RESULT_JSON và thử lại.</div>')
    errs = val.get("errors") or []
    errlist = ('<h3>Lỗi</h3><ul>' + "".join(
        f'<li style="color:#B91C1C">{_esc(e)}</li>' for e in errs) + '</ul>') if errs else ""
    return (
        '<article class="md"><h1>🎨 Bridge run — ' + _esc(rid) + '</h1>'
        + head + errlist + _draft_banner() +
        '<h2 id="import">Retry import</h2>'
        '<form method="post" action="/design-skill-bridge/import">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<textarea name="raw" rows="8" style="width:100%;font-family:ui-monospace,'
        'monospace;font-size:12px" placeholder="Dán lại RESULT_JSON đã sửa"></textarea>'
        '<p><button class="tkbtn primary">Import &amp; validate →</button> '
        f'<a class="tkbtn" href="/design-skill-bridge">← Bảng quản lý</a></p></form>'
        '</article>')


def run_view_html(run, csrf):
    """Open a run by its state (WS1.1 routing): PACK/WAITING → work page (NOT
    rejected); IMPORT_FAILED/REJECTED → error page; candidate → review;
    approved/sent → result + Launch Kit handoff."""
    if not run:
        return '<article class="md"><h1>🎨 Bridge run</h1><p>Run not found.</p></article>'
    rid = run["run_id"]
    state = _derive_state(run, _sent_run_ids())
    res = run.get("result") or {}
    if state in ("OWNER_APPROVED", "SENT_TO_LAUNCHKIT"):
        return approved_html(rid, res.get("listing_seeds") or {}, csrf)
    if state == "VALIDATED_CANDIDATE":
        val = run.get("validation") or {}
        v = {"ok": True, "errors": val.get("errors", []),
             "warnings": val.get("warnings", []), "result": res,
             "state": "VALIDATED_CANDIDATE"}
        return result_html(v, rid, csrf)
    if state in ("IMPORT_FAILED", "REJECTED"):
        return error_html(run, csrf)
    # PACK_CREATED / WAITING_FOR_RESULT — the WS1.1 fix: work page, not rejected
    return work_html(run, csrf)
