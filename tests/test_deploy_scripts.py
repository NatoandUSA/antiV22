"""The two deploy scripts must not diverge on data safety.

Both `deploy/push-to-vps.ps1` and `deploy/push-to-vps.sh` copy this machine's
data up to the server, so both can destroy data the server owns:

  * `keyword_data.csv` - the PC harvests, but the TEAM adds keywords ON the VPS
    through the web UI. Measured 2026-08-05: the server held **178 keywords**
    this machine did not. A straight scp deletes every one.
  * `data/agent.db` - written by two VPS crons and holding `discovered_keywords`,
    which `opportunity_inbox._history_from_db()` reads for the Inbox trend
    arrows. Measured 2026-08-05: the server held **12,543 rows** to this
    machine's 11,680.
  * `data/app.db` - team logins, tasks and activity. Server-only, always.

FIRST VERSION OF THIS FILE WAS NOT TRUSTWORTHY, which is the whole reason it is
written this way now. Three of its four assertions were vacuous:
  - the "downloads the server's copy" regex also matched the UPLOAD line, so
    deleting the download kept it green;
  - the ordering check used `src.index("merge_master")`, which found the word in
    a COMMENT, so moving the real call after the upload kept it green;
  - the app.db guard had an `or "NOT touched" in src` escape hatch that both
    scripts' own comments satisfied permanently.

So: every check below runs against COMMENT-STRIPPED command lines, anchors on
the scp SOURCE argument rather than "the string appears somewhere", and is
accompanied by a mutation test proving it fails when the guarded line is broken.
"""
import re
from pathlib import Path

import pytest

PS1 = Path("deploy/push-to-vps.ps1")
SH = Path("deploy/push-to-vps.sh")
SCRIPTS = [PS1, SH]


def _commands(path):
    """Executable lines only. Comments are prose and must never satisfy a check."""
    if not path.is_file():                     # a missing script is a FAILURE,
        raise AssertionError(                  # never a skip - renaming the file
            f"{path} is missing; the data-safety invariants it carries are "
            "unpinned. If it moved, update SCRIPTS.")
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _text(path):
    return "\n".join(_commands(path))


# flags that consume the NEXT token as their value
_FLAGS_WITH_VALUE = {"-P", "-o", "-i", "-F", "-l", "-c", "-S"}


def _scp_operands(line):
    """Positional [source, dest] of an scp command, or [] if the line isn't one.

    Must cope with the command being wrapped: the bash download is written
    `if ! scp -P "$VPS_PORT" REMOTE LOCAL; then`, so a naive "first token that
    isn't a flag" reads `if` as the source and silently classifies a real
    download as 'not a download'. That is precisely the kind of hole this file
    exists to close, so parse properly: find the `scp` token, then walk forward.
    """
    toks = re.split(r"\s+", line.strip())
    if "scp" not in toks:
        return []
    out, skip = [], False
    for tok in toks[toks.index("scp") + 1:]:
        if skip:
            skip = False
            continue
        if tok in _FLAGS_WITH_VALUE:
            skip = True
            continue
        if tok.startswith("-"):
            continue
        cleaned = tok.strip("\"'").rstrip(";").strip("\"'")
        if not cleaned or cleaned in ("then", "&&", "||", "{", "}"):
            continue
        out.append(cleaned)
    return out


def _scp_uploads(cmds):
    """scp lines whose SOURCE is local -> these WRITE the VPS."""
    up = []
    for line in cmds:
        ops = _scp_operands(line)
        if ops and ":" not in ops[0]:
            up.append((ops[0], line))
    return up


def _scp_downloads(cmds):
    """scp lines whose SOURCE is remote -> these READ the VPS."""
    down = []
    for line in cmds:
        ops = _scp_operands(line)
        if ops and ":" in ops[0]:
            down.append((ops[0], line))
    return down


# --------------------------------------------------------------------------- #
# keyword_data.csv: union the server's copy in before pushing ours
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_downloads_the_servers_master_as_an_scp_SOURCE(script):
    """Anchored on the source argument. The old regex matched the upload line's
    DESTINATION too, so removing the download entirely left the test green."""
    downs = _scp_downloads(_commands(script))
    assert any(d.endswith("keyword_data.csv") for d, _ in downs), (
        f"{script.name} never downloads the VPS keyword_data.csv as an scp "
        f"source; downloads found: {[d for d, _ in downs] or 'none'}")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_calls_merge_master_as_code_not_in_a_comment(script):
    cmds = _text(script)
    assert "import merge_master" in cmds, (
        f"{script.name} has no executable merge_master call (a mention in a "
        "comment does not union anything)")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_merge_happens_before_the_reports_are_built_and_before_the_upload(script):
    """Ordering is the point. Merging after `daily` ships a CSV containing the
    team's keywords next to reports rendered without them."""
    cmds = _commands(script)
    merge_at = next(i for i, l in enumerate(cmds) if "import merge_master" in l)
    build_at = next(i for i, l in enumerate(cmds) if "main.py daily" in l)
    upload_at = next(i for i, l in enumerate(cmds)
                     for s, _ in [(_scp_uploads([l]) or [(None, None)])[0]]
                     if s and s.endswith("keyword_data.csv"))
    assert merge_at < build_at, f"{script.name} builds reports before merging"
    assert merge_at < upload_at, f"{script.name} uploads before merging"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_a_failed_download_aborts_instead_of_uploading_blind(script):
    """A failed scp is NOT an empty server. The first fix treated every failure
    as 'no keyword_data.csv on the VPS yet' and then uploaded anyway - the same
    deletion bug through a different door."""
    cmds = _text(script)
    assert re.search(r"test -f [\"']?\$\{?VPS_PATH\}?/keyword_data\.csv", cmds), (
        f"{script.name} does not probe for the remote master with `test -f`, so "
        "it cannot tell 'absent' from 'unreachable'")
    assert re.search(r"exit 1", cmds), (
        f"{script.name} never aborts; a download failure must not fall through "
        "to the upload")


# --------------------------------------------------------------------------- #
# the databases the server owns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_agent_db_is_never_uploaded_wholesale(script):
    """It holds discovered_keywords, which the VPS writes on two crons and the
    Inbox trend arrows read. Overwriting it destroys the server's own history."""
    bad = [line for src, line in _scp_uploads(_commands(script))
           if "agent.db" in src]
    assert not bad, (
        f"{script.name} uploads agent.db wholesale, destroying the VPS's "
        f"discovered_keywords: {bad}")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_app_db_is_never_uploaded(script):
    """Team logins, tasks and activity live only on the server."""
    bad = [line for src, line in _scp_uploads(_commands(script))
           if "app.db" in src]
    assert not bad, f"{script.name} uploads app.db: {bad}"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_the_master_is_backed_up_on_the_server_before_it_is_written(script):
    cmds = _commands(script)
    backup_at = next((i for i, l in enumerate(cmds) if "backups" in l), None)
    assert backup_at is not None, f"{script.name} writes the VPS with no backup"
    upload_at = next(i for i, l in enumerate(cmds)
                     for s, _ in [(_scp_uploads([l]) or [(None, None)])[0]]
                     if s and s.endswith("keyword_data.csv"))
    assert backup_at < upload_at, f"{script.name} backs up after writing"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_the_master_lands_atomically(script):
    """A dashboard read must never see a half-written master."""
    cmds = _text(script)
    assert "keyword_data.csv.tmp" in cmds and "mv -f" in cmds, (
        f"{script.name} does not land keyword_data.csv via a temp name + mv")


# --------------------------------------------------------------------------- #
# MUTATION TESTS - prove the guards above actually bite.
# Each breaks one line the real script depends on and asserts the matching
# check fails. Without these, a vacuous assertion looks identical to a passing
# one, which is exactly how the first version of this file shipped.
# --------------------------------------------------------------------------- #
def _mutate(tmp_path, script, replace, with_):
    """Copy `script` to tmp with one substitution, return a Path-like for it."""
    dst = tmp_path / script.name
    src = script.read_text(encoding="utf-8")
    assert replace in src, f"mutation target not found in {script.name}: {replace!r}"
    dst.write_text(src.replace(replace, with_), encoding="utf-8")
    return dst


def test_mutation_removing_the_download_fails_the_download_check(tmp_path):
    broken = _mutate(
        tmp_path, SH,
        'if ! scp -P "$VPS_PORT" "$VPS_USER@$VPS_HOST:$VPS_PATH/keyword_data.csv" "$VPS_COPY"; then',
        'if false; then')
    with pytest.raises(AssertionError):
        test_downloads_the_servers_master_as_an_scp_SOURCE(broken)


def test_mutation_moving_merge_after_upload_fails_the_ordering_check(tmp_path):
    src = SH.read_text(encoding="utf-8")
    call = ('    "$PYTHON" -c "from src.harvest import merge_master; '
            "c,e = merge_master('$VPS_COPY'); "
            'print(f\'  carried in {c} VPS-only keyword(s), enriched {e}\')"')
    assert call in src
    moved = src.replace(call, "    true") + "\n" + call.strip() + "\n"
    dst = tmp_path / "push-to-vps.sh"
    dst.write_text(moved, encoding="utf-8")
    with pytest.raises(AssertionError):
        test_merge_happens_before_the_reports_are_built_and_before_the_upload(dst)


def test_mutation_adding_an_app_db_upload_fails_the_app_db_check(tmp_path):
    broken = _mutate(
        tmp_path, SH,
        'scp -P "$VPS_PORT" -r reports/latest',
        'scp -P "$VPS_PORT" data/app.db "$VPS_USER@$VPS_HOST:$VPS_PATH/data/app.db"\n'
        'scp -P "$VPS_PORT" -r reports/latest')
    with pytest.raises(AssertionError):
        test_app_db_is_never_uploaded(broken)


def test_mutation_adding_an_agent_db_upload_fails_the_agent_db_check(tmp_path):
    broken = _mutate(
        tmp_path, SH,
        'scp -P "$VPS_PORT" -r reports/latest',
        'scp -P "$VPS_PORT" data/agent.db "$VPS_USER@$VPS_HOST:$VPS_PATH/data/agent.db.tmp"\n'
        'scp -P "$VPS_PORT" -r reports/latest')
    with pytest.raises(AssertionError):
        test_agent_db_is_never_uploaded_wholesale(broken)


def test_mutation_removing_the_abort_fails_the_failure_handling_check(tmp_path):
    src = SH.read_text(encoding="utf-8")
    dst = tmp_path / "push-to-vps.sh"
    dst.write_text(src.replace("test -f '$VPS_PATH/keyword_data.csv'", "true"),
                   encoding="utf-8")
    with pytest.raises(AssertionError):
        test_a_failed_download_aborts_instead_of_uploading_blind(dst)


def test_a_missing_script_fails_rather_than_skips(tmp_path):
    with pytest.raises(AssertionError, match="missing"):
        _commands(tmp_path / "does-not-exist.sh")
