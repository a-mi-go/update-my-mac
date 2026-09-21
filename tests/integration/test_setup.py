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


def run_setup_answering(answers, home, bin_dir, tool_dir):
    """Drive setup.sh through a pty, so its prompts behave as for a person."""
    import pty

    parent, child = pty.openpty()
    process = subprocess.Popen(
        [str(SETUP)],
        stdin=child,
        stdout=child,
        stderr=child,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "UV_TOOL_BIN_DIR": str(bin_dir),
            "UV_TOOL_DIR": str(tool_dir),
            "TERM": "dumb",
            **uv_caches(),
        },
        close_fds=True,
    )
    os.close(child)
    os.write(parent, "".join(answer + "\n" for answer in answers).encode())

    output = b""
    while True:
        try:
            chunk = os.read(parent, 1024)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    os.close(parent)
    process.wait(timeout=600)
    return process.returncode, output.decode(errors="replace")


def home_with_alias(tmp_path, line="alias update=\"~/apply_updates.sh\"\n"):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".zshrc").write_text("# my shell\n" + line)
    return home


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_an_existing_alias_is_pointed_out(tmp_path):
    home = home_with_alias(tmp_path)
    before = (home / ".zshrc").read_text()

    result = run_setup(home, tmp_path / "bin", tmp_path / "tools")

    assert result.returncode == 0, result.stderr
    assert "An 'update' alias is defined in" in result.stdout
    assert "unalias update" in result.stdout
    # Nobody was there to ask, so the file is untouched.
    assert (home / ".zshrc").read_text() == before


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_the_alias_can_be_commented_out(tmp_path):
    home = home_with_alias(tmp_path)

    code, output = run_setup_answering(["y"], home, tmp_path / "bin", tmp_path / "tools")

    assert code == 0, output
    assert "# alias update=" in (home / ".zshrc").read_text()
    backups = list(home.glob(".zshrc.bak-*"))
    assert len(backups) == 1
    assert "\nalias update=" in backups[0].read_text()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_it_can_be_installed_under_another_name(tmp_path):
    home = home_with_alias(tmp_path)
    bin_dir = tmp_path / "bin"

    code, output = run_setup_answering(
        ["n", "mac-update"], home, bin_dir, tmp_path / "tools"
    )

    assert code == 0, output
    # The alias was left alone, so the command got a name of its own.
    assert "alias update=" in (home / ".zshrc").read_text()
    assert (bin_dir / "mac-update").exists()

    installed = subprocess.run(
        ["mac-update", "--version"],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "update-my-mac" in installed.stdout


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_a_name_that_is_not_a_plain_name_is_refused(tmp_path):
    home = home_with_alias(tmp_path)
    bin_dir = tmp_path / "bin"

    code, output = run_setup_answering(
        ["n", "../escaped"], home, bin_dir, tmp_path / "tools"
    )

    assert code == 1
    assert "not a usable command name" in output
    assert not (tmp_path / "escaped").exists()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_an_existing_command_is_never_overwritten(tmp_path):
    home = home_with_alias(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "npm").write_text("#!/bin/sh\necho real npm\n")

    code, output = run_setup_answering(["n", "npm"], home, bin_dir, tmp_path / "tools")

    assert code == 1
    assert "already exists" in output
    assert (bin_dir / "npm").read_text() == "#!/bin/sh\necho real npm\n"
