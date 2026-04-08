"""Shared fixtures for TUI tests."""

import curses
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add device/lib to path so we can import tui modules
DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
LIB_DIR = os.path.join(DEVICE_DIR, 'lib')
TUI_DIR = os.path.join(DEVICE_DIR, 'lib', 'tui')
SCRIPTS_DIR = os.path.join(DEVICE_DIR, 'scripts')

if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


# ── Curses key constants (safe to reference without a terminal) ────────────

KEY_UP = curses.KEY_UP
KEY_DOWN = curses.KEY_DOWN
KEY_LEFT = curses.KEY_LEFT
KEY_RIGHT = curses.KEY_RIGHT
KEY_ENTER = ord('\n')
KEY_ESC = 27
KEY_Q = ord('q')
KEY_B = ord('b')
KEY_J = ord('j')
KEY_K = ord('k')
KEY_H = ord('h')
KEY_L = ord('l')
KEY_R = ord('r')
KEY_A = ord('a')
KEY_Y = ord('y')


@pytest.fixture
def mock_stdscr():
    """Create a mock curses stdscr with sensible defaults."""
    scr = MagicMock()
    scr.getmaxyx.return_value = (24, 80)
    scr.getyx.return_value = (0, 0)
    scr.derwin.return_value = MagicMock()
    scr.subwin.return_value = MagicMock()
    # addnstr and addstr should not raise by default
    scr.addnstr.return_value = None
    scr.addstr.return_value = None
    return scr


@pytest.fixture
def mock_stdscr_wide():
    """Mock stdscr at a wider resolution (40x120)."""
    scr = MagicMock()
    scr.getmaxyx.return_value = (40, 120)
    scr.getyx.return_value = (0, 0)
    scr.derwin.return_value = MagicMock()
    scr.subwin.return_value = MagicMock()
    scr.addnstr.return_value = None
    scr.addstr.return_value = None
    return scr


@pytest.fixture
def mock_stdscr_small():
    """Mock stdscr at a small resolution (16x40) to test cramped layouts."""
    scr = MagicMock()
    scr.getmaxyx.return_value = (16, 40)
    scr.getyx.return_value = (0, 0)
    scr.derwin.return_value = MagicMock()
    scr.subwin.return_value = MagicMock()
    scr.addnstr.return_value = None
    scr.addstr.return_value = None
    return scr


@pytest.fixture
def scripts_dir():
    """Return path to device/scripts/."""
    return SCRIPTS_DIR


@pytest.fixture
def tui_dir():
    """Return path to device/lib/tui/."""
    return TUI_DIR


@pytest.fixture
def framework_source():
    """Read framework.py source."""
    with open(os.path.join(TUI_DIR, 'framework.py')) as f:
        return f.read()


def make_key_sequence(*keys):
    """Build a getch side_effect list from key constants.

    Usage:
        stdscr.getch.side_effect = make_key_sequence(KEY_DOWN, KEY_DOWN, KEY_ENTER, KEY_Q)
    """
    return list(keys)
