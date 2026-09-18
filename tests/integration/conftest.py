import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def launchd_home(tmp_path_factory):
    """A HOME with uv in ~/.local/bin, one of the few places the launcher looks.

    Where this machine keeps uv is nobody's business but its own — CI's setup-uv
    puts it in a tool cache — so symlink it somewhere the launcher will find it.
    Otherwise these tests quietly skip on CI and the launcher goes untested.
    """
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")

    home = tmp_path_factory.mktemp("launchd-home")
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "uv").symlink_to(uv)
    return home


@pytest.fixture(scope="session")
def uv_env():
    # Without these, uv treats the temporary HOME as a fresh machine and
    # re-downloads the interpreter and every dependency.
    real_home = Path(os.environ["HOME"])
    return {
        "UV_CACHE_DIR": os.environ.get(
            "UV_CACHE_DIR", str(real_home / ".cache" / "uv")
        ),
        "UV_PYTHON_INSTALL_DIR": os.environ.get(
            "UV_PYTHON_INSTALL_DIR",
            str(real_home / ".local" / "share" / "uv" / "python"),
        ),
    }
