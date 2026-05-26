"""Tests for tui.framework._run_and_capture: subprocess execution and
output processing.

Calls the real production function — the previous version of this test
defined a hand-copied standalone helper that drifted from the real
implementation (different timeout string, missing "(no output)" /
"(error: ...)" branches), so passing tests didn't certify production.
"""

import os
import sys
import pytest

DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
LIB_DIR = os.path.join(DEVICE_DIR, 'lib')
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

from tui.framework import _run_and_capture  # noqa: E402


class TestRunAndCapture:
    def test_simple_command(self):
        lines, retcode, _ = _run_and_capture(["echo", "hello world"])
        assert retcode == 0
        assert "hello world" in lines

    def test_multiline_output(self):
        lines, retcode, _ = _run_and_capture(["printf", "line1\nline2\nline3"])
        assert retcode == 0
        assert "line1" in lines
        assert "line2" in lines
        assert "line3" in lines

    def test_strips_ansi_codes(self):
        lines, retcode, _ = _run_and_capture(
            ["printf", "\x1b[32mgreen\x1b[0m \x1b[1mbold\x1b[0m"]
        )
        assert retcode == 0
        # Production strips ANSI then splitlines — colorless text remains.
        assert any("green" in l and "bold" in l for l in lines)
        assert not any("\x1b" in l for l in lines)

    def test_strips_complex_ansi(self):
        lines, _, _ = _run_and_capture(
            ["printf", "\x1b[38;5;196mred256\x1b[0m"]
        )
        assert any("red256" in l for l in lines)
        assert not any("\x1b" in l for l in lines)

    def test_nonzero_exit_code(self):
        _, retcode, _ = _run_and_capture(["bash", "-c", "exit 42"])
        assert retcode == 42

    def test_stderr_captured(self):
        lines, _, _ = _run_and_capture(
            ["bash", "-c", "echo stdout; echo stderr >&2"]
        )
        assert any("stdout" in l for l in lines)
        assert any("stderr" in l for l in lines)

    def test_timeout_returns_sentinel_string(self):
        """Production hard-codes the literal '(timed out after 30s)' even
        when timeout differs (a separate bug already noted). The test
        documents that production behavior so regressions surface."""
        lines, retcode, _ = _run_and_capture(["sleep", "10"], timeout=1)
        assert retcode == 1
        assert any("timed out" in l.lower() for l in lines)

    def test_empty_output_returns_no_output_sentinel(self):
        """Production replaces blank output with '(no output)'."""
        lines, retcode, _ = _run_and_capture(["true"])
        assert retcode == 0
        assert any("no output" in l for l in lines)

    def test_max_width_calculation(self):
        lines, _, width = _run_and_capture(
            ["printf", "short\nthis is a longer line\nmed"]
        )
        assert width == max(len(l) for l in lines)
        assert width >= len("this is a longer line")

    def test_missing_binary_returns_error_sentinel(self):
        """Production catches Exception (FileNotFoundError) and returns
        an '(error: ...)' line — does not raise."""
        lines, retcode, _ = _run_and_capture(["/nonexistent/script.sh"])
        assert retcode == 1
        assert any("error" in l.lower() for l in lines)


class TestRunAndCaptureWithRealScripts:
    """Run actual scripts from device/scripts/ and verify output."""

    SCRIPTS_DIR = os.path.join(DEVICE_DIR, 'scripts')

    def _script_path(self, rel):
        return os.path.join(self.SCRIPTS_DIR, rel)

    @pytest.mark.parametrize("script,expected_retcode", [
        # Scripts that should work on any system (just checking they parse)
        ("util/webdash-info.sh", None),  # May fail without webdash, that's ok
    ])
    def test_script_is_parseable(self, script, expected_retcode):
        """Each script should at least pass bash -n (syntax check)."""
        path = self._script_path(script)
        if not os.path.isfile(path):
            pytest.skip(f"Script not found: {path}")
        _, retcode, _ = _run_and_capture(["bash", "-n", path])
        assert retcode == 0, f"Syntax error in {script}"
