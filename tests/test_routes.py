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
    "/cheatsheet", "/workflow", "/suppliers", "/feedback", "/profit", "/grade",
    "/alerts", "/launchpad", "/trackers", "/research", "/shops", "/listings",
])
def test_pages_render(client, route):
    assert client.get(route).status_code == 200


def test_spy_and_run_without_keyword_are_graceful(client):
    assert client.get("/spy").status_code == 200          # prompt, no crash
    assert client.get("/run").status_code == 200


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
