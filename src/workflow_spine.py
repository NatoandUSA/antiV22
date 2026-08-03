"""The 12-step Etsy workflow — ONE definition, rendered in every place.

This module exists because the dashboard grew to 104 routes and 39 CLI commands
with no single answer to "what step am I in?". WORKFLOW.md described a 9-step
V30 flow, the home page listed tools alphabetically, and the owner's real
process had 12 steps that matched neither. Staff navigated by memory.

STEPS is the single source of truth. The home page and WORKFLOW.md both render
from it, so the two can never drift again. Adding a route does NOT mean adding a
step: every step has exactly ONE canonical route, and everything else is a
support route (see SUPPORT_ROUTES).

`status()` reports each step from REAL data — honest-nulls, same as the rest of
the app: a step is only "done" when its output actually exists on disk. It never
guesses and never blocks; a broken probe degrades that one step to "unknown".

Nothing here ranks, scores or publishes. It is a map, not an engine.
"""
from pathlib import Path

OWNER, SELLER, DESIGNER, MANAGER, RESEARCHER = (
    "Owner", "Seller", "Designer", "Manager", "Researcher")

# Each step: the question it answers, its ONE canonical route, what it needs,
# what it produces, and who owns it.
STEPS = [
    {
        "n": 1, "key": "feed", "name": "MCP / YTrends keyword feed",
        "route": "/trending", "owner": RESEARCHER,
        "need": "Live YTrends index. Harvest itself runs on the PC: `py main.py harvest`",
        # /trending BROWSES the live index; it cannot harvest. Harvest is
        # `py main.py harvest` on the PC because the VPS IP is blocked from
        # YTrends. Labelling this "Harvest keywords" promised an action the
        # page does not perform.
        "action": ("Browse trending keywords", "/trending"),
        "output": "keyword_data.csv — the master every later step ranks",
        "why": "Raw keyword supply. Nothing downstream can rank what was never pulled.",
    },
    {
        "n": 2, "key": "pinterest", "name": "Pinterest trend signal",
        "route": "/pinterest-trends", "owner": RESEARCHER,
        "need": "Pinterest export or capture for the niche",
        "action": ("Open Pinterest trends", "/pinterest-trends"),
        "output": "Demand corroboration badge on matching keywords",
        "why": "Second, independent read on demand before spending time on a niche.",
    },
    {
        "n": 3, "key": "supplier", "name": "Supplier feasibility",
        "route": "/suppliers", "owner": OWNER,
        "need": "Supplier library (CSV import or saved suppliers)",
        "action": ("Check supplier fit", "/suppliers"),
        "output": "Can we actually make and ship it, at what cost",
        "why": "A keyword you cannot produce profitably is not an opportunity.",
    },
    {
        "n": 4, "key": "rank", "name": "Find good keyword / Rank",
        "route": "/inbox", "owner": RESEARCHER,
        "need": "keyword_data.csv from step 1",
        "action": ("Open Opportunity Inbox", "/inbox"),
        "output": "Final action per keyword: Build now / Confirm first / Watch / Skip",
        "why": "The layered L0–L4 engine decides. Work the top of this list, not a hunch.",
    },
    {
        "n": 5, "key": "pattern", "name": "Pattern Miner on real Etsy results",
        "route": "/pattern-miner", "owner": RESEARCHER,
        "need": "A keyword from step 4",
        "action": ("Mine the pattern", "/pattern-miner"),
        "output": "Why the current winners rank for this keyword",
        "why": "Read the real SERP before designing anything.",
    },
    {
        "n": 6, "key": "evidence", "name": "HeyEtsy evidence",
        "route": "/imports", "owner": RESEARCHER,
        "need": "HeyEtsy Detail + Etsy Reviews export (Evidence Exporter extension)",
        "action": ("Import evidence", "/imports"),
        "output": "Views · sold · favorites · listing age · shop proof, per listing",
        "why": "Third-party estimates, capped at CONFIRM_FIRST — never treated as real Etsy sales.",
    },
    {
        "n": 7, "key": "openers", "name": "Open the best 5 / 10 / 20 listings",
        "route": "/imports", "owner": RESEARCHER,
        "need": "Imported evidence from step 6",
        "action": ("Open winner listings", "/imports"),
        "output": "The actual Etsy listing pages of the winners",
        "why": "Look at the real listings. The evidence card links straight to them.",
    },
    {
        "n": 8, "key": "extract", "name": "Extract the winning pattern",
        "route": "/pattern-miner", "owner": RESEARCHER,
        "need": "Evidence + reviews from step 6",
        "action": ("Read the winning pattern", "/pattern-miner"),
        "output": "Title · tags · photos · price · personalization · reviews · buyer angle",
        "why": "Turn a winner into a repeatable recipe instead of a screenshot.",
    },
    {
        "n": 9, "key": "candidates", "name": "Generate new keyword candidates",
        "route": "/imports", "owner": RESEARCHER,
        "need": "A dissected winner from step 8",
        "action": ("See derived candidates", "/imports"),
        "output": "Keywords from the winner's title, real tags and review language",
        "why": "New keywords grounded in something that already sells, not guesswork.",
    },
    {
        "n": 10, "key": "rerank", "name": "Send candidates to Re-rank / Inbox",
        "route": "/rerank", "owner": RESEARCHER,
        "need": "Candidates from step 9",
        # The SEND is POST /send-to-rerank and its button lives on /imports
        # (and /pattern-miner). GET /rerank only REVIEWS what was already
        # sent, so pointing the action here sent nothing and looked broken.
        "action": ("Pick candidates & send", "/imports"),
        "output": "Candidates in the master tagged winner:<listing_id>, re-ranked",
        "why": ("Closes the loop back to step 4. One click — no retyping. "
                "Capped at CONFIRM_FIRST; the frozen engine still decides."),
    },
    {
        "n": 11, "key": "build", "name": "Build listing / design / photo plan",
        "route": "/launch-kit", "owner": SELLER,
        "need": "A keyword the engine cleared at step 4 or 10",
        "action": ("Open Launch Kit", "/launch-kit"),
        "output": "Title · 13 tags · description · personalization · photo brief",
        "why": "English-only output. Nothing is ever auto-published.",
    },
    {
        "n": 12, "key": "team", "name": "Assign Team Ops + learn Day 3 / Day 7",
        "route": "/team/ops", "owner": MANAGER,
        "need": "A built listing from step 11",
        "action": ("Assign and track", "/team/ops"),
        "output": "Owned tasks, then the Day 3 / Day 7 keep-fix-drop-scale call",
        "why": "Work only counts once someone owns it and the result is measured.",
    },
]

# Everything else. Real tools, but NOT workflow steps — listing them all on the
# home page is what made the dashboard unreadable.
# --------------------------------------------------------------------------
# PHASES — what the team actually navigates by (V37.10).
#
# The 12 steps above are the right CHECKLIST but the wrong NAVIGATION. Several
# are one sitting-down job on one route: 6/7/8 are all "study the winners"
# (/imports -> /pattern-miner), and 9/10 became a SINGLE BUTTON once the
# winner->Inbox loop was closed in V37.7 — keeping them apart invented work that
# no longer exists. Twelve tiles on the page staff open every morning read as a
# project plan, not a day's work.
#
# So: five phases on screen, the twelve steps preserved inside them. Nothing is
# lost — WORKFLOW.md still documents all 12, and every canonical route is
# unchanged.
#
# Guide/instruction text is VIETNAMESE (team-facing). Listing OUTPUT — title,
# 13 tags, description — stays English, because the buyers are American. That
# split is the project's long-standing rule, not a new decision.
PHASES = [
    {"p": 1, "key": "find", "steps": (1, 2, 3),
     "vi": "Tìm & lọc", "en": "Find & filter", "icon": "\U0001F50E",
     "route": "/trending", "owner": RESEARCHER,
     "vi_do": "Gom từ khoá, xem tín hiệu Pinterest, kiểm nhà cung cấp làm được hay không",
     "vi_out": "Danh sách từ khoá thô đã qua cổng lọc",
     "en_do": "Collect keywords, check the Pinterest signal, confirm a supplier can make it",
     "en_out": "Raw keywords that passed the early gates",
     "tools": (("Trending now", "/trending"), ("Pinterest trends", "/pinterest-trends"),
               ("Supplier fit", "/suppliers"))},
    {"p": 2, "key": "rank", "steps": (4,),
     "vi": "Xếp hạng", "en": "Rank", "icon": "\U0001F3C6",
     "route": "/inbox", "owner": RESEARCHER,
     "vi_do": "Để máy chấm điểm và nói rõ nên làm cái nào trước",
     "vi_out": "Hành động cuối cho từng từ khoá: Làm ngay / Kiểm tra / Theo dõi / Bỏ",
     "en_do": "Let the engine score them and say what to work on first",
     "en_out": "Final action per keyword: Build now / Confirm / Watch / Skip",
     "tools": (("Opportunity Inbox", "/inbox"), ("Long-tail lane", "/longtail"),
               ("Build Queue", "/build-queue"))},
    # Phases 3 and 4 both used to route to /imports. /imports is the YTuong
    # Import Center - a drop box. It is where the evidence ARRIVES, not where
    # either job is DONE: phase 3's actual work is reading the winner's recipe
    # (Pattern Miner) and phase 4's is deriving new keywords (Keyword Lab).
    # Sending both phase cards to the same upload page is why the owner said
    # "Learn from winners and New KW all lead to YTuong Import Center".
    # /imports stays reachable as a tool of phase 3 (it IS step 6/7).
    {"p": 3, "key": "learn", "steps": (5, 6, 7, 8),
     "vi": "Học người thắng", "en": "Learn from winners", "icon": "\U0001F52C",
     "route": "/pattern-miner", "owner": RESEARCHER,
     "vi_do": "Nhập bằng chứng HeyEtsy, mở listing top, đọc ra công thức thắng",
     "vi_out": "Tiêu đề · tag · ảnh · giá · cá nhân hoá · góc nhìn người mua",
     "en_do": "Import HeyEtsy evidence, open the top listings, read the winning recipe",
     "en_out": "Title · tags · photos · price · personalization · buyer angle",
     "tools": (("Pattern Miner", "/pattern-miner"), ("Import evidence", "/imports"),
               ("Etsy Spy", "/etsy-spy"))},
    {"p": 4, "key": "newkw", "steps": (9, 10),
     "vi": "Từ khoá mới", "en": "New keywords", "icon": "\U0001F4A1",
     "route": "/keyword-lab", "owner": RESEARCHER,
     "vi_do": "Tool tự sinh từ khoá từ winner — bấm một nút đẩy lại vào Inbox",
     "vi_out": "Từ khoá mới có gắn nguồn winner, được xếp hạng lại",
     "en_do": "The tool derives keywords from a winner — one button sends them back",
     "en_out": "New keywords tagged with their source winner, re-ranked",
     "tools": (("Keyword Lab", "/keyword-lab"), ("Re-rank", "/rerank"),
               ("Winner candidates", "/imports"))},
    {"p": 5, "key": "ship", "steps": (11, 12),
     "vi": "Làm & giao", "en": "Build & ship", "icon": "\U0001F680",
     "route": "/launch-kit", "owner": SELLER,
     "vi_do": "Lên listing + ảnh, giao việc cho team, đo kết quả Ngày 3 / Ngày 7",
     "vi_out": "Listing hoàn chỉnh (tiếng Anh) + việc đã có người nhận",
     "en_do": "Build the listing + photos, assign the team, measure Day 3 / Day 7",
     "en_out": "A finished listing (English) with an owner on every task",
     "tools": (("Launch Kit", "/launch-kit"), ("Photo brief", "/photo-brief"),
               ("Team Ops", "/team/ops"))},
]


def phase_of(key):
    """The PHASE dict for a phase key, or None."""
    return next((p for p in PHASES if p["key"] == key), None)


def neighbours(key):
    """(previous phase, next phase) around a phase key - either may be None.
    Powers the Back / Next buttons so a tool page is never a dead end."""
    ks = [p["key"] for p in PHASES]
    if key not in ks:
        return None, None
    i = ks.index(key)
    return (PHASES[i - 1] if i else None,
            PHASES[i + 1] if i + 1 < len(PHASES) else None)


def steps_of(phase):
    """The STEPS dicts belonging to a phase, in order."""
    return [s for s in STEPS if s["n"] in phase["steps"]]


def phase_status(st=None):
    """Roll the 12 step states up to 5 phase states.

    A phase is ready only when every step in it is ready; it is 'todo' when any
    step is waiting on data. Same honest-nulls rule as status() — we never call a
    phase done because most of it happens to be.
    """
    st = st or status()
    out = {}
    for ph in PHASES:
        kids = [(st.get(s["key"]) or {}) for s in steps_of(ph)]
        states = [k.get("state") for k in kids]
        if states and all(x == "ready" for x in states):
            state = "ready"
        elif "todo" in states:
            state = "todo"
        else:
            state = "unknown"
        first_open = next((s for s in steps_of(ph)
                           if (st.get(s["key"]) or {}).get("state") != "ready"),
                          None)
        out[ph["key"]] = {
            "state": state,
            "done": sum(1 for x in states if x == "ready"),
            "total": len(states),
            "next_step": first_open,
            "detail": ((st.get(first_open["key"]) or {}).get("detail")
                       if first_open else
                       (kids[-1].get("detail") if kids else "")),
        }
    return out


def current_phase(st=None):
    """The phase containing the step the team is actually on."""
    st = st or status()
    n = current_step(st)
    for ph in PHASES:
        if n in ph["steps"]:
            return ph
    return PHASES[-1]


SUPPORT_ROUTES = [
    ("Research + discovery", ["/opportunities", "/gems", "/newest", "/research",
                              "/research-queue", "/longtail", "/keyword-lab",
                              "/should-sell", "/shortlist", "/winners",
                              "/etsy-spy", "/spy", "/kw-history"]),
    ("Evidence + imports", ["/import-file", "/score-import", "/listings",
                            "/shops", "/enrich-leads", "/imports/add"]),
    ("Build + design", ["/draft-listing", "/photo-brief", "/design-skill-bridge",
                        "/design-analyzer", "/grade", "/analyze", "/ads-plan"]),
    ("Team + admin", ["/team", "/team/calendar", "/me/tasks", "/admin/users",
                      "/admin/tasks", "/admin/reviews", "/admin/activity",
                      "/launchpad", "/confirm"]),
    ("Monitoring", ["/alerts", "/trackers", "/profit", "/status", "/daily-brief",
                    "/build-queue", "/feedback"]),
    ("Reference", ["/workflow", "/how-to-use", "/cheatsheet", "/training"]),
]

_UNKNOWN = {"state": "unknown", "detail": "could not read"}


def _p(*parts):
    return Path(*parts)


def _count_json(d):
    p = _p("data", "imports", d)
    return len(list(p.glob("*.json"))) if p.is_dir() else 0


def _master_rows():
    p = _p("keyword_data.csv")
    if not p.is_file():
        return 0
    import csv
    try:
        with p.open(encoding="utf-8-sig") as fh:
            return sum(1 for _ in csv.DictReader(fh))
    except Exception:  # noqa: BLE001
        return 0


def _source_rows(prefix):
    p = _p("keyword_data.csv")
    if not p.is_file():
        return 0
    import csv
    try:
        with p.open(encoding="utf-8-sig") as fh:
            return sum(1 for r in csv.DictReader(fh)
                       if str(r.get("source") or "").startswith(prefix))
    except Exception:  # noqa: BLE001
        return 0


def _ok(detail):
    return {"state": "ready", "detail": detail}


def _todo(detail):
    return {"state": "todo", "detail": detail}


def status():
    """Per-step state from real data: ready / todo / unknown, plus one line of
    evidence. Read-only and best-effort — a failing probe never breaks the page."""
    out = {}
    try:
        n = _master_rows()
        out["feed"] = _ok(f"{n:,} keywords in the master") if n else \
            _todo("no keyword_data.csv — run harvest")
    except Exception:  # noqa: BLE001
        out["feed"] = dict(_UNKNOWN)
    try:
        c = _count_json("pinterest")
        out["pinterest"] = _ok(f"{c} Pinterest capture(s) imported") if c else \
            _todo("no Pinterest capture yet")
    except Exception:  # noqa: BLE001
        out["pinterest"] = dict(_UNKNOWN)
    # Step 3 reads the supplier LIBRARY, not the capture lane: the question is
    # "can we make it?", and a captured supplier page does not answer that. The
    # step is only ready when the library is complete enough to be trusted —
    # which is the same switch that turns feasibility enforcement on.
    try:
        from src import feasibility_gate as fg
        cov = fg.coverage()
        if cov["status"] == fg.COV_NONE:
            out["supplier"] = _todo("no supplier products imported yet")
        elif cov["status"] == fg.COV_COMPLETE:
            out["supplier"] = _ok(f"{cov['products']} product(s) confirmed across "
                                  f"{len(cov['with_products'])} supplier(s)")
        else:
            miss = len(cov["missing_sources"])
            out["supplier"] = _todo(
                f"{cov['products']} product(s) on file, coverage PARTIAL — "
                + (f"{miss} registered supplier(s) have none imported"
                   if miss else
                   f"{cov['products'] - cov['confirmed']} row(s) unconfirmed"))
    except Exception:  # noqa: BLE001
        out["supplier"] = dict(_UNKNOWN)
    try:
        from src import opportunity_inbox as oi
        d = oi.build_inbox(limit=100000, show_archived=True)
        rows = d.get("rows") or []
        act = {}
        for r in rows:
            act[r.get("action")] = act.get(r.get("action"), 0) + 1
        live = act.get("BUILD_NOW", 0) + act.get("CONFIRM_FIRST", 0)
        out["rank"] = _ok(f"{len(rows):,} ranked · {live} actionable "
                          f"(Build {act.get('BUILD_NOW', 0)} / Confirm "
                          f"{act.get('CONFIRM_FIRST', 0)})") if rows else \
            _todo("nothing ranked yet")
    except Exception:  # noqa: BLE001
        out["rank"] = dict(_UNKNOWN)
    # Pattern Miner is an on-demand read of the live SERP: it persists no
    # artifact, so the honest status is "usable once step 4 has ranked something"
    # rather than a fake completion tick.
    out["pattern"] = (_ok("ready — open it on any ranked keyword")
                      if (out.get("rank") or {}).get("state") == "ready"
                      else _todo("rank a keyword first (step 4)"))
    try:
        det = _count_json("etsy_listing_detail")
        rev = _count_json("etsy_listing_reviews")
        out["evidence"] = _ok(f"{det} winner(s) imported · {rev} with reviews") \
            if det else _todo("no HeyEtsy evidence imported")
        out["openers"] = _ok(f"{det} listing link(s) ready to open") if det else \
            _todo("import evidence first (step 6)")
        out["extract"] = _ok(f"{rev} winner(s) with review language read") \
            if rev else _todo("import an Etsy Reviews export")
    except Exception:  # noqa: BLE001
        out["evidence"] = out["openers"] = out["extract"] = dict(_UNKNOWN)
    try:
        from src import feed_evidence_router as fer
        maps = _count_json("listing_keyword_map")
        total = 0
        for p in (_p("data", "imports", "listing_keyword_map").glob("*.json")
                  if _p("data", "imports", "listing_keyword_map").is_dir() else []):
            total += len(fer.candidates_for_rerank(p.stem))
        out["candidates"] = _ok(f"{total} candidate(s) from {maps} winner(s)") \
            if total else _todo("dissect a winner first (step 8)")
        pushes = _count_json("rerank_pushes")
        pushed = _source_rows("winner:")
        out["rerank"] = _ok(f"{pushed} keyword(s) pushed in {pushes} batch(es)") \
            if pushed else _todo(f"{total} candidate(s) waiting to be sent")
    except Exception:  # noqa: BLE001
        out["candidates"] = out["rerank"] = dict(_UNKNOWN)
    try:
        runs = _p("reports", "latest")
        out["build"] = _ok("latest listing pack available") \
            if (runs / "listing_pack.md").is_file() else \
            _todo("no listing pack built yet")
    except Exception:  # noqa: BLE001
        out["build"] = dict(_UNKNOWN)
    try:
        from src import team_ops as t
        n = len(t.list_tasks() or []) if hasattr(t, "list_tasks") else 0
        out["team"] = _ok(f"{n} task(s) on the board") if n else \
            _todo("no tasks assigned yet")
    except Exception:  # noqa: BLE001
        out["team"] = dict(_UNKNOWN)
    for s in STEPS:
        out.setdefault(s["key"], dict(_UNKNOWN))
    return out


def current_step(st=None):
    """The first step that is not ready — i.e. "you are here"."""
    st = st or status()
    for s in STEPS:
        if (st.get(s["key"]) or {}).get("state") != "ready":
            return s["n"]
    return STEPS[-1]["n"]
