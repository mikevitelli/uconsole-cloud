"""Tests for the framework.py feature handler registry — load + filter."""

import importlib
import os
import sys

import pytest


# Make the device's tui package importable
DEVICE_LIB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "device", "lib",
)
if DEVICE_LIB not in sys.path:
    sys.path.insert(0, DEVICE_LIB)


@pytest.fixture
def fresh_framework(monkeypatch):
    """Reload framework + every feature module so each test starts clean.

    Mutates module-level state (SUBMENUS, CATEGORIES, _HANDLERS_CACHE), so
    we throw the framework away and re-import for each test.
    """
    # Drop tui.framework + every tui.* module that may have been imported
    drop = [name for name in sys.modules if name == "tui.framework" or name.startswith("tui.")]
    for name in drop:
        del sys.modules[name]
    fw = importlib.import_module("tui.framework")
    return fw


def test_load_handlers_returns_non_empty_dict(fresh_framework):
    h = fresh_framework._load_handlers()
    assert isinstance(h, dict)
    assert len(h) > 30, f"expected ~64 handlers, got {len(h)}"


def test_load_handlers_includes_known_handlers(fresh_framework):
    h = fresh_framework._load_handlers()
    for key in ("_processes", "_esp32_hub", "_marauder", "_telegram", "_theme"):
        assert key in h, f"{key} missing from loaded handlers"


def test_broken_module_skipped_and_logged(fresh_framework, tmp_path, monkeypatch):
    """A module that raises on import is logged and its handlers are absent."""
    # Redirect ~/crash.log to tmp so we don't pollute the real one
    monkeypatch.setenv("HOME", str(tmp_path))

    # Insert a deliberately-broken module into FEATURE_MODULES at the front
    fresh_framework.FEATURE_MODULES.insert(0, "tui.does_not_exist_zzz")

    h = fresh_framework._load_handlers()

    # Every other module still loaded; only the broken one is missing
    assert "_processes" in h
    assert len(h) > 30

    # crash.log should record the failure
    log_path = tmp_path / "crash.log"
    assert log_path.exists(), "crash.log should have been written"
    contents = log_path.read_text()
    assert "feature-import-failed" in contents
    assert "tui.does_not_exist_zzz" in contents


def test_filter_drops_unknown_handler_items(fresh_framework):
    """A menu item pointing to an unknown _foo target is removed by _filter_menus."""
    # Inject a fake item into one submenu
    fake_key = list(fresh_framework.SUBMENUS.keys())[0]
    fresh_framework.SUBMENUS[fake_key].append(
        ("Fake item", "_definitely_not_a_real_handler", "should be dropped", "action", "?")
    )
    before_count = len(fresh_framework.SUBMENUS[fake_key])

    handlers = fresh_framework._load_handlers()
    fresh_framework._filter_menus(handlers)

    after_count = len(fresh_framework.SUBMENUS[fake_key])
    assert after_count == before_count - 1, "fake item should be dropped"
    targets = [item[1] for item in fresh_framework.SUBMENUS[fake_key]]
    assert "_definitely_not_a_real_handler" not in targets


def test_filter_preserves_shell_scripts_and_sub_drilldowns(fresh_framework):
    """Non-underscore script paths and sub:foo drilldowns survive filtering."""
    handlers = fresh_framework._load_handlers()

    # Pick a submenu that has a shell-script-target item
    sample_target = None
    for items in fresh_framework.SUBMENUS.values():
        for item in items:
            if not item[1].startswith(("_", "sub:")):
                sample_target = item[1]
                break
        if sample_target:
            break

    fresh_framework._filter_menus(handlers)

    # The sample shell-script target should still be present somewhere
    found = any(
        item[1] == sample_target
        for items in fresh_framework.SUBMENUS.values()
        for item in items
    )
    assert found, f"shell-script target {sample_target} was filtered out"


def test_filter_preserves_gui_and_url_prefixes(fresh_framework):
    """_gui:foo and _url:foo targets are not filtered (handled by run_script)."""
    fake_key = list(fresh_framework.SUBMENUS.keys())[0]
    fresh_framework.SUBMENUS[fake_key].extend([
        ("GUI item", "_gui:nonexistent", "kept", "action", "?"),
        ("URL item", "_url:https://example.com", "kept", "action", "?"),
    ])

    handlers = fresh_framework._load_handlers()
    fresh_framework._filter_menus(handlers)

    targets = [item[1] for items in fresh_framework.SUBMENUS.values() for item in items]
    assert "_gui:nonexistent" in targets
    assert "_url:https://example.com" in targets


def test_get_handlers_filters_menus_on_first_call(fresh_framework):
    """_get_handlers must filter the menus exactly once; subsequent calls are no-ops."""
    fake_key = list(fresh_framework.SUBMENUS.keys())[0]
    fresh_framework.SUBMENUS[fake_key].append(
        ("Fake", "_no_such_handler_xyz", "should vanish", "action", "?")
    )

    fresh_framework._get_handlers()

    targets = [item[1] for item in fresh_framework.SUBMENUS[fake_key]]
    assert "_no_such_handler_xyz" not in targets
