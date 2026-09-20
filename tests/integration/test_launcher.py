"""The launcher has to work from a launchd job, which is the point of all this:
PATH is /usr/bin:/bin:/usr/sbin:/sbin, there is no terminal, and nothing that
depends on a login shell exists.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "update"
LAUNCHD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
# Kept in step with the prefixes the launcher adds to PATH.
PREFIXES = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")


def run_launcher(*args, home, env=None, path=LAUNCHD_PATH):
    return subprocess.run(
        [str(LAUNCHER), *args],
        env={"PATH": path, "HOME": str(home), **(env or {})},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_launcher_is_executable():
    assert os.access(LAUNCHER, os.X_OK)


def test_version_under_launchd_path(launchd_home, uv_cache_env):
    result = run_launcher("--version", home=launchd_home, env=uv_cache_env)
    assert result.returncode == 0, result.stderr
    assert "update-my-mac" in result.stdout


def test_stub_mode_exits_non_zero(launchd_home, uv_cache_env):
    result = run_launcher("--retry-app", home=launchd_home, env=uv_cache_env)
    assert result.returncode == 1, result.stderr
    assert "not implemented yet" in result.stdout


@pytest.mark.skipif(
    any(Path(p, "uv").exists() for p in PREFIXES),
    reason="uv lives in a prefix the launcher always finds",
)
def test_missing_uv_fails_instead_of_prompting(tmp_path):
    # stdin is closed, so if the launcher ever prompts here it hangs and the
    # timeout fails the test instead of it passing by accident.
    result = run_launcher("--version", home=tmp_path, path=str(tmp_path))
    assert result.returncode == 1
    assert "uv" in result.stderr


def test_every_manager_is_reachable_from_a_launchd_environment(tmp_path, uv_cache_env):
    """The launcher has to find the managers where each one actually lives.

    pnpm is the reason this exists: it refuses to run unless its own global bin
    directory is on PATH, which a login shell would normally have done.
    """
    home = tmp_path / "home"
    local_bin = home / ".local" / "bin"
    pnpm_bin = home / "Library" / "pnpm" / "bin"
    local_bin.mkdir(parents=True)
    pnpm_bin.mkdir(parents=True)

    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    (local_bin / "uv").symlink_to(uv)

    mocks = Path(__file__).parent / "mocks"
    # Placed ahead of the real tools by the launcher's own PATH order.
    for tool in ("brew", "mas", "npm"):
        shutil.copy(mocks / tool, local_bin / tool)
    shutil.copy(mocks / "pnpm", pnpm_bin / "pnpm")

    env = dict(uv_cache_env, MOCK_FIXTURES=str(Path(__file__).parent / "fixtures" / "clean"))
    result = run_launcher("--check", home=home, env=env)

    assert result.returncode == 0, result.stderr
    for label in ("Mac App Store", "Homebrew", "npm (global)", "pnpm (global)"):
        assert label in result.stdout


def test_works_through_a_symlink(tmp_path, launchd_home, uv_cache_env):
    """The documented install is a symlink into ~/.local/bin.

    The launcher has to find the project from the real file's location; if it
    looks next to the symlink instead, uv runs outside the project and re-runs
    the first `update` on PATH, which is the symlink.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "update").symlink_to(LAUNCHER)

    result = subprocess.run(
        [str(bin_dir / "update"), "--version"],
        env={"PATH": f"{bin_dir}:{LAUNCHD_PATH}", "HOME": str(launchd_home), **uv_cache_env},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert result.returncode == 0, result.stderr
    assert "update-my-mac" in result.stdout
    assert "recursively invoked" not in result.stderr
