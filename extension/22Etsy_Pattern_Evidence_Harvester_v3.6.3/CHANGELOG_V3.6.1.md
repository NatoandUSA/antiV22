# v3.6.1 patch notes — Etsy review-section fallback fix

## Fixed
- Review capture on Etsy listing pages where visible item reviews are rendered without the older `data-review-container` / review-class selectors.
- Added fallback scan around headings such as `Reviews for this item` and `Reviews for this shop`.
- Added safer review text and buyer fallback extraction for Etsy's newer class-less review layout.
- Kept v3.6 Evidence Router metadata and `/api/import` only boundary.

## Still bounded
- Public rendered data only.
- No private Etsy API.
- No marketplace click/publish automation.
- No ChatGPT toolbar or RESULT_JSON handling.
