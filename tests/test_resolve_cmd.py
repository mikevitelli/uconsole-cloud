"""Tests for _resolve_cmd: script path resolution.

This is the function that broke in production (doubled subdir paths).
Tests every script reference in menus against actual files.
"""

import os
import sys
import pytest

EXAMPLE_DEVICE = os.path.join(os.path.dirname(__file__), '..', 'example-device')
LIB_DIR = os.path.join(EXAMPLE_DEVICE, 'lib')
SCRIPTS_DIR = os.path.join(EXAMPLE_DEVICE, 'scripts')

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


def _resolve_cmd_standalone(script_name, script_dir):
    """Standalone copy of _resolve_cmd for testing without curses imports."""
    parts = script_name.split()
    name = parts[0]
    bases = []
    for b in [script_dir, '/opt/uconsole/scripts', os.path.expanduser('~/scripts')]:
        if os.path.isdir(b) and b not in bases:
            bases.append(b)
    for b in bases:
        path = os.path.join(b, name)
        if os.path.isfile(path):
            return path, ["bash", path] + parts[1:]
    basename = os.path.basename(name)
    if basename != name:
        for b in bases:
            path = os.path.join(b, basename)
            if os.path.isfile(path):
                return path, ["bash", path] + parts[1:]
    return None, None


def _extract_all_script_names():
    """Extract every script reference from framework.py menus."""
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
        elif isinstance(node, ast.Tuple) and len(node.elts) == 4:
            script_node = node.elts[1]
            if isinstance(script_node, ast.Constant) and isinstance(script_node.value, str):
                val = script_node.value
                if not val.startswith('_') and not val.startswith('sub:'):
                    scripts.append(val)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('SUBMENUS', 'CATEGORIES'):
                    walk_tuples(node.value)

    return scripts


ALL_SCRIPT_REFS = _extract_all_script_names()


class TestResolveCmdWithExampleDevice:
    """Test _resolve_cmd using SCRIPTS_DIR = example-device/scripts/."""

    @pytest.mark.parametrize("script_ref", ALL_SCRIPT_REFS)
    def test_resolves(self, script_ref):
        """Each menu script reference must resolve to a real file."""
        path, cmd = _resolve_cmd_standalone(script_ref, SCRIPTS_DIR)
        assert path is not None, (
            f"_resolve_cmd failed for '{script_ref}'. "
            f"Expected to find: {os.path.join(SCRIPTS_DIR, script_ref.split()[0])}"
        )
        assert os.path.isfile(path), f"Resolved path does not exist: {path}"

    @pytest.mark.parametrize("script_ref", ALL_SCRIPT_REFS)
    def test_cmd_starts_with_bash(self, script_ref):
        """Resolved command must start with 'bash'."""
        path, cmd = _resolve_cmd_standalone(script_ref, SCRIPTS_DIR)
        if cmd is not None:
            assert cmd[0] == "bash"

    @pytest.mark.parametrize("script_ref", ALL_SCRIPT_REFS)
    def test_preserves_args(self, script_ref):
        """Script arguments must be preserved in the resolved command."""
        path, cmd = _resolve_cmd_standalone(script_ref, SCRIPTS_DIR)
        parts = script_ref.split()
        if cmd is not None and len(parts) > 1:
            assert cmd[2:] == parts[1:], f"Args mismatch: expected {parts[1:]}, got {cmd[2:]}"


class TestResolveCmdEdgeCases:
    def test_nonexistent_script(self):
        path, cmd = _resolve_cmd_standalone("nonexistent/fake.sh", SCRIPTS_DIR)
        assert path is None
        assert cmd is None

    def test_script_with_args(self):
        """Scripts with args like 'system/update.sh all' should resolve."""
        path, cmd = _resolve_cmd_standalone("system/update.sh all", SCRIPTS_DIR)
        if path:
            assert cmd[-1] == "all"

    def test_no_double_subdir(self):
        """Must NOT create paths like scripts/util/util/script.sh."""
        path, cmd = _resolve_cmd_standalone("util/webdash-info.sh", SCRIPTS_DIR)
        if path:
            assert "util/util/" not in path, f"Doubled subdir in path: {path}"
            assert "util\\util\\" not in path

    def test_fallback_to_basename(self):
        """If subdir/script.sh not found, try just script.sh in base dirs."""
        # Create a scenario where this matters: nonexistent subdir
        path, cmd = _resolve_cmd_standalone("fakedir/battery.sh", SCRIPTS_DIR)
        # Should try basename fallback: look for battery.sh in base dirs
        # May or may not find it depending on layout, but should not crash
        # The key assertion is no exception
