# 22Etsy Pattern Evidence Harvester v3.6.2

Chrome extension for collecting **public rendered marketplace evidence** and sending it to the 22etsy `/api/import` endpoint.

It is designed for the Pattern Miner workflow:

1. Search a keyword on Etsy → **Send keyword results**.
2. Open 5–10 strong listing pages → **Send listing evidence**.
3. Open the review modal/section → **Harvest reviews** → **Send reviews**.
4. Open the matching HeyEtsy listing page → **Send HeyEtsy evidence**.
5. Pattern Miner groups the evidence by keyword, listing ID, and pattern batch ID.

## What it captures

### Etsy keyword result pages
- query/keyword, rank position, listing ID, title, shop, price, image, listing URL
- visible badges such as ad, bestseller, free shipping
- HeyEtsy overlay metrics if rendered

### Etsy listing detail pages
- one main listing row, not related listings
- title, shop, price, rating/reviews, images, description, personalization/options, shipping/policies, breadcrumbs

### Etsy reviews
- public rendered review cards from the review section or open review modal
- review text, buyer/date when rendered, rating, purchased item text, review photo, seller response, summary/histogram fields when rendered
- dedupes review rows, supports Etsy class-less review sections, and chunks large sends

### Etsy shop pages
- shop name, rating/reviews/sales when rendered, announcement/about/sections, visible listing cards

### HeyEtsy listing pages
- listing-level metrics rendered by HeyEtsy: sold/revenue/views/favorites/age/tags/images/shop context
- values are labeled as HeyEtsy estimates

## Buttons

- **Grab all**: read-only auto-scroll, then CSV download.
- **CSV / JSON**: local backup exports.
- **Send keyword results / Send listing evidence / Send shop snapshot / Send HeyEtsy evidence**: post evidence to `/api/import`.
- **Harvest reviews**: scrolls the open review modal/container to load more public rendered reviews.
- **+ Add current reviews**: adds currently rendered reviews to a deduped review batch.
- **Send reviews**: sends review evidence to `/api/import`, chunked when large.

## Safety boundaries

- Read-only rendered/public data only.
- No Etsy seller account automation.
- No publish automation.
- No private Etsy APIs.
- No login bypass.
- No ChatGPT toolbar.
- No GPT `RESULT_JSON` handling.
- Posts only to `/api/import`.

## Install

1. Unzip the extension folder on your PC.
2. Open `chrome://extensions`.
3. Enable Developer Mode.
4. Click **Load unpacked** and select the extension folder.
5. Open the extension popup and set:
   - Operator name
   - Agent import URL, e.g. `https://etsy.theglobalserviceteam.site/api/import`
   - Import token

## Manual test checklist

- Etsy search page shows **Etsy Search Results**.
- Etsy listing page shows **Etsy Listing Detail** and review tools.
- Review harvest count grows when the Etsy review modal loads more rows.
- Etsy shop page shows **Etsy Shop Snapshot**.
- HeyEtsy listing page shows **HeyEtsy Listing Detail**.
- Send buttons show exact success/error status.
- Bad token returns a visible error instead of a dead button.


## v3.6.0 V37.4 alignment

This version adds Evidence Router hints so Rank / Pattern / Re-rank can separate exact proof, cluster proof, listing-only evidence, and buyer-review voice. It does **not** decide BUILD_NOW in the extension.

New fields sent in payloads include `evidence_router_version`, `evidence_route_hint`, `proof_scope_hint`, `data_use_hint`, `exact_proof_required_for_build_now`, `listing_evidence_single_listing_cap`, and `reviews_do_not_boost_l2_market_signal`.

The popup now has a **Focus keyword / Pattern batch keyword** field. Set this before opening competitor listing pages so listing detail and review evidence can attach to the right Pattern Miner / Re-rank context.

Recommended V37.4 flow:

1. Search a keyword on Etsy and send keyword results.
2. Open 5–10 winning listings and send listing evidence.
3. Open reviews and send review evidence.
4. Open HeyEtsy listing detail and send HeyEtsy evidence.
5. Backend maps evidence to keyword using listing ID + match confidence; single-listing evidence caps at CONFIRM_FIRST until multi-shop proof exists.


## v3.6.2 review fix

When Etsy renders visible reviews without the older review-card selectors, use **Harvest reviews** or **+ Add current reviews**. v3.6.2 scans the visible `Reviews for this item` / `Reviews for this shop` text and also captures the review graph/rating distribution when Etsy renders percentages.
