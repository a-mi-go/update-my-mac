"""What a scheduled run looks like: PATH=/usr/bin:/bin:/usr/sbin:/sbin and
nothing a login shell would have added. The managers have to be found anyway.
"""

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
MOCKS = HERE / "mocks"
FIXTURES = HERE / "fixtures"
LAUNCHD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def home_with_managers(tmp_path):
    """A home with fake managers where each one really lives."""
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    pnpm_bin = home / "Library" / "pnpm" / "bin"
    local_bin.mkdir(parents=True)
    pnpm_bin.mkdir(parents=True)

    shutil.copy(MOCKS / "brew", local_bin / "brew")
    shutil.copy(MOCKS / "npm", local_bin / "npm")
    shutil.copy(MOCKS / "pnpm", pnpm_bin / "pnpm")
    return home


def run_check(home, prefixes=""):
    env = {
        "PATH": LAUNCHD_PATH,
        "HOME": str(home),
        "TERM": "dumb",
        "MOCK_FIXTURES": str(FIXTURES / "clean"),
        # No real prefixes, so only what this test planted can be found.
        "UPDATE_MY_MAC_PREFIXES": prefixes,
    }
    return subprocess.run(
        [sys.executable, "-m", "update_my_mac", "--check"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_managers_are_found_without_a_login_shell(tmp_path):
    result = run_check(home_with_managers(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "Homebrew" in result.stdout
    assert "npm (global)" in result.stdout
    # pnpm only works when its own global bin directory is on PATH.
    assert "pnpm (global)" in result.stdout


def test_a_prefix_can_be_pointed_somewhere_unusual(tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()
    prefix = tmp_path / "opt" / "elsewhere"
    (prefix / "bin").mkdir(parents=True)
    shutil.copy(MOCKS / "mas", prefix / "bin" / "mas")

    result = run_check(home, prefixes=str(prefix))

    assert result.returncode == 0, result.stderr
    assert "Mac App Store" in result.stdout
