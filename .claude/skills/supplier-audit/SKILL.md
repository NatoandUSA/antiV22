---
name: supplier-audit
description: Internal checklist. Verify supplier data, CSV import, and mode-correct supplier matching (POD vs Embroidery vs ShineOn). Use when touching supplier_ops, supplier_pull, the supplier library UI, or CSV import.
---

# Supplier Audit (internal)

## Files to inspect
`src/supplier_ops.py` (`match`, `_mode_ok`, `import_csv`, `sync`, `SCHEMA`),
`src/supplier_pull.py`, `data/suppliers/supplier_sources.json`, the `/suppliers` route.

## Rules
- Mode-correct matching: embroidery is satisfied ONLY by EMBROIDERY/CHENILLE rows;
  POD is not satisfied by embroidery rows (`_mode_ok`).
- CSV import (ShineOn / Embroidery) normalizes into the unified 36-col SCHEMA with headers.
- Never invents data: a missing field stays empty and appears in `missing_fields`.
- SUPPLIER_CONFIRMED requires product_url + base_cost + material (see supplier.schema.json).
- Digital / unsupported products -> PRODUCT_NOT_SUPPORTED, not a fake match.

## Commands
```
py main.py supplier match --product "chenille name bag" --mode embroidery --country US
py main.py supplier match --product "usa raccoon shirt" --mode pod --country US
py main.py supplier import-csv --source embroidery --file data/suppliers/Embroidery.csv
py main.py validate suppliers
```

## Pass/fail
- Embroidery product matches an embroidery supplier; POD product does NOT get mode
  credit from an embroidery-only supplier.
- `validate suppliers` shows no CONFIRMED-without-cost/URL rows.

## What NOT to do
- Do not mark a supplier CONFIRMED without the required fields.
- Do not treat embroidery as POD (or vice-versa) in scoring.
