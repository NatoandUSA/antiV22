"""Design Analyzer (V36 add-on) — one Gemini vision call turns a design image
into a structured, commercial analysis: what it depicts, its meaning, a
trademark read, print-ready prompts (recreate = analysis-only, plus a SAFE
original redesign in standard + embroidery form), and an Etsy SEO pack (title /
13 tags / description) in English + Vietnamese.

The model's IP and stitch reads are LAYERED with the project's OWN deterministic
gates (trademark.check + product_fit.producibility), so the verdict never rests
on the model alone — same honest, gate-first philosophy as the ranking engine.

Cost / keys: uses the Gemini API (Google AI Studio key in env GEMINI_API_KEY);
Gemini 2.5 Flash on the free tier is effectively $0 at this volume. If the key
is missing or the call fails, analyze() returns an honest error dict and NEVER
raises — the web app must not break because a secondary tool is down.

Guardrails (unchanged project rules): PUBLISH_AUTOMATION stays false; original
designs only — the "recreate" prompt is for ANALYSIS ONLY, never to reproduce
and sell someone else's design.
"""
import base64
import json
import os
import re

# Default is the rolling alias so it does NOT 404 when Google rotates model
# versions (gemini-2.5-flash was retired for new keys mid-2026). Override any
# time with GEMINI_MODEL in .env.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
# Tried in order when the chosen model is unavailable on this key (404 / retired),
# so the tool keeps working across Google's model churn without a code change.
_FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.5-flash",
                    "gemini-3.5-flash-lite", "gemini-2.5-flash-lite",
                    "gemini-2.0-flash"]
_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent")


def _is_model_unavailable(msg):
    """True if the error is 'this model is unavailable/retired' (worth trying
    another model) rather than an auth/quota/network error (do not retry)."""
    m = (msg or "").lower()
    return ("404" in m or "not found" in m or "no longer available" in m
            or "is not supported" in m or "not available" in m)

SYSTEM = (
    "You are an expert print-on-demand (POD) product analyst, IP/trademark risk "
    "assessor, and Etsy SEO specialist working for a seller who makes embroidery "
    "and print-on-demand products. You are precise, commercial, and honest about "
    "legal risk. You answer in strict JSON only — no markdown, no commentary "
    "outside the JSON."
)

# The exact JSON contract (kept identical to the seller's existing analyzer so
# the output is familiar). Gemini is additionally forced to application/json.
_USER_TMPL = """Analyze the attached design image. {ctx}

Return ONLY a JSON object with EXACTLY these keys:
{{
 "content_en": "1-3 sentences: what the design literally depicts.",
 "content_vi": "Vietnamese translation of content_en.",
 "meaning_en": "1-3 sentences: the meaning / cultural or brand references, any text phrases and what they refer to.",
 "meaning_vi": "Vietnamese translation of meaning_en.",
 "trademark_en": "2-4 sentences: trademark & copyright assessment. Name any protected brand, artist, character, logo, slogan or IP owner you can identify. If clean, say why it is low risk.",
 "trademark_vi": "Vietnamese translation of trademark_en.",
 "ip_owner": "Likely IP owner if any, else empty string.",
 "risk_level": "exactly one of: Low, Medium, High",
 "risk_reason_en": "one short sentence justifying the risk_level.",
 "risk_reason_vi": "Vietnamese translation of risk_reason_en.",
 "subject": "the main subject in 1-4 words, e.g. 'dachshund dog'",
 "style": "the visual style in 1-3 words, e.g. 'vintage line-art'",
 "extracted_text": ["verbatim text phrases visible in the design, [] if none"],
 "prompt_original": "A single detailed AI image prompt (English) that would RECREATE this design faithfully as a centered, print-ready PNG, 5000x5000px, 1:1, transparent or solid background, generous margins. FOR ANALYSIS ONLY.",
 "prompt_redesign_standard": "A single detailed AI image prompt (English) for a NEW, ORIGINAL redesign in the SAME niche/vibe that is SAFE — remove or replace any trademarked names, real people, logos, album titles and protected slogans with generic, non-infringing equivalents. Commercially appealing. Print-ready PNG, 5000x5000px, 1:1, generous margins.",
 "prompt_redesign_embroidery": "Same safe redesign but for MACHINE EMBROIDERY: bold simple shapes, max 4-6 solid thread colors, thick readable lettering, no gradients, no photorealism, no tiny details, clear outlines, high contrast.",
 "seo_title": "An Etsy-optimized, TRADEMARK-SAFE product title (max 140 chars) for the safe redesign — front-load the strongest keywords, no protected brand/artist names.",
 "seo_tags": ["exactly 13 Etsy tags", "each <= 20 chars", "multi-word long-tail", "no trademarked terms"],
 "seo_description": "A 2-3 sentence Etsy listing description for the safe redesign: benefit-driven, keyword-rich, mentions it's a great gift, no trademarked terms."
}}

Rules: seo_tags MUST be exactly 13 strings, each <= 20 characters. Never invent a fake IP owner. If the design is generic/original, set risk_level "Low" and ip_owner "". Output valid JSON only."""


# --------------------------------------------------------------------------
# Gemini call (isolated so tests can monkeypatch it)
# --------------------------------------------------------------------------

def _gemini(image_b64, mime, prompt, model, key, timeout=45):
    """POST to Gemini generateContent. Returns the model's text (JSON string).
    Raises on network/HTTP error (caller catches)."""
    import requests  # lazy: a missing dep must not break module import
    url = _ENDPOINT.format(model=model)
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": image_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2400,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(url, params={"key": key}, json=body, timeout=timeout)
    if r.status_code != 200:
        # surface Gemini's own error message when present
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            msg = ""
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {msg or r.text[:200]}")
    data = r.json()
    cands = data.get("candidates") or []
    if not cands:
        pf = (data.get("promptFeedback") or {}).get("blockReason")
        raise RuntimeError(f"Gemini returned no candidates"
                           + (f" (blocked: {pf})" if pf else ""))
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def _parse_json(t):
    if not t:
        return None
    s = t.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        pass
    a, b = s.find("{"), s.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(s[a:b + 1])
        except Exception:  # noqa: BLE001
            return None
    return None


def _sniff_mime(b):
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


# --------------------------------------------------------------------------
# Deterministic gates (project's own logic, layered over the model)
# --------------------------------------------------------------------------

_RISK_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_RANK_RISK = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}


def _norm_model_risk(v):
    v = (v or "").strip().lower()
    if v.startswith("high"):
        return "HIGH"
    if v.startswith("med"):
        return "MEDIUM"
    return "LOW"


def _gates(parsed, title, mode):
    """Layer our OWN trademark + stitch checks over the model's read and return
    the combined, more-cautious verdict. Never trusts the model alone on IP."""
    from src.trademark import check as tm_check
    from src import product_fit as pf

    # ---- IP: most cautious of (model risk) and (our trademark heuristic) ----
    # Check each field SEPARATELY (not one concatenated string) so a brand in any
    # single field is caught, without the combined length tripping the long-slogan
    # CAUTION heuristic that is only meant for individual tags.
    model_risk = _norm_model_risk(parsed.get("risk_level"))
    ip_owner = (parsed.get("ip_owner") or "").strip()
    fields = [title or ""] + list(parsed.get("extracted_text") or []) + [
        parsed.get("subject") or "", ip_owner]
    our_tm, our_reason = "OK", ""
    for fld in fields:
        fld = (fld or "").strip()
        if not fld:
            continue
        risk, reason = tm_check(fld)
        if _RISK_RANK[{"HIGH": "HIGH", "CAUTION": "MEDIUM", "OK": "LOW"}[risk]] > \
           _RISK_RANK[{"HIGH": "HIGH", "CAUTION": "MEDIUM", "OK": "LOW"}[our_tm]]:
            our_tm, our_reason = risk, reason
    our_risk = {"HIGH": "HIGH", "CAUTION": "MEDIUM", "OK": "LOW"}[our_tm]
    # a named non-empty owner is at least MEDIUM even if the words look clean
    if ip_owner and ip_owner.lower() not in ("", "none", "n/a"):
        model_risk = _RANK_RISK[max(_RISK_RANK[model_risk], 1)]
    ip_level = _RANK_RISK[max(_RISK_RANK[model_risk], _RISK_RANK[our_risk])]
    ip_sources = []
    if our_tm != "OK":
        ip_sources.append(f"blocklist: {our_reason or our_tm}")
    if _norm_model_risk(parsed.get("risk_level")) != "LOW":
        ip_sources.append("vision model flagged a brand/IP reference")
    if ip_owner:
        ip_sources.append(f"named owner: {ip_owner}")

    # ---- Stitch safety: our producibility read on the concept text ----
    concept = " ".join([parsed.get("subject") or "", parsed.get("style") or "",
                        parsed.get("content_en") or ""]).strip()
    prod = pf.producibility(concept, "embroidery")  # force the stitch read
    stitch_ok = prod.get("label") in ("STITCH_SAFE", "STITCH_OK", "PRINTS_FINE")

    # ---- Safe-to-produce gate (Phase 1: no demand data yet) ----
    if ip_level == "HIGH":
        verdict, why = "SKIP", "IP risk HIGH — do not produce or list"
    elif mode == "embroidery" and not stitch_ok:
        verdict, why = "REDESIGN", ("embroidery stitch risk — simplify before "
                                    "producing (" + "; ".join(prod.get("reasons", [])) + ")")
    elif ip_level == "MEDIUM":
        verdict, why = "VERIFY", "verify the trademark at tmsearch.uspto.gov before producing"
    else:
        verdict, why = "OK_TO_DESIGN", "safe to produce as an ORIGINAL design"

    return {
        "ip_level": ip_level,
        "ip_sources": ip_sources,
        "stitch": {"label": prod.get("label"), "score": prod.get("score"),
                   "reasons": prod.get("reasons", [])},
        "produce_verdict": verdict,
        "produce_reason": why,
        "model_risk": _norm_model_risk(parsed.get("risk_level")),
        "blocklist_risk": our_tm,
    }


# --------------------------------------------------------------------------
# Public entry
# --------------------------------------------------------------------------

MAX_IMAGE_BYTES = 7 * 1024 * 1024


def analyze(image_bytes, title="", link="", mode=None, model=None, key=None):
    """Analyze one design image. Returns a dict; on failure {"ok": False,
    "error": ...}. Never raises."""
    # Explicit key="" means "no key" (deterministic for callers/tests); key=None
    # falls back to the environment (how the web route calls it).
    if key is None:
        key = os.getenv("GEMINI_API_KEY", "")
    key = (key or "").strip()
    if not key:
        return {"ok": False, "error": "GEMINI_API_KEY is not set — add your "
                "Google AI Studio key to the server .env and restart."}
    if not image_bytes:
        return {"ok": False, "error": "No image was uploaded."}
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return {"ok": False, "error": "Image is too large (max 7 MB). Resize and retry."}
    ctx = ""
    if title:
        ctx += f'The seller\'s original listing title is: "{title}". '
    if link:
        ctx += f"Source link: {link}."
    prompt = _USER_TMPL.format(ctx=ctx.strip())
    b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = _sniff_mime(image_bytes)
    # Try the chosen model, then fall back through current models if it's retired.
    tried, last_err = [], ""
    for mdl in [model or DEFAULT_MODEL] + _FALLBACK_MODELS:
        if mdl in tried:
            continue
        tried.append(mdl)
        try:
            raw = _gemini(b64, mime, prompt, mdl, key)
            break
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            if _is_model_unavailable(last_err):
                continue                      # model retired -> try the next one
            return {"ok": False, "error": f"Gemini call failed: {exc}"}
    else:
        return {"ok": False, "error": "No available Gemini model — set GEMINI_MODEL "
                "in .env to a current model (e.g. gemini-3.5-flash). Last error: "
                + last_err}
    parsed = _parse_json(raw)
    if not isinstance(parsed, dict):
        return {"ok": False, "error": "The model did not return valid JSON.",
                "raw": (raw or "")[:800]}
    # normalise seo_tags to a clean 13-list
    tags = parsed.get("seo_tags")
    if isinstance(tags, list):
        parsed["seo_tags"] = [str(t).strip()[:20] for t in tags if str(t).strip()][:13]
    else:
        parsed["seo_tags"] = []
    parsed["gates"] = _gates(parsed, title, mode)
    parsed["ok"] = True
    return parsed


# --------------------------------------------------------------------------
# Server-side rendering (keeps web.py thin)
# --------------------------------------------------------------------------

def _esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace(
        "<", "&lt;").replace(">", "&gt;")


_VERDICT_META = {
    "OK_TO_DESIGN": ("#1F8A4C", "✅ OK to design (original)"),
    "VERIFY": ("#E5850B", "🔍 Verify trademark first"),
    "REDESIGN": ("#8B5CF6", "🧵 Redesign for stitch"),
    "SKIP": ("#B91C1C", "🚫 Skip — IP risk"),
}
_IP_COLOR = {"LOW": "#1F8A4C", "MEDIUM": "#E5850B", "HIGH": "#B91C1C"}


def form_html(csrf_token, prefill_q=""):
    return f"""<article class="md"><h1>🎨 Design Analyzer</h1>
<p class="muted">Upload a design image → trademark read (model + your own blocklist),
a SAFE original redesign prompt (standard + embroidery), and an Etsy SEO pack.
Runs on Gemini (free tier). Draft only — original designs, no auto-publish.</p>
<form method="POST" action="/design-analyzer" enctype="multipart/form-data" style="max-width:560px">
  <input type="hidden" name="_csrf" value="{_esc(csrf_token)}">
  <p><label><b>Design image</b> (PNG/JPG, ≤7 MB)<br>
    <input type="file" name="image" accept="image/*" required></label></p>
  <p><label><b>Original title</b> (optional)<br>
    <textarea name="title" rows="2" style="width:100%" placeholder="e.g. dachshund flower shirt">{_esc(prefill_q)}</textarea></label></p>
  <p><label><b>Etsy / product link</b> (optional)<br>
    <input type="text" name="link" style="width:100%" placeholder="https://www.etsy.com/listing/..."></label></p>
  <p><label><input type="checkbox" name="emb" value="1"> <b>Embroidery-safe mode</b>
    (bold shapes, ≤6 colors, no gradients/tiny detail)</label></p>
  <p><button type="submit" class="btn">Analyze design</button></p>
</form></article>"""


def result_html(r, csrf_token):
    if not r or not r.get("ok"):
        err = _esc((r or {}).get("error", "Unknown error"))
        raw = (r or {}).get("raw")
        extra = f'<pre style="white-space:pre-wrap;font-size:12px">{_esc(raw)}</pre>' if raw else ""
        return (f'<article class="md"><h1>🎨 Design Analyzer</h1>'
                f'<div style="background:#FDF2F0;border:1px solid #F3B7AE;'
                f'border-radius:10px;padding:12px 14px;color:#7f1d1d">⚠ {err}</div>'
                f'{extra}</article>' + form_html(csrf_token))
    g = r.get("gates", {})
    vcol, vlabel = _VERDICT_META.get(g.get("produce_verdict"), ("#64748b", g.get("produce_verdict", "")))
    ipc = _IP_COLOR.get(g.get("ip_level"), "#64748b")
    tags = r.get("seo_tags", [])
    emb_prompt = r.get("prompt_redesign_embroidery") or r.get("prompt_redesign_standard") or ""
    std_prompt = r.get("prompt_redesign_standard") or ""

    def box(title, body):
        return (f'<div style="border:1px solid #EBE4DA;border-radius:12px;'
                f'padding:12px 14px;margin:10px 0"><div style="font-weight:800;'
                f'font-size:12px;text-transform:uppercase;letter-spacing:.4px;'
                f'color:#D24C0C;margin-bottom:6px">{title}</div>{body}</div>')

    def pre(text):
        return (f'<pre style="white-space:pre-wrap;word-break:break-word;'
                f'background:#faf7f2;border:1px solid #EBE4DA;border-radius:8px;'
                f'padding:10px;font-size:12.5px;margin:4px 0">{_esc(text)}</pre>')

    ip_src = "".join(f"<li>{_esc(s)}</li>" for s in g.get("ip_sources", [])) or "<li>no blocklist or model IP flags</li>"
    st = g.get("stitch", {})
    tagchips = "".join(
        f'<span style="display:inline-block;background:#EEF2FF;color:#1d4ed8;'
        f'border:1px solid #d5e2fb;border-radius:99px;padding:3px 9px;'
        f'font-size:12px;margin:2px">{_esc(t)}</span>' for t in tags)

    html = f"""<article class="md"><h1>🎨 Design Analyzer</h1>
<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">
  <span style="background:{vcol};color:#fff;font-weight:800;border-radius:99px;padding:6px 14px">{_esc(vlabel)}</span>
  <span style="background:{ipc};color:#fff;font-weight:800;border-radius:99px;padding:6px 14px">IP: {_esc(g.get('ip_level'))}</span>
  <span style="background:#2B2926;color:#fff;font-weight:700;border-radius:99px;padding:6px 14px">Stitch: {_esc(st.get('label'))} ({_esc(st.get('score'))})</span>
</div>
<p class="muted" style="margin-top:0">{_esc(g.get('produce_reason'))}</p>

{box("Trademark / IP (model + your blocklist)",
     f'<p style="margin:0 0 6px"><b>Model:</b> {_esc(r.get("trademark_en"))}</p>'
     f'<p style="margin:0 0 6px"><b>Owner:</b> {_esc(r.get("ip_owner") or "—")}</p>'
     f'<ul style="margin:6px 0 0">{ip_src}</ul>')}

{box("Content &amp; meaning (EN / VI)",
     f'<p style="margin:0 0 4px"><b>Content:</b> {_esc(r.get("content_en"))}</p>'
     f'<p style="margin:0 0 8px;color:#555">{_esc(r.get("content_vi"))}</p>'
     f'<p style="margin:0 0 4px"><b>Meaning:</b> {_esc(r.get("meaning_en"))}</p>'
     f'<p style="margin:0;color:#555">{_esc(r.get("meaning_vi"))}</p>')}

{box("✅ SAFE original redesign prompt — Standard", pre(std_prompt))}
{box("🧵 SAFE original redesign prompt — Embroidery", pre(emb_prompt))}
{box("Recreate prompt — ⚠ ANALYSIS ONLY (do NOT produce/sell)", pre(r.get("prompt_original")))}

{box("Etsy SEO pack (safe redesign)",
     f'<p style="margin:0 0 4px"><b>Title</b> ({len(r.get("seo_title") or "")}/140)</p>'
     f'<div style="background:#faf7f2;border:1px solid #EBE4DA;border-radius:8px;padding:8px 10px;margin-bottom:8px">{_esc(r.get("seo_title"))}</div>'
     f'<p style="margin:0 0 4px"><b>13 tags</b></p><div>{tagchips}</div>'
     f'<p style="margin:8px 0 4px"><b>Description</b></p>'
     f'<div style="background:#faf7f2;border:1px solid #EBE4DA;border-radius:8px;padding:8px 10px">{_esc(r.get("seo_description"))}</div>')}

<p style="margin-top:14px"><a href="/design-analyzer">← Analyze another design</a></p>
</article>"""
    return html
