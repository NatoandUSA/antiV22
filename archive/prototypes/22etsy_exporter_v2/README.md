# 22Etsy Exporter v2.0 (Chrome extension, for 22etsy-agent)

One-click capture of the data **already rendered on your screen** → CSV / JSON
download, or **Send to agent** (POSTs to your dashboard's `/api/import`).
Read-only: no clicking, no automation, no login access — it reads the DOM the
same way "Save Page As" would.

## Supported pages → what it captures → which dashboard lane

| Page | Columns captured | Lands in |
|---|---|---|
| **YTrends** (trends.ytuong.ai) any table | the table as-is (keywords, gems, categories…) | Rank / Inbox (L2 market signal) |
| **ytuong.me "Hot"** listing cards | listing_id, title, price_usd, sold_24h, views_24h, favorites_24h, badge, url | Etsy Spy → Pattern Miner |
| **Etsy search** (+ HeyEtsy overlay on) | listing_id, title, shop, price, reviews, star_seller, ad, bestseller, free_shipping + he_sold/views/favorites/revenue/tags | Etsy Spy → Pattern Miner |
| **Pinterest** search/board | pin_id, title, description, saves, comments, pinner, board, outbound, image | Pinterest lane (confirmation) |
| **Amazon search** results | asin, title, price, list_price, rating, ratings_count, bought_past_month, sponsored, prime, url | Amazon (reference) |
| **Alibaba search** results | title, price, min_order, sold, supplier, supplier_years, verified, url | Supplier Trend lane |

The toolbar shows **"N rows detected"** as soon as it loads — if it says 0,
scroll so the cards render, then click again. Empty cells mean the page simply
didn't show that stat (honest nulls — nothing is invented).

## Install / update
1. chrome://extensions → Developer mode ON → "Load unpacked" → this folder.
   (Updating: click ↻ on the extension card.)
2. Click the extension icon → set **Agent URL** to
   `https://YOUR-DASHBOARD/api/import` and your **import token**.
3. On any supported page: **CSV** / **JSON** to download, **Send to agent** to
   push straight into the dashboard (auto-routed by columns).

## Notes
- Amazon "bought in past month" and ratings only appear on listings where Amazon
  shows them; Alibaba prices appear once the card has rendered on screen.
- Scroll to the bottom of a results page before exporting to capture everything
  that's loaded.
- The agent auto-routes by columns: keyword tables → Rank, listing exports →
  Etsy Spy / Pattern Miner, supplier exports → Supplier lane, product exports
  with sales+revenue+age → Etsy Proof.
