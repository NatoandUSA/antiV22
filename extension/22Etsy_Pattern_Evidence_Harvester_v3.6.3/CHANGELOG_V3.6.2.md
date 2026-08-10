# 22Etsy Pattern Evidence Harvester v3.6.2

- Fixes visible Etsy review fallback parsing when Etsy does not expose old review container selectors.
- Adds text-based review extraction around "Reviews for this item" / "Reviews for this shop" sections.
- Adds review graph / rating distribution capture when Etsy renders percentages such as "5 star 82%".
- Adds rating_distribution_json to listing detail and review evidence rows.
- Keeps all v3.6 Evidence Router fields and /api/import-only boundary.
