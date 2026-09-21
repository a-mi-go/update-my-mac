"""setup.sh is how the tool gets installed, so it gets run for real.

Everything uv would otherwise write to the machine — the tool directory and the
executable — goes to a temporary place, so this leaves no trace and can't
disturb an install the developer already has.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP = REPO_ROOT / "setup.sh"


def uv_caches():
    real_home = Path(os.environ["HOME"])
    return {
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(real_home / ".cache" / "uv")),
        "UV_PYTHON_INSTALL_DIR": os.environ.get(
            "UV_PYTHON_INSTALL_DIR",
            str(real_home / ".local" / "share" / "uv" / "python"),
        ),
    }


def run_setup(home, bin_dir, tool_dir):
    return subprocess.run(
        [str(SETUP)],
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "UV_TOOL_BIN_DIR": str(bin_dir),
            "UV_TOOL_DIR": str(tool_dir),
            **uv_caches(),
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
    )


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_setup_installs_a_command_that_runs(tmp_path):
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    home.mkdir()

    result = run_setup(home, bin_dir, tmp_path / "tools")

    assert result.returncode == 0, result.stderr
    assert (bin_dir / "update").exists()

    # And the installed command works, found by name on PATH.
    installed = subprocess.run(
        ["update", "--version"],
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(home),
            "UPDATE_MY_MAC_PREFIXES": "",
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert installed.returncode == 0, installed.stderr
    assert "update-my-mac" in installed.stdout


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_setup_replaces_an_older_symlink_install(tmp_path):
    """Upgrading from the bash launcher, which was linked into the same place."""
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    home.mkdir()
    bin_dir.mkdir()
    (bin_dir / "update").symlink_to("/gone/launcher")

    result = run_setup(home, bin_dir, tmp_path / "tools")

    assert result.returncode == 0, result.stderr
    assert (bin_dir / "update").resolve().exists()

    installed = subprocess.run(
        ["update", "--version"],
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(home),
            "UPDATE_MY_MAC_PREFIXES": "",
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "update-my-mac" in installed.stdout
