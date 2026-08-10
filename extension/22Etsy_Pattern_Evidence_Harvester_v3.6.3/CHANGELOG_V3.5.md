# v3.6.0 upgrade notes

Renamed to **22Etsy Pattern Evidence Harvester**.

## Added
- Dedicated Etsy search result extractor for Pattern Miner batches.
- Dedicated Etsy listing detail extractor so related listings are not mistaken as the main listing.
- Dedicated Etsy shop snapshot extractor.
- Improved Etsy reviews capture with review modal/container scroll harvesting.
- Review de-duping and chunked send for large review batches.
- Better toolbar labels by page type.
- Pattern grouping fields: `pattern_batch_id`, `source_page_type`, `evidence_group`, `keyword`, `listing_id`, `etsy_url`, `heyetsy_url`.
- Popup shortcuts to Import Center and Pattern Miner.

## Kept
- CSV/JSON backup.
- /api/import only.
- X-Import-Token.
- No ChatGPT toolbar.
- No marketplace publish or account automation.

## Manual test recommended
- Etsy keyword result page.
- Etsy listing page.
- Etsy review modal.
- Etsy shop page.
- HeyEtsy listing page.
- Bad token error display.
