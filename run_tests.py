"""Sandbox test runner - a minimal pytest shim + importlib loop.

The cloud sandbox has no pytest wheel available, so this runner implements the
small pytest surface the suite actually uses (fixture, mark.parametrize,
raises, approx, skip, monkeypatch, tmp_path, plus conftest fixtures like
`sandbox` and per-module fixtures like `client`) and runs every tests/test_*.py
via importlib. Exit code 0 only when every test passes.

NOT shipped to production behavior - a dev tool. On the owner's PC / CI keep
using real pytest (`pytest -q`).
"""
import importlib.util
import inspect
import os
import socket
import sys
import tempfile
import traceback
from pathlib import Path

socket.setdefaulttimeout(4)
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("YTX_IMPORT_TOKEN", "test-token")


# --------------------------- pytest shim -----------------------------------

class _Skip(Exception):
    pass


class _Raises:
    def __init__(self, exc, match=None):
        self.exc, self.match = exc, match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"did not raise {self.exc}")
        if not issubclass(et, self.exc):
            return False
        if self.match is not None:
            import re
            if not re.search(self.match, str(ev)):
                raise AssertionError(f"{ev!r} !~ {self.match!r}")
        self.value = ev
        return True


class _Approx:
    def __init__(self, v, rel=None, abs=None):  # noqa: A002
        self.v, self.rel, self.abs = v, rel, abs

    def __eq__(self, other):
        rel = 1e-6 if self.rel is None else self.rel
        tol = max(abs(self.v) * rel, self.abs or 1e-12)
        return abs(other - self.v) <= tol

    def __repr__(self):
        return f"approx({self.v})"


class _Mark:
    def parametrize(self, names, values):
        def deco(fn):
            fn._param = (names, values)
            return fn
        return deco

    def __getattr__(self, _):
        def deco(fn):
            return fn
        return deco


class _PytestShim:
    mark = _Mark()

    @staticmethod
    def fixture(fn=None, **kw):
        def deco(f):
            f._is_fixture = True
            f._autouse = bool(kw.get("autouse"))
            return f
        return deco(fn) if fn else deco

    raises = _Raises
    approx = _Approx

    @staticmethod
    def skip(reason=""):
        raise _Skip(reason)

    @staticmethod
    def fail(reason=""):
        raise AssertionError(reason)

    class importorskip:
        def __new__(cls, name, **kw):
            try:
                return __import__(name)
            except ImportError:
                raise _Skip(name)


sys.modules["pytest"] = _PytestShim()  # type: ignore[assignment]
import pytest  # noqa: E402  (the shim)


class MonkeyPatch:
    def __init__(self):
        self._attrs, self._items, self._envs, self._cwd = [], [], [], None

    def setattr(self, target, name, value=None, raising=True):
        if isinstance(target, str) and value is None:
            value = name
            target, _, name = target.rpartition(".")
        if isinstance(target, str):
            import importlib
            target = importlib.import_module(target)
        had = hasattr(target, name)
        self._attrs.append((target, name, getattr(target, name, None), had))
        setattr(target, name, value)

    def setitem(self, d, k, v):
        self._items.append((d, k, d.get(k), k in d))
        d[k] = v

    def delitem(self, d, k, raising=True):
        if k in d:
            self._items.append((d, k, d.get(k), True))
            del d[k]

    def setenv(self, k, v):
        self._envs.append((k, os.environ.get(k)))
        os.environ[k] = str(v)

    def delenv(self, k, raising=True):
        self._envs.append((k, os.environ.get(k)))
        os.environ.pop(k, None)

    def chdir(self, p):
        if self._cwd is None:
            self._cwd = os.getcwd()
        os.chdir(p)

    def undo(self):
        for t, n, old, had in reversed(self._attrs):
            if had:
                setattr(t, n, old)
            else:
                delattr(t, n)
        for d, k, old, had in reversed(self._items):
            if had:
                d[k] = old
            else:
                d.pop(k, None)
        for k, old in reversed(self._envs):
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        if self._cwd is not None:
            os.chdir(self._cwd)


# --------------------------- fixture resolution ----------------------------

def _load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = m
    spec.loader.exec_module(m)
    return m


def _conftest():
    return _load_module(ROOT / "conftest.py")


def _resolve_fixture(name, module, conftest, mp, tmpdir, finalizers, cache):
    if name in cache:
        return cache[name]
    if name == "monkeypatch":
        cache[name] = mp
        return mp
    if name == "tmp_path":
        p = Path(tempfile.mkdtemp(dir=tmpdir))
        cache[name] = p
        return p
    fn = getattr(module, name, None) or getattr(conftest, name, None)
    if fn is None or not getattr(fn, "_is_fixture", False):
        raise RuntimeError(f"unknown fixture {name}")
    kwargs = {a: _resolve_fixture(a, module, conftest, mp, tmpdir, finalizers,
                                  cache)
              for a in inspect.signature(fn).parameters}
    if inspect.isgeneratorfunction(fn):
        gen = fn(**kwargs)
        val = next(gen)
        finalizers.append(gen)
    else:
        val = fn(**kwargs)
    cache[name] = val
    return val


def _run_test(fn, module, conftest, tmpdir):
    mp = MonkeyPatch()
    finalizers, cache = [], {}
    cwd = os.getcwd()
    try:
        # autouse fixtures (module-level then conftest) run for every test
        for src_mod in (conftest, module):
            for aname in dir(src_mod):
                afn = getattr(src_mod, aname, None)
                if (callable(afn) and getattr(afn, "_is_fixture", False)
                        and getattr(afn, "_autouse", False)):
                    _resolve_fixture(aname, module, conftest, mp, tmpdir,
                                     finalizers, cache)
        kwargs = {a: _resolve_fixture(a, module, conftest, mp, tmpdir,
                                      finalizers, cache)
                  for a in inspect.signature(fn).parameters}
        fn(**kwargs)
        return "pass", None
    except _Skip as s:
        return "skip", str(s)
    except AssertionError:
        return "fail", traceback.format_exc()
    except SystemExit:
        # e.g. the MCP client sys.exit()s when the network is unreachable in
        # the sandbox - report it as an error, never kill the whole loop
        return "error", traceback.format_exc()
    except Exception:  # noqa: BLE001
        return "error", traceback.format_exc()
    finally:
        for gen in reversed(finalizers):
            try:
                next(gen, None)
            except Exception:  # noqa: BLE001
                pass
        mp.undo()
        os.chdir(cwd)


def main():
    conftest = _conftest()
    files = sorted((ROOT / "tests").glob("test_*.py"))
    if len(sys.argv) > 1:                      # substring filters
        files = [f for f in files
                 if any(a in f.name for a in sys.argv[1:])]
    total = passed = skipped = 0
    failures = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            try:
                module = _load_module(f)
            except Exception:  # noqa: BLE001
                failures.append((f.name, traceback.format_exc()))
                print(f"[LOAD-ERROR] {f.name}")
                continue
            for name in sorted(dir(module)):
                if not name.startswith("test_"):
                    continue
                fn = getattr(module, name)
                if not callable(fn):
                    continue
                variants = [((), fn)]
                if hasattr(fn, "_param"):
                    names, values = fn._param
                    keys = [k.strip() for k in names.split(",")]
                    variants = []
                    for v in values:
                        vals = v if isinstance(v, (tuple, list)) else (v,)
                        bound = dict(zip(keys, vals))

                        def make(fn=fn, bound=bound):
                            def run(**kw):
                                return fn(**{**bound, **kw})
                            sig = inspect.signature(fn)
                            keep = [p for p in sig.parameters
                                    if p not in bound]
                            run.__signature__ = inspect.Signature(
                                [sig.parameters[p] for p in keep])
                            return run
                        variants.append((tuple(bound.values()), make()))
                for pid, vfn in variants:
                    total += 1
                    label = f"{f.name}::{name}" + (f"[{pid}]" if pid else "")
                    status, err = _run_test(vfn, module, conftest, tmpdir)
                    if status == "pass":
                        passed += 1
                        print(f"PASS {label}")
                    elif status == "skip":
                        skipped += 1
                        print(f"SKIP {label} ({err})")
                    else:
                        failures.append((label, err))
                        print(f"FAIL {label}")
    print(f"\n==== {passed}/{total} passed, {skipped} skipped, "
          f"{len(failures)} failed ====")
    for label, err in failures:
        print(f"\n--- {label} ---\n{err}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
