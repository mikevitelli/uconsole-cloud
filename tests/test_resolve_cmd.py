"""Tests for tui.framework._resolve_cmd: script path resolution.

Calls the real production function. The previous version defined a
hand-copied standalone helper with different search-base semantics
(included ~/scripts that production does not), so passing tests didn't
certify the production resolver.

This is the function that broke in production (doubled subdir paths).
Tests every script reference in menus against actual files on disk.
"""

import os
import sys
import pytest

DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
LIB_DIR = os.path.join(DEVICE_DIR, 'lib')
SCRIPTS_DIR = os.path.join(DEVICE_DIR, 'scripts')

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

# When framework.py imports, _PKG_ROOT resolves to <repo>/device, so
# SCRIPT_DIR auto-resolves to <repo>/device/scripts — exactly what we
# want for these tests. No env override needed.
from tui.framework import _resolve_cmd  # noqa: E402


# Scripts the menu references but that aren't shipped in the public tree
# (private repos provide them at install time — see test_tui_integrity.py).
# Single source of truth: packaging/private_scripts.txt — also consumed by
# packaging/build-deb.sh.
def _load_private_scripts():
    path = os.path.join(os.path.dirname(__file__), '..', 'packaging', 'private_scripts.txt')
    out = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                out.add(line)
    return out

KNOWN_PRIVATE_SCRIPTS = _load_private_scripts()


def _extract_all_script_names():
    """Extract every (non-private) script reference from framework.py menus."""
    import ast
    fw_path = os.path.join(LIB_DIR, 'tui', 'framework.py')
    with open(fw_path) as f:
        tree = ast.parse(f.read())

    scripts = []

    def walk_tuples(node):
        if isinstance(node, ast.Dict):
            for v in node.values:
                walk_tuples(v)
        elif isinstance(node, ast.List):
            for elt in node.elts:
                walk_tuples(elt)
        elif isinstance(node, ast.Tuple) and len(node.elts) in (4, 5):
            script_node = node.elts[1]
            if isinstance(script_node, ast.Constant) and isinstance(script_node.value, str):
                val = script_node.value
                if val.startswith('_') or val.startswith('sub:'):
                    return
                if val.split()[0] in KNOWN_PRIVATE_SCRIPTS:
                    return
                scripts.append(val)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('SUBMENUS', 'CATEGORIES'):
                    walk_tuples(node.value)

    return scripts


ALL_SCRIPT_REFS = _extract_all_script_names()


class TestResolveCmd:
    """Test the real _resolve_cmd against every menu reference."""

    @pytest.mark.parametrize("script_ref", ALL_SCRIPT_REFS)
    def test_resolves(self, script_ref):
        """Each menu script reference must resolve to a real file."""
        path, cmd = _resolve_cmd(script_ref)
        assert path is not None, (
            f"_resolve_cmd failed for '{script_ref}'. "
            f"Expected to find: {os.path.join(SCRIPTS_DIR, script_ref.split()[0])}"
        )
        assert os.path.isfile(path), f"Resolved path does not exist: {path}"

    @pytest.mark.parametrize("script_ref", ALL_SCRIPT_REFS)
    def test_cmd_starts_with_bash(self, script_ref):
        """Resolved command must start with 'bash'."""
        _, cmd = _resolve_cmd(script_ref)
        if cmd is not None:
            assert cmd[0] == "bash"

    @pytest.mark.parametrize("script_ref", ALL_SCRIPT_REFS)
    def test_preserves_args(self, script_ref):
        """Script arguments must be preserved in the resolved command."""
        _, cmd = _resolve_cmd(script_ref)
        parts = script_ref.split()
        if cmd is not None and len(parts) > 1:
            assert cmd[2:] == parts[1:], (
                f"Args mismatch: expected {parts[1:]}, got {cmd[2:]}"
            )


class TestResolveCmdEdgeCases:
    def test_nonexistent_script(self):
        path, cmd = _resolve_cmd("nonexistent/fake.sh")
        assert path is None
        assert cmd is None

    def test_script_with_args(self):
        """Scripts with args like 'system/update.sh all' should resolve."""
        path, cmd = _resolve_cmd("system/update.sh all")
        if path:
            assert cmd[-1] == "all"

    def test_no_double_subdir(self):
        """Must NOT create paths like scripts/util/util/script.sh."""
        path, _ = _resolve_cmd("util/webdash-info.sh")
        if path:
            assert "util/util/" not in path, f"Doubled subdir in path: {path}"
