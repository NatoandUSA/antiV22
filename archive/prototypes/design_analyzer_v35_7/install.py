#!/usr/bin/env python3
"""One-shot installer for the Design Analyzer (V35.7) into 22etsy-agent.

Why a script instead of hand-editing: it patches your CURRENT src/web.py in
place (preserving any local changes) and is IDEMPOTENT - safe to run twice.

Usage (from anywhere):
    py install.py "D:\\Claude\\22etsy-agent"
or, if you copy this folder into the repo and run from the repo root:
    cd D:\\Claude\\22etsy-agent
    py design_analyzer_v35_7\\install.py

It will:
  1. copy src/design_analyzer.py + tests/test_design_analyzer.py into the repo
  2. add the /design-analyzer route to src/web.py (before the /trending route)
  3. add the "Design Analyzer" home tool-card
  4. bump src/version.py to 35.7
  5. add GEMINI_API_KEY to .env.example (documentation only)
Then compile-checks web.py so a bad patch is caught immediately.
"""
import re
import shutil
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent

ROUTE_MARK = '@app.route("/design-analyzer"'
ROUTE_BLOCK = '''
    @app.route("/design-analyzer", methods=["GET", "POST"])
    @login_required
    def design_analyzer():
        # V35.7: image -> Gemini vision analysis (trademark read + safe original
        # redesign prompts + Etsy SEO pack), layered with our own trademark.check
        # + product_fit.producibility gates. Draft-only; 'recreate' is analysis-only.
        from src import design_analyzer as da
        if request.method == "POST":
            _check_csrf()
            f = request.files.get("image")
            img = f.read() if f else b""
            title = _no_tags((request.form.get("title") or "").strip())[:300]
            link = (request.form.get("link") or "").strip()[:500]
            mode = "embroidery" if request.form.get("emb") == "1" else None
            try:
                res = da.analyze(img, title=title, link=link, mode=mode)
            except (SystemExit, Exception) as exc:  # noqa: BLE001
                return _tool_error("Design Analyzer", exc)
            return page("Design Analyzer", _bar() + da.result_html(res, _csrf()))
        q, _m = _kw_mode()
        return page("Design Analyzer", _bar() + da.form_html(_csrf(), prefill_q=q or ""))

'''

REDESIGN_MARK = '"/design-analyzer/redesign"'
REDESIGN_BLOCK = '''
    @app.route("/design-analyzer/redesign", methods=["POST"])
    @login_required
    def design_analyzer_redesign():
        # V35.9: generate the SAFE redesign as an image (Nano Banana), gated on the
        # IP verdict. HIGH -> refused; MEDIUM -> needs the 'verified' tick.
        _check_csrf()
        from src import design_analyzer as da
        prompt = (request.form.get("prompt") or "").strip()[:4000]
        ip_level = (request.form.get("ip_level") or "LOW").strip()
        confirmed = request.form.get("confirmed") == "1"
        try:
            res = da.generate_redesign_gated(prompt, ip_level=ip_level,
                                             confirmed=confirmed)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return _tool_error("Redesign", exc)
        return page("Design Analyzer - Redesign",
                    _bar() + da.redesign_result_html(res, prompt))

'''

GUIDE_MARK = '@app.route("/training")'
GUIDE_BLOCK = '''
    @app.route("/training")
    @login_required
    def training():
        # V35.9: serve the Vietnamese staff walkthrough as a full page.
        from pathlib import Path as _P
        from flask import Response as _Resp
        for _p in (_P("staff_guide_vn.html"), _P("docs/staff_guide_vn.html")):
            if _p.is_file():
                return _Resp(_p.read_text(encoding="utf-8"), mimetype="text/html")
        return page("Huong dan", _bar() + '<article class="md"><p>Chua cai tai '
                    'lieu (staff_guide_vn.html).</p></article>')

'''
GUIDE_NAV_MARK = 'href="/training"'
GUIDE_NAV_ADD = (
    "\n            '<a class=\"toolcard\" href=\"/training\"><b>\U0001F4DA "
    "Hướng dẫn nhân viên</b>'\n            '<span>Quy "
    "trình 9 bước + công cụ mới (Tiếng "
    "Việt)</span></a>'"
)

GUIDE_NAV_ANCHOR = "safe original redesign prompt, Etsy SEO pack</span></a>'"

NAV_MARK = 'href="/design-analyzer"'
NAV_ANCHOR = "<span>SEO / Trust / Image scores + publish gate</span></a>'"
NAV_ADD = (
    "\n            '<a class=\"toolcard\" href=\"/design-analyzer\"><b>\U0001F3A8 "
    "Design Analyzer</b>'\n            '<span>Image → trademark read, safe "
    "original redesign prompt, Etsy SEO pack</span></a>'"
)


def _resolve_repo():
    if len(sys.argv) > 1:
        repo = Path(sys.argv[1]).expanduser().resolve()
    else:
        repo = Path.cwd().resolve()
    if not (repo / "src" / "web.py").is_file():
        sys.exit(f"ERROR: {repo} does not look like the repo (no src/web.py).\n"
                 f"Run:  py install.py \"D:\\Claude\\22etsy-agent\"")
    return repo


def _copy_sources(repo):
    for rel in ("src/design_analyzer.py", "tests/test_design_analyzer.py"):
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PKG / rel, dst)
        print(f"  copied {rel}")
    guide = PKG / "staff_guide_vn.html"
    if guide.is_file():
        shutil.copyfile(guide, repo / "staff_guide_vn.html")
        print("  copied staff_guide_vn.html")


def _patch_web(repo):
    p = repo / "src" / "web.py"
    txt = p.read_text(encoding="utf-8")
    changed = False

    # 1) route
    if ROUTE_MARK in txt:
        print("  route already present - skipped")
    else:
        anchor = '    @app.route("/trending")'
        if anchor in txt:
            txt = txt.replace(anchor, ROUTE_BLOCK.lstrip("\n") + "\n" + anchor, 1)
            changed = True
            print("  route inserted before /trending")
        else:
            m = re.search(r'return redirect\(f"/launch-kit\?q=\{_qp2\(q\)\}'
                          r'&mode=\{mode\}&sent=1"\)\n', txt)
            if m:
                txt = txt[:m.end()] + ROUTE_BLOCK + txt[m.end():]
                changed = True
                print("  route inserted after launch_kit_submit")
            else:
                sys.exit("ERROR: could not find an anchor for the route.\n"
                         "Send Claude the region around @app.route(\"/trending\").")

    # 1b) redesign route (image generation, gated on verdict)
    if REDESIGN_MARK in txt:
        print("  redesign route already present - skipped")
    else:
        anchor = '    @app.route("/trending")'
        if anchor in txt:
            txt = txt.replace(anchor, REDESIGN_BLOCK.lstrip("\n") + "\n" + anchor, 1)
            changed = True
            print("  redesign route inserted before /trending")
        else:
            print("  WARNING: could not anchor the redesign route (non-fatal); the "
                  "analyzer still works, just no image-generation button.")

    # 1c) training page route (staff walkthrough)
    if GUIDE_MARK in txt:
        print("  training route already present - skipped")
    else:
        anchor = '    @app.route("/trending")'
        if anchor in txt:
            txt = txt.replace(anchor, GUIDE_BLOCK.lstrip("\n") + "\n" + anchor, 1)
            changed = True
            print("  training route inserted before /trending")
        else:
            print("  WARNING: could not anchor the training route (non-fatal).")

    # 2) nav card
    if NAV_MARK in txt:
        print("  nav card already present - skipped")
    elif NAV_ANCHOR in txt:
        txt = txt.replace(NAV_ANCHOR, NAV_ANCHOR + NAV_ADD, 1)
        changed = True
        print("  nav card inserted after Listing Analyzer")
    else:
        print("  WARNING: Listing Analyzer nav anchor not found - the route still "
              "works at /design-analyzer, just no home card. (Non-fatal.)")

    # 2b) training nav card (added after the Design Analyzer card)
    if GUIDE_NAV_MARK in txt:
        print("  training nav card already present - skipped")
    elif GUIDE_NAV_ANCHOR in txt:
        txt = txt.replace(GUIDE_NAV_ANCHOR, GUIDE_NAV_ANCHOR + GUIDE_NAV_ADD, 1)
        changed = True
        print("  training nav card inserted")
    else:
        print("  training nav card anchor not found - /training still works "
              "(non-fatal)")

    if changed:
        p.write_text(txt, encoding="utf-8")


def _bump_version(repo):
    p = repo / "src" / "version.py"
    if not p.is_file():
        print("  version.py not found - skipped")
        return
    txt = p.read_text(encoding="utf-8")
    new = re.sub(r'VERSION\s*=\s*"[^"]*"', 'VERSION = "35.9"', txt)
    if new != txt:
        p.write_text(new, encoding="utf-8")
        print("  version bumped to 35.9")
    else:
        print("  version already 35.9 (or pattern not found)")


def _env_example(repo):
    p = repo / ".env.example"
    line = "GEMINI_API_KEY="
    if not p.is_file():
        print("  .env.example not found - skipped")
        return
    txt = p.read_text(encoding="utf-8")
    if "GEMINI_API_KEY" in txt:
        print("  .env.example already documents GEMINI_API_KEY - skipped")
        return
    add = ("\n# Google AI Studio key for the Design Analyzer (Gemini vision). "
           "Free tier is fine.\nGEMINI_API_KEY=\n"
           "# optional model override (default gemini-2.5-flash)\n"
           "GEMINI_MODEL=gemini-2.5-flash\n")
    p.write_text(txt.rstrip("\n") + "\n" + add, encoding="utf-8")
    print("  GEMINI_API_KEY documented in .env.example")


def _compile_check(repo):
    import py_compile
    for rel in ("src/web.py", "src/design_analyzer.py"):
        try:
            py_compile.compile(str(repo / rel), doraise=True)
            print(f"  OK compiles: {rel}")
        except py_compile.PyCompileError as e:
            sys.exit(f"ERROR: {rel} failed to compile after patch:\n{e}")


def main():
    repo = _resolve_repo()
    print(f"Installing Design Analyzer V35.7 into: {repo}\n")
    _copy_sources(repo)
    _patch_web(repo)
    _bump_version(repo)
    _env_example(repo)
    _compile_check(repo)
    print("\nDONE. Next steps:")
    print("  1) Put your Google AI Studio key in the SERVER .env (on the VPS):")
    print("       nano ~/etsy-agent/.env    ->    GEMINI_API_KEY=AIza...")
    print("  2) Local check:  py -m pytest -q")
    print("  3) Commit + push, then deploy on the VPS (see README.md).")


if __name__ == "__main__":
    main()
