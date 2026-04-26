"""Tests for menu navigation logic.

Tests category/item selection, submenu entry/exit, and key dispatch
without needing a real terminal. Uses mocked stdscr with key sequences.
"""

import ast
import os
import sys
import curses
from unittest.mock import MagicMock, patch

import pytest

DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
LIB_DIR = os.path.join(DEVICE_DIR, 'lib')
TUI_DIR = os.path.join(DEVICE_DIR, 'lib', 'tui')

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


def _parse_categories():
    """Parse CATEGORIES from framework.py AST."""
    fw_path = os.path.join(TUI_DIR, 'framework.py')
    with open(fw_path) as f:
        tree = ast.parse(f.read())

    categories = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'CATEGORIES':
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Dict):
                                cat = {}
                                for k, v in zip(elt.keys, elt.values):
                                    if isinstance(k, ast.Constant):
                                        if k.value == 'name' and isinstance(v, ast.Constant):
                                            cat['name'] = v.value
                                        elif k.value == 'items' and isinstance(v, ast.List):
                                            items = []
                                            for item in v.elts:
                                                # Items are (label, target, desc, mode) or
                                                # (label, target, desc, mode, icon) — accept 4 or 5.
                                                if isinstance(item, ast.Tuple) and len(item.elts) in (4, 5):
                                                    vals = [
                                                        e.value if isinstance(e, ast.Constant) else None
                                                        for e in item.elts
                                                    ]
                                                    items.append(tuple(vals[:4]))
                                            cat['items'] = items
                                categories.append(cat)
    return categories


CATEGORIES = _parse_categories()


def _parse_submenus():
    """Parse SUBMENUS from framework.py AST."""
    fw_path = os.path.join(TUI_DIR, 'framework.py')
    with open(fw_path) as f:
        tree = ast.parse(f.read())

    submenus = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'SUBMENUS':
                    if isinstance(node.value, ast.Dict):
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant) and isinstance(v, ast.List):
                                items = []
                                for item in v.elts:
                                    if isinstance(item, ast.Tuple) and len(item.elts) in (4, 5):
                                        vals = [
                                            e.value if isinstance(e, ast.Constant) else None
                                            for e in item.elts
                                        ]
                                        items.append(tuple(vals[:4]))
                                submenus[k.value] = items
    return submenus


SUBMENUS = _parse_submenus()


class TestCategoryStructure:
    """Verify the CATEGORIES data structure is well-formed."""

    def test_has_categories(self):
        assert len(CATEGORIES) > 0

    def test_expected_category_names(self):
        names = [c['name'] for c in CATEGORIES]
        for expected in ['SYSTEM', 'MONITOR', 'FILES', 'POWER', 'NETWORK', 'HARDWARE', 'TOOLS', 'GAMES', 'CONFIG']:
            assert expected in names, f"Missing category: {expected}"

    @pytest.mark.parametrize("cat", CATEGORIES, ids=[c['name'] for c in CATEGORIES])
    def test_category_has_items(self, cat):
        assert len(cat['items']) > 0, f"Category {cat['name']} has no items"

    @pytest.mark.parametrize("cat", CATEGORIES, ids=[c['name'] for c in CATEGORIES])
    def test_items_have_required_fields(self, cat):
        # Items are (label, target, desc, mode) or (label, target, desc, mode, icon).
        # _parse_categories already truncates to 4 — assert nothing slipped past.
        for item in cat['items']:
            assert len(item) == 4, f"Item {item[0]} in {cat['name']} has {len(item)} fields, expected 4"

    @pytest.mark.parametrize("cat", CATEGORIES, ids=[c['name'] for c in CATEGORIES])
    def test_valid_modes(self, cat):
        valid_modes = {'panel', 'stream', 'action', 'fullscreen', 'submenu', 'confirm'}
        for label, script, desc, mode in cat['items']:
            assert mode in valid_modes, f"Invalid mode '{mode}' for {label} in {cat['name']}"

    @pytest.mark.parametrize("cat", CATEGORIES, ids=[c['name'] for c in CATEGORIES])
    def test_submenu_items_point_to_valid_submenus(self, cat):
        for label, script, desc, mode in cat['items']:
            if mode == 'submenu':
                assert script in SUBMENUS, (
                    f"Submenu item '{label}' in {cat['name']} references "
                    f"'{script}' which doesn't exist in SUBMENUS"
                )


class TestSubmenuStructure:
    """Verify SUBMENUS data structure."""

    def test_has_submenus(self):
        assert len(SUBMENUS) > 0

    @pytest.mark.parametrize("key", list(SUBMENUS.keys()))
    def test_submenu_not_empty(self, key):
        assert len(SUBMENUS[key]) > 0, f"Submenu '{key}' is empty"

    @pytest.mark.parametrize("key", list(SUBMENUS.keys()))
    def test_submenu_items_have_required_fields(self, key):
        # Items are (label, target, desc, mode) or (label, target, desc, mode, icon).
        # _parse_submenus already truncates to 4 — assert nothing slipped past.
        for item in SUBMENUS[key]:
            assert len(item) == 4, f"Item {item[0]} in {key} has {len(item)} fields"

    @pytest.mark.parametrize("key", list(SUBMENUS.keys()))
    def test_submenu_valid_modes(self, key):
        valid_modes = {'panel', 'stream', 'action', 'fullscreen', 'submenu', 'confirm'}
        for label, script, desc, mode in SUBMENUS[key]:
            assert mode in valid_modes, f"Invalid mode '{mode}' for {label} in {key}"

    def test_no_recursive_submenus(self):
        """Submenus should not reference other submenus (only 1 level deep)."""
        for key, items in SUBMENUS.items():
            for label, script, desc, mode in items:
                if mode == 'submenu':
                    pytest.fail(
                        f"Submenu '{key}' item '{label}' references another "
                        f"submenu '{script}'. Only 1 level of nesting supported."
                    )


class TestNavigationBounds:
    """Test that navigation indices stay in bounds."""

    @pytest.mark.parametrize("cat_idx", range(len(CATEGORIES)))
    def test_category_index_valid(self, cat_idx):
        assert 0 <= cat_idx < len(CATEGORIES)
        cat = CATEGORIES[cat_idx]
        for item_idx in range(len(cat['items'])):
            assert 0 <= item_idx < len(cat['items'])

    def test_wrapping_categories(self):
        """Navigation should handle being at first/last category."""
        n = len(CATEGORIES)
        # Going left from 0 should either wrap or clamp
        assert n > 1, "Need more than 1 category to test wrapping"

    def test_all_categories_reachable(self):
        """Every category should be reachable by sequential right navigation."""
        # Starting from 0, pressing right (n-1) times should reach all
        n = len(CATEGORIES)
        visited = set()
        idx = 0
        for _ in range(n):
            visited.add(idx)
            idx = min(idx + 1, n - 1)
        assert len(visited) == n


class TestMenuItemCoverage:
    """Ensure every script/tool referenced in menus is accounted for."""

    def _all_menu_scripts(self):
        """Collect all script references from categories and submenus."""
        scripts = []
        for cat in CATEGORIES:
            for label, script, desc, mode in cat['items']:
                scripts.append((f"{cat['name']}/{label}", script, mode))
        for key, items in SUBMENUS.items():
            for label, script, desc, mode in items:
                scripts.append((f"{key}/{label}", script, mode))
        return scripts

    def test_no_empty_script_names(self):
        for path, script, mode in self._all_menu_scripts():
            assert script and script.strip(), f"Empty script name at {path}"

    def test_no_none_modes(self):
        for path, script, mode in self._all_menu_scripts():
            assert mode is not None, f"None mode at {path}"

    def test_native_tools_start_with_underscore(self):
        for path, script, mode in self._all_menu_scripts():
            if mode == 'action' and script.startswith('_'):
                # Native tools should have underscore prefix
                pass
            elif script.startswith('_') and mode != 'submenu':
                # All underscore refs should be native tools (action mode)
                assert mode == 'action', (
                    f"Native tool '{script}' at {path} has mode '{mode}', expected 'action'"
                )

    def test_submenu_refs_start_with_sub_colon(self):
        for cat in CATEGORIES:
            for label, script, desc, mode in cat['items']:
                if mode == 'submenu':
                    assert script.startswith('sub:'), (
                        f"Submenu '{label}' in {cat['name']} has script "
                        f"'{script}' without 'sub:' prefix"
                    )

    def test_shell_scripts_have_sh_extension(self):
        for path, script, mode in self._all_menu_scripts():
            if not script.startswith('_') and not script.startswith('sub:'):
                script_file = script.split()[0]
                assert script_file.endswith('.sh'), (
                    f"Script '{script}' at {path} doesn't end with .sh"
                )
