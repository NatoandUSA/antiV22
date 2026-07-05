"""End-to-end pipeline test, isolated in a temp-cwd sandbox.

This reuses the existing, battle-tested `run_selftest()` (100+ assertions
covering the manager pipeline, publish gates, bilingual reports, PDF export,
timestamps, and the operational report set) but runs it inside a throwaway
copy of the project. That makes it order-independent and stops it from
mutating the real reports/ tree -- the two defects that made the bespoke
`py main.py selftest` harness fragile.

The CLI command `py main.py selftest` still works for end users; this simply
gives the same coverage a clean, CI-friendly `pytest` entry point.
"""


def test_full_selftest_pipeline(sandbox):
    from src.selftest import run_selftest
    # run_selftest() prints per-check PASS/FAIL lines (captured by pytest and
    # shown on failure) and returns True only if every check passed.
    assert run_selftest() is True


def test_main_is_importable_and_dispatch_matches_known(sandbox):
    import main
    # The dispatch table is the single source of truth for known commands.
    assert callable(main.main)
    assert all(callable(h) for h in main.COMMANDS.values())
    assert main.LIVE_API_CMDS <= set(main.COMMANDS)
    for name in ("daily", "selftest", "pdfcheck", "listing", "manager"):
        assert name in main.COMMANDS
