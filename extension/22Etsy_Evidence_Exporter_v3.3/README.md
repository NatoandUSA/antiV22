# 22Etsy Evidence Exporter — v3.3.0

A clean, read-only Chrome extension that captures the data **already rendered on your screen** and turns it into a CSV, a JSON file, or a push to your 22etsy agent's `/api/import` endpoint.

It never clicks anything on a marketplace, never logs in, never automates a store, and never opens ChatGPT. Exactly what "Save Page As" would keep — minus the manual work.

> **v3.3 change:** all ChatGPT / V8.2 / Design Bridge automation has been removed. This extension is now an **evidence exporter only**. Design work happens manually inside the 22etsy **Design Workspace** (see the boundary note below).

---

## What it captures

| Source | What you get |
|---|---|
| **YTrends** (`trends.ytuong.ai`) | Any rendered data table — keywords, gems, categories, etc. |
| **ytuong.me** "Hot" cards | listing id / title / price + 24h sold / views / favorites |
| **Etsy** search results | listing id, title, shop, price, reviews, badges — **plus** the full HeyEtsy overlay (lifetime sold, revenue, views, favorites, conversion, created/age, tags, categories) when the HeyEtsy panel is on |
| **HeyEtsy** `/listing/{id}` | Single-record analytics page: sold, revenue, views, favorites, conversion, created/updated, shop stats, tags, image URLs |
| **Pinterest** | Pins from hydration JSON first, DOM fallback — saves, comments, board, outbound link, image |
| **Amazon** search results | asin, title, price, list price, rating, ratings count, "bought past month", sponsored, prime |
| **Alibaba / AliExpress / 1688** | title, price, min order, sold, supplier, supplier years, verified |

Empty fields are left empty. The extension **never invents** a missing value (`evidence_policy: rendered_page_only_no_invention`).

---

## Toolbar buttons (on any supported page)

- **↓ Grab all** — auto-scrolls the page so lazy / infinite-scroll rows finish loading, then downloads a CSV. Scroll only; it never clicks "Next".
- **CSV now** — download the currently rendered rows as CSV.
- **JSON** — download the evidence payload as JSON.
- **Send to agent** — POST the payload to your configured `/api/import` URL.
- **Multi-page batch** — `+ Add page`, `Batch CSV`, `Send batch`, `Clear`. You navigate the pages yourself; the extension de-dupes rows into one set. It never clicks pagination.
- **×** — hide the toolbar.

---

## Setup (popup)

Click the extension icon and fill in:

1. **Your name (operator)** — optional label saved into import history.
2. **Agent import URL** — e.g. `https://etsy.theglobalserviceteam.site/api/import`.
3. **Import token (X-Import-Token)** — matches `YTX_IMPORT_TOKEN` in the agent `.env`. Stored masked; never printed.

Then **Save settings**. Use **Test connection to /api/import** to confirm the URL and token reach the agent (it sends a harmless zero-row ping and reports the HTTP status — no real data is created).

---

## Data contract (Send to agent → `/api/import`)

```json
{
  "schema_version": "1.1",
  "exporter_version": "3.3.0",
  "view": "source-viewslug",
  "captured_at": "ISO timestamp",
  "source": "current page URL",
  "source_type": "heyetsy_listing_detail | etsy | ytrends | pinterest | amazon | alibaba | supplier-1688 | ...",
  "evidence_policy": "rendered_page_only_no_invention",
  "operator": "optional operator name",
  "headers": ["..."],
  "rows": [["..."]]
}
```

The **only** endpoint the background worker will post to is `/api/import` on the 22etsy agent host (plus `localhost` / `127.0.0.1` `/api/import` for local dev). There is no design-result path anymore.

---

## Design Workspace boundary (important)

This extension does **not** create, validate, download, or send any design job or GPT `RESULT_JSON`. Design work is manual and lives entirely inside **22etsy**:

1. In 22etsy Design Workspace you upload the main photo, HeyEtsy evidence, the Etsy listing URL, and the HeyEtsy URL.
2. 22etsy builds the GPT prompt and the `RESULT_JSON` template for you.
3. You run GPT manually and paste the answer.
4. You paste `RESULT_JSON` back into 22etsy, which validates it and hands off to the Launch Kit.

The extension's only job is to get clean evidence out of the page and into `/api/import`.

---

## Permissions

- `storage`, `downloads` — save your settings and write CSV/JSON files.
- Host permissions cover only the data-source sites listed above plus the 22etsy agent host. There is **no** ChatGPT/OpenAI host, and **no** `<all_urls>`.

## Install (unpacked)

1. Open `chrome://extensions`.
2. Turn on **Developer mode**.
3. **Load unpacked** → select this folder.
4. Open a supported page; the toolbar appears bottom-right.
