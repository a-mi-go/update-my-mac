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


def run_check_against_mocks(scenario, home, path=None, app_dirs=""):
    env = {
        "PATH": path if path is not None else f"{MOCKS}:/usr/bin:/bin",
        "MOCK_FIXTURES": str(FIXTURES / scenario),
        "HOME": str(home),
        "TERM": "dumb",
        # Only the fakes on PATH above, never this machine's real managers,
        # and no scanning of the real /Applications either.
        "UPDATE_MY_MAC_PREFIXES": "",
        "UPDATE_MY_MAC_APP_DIRS": app_dirs,
    }
    return subprocess.run(
        [sys.executable, "-m", "update_my_mac", "--check"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_reports_outdated_packages(empty_home):
    result = run_check_against_mocks("outdated", empty_home)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "Xcode" in out
    assert "ripgrep" in out
    assert "typescript  5.4.2 → 5.4.5" in out
    assert "eslint  9.0.0 → 9.12.0" in out
    assert "6 outdated in total" in out


def test_nothing_outdated_says_so(empty_home):
    result = run_check_against_mocks("clean", empty_home)
    assert "Everything is up to date" in result.stdout


@pytest.mark.parametrize("label", ["Mac App Store", "Homebrew", "npm", "pnpm"])
def test_clean_managers_are_listed_as_up_to_date(label, empty_home):
    result = run_check_against_mocks("clean", empty_home)
    assert label in result.stdout


def test_managers_that_are_not_installed_are_skipped(tmp_path, empty_home):
    # An empty PATH entry means nothing resolves, so nothing should be reported.
    result = run_check_against_mocks("outdated", empty_home, path=f"{tmp_path}:/usr/bin:/bin")
    assert result.returncode == 0, result.stderr
    assert "No supported package managers found" in result.stdout


def test_a_failing_manager_is_reported_as_failed_not_outdated(empty_home):
    # npm exits 1 for a registry failure exactly as it does for updates found.
    result = run_check_against_mocks("npm_failure", empty_home)
    # Non-zero so a scheduled run can tell "nothing outdated" from "did not run".
    assert result.returncode == 1
    assert "npm (global): check failed" in result.stdout
    assert "ENOTFOUND" in result.stdout
    # A failed check must not be summarised as everything being fine.
    assert "Everything is up to date" not in result.stdout


def test_untracked_apps_show_up_in_the_report(tmp_path, empty_home):
    apps = tmp_path / "Applications"
    (apps / "TokenEater.app" / "Contents").mkdir(parents=True)
    plist = apps / "TokenEater.app" / "Contents" / "Info.plist"
    plist.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        b'<plist version="1.0"><dict><key>CFBundleShortVersionString</key>'
        b"<string>5.12.2</string></dict></plist>\n"
    )

    result = run_check_against_mocks("clean", empty_home, app_dirs=str(apps))

    assert result.returncode == 0, result.stderr
    assert "Not tracked by any package manager: 1" in result.stdout
    assert "TokenEater  5.12.2" in result.stdout
