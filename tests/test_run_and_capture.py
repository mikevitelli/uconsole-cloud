"""Tests for _run_and_capture: subprocess execution and output processing."""

import os
import sys
import subprocess
from unittest.mock import patch, MagicMock

import pytest

DEVICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'device')
LIB_DIR = os.path.join(DEVICE_DIR, 'lib')
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)


def _run_and_capture(cmd, timeout=30):
    """Standalone copy matching framework.py implementation."""
    import re
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        combined = result.stdout + result.stderr
        lines = combined.strip().split('\n')
        lines = [re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line) for line in lines]
        max_width = max((len(line) for line in lines), default=0)
        return (lines, result.returncode, max_width)
    except subprocess.TimeoutExpired:
        return (["TIMEOUT after {} seconds".format(timeout)], 1, 30)


class TestRunAndCapture:
    def test_simple_command(self):
        lines, retcode, width = _run_and_capture(["echo", "hello world"])
        assert retcode == 0
        assert "hello world" in lines

    def test_multiline_output(self):
        lines, retcode, width = _run_and_capture(["printf", "line1\nline2\nline3"])
        assert retcode == 0
        assert len(lines) == 3
        assert lines[0] == "line1"
        assert lines[2] == "line3"

    def test_strips_ansi_codes(self):
        # echo with ANSI color codes
        lines, retcode, width = _run_and_capture(
            ["printf", "\x1b[32mgreen\x1b[0m \x1b[1mbold\x1b[0m"]
        )
        assert retcode == 0
        assert lines[0] == "green bold"

    def test_strips_complex_ansi(self):
        lines, _, _ = _run_and_capture(
            ["printf", "\x1b[38;5;196mred256\x1b[0m"]
        )
        assert "red256" in lines[0]
        assert "\x1b" not in lines[0]

    def test_nonzero_exit_code(self):
        lines, retcode, width = _run_and_capture(["bash", "-c", "exit 42"])
        assert retcode == 42

    def test_stderr_captured(self):
        lines, retcode, width = _run_and_capture(
            ["bash", "-c", "echo stdout; echo stderr >&2"]
        )
        assert any("stdout" in l for l in lines)
        assert any("stderr" in l for l in lines)

    def test_timeout(self):
        lines, retcode, width = _run_and_capture(
            ["sleep", "10"], timeout=1
        )
        assert retcode == 1
        assert "TIMEOUT" in lines[0]

    def test_empty_output(self):
        lines, retcode, width = _run_and_capture(["true"])
        assert retcode == 0
        # Empty output gives [''] after strip().split('\n')
        assert isinstance(lines, list)

    def test_max_width_calculation(self):
        lines, retcode, width = _run_and_capture(
            ["printf", "short\nthis is a longer line\nmed"]
        )
        assert width == len("this is a longer line")

    def test_binary_in_path(self):
        """Should handle scripts that don't exist gracefully."""
        with pytest.raises(FileNotFoundError):
            _run_and_capture(["/nonexistent/script.sh"])


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
        lines, retcode, _ = _run_and_capture(["bash", "-n", path])
        assert retcode == 0, f"Syntax error in {script}: {lines}"
