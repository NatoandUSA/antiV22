# v3.6.0 upgrade notes — V37.4 Evidence Router alignment

This version updates the v3.5 Pattern Evidence Harvester to better match the V37.4 Rank → Pattern → Re-rank requirements.

## Added
- Evidence Router metadata in every `/api/import` payload:
  - `evidence_router_version: v37.4`
  - `evidence_route_hint`
  - `proof_scope_hint`
  - `data_use_hint`
  - `exact_proof_required_for_build_now: true`
  - `listing_evidence_single_listing_cap: CONFIRM_FIRST`
  - `reviews_do_not_boost_l2_market_signal: true`
- Focus keyword / Pattern batch keyword in popup settings.
  - Useful when opening Etsy listing pages and review pages where the search query is no longer in the URL.
- Etsy search result rows now include:
  - `keyword_context`
  - `keyword_match_type`
  - `keyword_match_confidence`
  - `proof_scope_hint`
  - `evidence_route_hint`
  - `data_use_hint`
- Etsy listing detail rows now include evidence-route fields, image count, and `summary_once_per_listing` hint.
- HeyEtsy listing detail rows now clearly label third-party estimated evidence and single-listing CONFIRM_FIRST cap.
- Etsy review rows now clearly label buyer-voice evidence as not L2 Market Signal and include `summary_once_per_listing_do_not_sum_per_row`.
- Listing page button: `Send detail+reviews`, which sends listing detail and currently rendered reviews as separate evidence lanes.
- Popup shortcut to Re-rank.
- Toolbar hide persists for the tab session instead of reappearing every 1.5 seconds.

## Still intentionally not done
- The extension does not decide BUILD_NOW.
- The extension does not claim exact proof by itself.
- The extension does not call variants “highest converting.”
- The extension does not write to Etsy, publish listings, click marketplace actions, or use private APIs.

## Backend expectation
The 22Etsy backend should route these payloads into separate Evidence Router lanes:
- `etsy_listing_detail`
- `etsy_listing_reviews`
- `etsy_review_summary`
- `listing_keyword_map`

The backend must still enforce proof scope, match confidence, shop-spread, L0 gates, L3 Can-We-Win, and Publish Gate.
