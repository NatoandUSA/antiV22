# Supplier API reference (for future fulfillment automation)

All base costs below are PLACEHOLDERS - replace with real dashboard prices.

## Printify - catalog + orders (INTEGRATED for costs)
- Docs: https://developers.printify.com
- Auth: Bearer personal access token, base https://api.printify.com/v1
- We use: catalog blueprints/providers/shipping (py main.py printify ...)

## ShineOn - orders only (Phase 3)
- Docs: https://teamshineon.zendesk.com/hc/en-us/articles/10120654767121
- Order submission API for high-volume stores; ShineOn suggests starting
  with CSV ordering. No pricing catalog - base costs from their dashboard.

## BurgerPrints - orders only (Phase 3)
- Docs: https://api-docs.burgerprints.com (API v2)
- Get/create/cancel orders. API key from Fulfillment store settings,
  sent as password in params. No catalog - costs from dashboard.

## Printway - orders (Phase 3)
- Docs: https://documenter.getpostman.com/view/25190860/2s9Y5WyPUk (v3)
- Order-focused API. Costs from dashboard.

## Phase 3 plan (when sales start)
Ask Claude Code: "Build src/fulfillment.py that reads new Etsy orders
from my exported CSV and creates matching orders via the right supplier
API (Printify/BurgerPrints/Printway), with a manual confirm step before
each submission."

---

# Adding a NEW supplier later (no blind scraping)

The supplier registry is `data/supplier_catalog.csv` (columns:
supplier, product_line, catalog_url, data_source, notes). When you onboard a
new supplier, add one row there first, then bring its data in by ONE of the two
safe paths below. **We never blind-scrape a supplier's website** (it breaks the
moment they change their HTML, it can get your account blocked, and it produces
silently-wrong costs). Both paths below use data you are already entitled to
from your own logged-in account.

## Path A — dashboard CSV export (preferred, zero code risk)
This is how ShineOn (1010 products) and the embroidery price sheet came in.

1. In the supplier's seller dashboard, export the catalog / price list as CSV.
2. Save it into the project's `data/` folder (e.g. `data/newsupplier_raw.csv`).
3. Tell Claude Code:
   > "Parse data/newsupplier_raw.csv into a clean data/<name>_products.csv
   > (sku, title, base_cost_usd, ...) and add its real costs to
   > supplier_costs.csv and costs.csv. Then run `py main.py selftest`."
4. Add a `selftest` check for the new file so a broken import is caught early.

No API, no cookies, no scraping. If the supplier offers an export, always use it.

## Path B — reverse-engineer YOUR OWN session (when there is no export)
Only when you need the live catalog and there is no CSV export. You capture a
recording of your own browser talking to the supplier, and Claude Code turns the
internal JSON endpoints into a small, polite client — the SAME shape as
`src/ytrends_client.py` (cache-first, 1 request/second, retry with backoff,
and **fail-fast guards**). No HTML scraping, no headless browser hammering the site.

### 1. Capture a HAR of your own logged-in session
1. Log in to the supplier in Chrome/Edge. Press **F12** → **Network** tab.
2. Tick **Preserve log**. Click the 🚫 (clear) button once to start clean.
3. Browse the catalog normally — open a few product/price pages so the real
   data requests happen.
4. Right-click anywhere in the request list → **Save all as HAR with content**.
   Save it as `har_capture.har` somewhere local.

### 2. Hand it to Claude Code
   > "Here is har_capture.har from my logged-in <supplier> session. Find the
   > internal JSON endpoints that return the product catalog and prices, and
   > build src/<supplier>_client.py modeled on src/ytrends_client.py."

Claude Code will build a client that:
- **Caches** every response in SQLite for the day (repeat runs cost 0 quota).
- Sends **max 1 request/second** and retries 429/5xx with exponential backoff.
- **Fails fast with a clear message, never a wrong number.** On the first call
  it runs a *probe guard*: it checks the response is the shape we expect
  (the fields we need are present). If the endpoint moved or the JSON changed,
  or you get 401/403, it stops with a plain-English "re-capture your session"
  message — exactly like the YTrends `AUTH_HELP` block — instead of guessing.

### Security — treat the HAR and cookies like a password
- A HAR contains your live login session. **Never** paste it into chat, commit
  it, or share it. Hand Claude Code the file *path*; it reads it locally.
- Session cookies go in `.env` (already gitignored), never in code or chat.
- Delete `har_capture.har` once the client is built.

### Never do
- No scraping the rendered HTML pages.
- No headless-browser bots looping over the catalog.
- No sharing your cookie / HAR / `.env` with anyone or any machine.
