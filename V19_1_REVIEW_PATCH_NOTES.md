# Etsy Product Manager V19.1 Review Patch

Changes made:
- Version bumped to V19.1.
- Manager report Section 0 now checks production partner disclosure, not just whether a partner name exists.
- Seller pack now blocks customer-facing DESCRIPTION when supplier/material/size/processing evidence is missing.
- Seller pack now shows Customer-facing copy allowed: YES/NO.
- Seller pack hides post-publish actions unless final QA is PUBLISH_READY.
- Replaced risky launch/day plan wording so publishing is conditional on PUBLISH_READY.
- Added discover listing relevance filter to reject unrelated top listings, e.g. love-spell/service listings for physical-product keywords.
- Added selftests for seller placeholder blocking and discover relevance filtering.
- README and main command comments updated to clarify draft-only vs publish-ready.

Selftest:
- python main.py selftest => PASS
