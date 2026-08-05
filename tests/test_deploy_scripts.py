"""The two deploy scripts must not diverge on data safety.

Both `deploy/push-to-vps.ps1` and `deploy/push-to-vps.sh` copy this machine's
`keyword_data.csv` up to the server. The PC harvests, but the TEAM adds keywords
ON the VPS through the web UI (Keyword Lab, long-tail pulls, extension drops), so
a straight `scp` over the server's file deletes all of them.

`harvest.merge_master()` was written to fix exactly that and was wired into the
PowerShell script only. The bash script — which `main.py expand` advertises to Mac
users — kept the raw overwrite. Measured on 2026-08-05 the server held **178
keywords** this machine did not; running the .sh would have destroyed every one.

These tests pin the invariant rather than the wording: whatever else a deploy
script does, it must pull the server's copy and union it in BEFORE it pushes.
"""
import re
from pathlib import Path

import pytest

SCRIPTS = [Path("deploy/push-to-vps.ps1"), Path("deploy/push-to-vps.sh")]


def _text(p):
    if not p.is_file():
        pytest.skip(f"{p} not present")
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_deploy_unions_the_vps_base_instead_of_overwriting_it(script):
    src = _text(script)
    assert "merge_master" in src, (
        f"{script.name} pushes keyword_data.csv without unioning the VPS copy — "
        "this is the cross-machine deletion bug")
    # it must also FETCH the server's copy; merging a file that was never
    # downloaded is a no-op that still overwrites. The remote side is written
    # with the path VARIABLE in both scripts ($VPS_PATH / ${VPS_PATH}), so match
    # the remote spec rather than a hardcoded directory.
    assert re.search(r"scp[^\n]*:\$\{?VPS_PATH\}?/keyword_data\.csv", src), (
        f"{script.name} never downloads the VPS keyword_data.csv to merge")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_the_merge_happens_before_the_upload(script):
    """Ordering is the whole point: merge, then push the union."""
    src = _text(script)
    merge_at = src.index("merge_master")
    # the upload is the scp whose SOURCE is the local master
    up = re.search(r"scp[^\n]*\s\"?keyword_data\.csv\"?\s", src)
    assert up, f"{script.name} has no upload of the local keyword_data.csv"
    assert merge_at < up.start(), (
        f"{script.name} uploads the local master before merging the VPS copy")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_agent_db_is_shipped_atomically(script):
    """agent.db is read live by the dashboard; a half-written copy is a broken
    page. Both scripts must land it via a temp name + rename."""
    src = _text(script)
    assert "agent.db.tmp" in src and "mv -f" in src, (
        f"{script.name} does not ship agent.db atomically")


def test_app_db_is_never_shipped():
    """data/app.db holds team logins, tasks and activity and lives ONLY on the
    server. Copying the local one up would wipe the team's accounts."""
    for script in SCRIPTS:
        src = _text(script)
        assert "app.db" not in src or "NOT touched" in src, (
            f"{script.name} appears to copy app.db to the VPS")
