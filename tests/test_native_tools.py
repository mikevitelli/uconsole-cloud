"""Tests for native tool imports and handlers.

Verifies every native tool (_theme, _monitor, etc.) can be imported
and has a callable handler. This catches the exact class of bug that
broke production (missing run_trackball_scroll_toggle).
"""

import ast
import importlib
import importlib.util
import os
import sys

import pytest

DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
LIB_DIR = os.path.join(DEVICE_DIR, 'lib')
TUI_DIR = os.path.join(DEVICE_DIR, 'lib', 'tui')

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


def _extract_native_tool_imports():
    """Extract all imports from _get_native_tools function."""
    fw_path = os.path.join(TUI_DIR, 'framework.py')
    with open(fw_path) as f:
        tree = ast.parse(f.read())

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_get_native_tools':
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    for alias in child.names:
                        imports.append((child.module, alias.name))
    return imports


def _extract_native_tool_map():
    """Extract the key->function mapping from _get_native_tools return dict."""
    fw_path = os.path.join(TUI_DIR, 'framework.py')
    with open(fw_path) as f:
        tree = ast.parse(f.read())

    tool_map = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_get_native_tools':
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                    for key, val in zip(child.value.keys, child.value.values):
                        if isinstance(key, ast.Constant):
                            # Extract the function name from lambda scr: func(scr)
                            func_name = None
                            if isinstance(val, ast.Lambda) and isinstance(val.body, ast.Call):
                                if isinstance(val.body.func, ast.Name):
                                    func_name = val.body.func.id
                            tool_map[key.value] = func_name
    return tool_map


NATIVE_IMPORTS = _extract_native_tool_imports()
NATIVE_TOOL_MAP = _extract_native_tool_map()


class TestNativeToolImportsResolve:
    """Every import in _get_native_tools must resolve."""

    @pytest.mark.parametrize(
        "module,name",
        NATIVE_IMPORTS,
        ids=[f"{m}.{n}" for m, n in NATIVE_IMPORTS]
    )
    def test_import_resolves(self, module, name):
        mod = importlib.import_module(module)
        assert hasattr(mod, name), (
            f"{module}.{name} does not exist. "
            f"Available: {[x for x in dir(mod) if x.startswith('run_')]}"
        )

    @pytest.mark.parametrize(
        "module,name",
        NATIVE_IMPORTS,
        ids=[f"{m}.{n}" for m, n in NATIVE_IMPORTS]
    )
    def test_imported_is_callable(self, module, name):
        mod = importlib.import_module(module)
        obj = getattr(mod, name)
        assert callable(obj), f"{module}.{name} is not callable"


class TestNativeToolMap:
    """Every tool key must have a valid handler function."""

    @pytest.mark.parametrize(
        "tool_key,func_name",
        list(NATIVE_TOOL_MAP.items()),
        ids=list(NATIVE_TOOL_MAP.keys())
    )
    def test_handler_function_identified(self, tool_key, func_name):
        assert func_name is not None, (
            f"Tool '{tool_key}' has no identifiable handler function"
        )

    def test_all_handler_functions_in_imports_or_framework(self):
        """Every function referenced in the tool map must be imported or defined in framework.py."""
        imported_names = {name for _, name in NATIVE_IMPORTS}
        # Some handlers (like run_process_manager) are defined in framework.py itself
        fw_path = os.path.join(TUI_DIR, 'framework.py')
        with open(fw_path) as f:
            fw_tree = ast.parse(f.read())
        fw_funcs = {
            node.name for node in ast.walk(fw_tree)
            if isinstance(node, ast.FunctionDef)
        }
        available = imported_names | fw_funcs
        for tool_key, func_name in NATIVE_TOOL_MAP.items():
            if func_name is not None:
                assert func_name in available, (
                    f"Tool '{tool_key}' references '{func_name}' "
                    f"which is not imported or defined in framework.py"
                )


class TestTUIModuleExports:
    """Each TUI submodule should export what framework.py expects."""

    TUI_MODULES = [f for f in os.listdir(TUI_DIR)
                   if f.endswith('.py') and not f.startswith('__')]

    @pytest.mark.parametrize("module_file", TUI_MODULES)
    def test_module_imports_cleanly(self, module_file):
        module_name = f"tui.{module_file[:-3]}"
        try:
            importlib.import_module(module_name)
        except Exception as e:
            pytest.fail(f"Failed to import {module_name}: {e}")

    @pytest.mark.parametrize("module_file", TUI_MODULES)
    def test_module_has_run_functions(self, module_file):
        """Each non-framework module should export at least one run_ function."""
        # Utility modules that support TUI handlers but aren't handlers themselves
        UTILITY_MODULES = {'framework.py', 'esp32_detect.py', 'esp32_flash.py'}
        if module_file in UTILITY_MODULES:
            pytest.skip(f"{module_file} is a utility module")
        module_name = f"tui.{module_file[:-3]}"
        mod = importlib.import_module(module_name)
        run_funcs = [x for x in dir(mod) if x.startswith('run_')]
        assert len(run_funcs) > 0, (
            f"{module_name} has no run_* functions. "
            f"All exports: {[x for x in dir(mod) if not x.startswith('_')]}"
        )

    def test_no_orphan_modules(self):
        """Every TUI module (except framework.py) should be imported by framework.py."""
        fw_path = os.path.join(TUI_DIR, 'framework.py')
        with open(fw_path) as f:
            fw_source = f.read()

        for module_file in self.TUI_MODULES:
            if module_file == 'framework.py':
                continue
            module_base = module_file[:-3]
            assert f"tui.{module_base}" in fw_source, (
                f"tui/{module_file} exists but is never imported by framework.py"
            )
