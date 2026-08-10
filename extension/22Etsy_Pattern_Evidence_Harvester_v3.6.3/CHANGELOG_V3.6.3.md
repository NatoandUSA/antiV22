# 22Etsy Pattern Evidence Harvester v3.6.3

Backend-alignment + richer capture for the V37.5 Exact-Proof Loop. Additive only —
no field was removed, no new permission requested, still /api/import-only and read-only.

## Search results (keyword result page)
- Rows now come out in TRUE organic rank order (object-key iteration used to reorder
  numeric listing ids and lose the rank winners actually hold).
- New column `rank_position` — the organic rank of each listing (1 = top).

## Etsy listing detail page
- New column `listing_tags` — the listing's real Etsy tags (buyer keywords), the
  strongest input for Pattern Miner and for exact-keyword matching.
- New JSON-LD columns `jsonld_rating`, `jsonld_review_count`, `jsonld_price`,
  `jsonld_availability` — parsed from the page's structured Product data, which is
  stable even when Etsy changes CSS class names.

## Unchanged / still bounded
- All v3.6 Evidence Router metadata + focus_keyword flow kept.
- Public rendered data only. No private Etsy API. No publish/click automation.
