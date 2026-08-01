"""Dashboard route tests via the Flask test client (offline, no live MCP).

Covers the manual dashboard checklist that doesn't need network: pages render,
auth is enforced, forms save, the Archive card is gone, and Spy/Run without a
keyword give the graceful prompt. Live Spy/workspace (which hit the MCP) are
exercised by the audit run + selftest, not here, so this suite stays fast +
deterministic.
"""
import pytest

from src import web


def _ensure_owner():
    from src import auth
    auth.appdb.init_db()
    if not auth.get_user_by_email("owner@test.local"):
        auth.create_user("owner@test.local", "Test123!", "Test Owner", "OWNER", "test")
    return auth.get_user_by_email("owner@test.local")


@pytest.fixture
def client():
    u = _ensure_owner()
    app = web.build_app("", "secret")
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["uid"] = u["user_id"]
        s["_csrf"] = "t"          # seed the CSRF token like a browser's first GET
    # A real browser submits the injected CSRF token on every POST; mirror that
    # so the blanket CSRF guard doesn't 403 legitimate test POSTs.
    _orig_post = c.post

    def _post(*a, **k):
        d = k.get("data")
        if d is None:
            k["data"] = {"_csrf": "t"}
        elif isinstance(d, dict) and "_csrf" not in d:
            d["_csrf"] = "t"
        return _orig_post(*a, **k)

    c.post = _post
    return c


def test_auth_required():
    app = web.build_app("", "secret")
    anon = app.test_client()
    r = anon.get("/", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert "/login" in r.headers.get("Location", "")


def test_home_is_clean(client):
    body = client.get("/").get_data(as_text=True)
    assert "Archive — reports" not in body           # Archive card removed
    assert 'href="/cheatsheet"' in body              # Cheat Sheet present
    for card in ("Spy + Reverse Engine", "Launchpad", "Profit Center",
                 "Listing Analyzer", "Market &amp; keyword tracker"):
        assert card in body


@pytest.mark.parametrize("route", [
    "/cheatsheet", "/how-to-use", "/workflow", "/suppliers", "/feedback", "/profit", "/grade",
    "/alerts", "/launchpad", "/trackers", "/research", "/shops", "/listings",
    "/team", "/team/calendar", "/team/calendar?view=overdue",
    "/team/calendar?view=month", "/me/tasks",
    "/team/feedback", "/imports", "/research-queue", "/confirm",
])
def test_pages_render(client, route):
    assert client.get(route).status_code == 200


def test_longtail_lane_renders_and_is_linked(client):
    """The lane is a view over the frozen engine — it must render offline and be
    reachable from the top bar (it's a daily-use page, not a hidden route)."""
    body = client.get("/longtail").get_data(as_text=True)
    assert "Long-tail lane" in body
    assert "Pull more long-tails" in body           # the supply action is present
    assert 'href="/longtail"' in client.get("/").get_data(as_text=True)
    assert client.get("/longtail?words=4").status_code == 200
    assert client.get("/longtail?q=dad+shirt").status_code == 200


def test_longtail_lane_does_not_change_the_ranking(client):
    """Hard guarantee: opening the lane must leave every verdict/action alone."""
    from src import longtail as lt, opportunity_inbox as oi
    before = [(r["keyword"], r["verdict"], r["action"], r["score"])
              for r in oi.build_inbox(None, limit=100000)["rows"]]
    lt.shortlist()
    after = [(r["keyword"], r["verdict"], r["action"], r["score"])
             for r in oi.build_inbox(None, limit=100000)["rows"]]
    assert before == after


def test_team_command_center(client):
    body = client.get("/team").get_data(as_text=True)
    assert "Team Command Center" in body
    assert "Test Owner" in body          # signed-in user shown
    assert "OWNER" in body               # role shown
    for section in ("My open", "Today control board", "Process pipeline",
                    "Team activity"):
        assert section in body, f"missing section: {section}"
    # every one of the 10 module destinations is still linked (no route removed)
    for href in ("/me/tasks", "/research-queue", "/imports", "/team/calendar",
                 "/admin/tasks", "/admin/reviews", "/admin/activity",
                 "/admin/users", "/team/feedback", "/me"):
        assert f'href="{href}"' in body, f"missing module link: {href}"
    # the command-center alias serves the same page
    assert client.get("/team/command-center").status_code == 200


def test_team_subpages_polish(client):
    # My Tasks renders (grouped view)
    assert "My Tasks" in client.get("/me/tasks").get_data(as_text=True)
    # Activity Log now exposes a filter form + CSV export, and the params work
    al = client.get("/admin/activity").get_data(as_text=True)
    assert "All users" in al and "All events" in al
    assert client.get("/admin/activity?type=SPY_SEARCH").status_code == 200
    assert client.get("/admin/activity?kw=nurse").status_code == 200
    assert client.get("/admin/activity/export").status_code == 200
    # Review Queue still renders
    assert client.get("/admin/reviews").status_code == 200


def test_security_xss_neutralized_and_headers(client):
    from src import saved
    # /grade result must not echo an executable tag from the title/keyword
    g = client.post("/grade", data={
        "title": "<img src=x onerror=alert(1)>", "tags": "a, b",
        "description": "a reasonably long description here",
        "keyword": "<svg onload=alert(1)>"}).get_data(as_text=True)
    assert "<img" not in g and "<svg" not in g
    # a javascript: shop URL must not become a live href
    saved.add_shop({"shop_name": "xss test shop",
                    "shop_url": "javascript:alert(document.cookie)", "category": "",
                    "niche": "", "status": "watching", "notes": "", "scores": {}})
    assert 'href="javascript:' not in client.get("/shops").get_data(as_text=True)
    # defense-in-depth headers present on every response
    h = client.get("/")
    assert h.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in h.headers


def test_task_datetime_due_and_edit(client):
    from src import tasks as tk
    # create with a date+time due value from the picker
    client.post("/admin/tasks/create", data={
        "title": "Research pouches", "assigned_to": "", "task_type": "KEYWORD_RESEARCH",
        "priority": "HIGH", "related_keyword": "summer pouch",
        "due_date": "2026-08-01T14:30"})
    t = [x for x in tk.list_tasks() if x["title"] == "Research pouches"][0]
    assert t["due_date"] == "2026-08-01T14:30"          # hour preserved
    # edit page renders + has the native picker
    ep = client.get(f"/admin/tasks/{t['task_id']}/edit")
    assert ep.status_code == 200 and 'type="datetime-local"' in ep.get_data(as_text=True)
    # save edits: title, priority, status, keyword, due
    r = client.post(f"/admin/tasks/{t['task_id']}/edit", data={
        "title": "Research pouches v2", "assigned_to": "",
        "task_type": "KEYWORD_RESEARCH", "priority": "URGENT",
        "related_keyword": "travel pouch", "status": "IN_PROGRESS",
        "due_date": "2026-08-02T09:00"})
    assert r.status_code in (301, 302)
    t2 = tk.get_task(t["task_id"])
    assert (t2["title"] == "Research pouches v2" and t2["priority"] == "URGENT"
            and t2["status"] == "IN_PROGRESS"
            and t2["related_keyword"] == "travel pouch"
            and t2["due_date"] == "2026-08-02T09:00")


def test_ytuong_import_creates_candidate_no_autopublish(client):
    from src import research as rs
    before = len(rs.list_candidates())
    r = client.post("/imports/add", data={"kind": "product_idea", "source": "YTuong",
                    "value": "monogram tote bag", "mode": "", "note": "trending"})
    assert r.status_code in (301, 302)                       # -> research queue
    after = rs.list_candidates()
    assert len(after) == before + 1
    c = after[0]
    assert c["status"] == "NEW_IDEA" and c["fit_status"] and c["product_mode"] in ("pod", "embroidery")
    # the queue shows it with deep links + build workspace, and never a publish button
    q = client.get("/research-queue").get_data(as_text=True)
    assert "monogram tote bag" in q and "Open in YTuong" in q and "Build workspace" in q
    assert "Publish now" not in q and ">Publish<" not in q     # no auto-publish path


def test_product_mode_preserved_import_to_workspace(client, monkeypatch):
    """#3: product mode survives Import -> Research Queue -> Build Workspace link
    -> /run -> workspace opts (supplier_type)."""
    from src import research as rs, workspace
    # 'sunset tote bag' would auto-guess POD; importing as embroidery must WIN.
    client.post("/imports/add", data={"kind": "product_idea", "source": "YTuong",
                "value": "sunset tote bag", "mode": "embroidery", "note": ""})
    cand = [c for c in rs.list_candidates() if c["title"] == "sunset tote bag"][0]
    assert cand["product_mode"] == "embroidery"           # explicit mode beats guess
    # the Research Queue 'Build workspace' link carries the mode
    q = client.get("/research-queue").get_data(as_text=True)
    assert "/run?q=sunset tote bag&mode=embroidery" in q
    # and /run maps ?mode= into the workspace opts (supplier_type) — no live data needed
    seen = {}
    monkeypatch.setattr(workspace, "build_workspace",
                        lambda kw, opts: seen.update(opts) or "<div>ws</div>")
    client.get("/run?q=sunset+tote+bag&mode=embroidery")
    assert seen.get("supplier_type") == "embroidery"


def test_home_daily_advanced_tiers(client):
    """Scope Reduction: home leads with Build Queue + Trend Feeds/Execution Helpers + an Advanced <details>;
    every surface still links (hidden != removed)."""
    b = client.get("/").get_data(as_text=True)
    # V36+: the "Daily — your everyday loop" card was removed; home now leads
    # with Build Queue + the split Trend Feeds / Execution Helpers shelves.
    assert "Build Queue" in b
    assert "Trend Feeds" in b and "Execution Helpers" in b
    assert "advtools" in b and "Advanced tools" in b
    for href in ("/build-queue", "/design-skill-bridge", "/imports",
                 "/research-queue"):
        assert href in b, href                       # promoted daily surfaces
    for href in ("/trending", "/opportunities", "/spy", "/grade", "/launchpad",
                 "/profit", "/trackers", "/shops", "/listings", "/feedback"):
        assert href in b, href                       # demoted, still live


def test_confirm_and_assign_flow(client):
    """Confirm & Assign: verdict per keyword + one-click assign in Embroidery mode."""
    from src import auth, research as rs
    owner = auth.get_user_by_email("owner@test.local")
    # verdicts
    assert "✅ GO" in client.get("/confirm?q=monogram tote bag").get_data(as_text=True)
    assert "⛔ NO" in client.get("/confirm?q=fathers day pokemon").get_data(as_text=True)
    assert "⚠" in client.get("/confirm?q=funny raccoon").get_data(as_text=True)  # CHECK
    # Google cross-check is opt-in (a button), not on the first load
    assert "google=1" in client.get("/confirm?q=monogram tote bag").get_data(as_text=True)
    # assign creates an embroidery candidate assigned to the staff member
    before = len(rs.list_candidates())
    r = client.post("/confirm/assign", data={"q": "monogram tote bag",
                    "assigned_to": str(owner["user_id"])})
    assert r.status_code in (301, 302)
    after = rs.list_candidates()
    assert len(after) == before + 1
    cand = [x for x in after if x["title"] == "monogram tote bag"][0]
    assert cand["product_mode"] == "embroidery" and cand["assigned_to"] == owner["user_id"]


def test_assign_defaults_to_24h_deadline(client):
    """Auto-assigned tasks get a 24h default deadline (editable later);
    unassigned tasks stay open-ended."""
    from datetime import datetime
    from src import auth, tasks as tk
    owner = auth.get_user_by_email("owner@test.local")
    client.post("/confirm/assign", data={"q": "24h deadline kw",
                "assigned_to": str(owner["user_id"])})
    t = [x for x in tk.list_tasks() if x["related_keyword"] == "24h deadline kw"][0]
    assert t["due_date"], "assigned task should get a default deadline"
    hrs = (datetime.strptime(t["due_date"], "%Y-%m-%dT%H:%M")
           - datetime.now()).total_seconds() / 3600
    assert 23 < hrs < 25, hrs
    assert not tk.create_task(title="no assignee", task_type="SUPPLIER_CHECK")["due_date"]


def test_confirm_cross_check_three_sources(client, monkeypatch):
    """Demand cross-check shows Google + Pinterest + X + Google 'rising' suggestions,
    and is opt-in (a button) so the page stays fast."""
    from src import crosscheck
    assert "Run cross-check" in client.get(
        "/confirm?q=monogram tote bag").get_data(as_text=True)
    monkeypatch.setattr(crosscheck, "confirm", lambda kw: {
        "google": {"status": "ok", "direction": "rising", "momentum_pct": 42,
                   "rising": ["monogram pouch", "bridesmaid tote"]},
        "pinterest": None, "x": None})
    b = client.get("/confirm?q=monogram tote bag&google=1").get_data(as_text=True)
    assert "Google Trends" in b and "Pinterest" in b and "X / Twitter" in b
    assert "Also rising" in b and "monogram pouch" in b   # clickable suggestions


def test_shortlist_page_and_verdicts(client, monkeypatch):
    """Shortlist ranks opportunities by the real score, shows verdicts + one-click
    Confirm, and degrades gracefully when the cache is cold."""
    from src import interactive as iv
    assert iv._verdict_from(80, "OK") == "GO"
    assert iv._verdict_from(65, "OK") == "CONDITIONAL"
    assert iv._verdict_from(50, "OK") == "WATCH"
    assert iv._verdict_from(90, "HIGH") == "SKIP"          # trademark hard-block
    assert iv._verdict_from(None, "OK") == "WATCH"         # missing score, not invented
    monkeypatch.setattr(iv, "shortlist", lambda mode="embroidery", limit=10: [
        {"keyword": "monogram tote bag", "product_type": "embroidery", "score": 82,
         "momentum": 40, "competition": "low", "conversion": 0.03, "price": 24,
         "tm": "OK", "verdict": "GO", "reason": "opportunity 82/100, low competition",
         "next_action": "Confirm & Assign -> supplier check"}])
    b = client.get("/shortlist").get_data(as_text=True)
    assert "monogram tote bag" in b and "PURSUE NOW" in b   # verdict label
    assert "Top 5 today" in b and "Why it matters" in b     # buckets + reason
    assert "/confirm?q=monogram tote bag" in b              # one-click into the loop

    def _boom(*a, **k):
        raise SystemExit("MCP cold")
    monkeypatch.setattr(iv, "shortlist", _boom)
    assert client.get("/shortlist").status_code == 200     # cold cache != crash


def test_import_url_without_keyword_shows_manual_message(client):
    """#8: an undecodable URL must not create a junk candidate — the user is asked
    to enter the keyword/title manually."""
    from src import research as rs
    before = len(rs.list_candidates())
    r = client.post("/imports/add", data={"kind": "product_idea", "source": "Etsy",
                    "value": "https://www.etsy.com/listing/123456789", "mode": ""},
                    follow_redirects=True)
    assert "Could not extract a keyword" in r.get_data(as_text=True)
    assert len(rs.list_candidates()) == before        # no junk candidate created


def test_task_work_report_flow(client):
    from src import tasks as tk, auth
    owner = auth.get_user_by_email("owner@test.local")   # the client is this OWNER
    t = tk.create_task(title="Report test", assigned_to_user_id=owner["user_id"],
                       task_type="KEYWORD_RESEARCH")
    # Save report WITHOUT changing status (the Save-report button -> __KEEP__)
    client.post("/me/tasks/status", data={"task_id": str(t["task_id"]),
                "status": "__KEEP__", "work_report": "found 3 gaps"})
    t1 = tk.get_task(t["task_id"])
    assert t1["work_report"] == "found 3 gaps" and t1["status"] == "TODO"
    # Submit for review WITH a report
    client.post("/me/tasks/status", data={"task_id": str(t["task_id"]),
                "status": "READY_FOR_REVIEW", "work_report": "done: shortlisted 5"})
    t2 = tk.get_task(t["task_id"])
    assert t2["status"] == "READY_FOR_REVIEW" and t2["work_report"] == "done: shortlisted 5"
    # The reviewer sees the report in the Review Queue
    assert "done: shortlisted 5" in client.get("/admin/reviews").get_data(as_text=True)


def test_tool_feedback_submit_and_resolve(client):
    from src import toolfeedback as tfb
    # a member submits feedback
    r = client.post("/team/feedback/add",
                    data={"category": "bug", "message": "Trending is slow to load"})
    assert r.status_code in (301, 302)
    mine = [f for f in tfb.list_all() if f["message"] == "Trending is slow to load"]
    assert mine and mine[0]["status"] == "open"
    fid = mine[0]["id"]
    # owner (the test client is OWNER) ticks it resolved
    r2 = client.post(f"/team/feedback/resolve/{fid}", data={"to": "resolved"})
    assert r2.status_code in (301, 302)
    assert tfb.get(fid)["status"] == "resolved"
    # and can reopen it
    client.post(f"/team/feedback/resolve/{fid}", data={"to": "open"})
    assert tfb.get(fid)["status"] == "open"


def test_spy_and_run_without_keyword_are_graceful(client):
    assert client.get("/spy").status_code == 200          # prompt, no crash
    assert client.get("/run").status_code == 200


def test_spy_is_self_contained_and_analyze_active_state(client):
    # /spy must carry its own keyword+mode+run form (no dependency on a Command
    # Center button that no longer exists)
    sp = client.get("/spy").get_data(as_text=True)
    assert 'action="/spy"' in sp and 'name="q"' in sp and "Decode competitors" in sp
    assert "click 🕵️ Spy" not in sp                       # old removed-button hint gone
    # /analyze active button reflects the current view
    ex = client.get("/analyze?q=dog+shirt&do=expand").get_data(as_text=True)
    seg = ex[ex.find('action="/analyze"'):ex.find('action="/analyze"') + 600]
    assert 'value="expand" class="primary"' in seg
    assert 'value="analyze" class="primary"' not in seg
    assert "#b45309" not in ex                             # inline styles removed


def test_spy_listing_url_parsing_and_broadening(client, monkeypatch):
    from src import interactive as iv, ytrends_mcp as mcp
    # plain keyword + slug-less URL don't touch the MCP
    assert iv.spy_target("usa raccoon shirt") == ("usa raccoon shirt", None)
    assert iv.spy_target("etsy.com/listing/4519711663") == ("", "4519711663")
    # a slug-less URL shows help, never runs Spy on a mangled "etsy.comlisting..." string
    ns = client.get("/spy?q=etsy.com/listing/4519711663").get_data(as_text=True)
    assert "has no title in it" in ns and "etsy.comlisting" not in ns
    # a full URL broadens the 5-word title to the product core that has data
    monkeypatch.setattr(mcp, "research_keyword",
                        lambda kw, days=30: {"top_listings": [1]} if kw == "photo badge reel" else {})
    monkeypatch.setattr(mcp, "analyze_competition",
                        lambda seed, seed_type="keyword": {})
    kw, lid = iv.spy_target(
        "https://www.etsy.com/listing/4519711663/personalized-photo-badge-reel-custom")
    assert lid == "4519711663" and kw == "photo badge reel"


def test_feedback_form_saves(client):
    r = client.post("/feedback/add", data={
        "listing_url": "https://etsy.com/listing/test",
        "keyword": "unit test kw", "day_7_views": "0"})
    assert r.status_code in (301, 302)                    # redirect after save


def test_profit_form_saves(client):
    r = client.post("/profit", data={
        "keyword": "unit test", "product_mode": "pod", "supplier": "T",
        "sale_price": "25", "product_cost": "6", "shipping_cost": "0"})
    assert r.status_code in (301, 302)


def test_listing_analyzer_runs_and_gates(client):
    r = client.post("/grade", data={
        "keyword": "dog shirt", "title": "dog shirt",
        "tags": "dog, shirt", "description": "short"})
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Publish Gate: false" in body                  # thin listing blocked
    assert "DRAFT ONLY" in body


def test_no_publish_button_language_leaks(client):
    # A DRAFT-only listing must never show a live "Publish now" instruction.
    body = client.post("/grade", data={
        "keyword": "dog shirt", "title": "dog shirt", "tags": "dog, shirt",
        "description": "short"}).get_data(as_text=True)
    assert "Publish now" not in body
    assert ">Publish<" not in body
