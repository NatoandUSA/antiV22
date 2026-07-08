# GitHub / Public-Tool Reference Research

Patterns studied to inform this round (product-fit filter, cleaner pages).
**Patterns and public docs only — no code copied, licenses respected.** Any dev
tools referenced are permissively licensed (MIT/Apache) and opt-in.

| Reference type | What it does | Useful pattern | Adopt? | Why / why not |
|---|---|---|---|---|
| Etsy scrapers (public repos) | Extract listing title/price/reviews/favorites/tags | The listing field schema (title, price, sold, favorites, tags, shop_id) + how they detect **shop handles** vs product titles | **Pattern only** | We never scrape Etsy (safety). But the "shop handle looks like a run-on token / ends in *studio/shop/designs*" heuristic informed `product_fit._looks_like_shop`. |
| Etsy API wrappers | Typed, safe access to the Etsy API | Thin typed connector + fail-fast on auth | Already have | Our `ytrends_mcp` client mirrors this (typed helpers, fail-fast probe). No change. |
| Etsy keyword tools (eRank/Marmalead-style) | Keyword expansion + grouping + tag quality | Group synonyms; flag low-quality/broad tags | **Partial** | Reinforced the **BROAD_SEED_ONLY** and generic-term handling in `product_fit`. Full clustering deferred (decision log #6). |
| Etsy tag optimizers (e.g. Taggregator, wordsy) | 13-tag scoring, replacement, typo checks | Char-packing, typo/relevance, tag frequency across winners | Already have | Built in Listing Analyzer + Spy "tags winners share" (V24). |
| Etsy MCP / Claude integrations | Clean tool interface; separate Claude calls from app logic | Keep model/tool calls behind a thin service; dashboard stays logic-free | Already have | `ytrends_mcp` + interactive/services split. No change. |
| Print-farm / catalog tools | Supplier catalog + cost/profit tracking | Normalized supplier schema; per-product cost/profit | Already have | `supplier_ops` (36-col schema) + Profit Center (V24). No change. |
| Flask / pytest / packaging patterns | Clean routes, tests, healthcheck, release zip | Test-client route tests; healthcheck; release packaging; JSON-schema validation | Already have + reused | Route/publish-gate/auth test suites, `healthcheck`, `package release`, `src/schemas/*`. |
| Pydantic / JSON Schema | Typed validation of stored data | Validate records against a schema | **Have (light)** | `data_validate` + `src/schemas/*.json`; use `jsonschema` only if installed (dependency-light). |
| Playwright (browser e2e) | Drive the UI in a real browser | Click-through smoke tests | **Skip for now** | The Flask test-client suite covers the same checklist offline + fast; a browser dep isn't worth it yet. |

**Net:** the only new pattern worth adopting this round was the **shop-handle / junk
detection** heuristic (→ `product_fit`). Everything else was either already present
in an Etsy-appropriate form or deferred to avoid clutter (see the decision log).
Licenses: nothing copied; our stack stays on Flask + Werkzeug + Markdown + requests
+ pytest (all permissive, already in the project).
