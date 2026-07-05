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
