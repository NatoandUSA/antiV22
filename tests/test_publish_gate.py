"""Publish-gate safety tests — the most important guardrails in the tool.

The invariant that must NEVER break: PUBLISH_READY=true only when there are zero
failed checks, and only after explicit manager sign-off. A known brand (HIGH
trademark) can never be cleared. Nothing here publishes anything.
"""
from src import workspace as w


def _tags(clean=13, safe=True, status="OK"):
    return [{"tag": f"clean tag {i}", "publish_safe": safe, "status": status}
            for i in range(clean)]


FULL = {"supplier": True, "competitor_audit": True, "material": True,
        "image": True, "trademark": True}


def test_gate_blocks_with_no_manager_signoff():
    ready, failed = w.publish_gate("kw", _tags(), False, "OK", [], "design",
                                   lr=70, fib=80, offer=75, confirms={})
    assert ready is False
    assert failed  # never "failed checks: none" when not ready


def test_gate_passes_only_with_full_signoff_and_scores():
    ready, failed = w.publish_gate("kw", _tags(), True, "OK", [], "design",
                                   lr=100, fib=80, offer=75, confirms=FULL)
    assert ready is True
    assert failed == []


def test_high_trademark_can_never_be_cleared():
    ready, failed = w.publish_gate("kw", _tags(), True, "HIGH", [], "design",
                                   lr=100, fib=80, offer=75, confirms=FULL)
    assert ready is False
    assert any("brand" in f or "trademark" in f for f in failed)


def test_each_automated_rule_produces_a_failure():
    # low scores
    _, f = w.publish_gate("kw", _tags(), True, "OK", [], "design",
                          lr=70, fib=60, offer=60, confirms=FULL)
    assert any("launch readiness" in x for x in f)
    assert any("first-image" in x for x in f)
    assert any("offer strength" in x for x in f)
    # wrong tag count
    _, f = w.publish_gate("kw", _tags(11), True, "OK", [], "design",
                          lr=100, fib=80, offer=75, confirms=FULL)
    assert any("13 tags" in x for x in f)
    # unsafe verdict
    _, f = w.publish_gate("kw", _tags(), True, "OK", [], "watch",
                          lr=100, fib=80, offer=75, confirms=FULL)
    assert any("WATCH" in x for x in f)
    # data flags
    _, f = w.publish_gate("kw", _tags(), True, "OK", ["DATA_CHECK"], "design",
                          lr=100, fib=80, offer=75, confirms=FULL)
    assert any("DATA_CHECK" in x for x in f)


def test_caution_trademark_needs_manager_but_can_be_approved():
    no_tm = {**FULL, "trademark": False}
    _, f = w.publish_gate("kw", _tags(), True, "CAUTION", [], "design",
                          lr=100, fib=80, offer=75, confirms=no_tm)
    assert any("trademark" in x for x in f)
    ready, _ = w.publish_gate("kw", _tags(), True, "CAUTION", [], "design",
                              lr=100, fib=80, offer=75, confirms=FULL)
    assert ready is True


def test_safety_invariant_ready_iff_no_failures():
    # ready is true if and only if there are no failed checks, across scenarios
    for conf in ({}, {"supplier": True}, FULL):
        for lr in (70, 100):
            ready, failed = w.publish_gate("kw", _tags(), conf.get("supplier", False),
                                           "OK", [], "design", lr=lr, fib=80,
                                           offer=75, confirms=conf)
            assert ready == (len(failed) == 0)


def test_launch_readiness_needs_manager_signoff():
    tags, L = _tags(), {"rec_price": 24.0}
    assert w.launch_readiness(True, tags, "OK", L, {}, confirms={})[0] < 85
    assert w.launch_readiness(True, tags, "OK", L, {}, confirms=FULL)[0] >= 85


def test_strict_verdict_sell_now_needs_all_gates():
    scores = [{"name": "Overall Product", "score": 90},
              {"name": "Competition", "score": 80}]
    assert w.strict_verdict("k", scores, {}, "OK", [], cww=90, lr=90, fib=90,
                            offer=90)["verdict"] == "SELL NOW"
    # weak first image drops it out of SELL NOW
    assert w.strict_verdict("k", scores, {}, "OK", [], cww=90, lr=90, fib=60,
                            offer=90)["verdict"] != "SELL NOW"
    # HIGH trademark = BLOCKED
    assert w.strict_verdict("k", scores, {}, "HIGH", [], cww=90, lr=90, fib=90,
                            offer=90)["verdict"] == "BLOCKED"
