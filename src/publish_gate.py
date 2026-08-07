"""THE canonical publish gate (single source of truth).

Every publish-readiness decision in the tool flows through publish_gate().
Nothing else may declare a listing publishable.

final_status is one of:
  PUBLISH_READY      - every gate passed with evidence
  NEEDS_REVIEW       - non-blocking gaps: manual review required
  BLOCKED            - hard violation (trademark/policy)
  INSUFFICIENT_DATA  - required evidence missing (supplier, audit, data)
"""
from src.validators import validate_title, validate_tags


def partner_status(sup):
    """4-state production partner status (V19)."""
    req = (sup.get("production_partner_required") or "").strip().lower()
    dis = (sup.get("production_partner_disclosed") or "").strip().lower()
    if req == "no":
        return "NOT_REQUIRED"
    if req == "yes" and dis == "yes":
        return "REQUIRED_DISCLOSED"
    if req == "yes":
        return "REQUIRED_NOT_DISCLOSED"
    return "UNKNOWN_REVIEW_REQUIRED"

BLOCKING = {"trademark_clear", "copyright_policy_clear"}
EVIDENCE = {"supplier_confirmed", "product_url_recorded",
            "supplier_url_verified", "material_verified", "size_verified",
            "base_cost_verified", "shipping_cost_verified",
            "processing_time_verified",
            "production_partner_disclosed",
            "seller_original_design_confirmed",
            "real_photo_confirmed",
            "competitor_audit_complete", "keyword_data_verified",
            "profitability_verified", "no_placeholders", "no_flagged_data",
            "trademark_verified_or_approved"}
REVIEW = {"title_quality_pass", "tag_quality_pass", "manual_review_complete"}

MIN_NET_PROFIT = 6.0     # dollars floor per sale
MIN_NET_MARGIN = 30.0    # percent net margin hard floor (target is 35-40%)


def _profit_ok(pm):
    """True only if we clear BOTH the $ floor and the net-margin floor.

    Margin is enforced only when the profit model reports it (the real
    pipeline always does); callers that pass just {"net_profit": N} still
    work off the dollar floor."""
    if not pm:
        return False
    if (pm.get("net_profit") or 0) < MIN_NET_PROFIT:
        return False
    margin = pm.get("profit_margin_pct")
    if margin is not None and margin < MIN_NET_MARGIN:
        return False
    return True


def _profit_reason(pm):
    pm = pm or {}
    return (f"net=${pm.get('net_profit', '?')}, "
            f"margin={pm.get('profit_margin_pct', '?')}% "
            f"(need >=${MIN_NET_PROFIT:.0f} and >={MIN_NET_MARGIN:.0f}%)")


def publish_gate(c):
    """c: dict candidate. Returns structured gate result."""
    sup = c.get("supplier_record") or {}
    material = sup.get("material", "")
    title_ok, title_issues = validate_title(c.get("title", ""), material,
                                            c.get("primary_keyword", ""))
    tags_ok, tag_issues = validate_tags(c.get("tags", []), material)
    tm_states = c.get("tm_states") or []
    desc = c.get("description", "")

    gates = {
        "supplier_confirmed":
            (c.get("supplier_status") == "SUPPLIER_CONFIRMED",
             f"supplier_status={c.get('supplier_status')}"),
        "supplier_last_verified":
            (bool((sup.get("last_verified") or "").strip()),
             sup.get("last_verified") or "no verification date recorded"),
        "product_url_recorded":
            (bool((sup.get("product_url") or "").strip()),
             sup.get("product_url") or "missing"),
        "supplier_url_verified":
            (bool((sup.get("supplier_catalog_url") or "").strip()),
             "supplier site URL missing"),
        "material_verified":
            (bool((sup.get("material") or "").strip()), "material missing"),
        "size_verified":
            (bool((sup.get("available_sizes") or "").strip()),
             "size/dimensions missing"),
        "base_cost_verified":
            (bool(str(sup.get("base_cost") or "").strip()),
             "base cost missing"),
        "shipping_cost_verified":
            (bool(str(sup.get("shipping_cost") or "").strip()),
             "shipping cost missing"),
        "processing_time_verified":
            (bool((sup.get("processing_time") or "").strip()),
             "processing time missing"),
        "production_partner_disclosed":
            ((sup.get("production_partner_disclosed") or "").strip().lower()
             == "yes" or (sup.get("production_partner_required") or ""
                          ).strip().lower() == "no",
             f"status={partner_status(sup)}"),
        "seller_original_design_confirmed":
            ((sup.get("seller_original_design_confirmed") or ""
              ).strip().lower() == "yes",
             "confirm the design is the seller's original work"),
        "real_photo_confirmed":
            ((c.get("real_photo_confirmed") or "").strip().lower() == "yes",
             "hero/macro/measurements/sew-out photos must be the REAL "
             "product, not an AI mockup - confirm real photos are ready"),
        "trademark_clear":
            (not any(s in ("TM_BLOCKED", "TM_CAUTION_UNVERIFIED")
                     for s in tm_states),
             f"states={sorted(set(tm_states))}"),
        "trademark_verified_or_approved":
            (all(s == "TM_VERIFIED_CLEAR" or
                 (s == "TM_HEURISTIC_OK_NOT_VERIFIED"
                  and c.get("manager_tm_approval"))
                 for s in tm_states) if tm_states else True,
             "USPTO-verify or record manager approval "
             "(decision=MANAGER_APPROVED in tm_verified.csv)"),
        "copyright_policy_clear":
            (not c.get("policy_violations"),
             "; ".join(c.get("policy_violations") or []) or "no known issue"),
        "competitor_audit_complete":
            (c.get("audit_status") == "COMPETITOR_AUDIT_OK",
             f"audit_status={c.get('audit_status')}"),
        "keyword_data_verified":
            (not c.get("primary_data_check"),
             "primary keyword clean" if not c.get("primary_data_check")
             else "primary keyword flagged DATA_CHECK_REQUIRED"),
        "no_flagged_data":
            (not c.get("cluster_has_flagged"),
             "flagged rows exist in cluster - researcher must clear them"
             if c.get("cluster_has_flagged") else "clean"),
        "profitability_verified":
            (_profit_ok(c.get("profit_model")),
             _profit_reason(c.get("profit_model"))),
        "title_quality_pass": (title_ok, "; ".join(title_issues) or "clean"),
        "tag_quality_pass": (tags_ok, "; ".join(tag_issues) or "clean"),
        "no_placeholders":
            ("NEED_SUPPLIER_DETAILS" not in desc and "[Fill" not in desc
             and "[X]" not in desc, "placeholders present"
             if "NEED_SUPPLIER_DETAILS" in desc else "clean"),
        "manual_review_complete":
            ((c.get("manual_review") or "").strip().lower() == "yes",
             "manager has not recorded final manual review"),
    }

    failed = {k for k, (ok, _) in gates.items() if not ok}
    if failed & BLOCKING:
        final = "BLOCKED"
    elif failed & EVIDENCE:
        final = "INSUFFICIENT_DATA"
    elif failed & REVIEW:
        final = "NEEDS_REVIEW"
    elif failed:
        final = "NEEDS_REVIEW"
    else:
        final = "PUBLISH_READY"

    return {
        "final_status": final,
        "production_partner_status": partner_status(sup),
        "gates": {k: {"passed": ok, "reason": why}
                  for k, (ok, why) in gates.items()},
        "blocked_by": sorted(failed),
    }
