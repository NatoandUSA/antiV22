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
    for name in ("input", "result", "validation", "approval"):
        p = d / f"{name}.json"
        if p.is_file():
            try:
                out[name] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                out[name] = None
    return out


def list_runs(limit=30):
    """Recent bridge runs with their state — powers the 'pending candidates'
    list so the owner can find results the extension imported straight from
    ChatGPT (which never opened a 22etsy page)."""
    if not BASE.is_dir():
        return []
    out = []
    for d in BASE.iterdir():
        if not d.is_dir():
            continue
        run = _load_run(d.name)
        if not run:
            continue
        val = run.get("validation") or {}
        appr = run.get("approval") or {}
        res = run.get("result") or {}
        inp = run.get("input") or {}
        seeds = res.get("listing_seeds") or {}
        state = ("OWNER_APPROVED" if appr.get("state") == "OWNER_APPROVED"
                 else "VALIDATED_CANDIDATE" if val.get("ok")
                 else "RESULT_IMPORTED" if res
                 else "PACK_CREATED")
        try:
            mtime = d.stat().st_mtime
        except OSError:
            mtime = 0
        out.append({
            "run_id": d.name, "state": state,
            "keyword": inp.get("keyword") or seeds.get("main_keyword")
            or res.get("keyword") or "",
            "target": seeds.get("target_product") or inp.get("target_product") or "",
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


def _state_pill(state):
    color = {"OWNER_APPROVED": "#15803d", "VALIDATED_CANDIDATE": "#2563eb",
             "RESULT_IMPORTED": "#a16207", "PACK_CREATED": "#777"}.get(state, "#777")
    label = {"OWNER_APPROVED": "✅ approved", "VALIDATED_CANDIDATE": "🔵 candidate",
             "RESULT_IMPORTED": "⚠ needs fix", "PACK_CREATED": "… pack"}.get(state, state)
    return f'<span class="pill" style="background:{color};color:#fff">{label}</span>'


def pending_html(runs):
    if not runs:
        return ""
    rows = "".join(
        f'<tr><td><a href="/design-skill-bridge/run/{_esc(r["run_id"])}">'
        f'{_esc(r["run_id"])}</a></td>'
        f'<td>{_esc(r["keyword"]) or "—"}</td>'
        f'<td>{_esc(r["target"]) or "—"}</td>'
        f'<td>{_state_pill(r["state"])}</td></tr>' for r in runs)
    return ('<details class="archive" open><summary>📥 Runs &amp; pending '
            'candidates (' + str(len(runs)) + ')</summary>'
            '<p class="note">Kết quả gửi từ ChatGPT (qua extension) xuất hiện ở '
            'đây. Bấm run để xem + owner duyệt.</p>'
            '<table><tr><th>Run</th><th>Keyword</th><th>Target</th><th>State</th>'
            f'</tr>{rows}</table></details>')


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
    q = (prefill_q or "").strip()
    copytext = _copy_text(q, keyword_context(q))
    return (
        '<article class="md"><h1>🎨 Design Skill Bridge</h1>'
        '<p class="tklead">1 keyword sẵn data → mở <b>ChatGPT Skill V8.2</b> → '
        'import <b>RESULT_JSON</b> về → owner duyệt → <b>listing_seeds</b> sang '
        'Launch Kit. Không gọi API. Skill trả listing_seeds; Launch Kit tạo listing cuối.</p>'
        # 1) the dashboard
        + pending_html(runs or []) +
        # 2) ready keyword + data to copy
        '<h2>1 · Keyword sẵn để copy</h2>'
        '<form method="get" action="/design-skill-bridge" style="margin:0 0 8px">'
        f'<input name="q" value="{_esc(q)}" placeholder="Gõ keyword rồi Enter…" '
        'style="width:66%"> <button class="tkbtn">Chuẩn bị data</button></form>'
        f'<textarea id="dsb-copy" readonly rows="4" style="width:100%;'
        f'font-family:ui-monospace,monospace;font-size:12.5px">{_esc(copytext)}</textarea>'
        '<p><button class="tkbtn" onclick="var t=document.getElementById(\'dsb-copy\');'
        't.select();document.execCommand(\'copy\');this.textContent=\'✓ Đã copy\';'
        'return false;">📋 Copy</button></p>'
        # 3) open the skill
        '<h2>2 · Mở ChatGPT Skill</h2>'
        f'<p><a class="tkbtn primary" href="{SKILL_URL}" target="_blank" '
        'rel="noopener">Open ChatGPT Skill V8.2 ↗</a> '
        '<span class="note">Trong GPT: dán nội dung vừa copy + đính kèm ảnh thiết kế '
        '+ Etsy URL + HeyEtsy → Start.</span></p>'
        # 4) import the JSON back
        '<h2>3 · Import JSON từ GPT</h2>'
        '<form method="post" action="/design-skill-bridge/import">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<textarea name="raw" rows="6" style="width:100%;font-family:ui-monospace,'
        'monospace;font-size:12px" placeholder="Dán RESULT_JSON từ ChatGPT vào đây '
        '(hoặc dùng nút &quot;↑ Send RESULT to agent&quot; của extension trên trang '
        'ChatGPT — tự về đây)."></textarea>'
        '<p><button class="tkbtn primary">Import &amp; validate →</button></p></form>'
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
        '<li>Gửi khối <b>RESULT_JSON</b> về đây — nút "Send result to agent" của '
        'extension, hoặc dán vào ô Import bên dưới.</li></ol>'
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
            '<form method="post" action="/design-skill-bridge/approve" '
            'style="display:inline">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<input type="hidden" name="run_id" value="{_esc(run_id)}">'
            '<button class="tkbtn primary" title="Owner only">✅ Owner approve →</button>'
            '</form>')
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


def run_view_html(run, csrf):
    """Render a stored run for the review page (owner opens a pending candidate)."""
    if not run:
        return '<article class="md"><h1>🎨 Bridge run</h1><p>Run not found.</p></article>'
    res = run.get("result") or {}
    if (run.get("approval") or {}).get("state") == "OWNER_APPROVED":
        return approved_html(run["run_id"], res.get("listing_seeds") or {}, csrf)
    val = run.get("validation") or {}
    v = {"ok": bool(val.get("ok")), "errors": val.get("errors", []),
         "warnings": val.get("warnings", []), "result": res,
         "state": val.get("state", "RESULT_IMPORTED")}
    return result_html(v, run["run_id"], csrf)
