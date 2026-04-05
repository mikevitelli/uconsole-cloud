"""Tests for shell script health.

Verifies every .sh script in example-device/scripts/ passes syntax checks,
has correct permissions, and follows conventions.
"""

import os
import subprocess
import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'example-device', 'scripts')


# Files that are sourced (not executed directly) and may be symlinks
SOURCED_FILES = {'lib.sh', 'config.sh'}


def _all_shell_scripts():
    """Walk scripts directory and collect all .sh files (excluding sourced libs)."""
    scripts = []
    for root, dirs, files in os.walk(SCRIPTS_DIR):
        for f in sorted(files):
            if f.endswith('.sh') and f not in SOURCED_FILES:
                full_path = os.path.join(root, f)
                # Skip broken symlinks
                if os.path.islink(full_path) and not os.path.exists(full_path):
                    continue
                rel = os.path.relpath(full_path, SCRIPTS_DIR)
                scripts.append(rel)
    return scripts


ALL_SCRIPTS = _all_shell_scripts()


class TestScriptSyntax:
    """Every shell script must pass bash -n (syntax check)."""

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_bash_syntax(self, script):
        path = os.path.join(SCRIPTS_DIR, script)
        result = subprocess.run(
            ["bash", "-n", path],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, (
            f"Syntax error in {script}:\n{result.stderr}"
        )


class TestScriptPermissions:
    """Every .sh script must be executable."""

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_executable(self, script):
        path = os.path.join(SCRIPTS_DIR, script)
        assert os.access(path, os.X_OK), f"{script} is not executable"


class TestScriptConventions:
    """Script convention checks."""

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_has_shebang(self, script):
        path = os.path.join(SCRIPTS_DIR, script)
        with open(path, 'rb') as f:
            first_line = f.readline()
        assert first_line.startswith(b'#!'), f"{script} missing shebang"

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_shebang_is_bash(self, script):
        """Shebang should reference bash (not sh, zsh, etc.)."""
        path = os.path.join(SCRIPTS_DIR, script)
        with open(path, 'rb') as f:
            first_line = f.readline().decode('utf-8', errors='replace').strip()
        assert 'bash' in first_line, (
            f"{script} shebang is '{first_line}', expected bash"
        )

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_no_hardcoded_home_paths(self, script):
        """Scripts should not hardcode /home/mikevitelli."""
        path = os.path.join(SCRIPTS_DIR, script)
        with open(path) as f:
            content = f.read()
        # Allow in comments but flag in actual code
        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.lstrip()
            if stripped.startswith('#'):
                continue
            if '/home/mikevitelli' in line and 'ssh' not in line.lower():
                pytest.fail(
                    f"{script}:{i} hardcodes /home/mikevitelli: {line.strip()}"
                )

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_no_trailing_carriage_returns(self, script):
        """Scripts must use Unix line endings (no \\r)."""
        path = os.path.join(SCRIPTS_DIR, script)
        with open(path, 'rb') as f:
            content = f.read()
        assert b'\r' not in content, f"{script} has Windows line endings (\\r\\n)"

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_ends_with_newline(self, script):
        """Scripts should end with a newline."""
        path = os.path.join(SCRIPTS_DIR, script)
        with open(path, 'rb') as f:
            content = f.read()
        if content:
            assert content.endswith(b'\n'), f"{script} does not end with newline"


class TestScriptSubdirectories:
    """Verify scripts are in the correct subdirectories."""

    EXPECTED_SUBDIRS = {'system', 'power', 'network', 'radio', 'util'}

    def test_all_scripts_in_subdirectories(self):
        """Every script should be in a recognized subdirectory."""
        misplaced = []
        for script in ALL_SCRIPTS:
            parts = script.split(os.sep)
            if len(parts) == 1:
                misplaced.append(script)
            elif parts[0] not in self.EXPECTED_SUBDIRS:
                misplaced.append(script)
        if misplaced:
            pytest.fail(
                f"Scripts not in expected subdirectories ({self.EXPECTED_SUBDIRS}):\n" +
                "\n".join(f"  - {s}" for s in misplaced)
            )

    def test_no_empty_subdirectories(self):
        """Each expected subdirectory should have at least one script."""
        for subdir in self.EXPECTED_SUBDIRS:
            path = os.path.join(SCRIPTS_DIR, subdir)
            if os.path.isdir(path):
                scripts = [f for f in os.listdir(path) if f.endswith('.sh')]
                assert len(scripts) > 0, f"Subdirectory {subdir}/ has no .sh scripts"
