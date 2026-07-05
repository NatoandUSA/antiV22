"""Pytest configuration + shared fixtures.

Living at the repo root, this file puts the project root on sys.path (so
`import src.<mod>` and `import main` work) and provides the `sandbox` fixture
that runs a test inside an isolated copy of the project. Report-generating
tests therefore never touch the real reports/ tree and are order-independent.
"""
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent

# Never copy generated output, secrets, VCS, or caches into the sandbox.
# Excluding reports/ and data/ is the whole point: the sandbox starts clean,
# so latest_day_dir()-style checks see only what the test itself generates.
_EXCLUDE = {".git", "reports", "data", "__pycache__", ".venv", "venv",
            "node_modules", ".pytest_cache", ".env"}


def _ignore(_dir, names):
    return {n for n in names if n in _EXCLUDE or n.endswith(".pyc")}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Copy the project into a temp dir and chdir there for the test.

    Yields the sandbox path. All relative paths the code uses (reports/,
    data/agent.db, tests/fixtures.json, main.py, README.md, ...) resolve
    inside this throwaway copy, so nothing leaks into the real workspace.
    """
    dst = tmp_path / "proj"
    shutil.copytree(REPO_ROOT, dst, ignore=_ignore)
    monkeypatch.chdir(dst)
    yield dst
