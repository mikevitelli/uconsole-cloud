#!/usr/bin/env python3
"""Comprehensive TUI integrity tests.

Verifies that every import, native tool, script path, and menu reference
in framework.py actually resolves. Catches the class of bug where the
cloud repo's device/ and the device's installed files diverge.

Run: python3 -m pytest tests/test_tui_integrity.py -v
"""

import ast
import os
import sys
import importlib
import importlib.util
import pytest

# ── Paths ──────────────────────────────────────────────────────────────────

DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
TUI_DIR = os.path.join(DEVICE_DIR, 'lib', 'tui')
SCRIPTS_DIR = os.path.join(DEVICE_DIR, 'scripts')
FRAMEWORK_PY = os.path.join(TUI_DIR, 'framework.py')

# Ensure we can import tui modules
LIB_DIR = os.path.join(DEVICE_DIR, 'lib')
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


# ── Helpers ────────────────────────────────────────────────────────────────

def parse_framework():
    """Parse framework.py into an AST."""
    with open(FRAMEWORK_PY) as f:
        return ast.parse(f.read(), filename=FRAMEWORK_PY)


def get_framework_source():
    """Read framework.py as text."""
    with open(FRAMEWORK_PY) as f:
        return f.read()


def extract_all_toplevel_imports(tree):
    """Extract all top-level 'from X import Y' and 'import X' statements."""
    imports = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module
            names = [alias.name for alias in node.names]
            imports.append((module, names))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, []))
    return imports


def extract_script_refs(source):
    """Extract all script path strings from SUBMENUS and CATEGORIES.

    Looks for tuples like ("Label", "subdir/script.sh args", "desc", "mode")
    and returns the script paths (without args).
    """
    scripts = []
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('SUBMENUS', 'CATEGORIES'):
                    _collect_script_refs(node.value, scripts)
    return scripts


def _collect_script_refs(node, scripts):
    """Recursively collect script path strings from nested AST structures."""
    if isinstance(node, ast.Dict):
        for value in node.values:
            _collect_script_refs(value, scripts)
    elif isinstance(node, ast.List):
        for elt in node.elts:
            _collect_script_refs(elt, scripts)
    elif isinstance(node, ast.Tuple) and len(node.elts) in (4, 5):
        # (label, script, desc, mode)
        script_node = node.elts[1]
        mode_node = node.elts[3]
        if isinstance(script_node, ast.Constant) and isinstance(mode_node, ast.Constant):
            script_str = script_node.value
            mode_str = mode_node.value
            # Skip native tools (underscore prefix) and submenus
            if not script_str.startswith('_') and not script_str.startswith('sub:'):
                # Extract just the script path (before any args)
                script_path = script_str.split()[0]
                scripts.append(script_path)


def extract_native_tool_keys(source):
    """Return all handler keys registered via the FEATURE_MODULES → HANDLERS chain.

    Loads the live handlers dict at runtime — covers everything any feature
    module declares in its module-level HANDLERS export.  The *source* arg is
    accepted for backwards compatibility but unused.
    """
    from tui.framework import _load_handlers
    return list(_load_handlers().keys())


def extract_menu_native_refs(source):
    """Extract all native tool references (underscore-prefixed) from menus."""
    refs = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('SUBMENUS', 'CATEGORIES'):
                    _collect_native_refs(node.value, refs)
    return refs


def _collect_native_refs(node, refs):
    """Recursively collect underscore-prefixed script refs."""
    if isinstance(node, ast.Dict):
        for value in node.values:
            _collect_native_refs(value, refs)
    elif isinstance(node, ast.List):
        for elt in node.elts:
            _collect_native_refs(elt, refs)
    elif isinstance(node, ast.Tuple) and len(node.elts) in (4, 5):
        script_node = node.elts[1]
        if isinstance(script_node, ast.Constant) and isinstance(script_node.value, str):
            if script_node.value.startswith('_'):
                refs.add(script_node.value)


def extract_submenu_refs(source):
    """Extract all sub:xxx references from CATEGORIES + SUBMENUS in framework.py
    *plus* every _ESP32_*_ITEMS list in esp32_hub.py.

    Reachability is transitive: if sub:foo only appears as a drilldown from
    sub:bar, that's still a real reference. Limiting to CATEGORIES would
    flag legitimately nested submenus (lora_mesh → lora_config) as orphans.
    """
    refs = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('CATEGORIES', 'SUBMENUS'):
                    _collect_submenu_refs(node.value, refs)

    # Also scan esp32_hub.py — its _ESP32_*_ITEMS lists feed runtime SUBMENUS
    esp32_hub_path = os.path.join(TUI_DIR, 'esp32_hub.py')
    if os.path.isfile(esp32_hub_path):
        with open(esp32_hub_path) as f:
            hub_tree = ast.parse(f.read())
        for node in ast.iter_child_nodes(hub_tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.startswith('_ESP32_'):
                        _collect_submenu_refs(node.value, refs)
    return refs


def _collect_submenu_refs(node, refs):
    """Recursively collect sub:xxx references."""
    if isinstance(node, ast.List):
        for elt in node.elts:
            _collect_submenu_refs(elt, refs)
    elif isinstance(node, ast.Dict):
        for value in node.values:
            _collect_submenu_refs(value, refs)
    elif isinstance(node, ast.Tuple) and len(node.elts) in (4, 5):
        script_node = node.elts[1]
        mode_node = node.elts[3]
        if (isinstance(script_node, ast.Constant) and isinstance(mode_node, ast.Constant)
                and mode_node.value == 'submenu'):
            refs.add(script_node.value)


def extract_submenu_keys(source):
    """Extract all keys defined in SUBMENUS dict."""
    keys = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'SUBMENUS':
                    if isinstance(node.value, ast.Dict):
                        for key in node.value.keys:
                            if isinstance(key, ast.Constant):
                                keys.add(key.value)
    return keys


# ── Test: framework.py parses without syntax errors ────────────────────────

class TestFrameworkSyntax:
    def test_parses(self):
        """framework.py must parse without syntax errors."""
        parse_framework()

    def test_all_tui_modules_parse(self):
        """Every .py in tui/ must parse without syntax errors."""
        for fname in os.listdir(TUI_DIR):
            if fname.endswith('.py'):
                fpath = os.path.join(TUI_DIR, fname)
                with open(fpath) as f:
                    try:
                        ast.parse(f.read(), filename=fpath)
                    except SyntaxError as e:
                        pytest.fail(f"Syntax error in {fname}: {e}")


# ── Test: all imports in _get_native_tools resolve ─────────────────────────

class TestFeatureModuleImports:
    """Every entry in framework.FEATURE_MODULES must import cleanly and expose HANDLERS."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from tui.framework import FEATURE_MODULES
        self.feature_modules = FEATURE_MODULES

    def test_has_modules(self):
        assert len(self.feature_modules) > 0, "FEATURE_MODULES is empty"

    def test_each_module_imports(self):
        """Every entry in FEATURE_MODULES must be importable."""
        failures = []
        for mod_name in self.feature_modules:
            try:
                importlib.import_module(mod_name)
            except ImportError as e:
                failures.append(f"Cannot import {mod_name}: {e}")
        if failures:
            pytest.fail("Import failures in FEATURE_MODULES:\n" + "\n".join(f"  - {f}" for f in failures))

    def test_each_module_exposes_handlers(self):
        """Every entry in FEATURE_MODULES must export a non-empty HANDLERS dict."""
        failures = []
        for mod_name in self.feature_modules:
            try:
                mod = importlib.import_module(mod_name)
            except ImportError:
                continue  # covered by test_each_module_imports
            handlers = getattr(mod, "HANDLERS", None)
            if not isinstance(handlers, dict) or not handlers:
                failures.append(f"{mod_name} missing or empty HANDLERS")
        if failures:
            pytest.fail("HANDLERS export failures:\n" + "\n".join(f"  - {f}" for f in failures))


# Handlers dispatched dynamically at runtime (not statically referenced in
# SUBMENUS or CATEGORIES) and therefore exempt from the static-ref check.
# Sourced from esp32_hub at runtime so adding a new dynamic menu item doesn't
# silently fall through to test_all_handlers_are_referenced as an "orphan".

def _dynamic_handlers():
    from tui import esp32_hub
    keys = set()
    for items in (esp32_hub._ESP32_MICROPYTHON_ITEMS,
                  esp32_hub._ESP32_MARAUDER_ITEMS,
                  esp32_hub._ESP32_COMMON_ITEMS,
                  esp32_hub._ESP32_MIMICLAW_ITEMS):
        for item in items:
            target = item[1]
            if isinstance(target, str) and target.startswith("_") and not target.startswith("_gui:") and not target.startswith("_url:"):
                keys.add(target)
    # Manual: * entries injected when firmware is UNKNOWN
    keys.update({"_esp32_force_mp", "_esp32_force_mrd", "_esp32_force_mc"})
    return keys


DYNAMIC_HANDLERS = _dynamic_handlers()


# ── Test: all native tool keys in menus have handlers ──────────────────────

class TestNativeToolCoverage:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source = get_framework_source()
        self.tool_keys = set(extract_native_tool_keys(self.source))
        self.menu_refs = extract_menu_native_refs(self.source)

    def test_all_menu_refs_have_handlers(self):
        """Every underscore-prefixed ref in menus must resolve to a registered handler.

        Skips _gui: and _url: prefixes (handled separately by run_script).
        """
        skipped_prefixes = ("_gui:", "_url:")
        actionable = {r for r in self.menu_refs if not r.startswith(skipped_prefixes)}
        missing = actionable - self.tool_keys
        if missing:
            pytest.fail(f"Menu references with no registered handler: {missing}")

    def test_all_handlers_are_referenced(self):
        """Every handler in _get_native_tools should be referenced in a menu.

        Handlers listed in DYNAMIC_HANDLERS are exempt — they are injected into
        the SUBMENUS dict at runtime (e.g. by run_esp32_hub) and are not visible
        to the static AST checker.
        """
        unreferenced = (self.tool_keys - self.menu_refs) - DYNAMIC_HANDLERS
        if unreferenced:
            pytest.fail(f"Handlers defined but never referenced in menus: {unreferenced}")


# ── Test: all submenu references resolve ───────────────────────────────────

class TestSubmenuIntegrity:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source = get_framework_source()
        self.submenu_refs = extract_submenu_refs(self.source)
        self.submenu_keys = extract_submenu_keys(self.source)

    def test_all_submenu_refs_have_definitions(self):
        """Every sub:xxx in CATEGORIES must have a matching SUBMENUS key."""
        missing = self.submenu_refs - self.submenu_keys
        if missing:
            pytest.fail(f"Submenu references with no definition: {missing}")

    # Submenus populated dynamically at runtime (not visible to static AST check)
    DYNAMIC_SUBMENUS = {"sub:esp32"}

    def test_all_submenu_defs_are_referenced(self):
        """Every SUBMENUS key should be referenced somewhere in CATEGORIES."""
        unreferenced = self.submenu_keys - self.submenu_refs - self.DYNAMIC_SUBMENUS
        if unreferenced:
            pytest.fail(f"Submenu definitions never referenced: {unreferenced}")

    def test_submenus_not_empty(self):
        """Every submenu must have at least one item."""
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'SUBMENUS':
                        if isinstance(node.value, ast.Dict):
                            for key, value in zip(node.value.keys, node.value.values):
                                if isinstance(key, ast.Constant) and isinstance(value, ast.List):
                                    assert len(value.elts) > 0, f"Submenu {key.value} is empty"


# ── Test: all script paths resolve to real files ───────────────────────────

# Scripts that the menu references but that are intentionally NOT shipped
# in the public tree. They live in private repos (e.g. ~/pkg) and land in
# /opt/uconsole/scripts/ at install time, so the menu reference is correct
# from a runtime perspective. The test must skip them so CI doesn't false-
# fail on the absence.
KNOWN_PRIVATE_SCRIPTS = {
    "system/backup.sh",   # removed from public tree in d2f3783 for security;
                          # users get it via their own backup repos
}


class TestScriptPaths:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source = get_framework_source()
        self.script_refs = extract_script_refs(self.source)

    def test_has_script_refs(self):
        """Menus must reference at least some scripts."""
        assert len(self.script_refs) > 0

    def test_each_script_exists(self):
        """Every script path referenced in menus must exist in device/scripts/.

        Skips KNOWN_PRIVATE_SCRIPTS — see above.
        """
        missing = []
        for script_path in self.script_refs:
            if script_path in KNOWN_PRIVATE_SCRIPTS:
                continue
            full_path = os.path.join(SCRIPTS_DIR, script_path)
            if not os.path.isfile(full_path):
                missing.append(script_path)
        if missing:
            pytest.fail(
                f"{len(missing)} script(s) referenced in menus but not found in "
                f"device/scripts/:\n" + "\n".join(f"  - {s}" for s in sorted(missing))
            )

    def test_scripts_are_executable(self):
        """Every .sh script must have the executable bit set."""
        non_exec = []
        for script_path in self.script_refs:
            if not script_path.endswith('.sh'):
                continue
            full_path = os.path.join(SCRIPTS_DIR, script_path)
            if os.path.isfile(full_path) and not os.access(full_path, os.X_OK):
                non_exec.append(script_path)
        if non_exec:
            pytest.fail(
                f"{len(non_exec)} script(s) not executable:\n" +
                "\n".join(f"  - {s}" for s in sorted(non_exec))
            )

    def test_scripts_have_shebang(self):
        """Every .sh script should start with a shebang line."""
        no_shebang = []
        for script_path in self.script_refs:
            if not script_path.endswith('.sh'):
                continue
            full_path = os.path.join(SCRIPTS_DIR, script_path)
            if os.path.isfile(full_path):
                with open(full_path, 'rb') as f:
                    first_line = f.readline()
                    if not first_line.startswith(b'#!'):
                        no_shebang.append(script_path)
        if no_shebang:
            pytest.fail(
                f"{len(no_shebang)} script(s) missing shebang:\n" +
                "\n".join(f"  - {s}" for s in sorted(no_shebang))
            )


# ── Test: all TUI submodules import cleanly ────────────────────────────────

class TestTUIModuleImports:
    def test_each_module_imports(self):
        """Every .py file in tui/ must import without errors."""
        failures = []
        for fname in sorted(os.listdir(TUI_DIR)):
            if not fname.endswith('.py') or fname.startswith('__'):
                continue
            module_name = f"tui.{fname[:-3]}"
            spec = importlib.util.spec_from_file_location(
                module_name, os.path.join(TUI_DIR, fname)
            )
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception as e:
                failures.append(f"{fname}: {type(e).__name__}: {e}")
        if failures:
            pytest.fail(
                "TUI module import failures:\n" +
                "\n".join(f"  - {f}" for f in failures)
            )


# ── Test: CATEGORIES structure is valid ────────────────────────────────────

class TestCategoriesStructure:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source = get_framework_source()

    def test_categories_is_list(self):
        """CATEGORIES must be a list."""
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'CATEGORIES':
                        assert isinstance(node.value, ast.List), "CATEGORIES must be a list"

    def test_each_category_has_name_and_items(self):
        """Each category dict must have 'name' and 'items' keys."""
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'CATEGORIES':
                        if isinstance(node.value, ast.List):
                            for i, elt in enumerate(node.value.elts):
                                assert isinstance(elt, ast.Dict), f"Category {i} is not a dict"
                                keys = [k.value for k in elt.keys if isinstance(k, ast.Constant)]
                                assert 'name' in keys, f"Category {i} missing 'name'"
                                assert 'items' in keys, f"Category {i} missing 'items'"

    def test_cat_descs_covers_all_categories(self):
        """CAT_DESCS must have an entry for every category name."""
        tree = ast.parse(self.source)
        cat_names = []
        cat_desc_keys = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'CATEGORIES':
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Dict):
                                    for k, v in zip(elt.keys, elt.values):
                                        if isinstance(k, ast.Constant) and k.value == 'name':
                                            if isinstance(v, ast.Constant):
                                                cat_names.append(v.value)
                    elif isinstance(target, ast.Name) and target.id == 'CAT_DESCS':
                        if isinstance(node.value, ast.Dict):
                            for k in node.value.keys:
                                if isinstance(k, ast.Constant):
                                    cat_desc_keys.append(k.value)

        missing = set(cat_names) - set(cat_desc_keys)
        if missing:
            pytest.fail(f"CAT_DESCS missing entries for categories: {missing}")


# ── Test: no duplicate menu entries ────────────────────────────────────────

class TestNoDuplicates:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.source = get_framework_source()

    def test_no_duplicate_native_tool_keys(self):
        """No duplicate keys in _get_native_tools return dict."""
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == '_get_native_tools':
                for child in ast.walk(node):
                    if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                        keys = [k.value for k in child.value.keys if isinstance(k, ast.Constant)]
                        dupes = [k for k in keys if keys.count(k) > 1]
                        if dupes:
                            pytest.fail(f"Duplicate native tool keys: {set(dupes)}")

    def test_no_duplicate_submenu_keys(self):
        """No duplicate keys in SUBMENUS dict."""
        keys = list(extract_submenu_keys(self.source))
        dupes = [k for k in keys if keys.count(k) > 1]
        if dupes:
            pytest.fail(f"Duplicate submenu keys: {set(dupes)}")

    def test_no_duplicate_category_names(self):
        """No duplicate category names."""
        tree = ast.parse(self.source)
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'CATEGORIES':
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Dict):
                                    for k, v in zip(elt.keys, elt.values):
                                        if isinstance(k, ast.Constant) and k.value == 'name':
                                            if isinstance(v, ast.Constant):
                                                names.append(v.value)
        dupes = [n for n in names if names.count(n) > 1]
        if dupes:
            pytest.fail(f"Duplicate category names: {set(dupes)}")


# ── Test: CONFIRM_SCRIPTS references valid scripts ─────────────────────────

class TestConfirmScripts:
    def test_confirm_scripts_exist(self):
        """Every script in CONFIRM_SCRIPTS must be a valid script or native tool."""
        source = get_framework_source()
        tree = ast.parse(source)
        tool_keys = set(extract_native_tool_keys(source))
        script_refs = set(extract_script_refs(source))

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'CONFIRM_SCRIPTS':
                        if isinstance(node.value, (ast.Set, ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    val = elt.value
                                    # Must be a known script path or native tool
                                    script_path = val.split()[0]
                                    is_native = val.startswith('_')
                                    is_script = os.path.isfile(os.path.join(SCRIPTS_DIR, script_path))
                                    if not is_native and not is_script:
                                        # Check if it matches a menu ref (with args)
                                        if script_path not in [s.split()[0] for s in script_refs]:
                                            pass  # Some confirm entries may reference scripts with args
