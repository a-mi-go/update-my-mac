"""The launcher has to work from a launchd job, which is the point of all this:
PATH is /usr/bin:/bin:/usr/sbin:/sbin, there is no terminal, and nothing that
depends on a login shell exists.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "update"
LAUNCHD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


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


def test_version_under_launchd_path(launchd_home, uv_env):
    result = run_launcher("--version", home=launchd_home, env=uv_env)
    assert result.returncode == 0, result.stderr
    assert "update-my-mac" in result.stdout


def test_stub_mode_exits_non_zero(launchd_home, uv_env):
    result = run_launcher("--check", home=launchd_home, env=uv_env)
    assert result.returncode == 1, result.stderr
    assert "not implemented yet" in result.stdout


@pytest.mark.skipif(
    any(Path(p, "uv").exists() for p in ("/opt/homebrew/bin", "/usr/local/bin")),
    reason="uv lives in a Homebrew prefix, which the launcher always finds",
)
def test_missing_uv_fails_instead_of_prompting(tmp_path):
    # stdin is closed, so if the launcher ever prompts here it hangs and the
    # timeout fails the test instead of it passing by accident.
    result = run_launcher("--version", home=tmp_path, path=str(tmp_path))
    assert result.returncode == 1
    assert "uv" in result.stderr
