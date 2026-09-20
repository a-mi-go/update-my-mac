"""`update --check` against fake package managers.

The fakes sit alone on PATH, so a manager is "installed" exactly when the test
says so, and the real brew/npm on this machine are never consulted.
"""

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
MOCKS = HERE / "mocks"
FIXTURES = HERE / "fixtures"


def run_check_against_mocks(scenario, path=None):
    env = {
        "PATH": path if path is not None else f"{MOCKS}:/usr/bin:/bin",
        "MOCK_FIXTURES": str(FIXTURES / scenario),
        "HOME": str(Path.home()),
        "TERM": "dumb",
    }
    return subprocess.run(
        [sys.executable, "-m", "update_my_mac", "--check"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_reports_outdated_packages():
    result = run_check_against_mocks("outdated")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "Xcode" in out
    assert "ripgrep" in out
    assert "typescript  5.4.2 → 5.4.5" in out
    assert "eslint  9.0.0 → 9.12.0" in out
    assert "5 outdated in total" in out


def test_nothing_outdated_says_so():
    result = run_check_against_mocks("clean")
    assert "Everything is up to date" in result.stdout


@pytest.mark.parametrize("label", ["Mac App Store", "Homebrew", "npm", "pnpm"])
def test_clean_managers_are_listed_as_up_to_date(label):
    result = run_check_against_mocks("clean")
    assert label in result.stdout


def test_managers_that_are_not_installed_are_skipped(tmp_path):
    # An empty PATH entry means nothing resolves, so nothing should be reported.
    result = run_check_against_mocks("outdated", path=f"{tmp_path}:/usr/bin:/bin")
    assert result.returncode == 0, result.stderr
    assert "No supported package managers found" in result.stdout


def test_a_failing_manager_is_reported_as_failed_not_outdated():
    # npm exits 1 for a registry failure exactly as it does for updates found.
    result = run_check_against_mocks("npm_failure")
    assert result.returncode == 0, result.stderr
    assert "npm (global): check failed" in result.stdout
    assert "ENOTFOUND" in result.stdout
    # A failed check must not be summarised as everything being fine.
    assert "Everything is up to date" not in result.stdout
