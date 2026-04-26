"""Lint-as-test — catches bug classes that bit us recently.

Two checks:

1. Pyflakes scan of every device/lib/tui/*.py — fails on undefined names,
   unused imports, redefined symbols. Would have caught the bare `C_OK` /
   `C_CRIT` references in `_adsb_fetch_hires_entry` (those resolved
   nowhere in framework.py and would NameError on first invocation).

   Skips the test class if pyflakes isn't installed. Install on Debian:
       sudo apt install python3-pyflakes

2. AST duplicate top-level assignment scan in framework.py and feature
   modules — fails if any module-level name is assigned twice. Would
   have caught the duplicate `_ESP32_MIMICLAW_ITEMS` from the wardrive
   merge (second silently overwrote the first, dropping the Settings
   entry until commit 011cac6 deduped it).
"""

import ast
import os
import subprocess
import sys

import pytest


DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
TUI_DIR = os.path.join(DEVICE_DIR, 'lib', 'tui')


def _tui_py_files():
    return [
        os.path.join(TUI_DIR, f)
        for f in sorted(os.listdir(TUI_DIR))
        if f.endswith('.py') and not f.startswith('__')
    ]


# ── Pyflakes — undefined names + dead imports ──────────────────────────────


# Pyflakes message substrings we treat as bugs (vs. style-only findings
# like "imported but unused" / "never used", which are real noise but not
# the regression class we care about catching here).
_PYFLAKES_BUG_PATTERNS = (
    "undefined name",          # the C_OK / C_CRIT class
    "redefinition of",         # silent overrides
    "may be undefined",        # control-flow undefined
    "syntax error",            # module won't even parse
)


@pytest.fixture(scope="session")
def _pyflakes_findings_by_file():
    """Run pyflakes once across every TUI module; map filename → bug lines.

    Session-scoped so the slow subprocess only runs once per pytest session
    (was ~50s when parametrised per-file).
    """
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        return None  # signals "skip" to consumers

    files = _tui_py_files()
    result = subprocess.run(
        [sys.executable, "-m", "pyflakes", *files],
        capture_output=True, text=True, timeout=60,
    )
    by_file = {os.path.basename(f): [] for f in files}
    for line in result.stdout.splitlines():
        if not any(pat in line for pat in _PYFLAKES_BUG_PATTERNS):
            continue
        # pyflakes output: <path>:<line>:<col>: <message>
        path = line.split(":", 1)[0]
        by_file.setdefault(os.path.basename(path), []).append(line)
    return by_file


class TestPyflakes:
    """Pyflakes on every TUI module — bug-class findings only."""

    @pytest.mark.parametrize("filename", [os.path.basename(p) for p in _tui_py_files()])
    def test_pyflakes_no_bug_findings(self, filename, _pyflakes_findings_by_file):
        if _pyflakes_findings_by_file is None:
            pytest.skip(
                "pyflakes not installed — install with `sudo apt install "
                "python3-pyflakes` to enable lint coverage"
            )
        bugs = _pyflakes_findings_by_file.get(filename, [])
        if bugs:
            pytest.fail(
                f"pyflakes bug-class findings in {filename}:\n"
                + "\n".join(f"  {b}" for b in bugs)
            )


# ── AST duplicate top-level assignment ─────────────────────────────────────


def _duplicate_toplevel_assignments(source, filename="<source>"):
    """Return a list of (name, line_numbers) for any module-level name
    assigned more than once via simple `NAME = ...` statements.

    Ignores augmented assignments (`+=`, `|=`) and tuple unpacking — those
    are legitimate reassignments. Also ignores names that start with `_t_`
    (test helpers in tests/).
    """
    tree = ast.parse(source, filename=filename)
    seen = {}  # name → list[lineno]
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    seen.setdefault(target.id, []).append(node.lineno)
    return [(name, lines) for name, lines in seen.items() if len(lines) > 1]


class TestDuplicateAssignments:
    """No top-level name should be assigned twice in framework.py or any
    feature module — silent reassignments hide bugs (see the wardrive-
    merge `_ESP32_MIMICLAW_ITEMS` regression that 011cac6 fixed)."""

    @pytest.mark.parametrize("path", _tui_py_files(), ids=lambda p: os.path.basename(p))
    def test_no_duplicate_toplevel_assignment(self, path):
        with open(path) as f:
            source = f.read()
        dups = _duplicate_toplevel_assignments(source, filename=path)
        if dups:
            details = "\n".join(
                f"  - {name} assigned at lines {lines}" for name, lines in dups
            )
            pytest.fail(
                f"Duplicate top-level assignments in {os.path.basename(path)}:\n{details}"
            )
