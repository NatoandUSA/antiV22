# Team Workflow (offline) - V19

Weekly cycle: Mon research -> Tue supplier+IP verification -> Wed design ->
Thu listing drafts -> Fri final QA + publish decision -> weekend light
monitoring. Handoff rule: a product moves stage ONLY when its owner's
daily form is filled and the manager updates the status.

Roles & rules:
- Manager: final decisions. High demand alone never approves a product.
- Claude operator: runs commands, saves outputs; Claude output is always
  human-reviewed.
- Researcher: never guesses - unverified data is marked UNVERIFIED.
- Supplier checker: missing proof blocks publishing.
- TM/IP reviewer: when unsure, CAUTION, never CLEAR.
- Designer: competitors are for positioning, not copying.
- Seller: drafting when approved; publishing ONLY at PUBLISH_READY.

File naming: YYYY-MM-DD_role_report_product-name.md
Folder layout: see folder_structure.md
Daily forms: forms_*.md in this folder.
Claude operator daily prompt: claude_daily_prompt.md
