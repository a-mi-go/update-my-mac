"""setup.sh is how the tool gets installed, so it gets run for real.

Everything uv would otherwise write to the machine — the tool directory and the
executable — goes to a temporary place, so this leaves no trace and can't
disturb an install the developer already has.
"""

import os
import pty
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP = REPO_ROOT / "setup.sh"

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")


def uv_caches():
    real_home = Path(os.environ["HOME"])
    return {
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", str(real_home / ".cache" / "uv")),
        "UV_PYTHON_INSTALL_DIR": os.environ.get(
            "UV_PYTHON_INSTALL_DIR",
            str(real_home / ".local" / "share" / "uv" / "python"),
        ),
    }


def setup_env(home, bin_dir, tool_dir):
    # Just uv and the system, so nothing else installed here can collide with a
    # name the test picks.
    uv_dir = Path(shutil.which("uv")).parent
    return {
        "PATH": f"{uv_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "UV_TOOL_BIN_DIR": str(bin_dir),
        "UV_TOOL_DIR": str(tool_dir),
        "TERM": "dumb",
        **uv_caches(),
    }


def run_setup(tmp_path, home, *args):
    return subprocess.run(
        [str(SETUP), *args],
        env=setup_env(home, tmp_path / "bin", tmp_path / "tools"),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
    )


def run_setup_answering(tmp_path, home, answers):
    """Drive setup.sh through a pty, so its prompts behave as for a person."""
    parent, child = pty.openpty()
    process = subprocess.Popen(
        [str(SETUP)],
        stdin=child,
        stdout=child,
        stderr=child,
        env=setup_env(home, tmp_path / "bin", tmp_path / "tools"),
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


def version_of(command, bin_dir, home):
    return subprocess.run(
        [command, "--version"],
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(home),
            "UPDATE_MY_MAC_PREFIXES": "",
        },
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout


def empty_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return home


def home_with_alias(tmp_path):
    home = empty_home(tmp_path)
    (home / ".zshrc").write_text('# my shell\nalias update="~/apply_updates.sh"\n')
    return home


def test_setup_installs_a_command_that_runs(tmp_path):
    home = empty_home(tmp_path)

    result = run_setup(tmp_path, home)

    assert result.returncode == 0, result.stderr
    assert "update-my-mac" in version_of("update", tmp_path / "bin", home)


def test_setup_replaces_an_older_symlink_install(tmp_path):
    """Upgrading from the bash launcher, which was linked into the same place."""
    home = empty_home(tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "update").symlink_to("/gone/launcher")

    result = run_setup(tmp_path, home)

    assert result.returncode == 0, result.stderr
    assert "update-my-mac" in version_of("update", tmp_path / "bin", home)


def test_the_name_can_be_given_up_front(tmp_path):
    home = empty_home(tmp_path)

    result = run_setup(tmp_path, home, "--name", "mac-update")

    assert result.returncode == 0, result.stderr
    assert "Try: mac-update --check" in result.stdout
    assert "update-my-mac" in version_of("mac-update", tmp_path / "bin", home)


def test_the_name_is_asked_for(tmp_path):
    home = empty_home(tmp_path)

    code, output = run_setup_answering(tmp_path, home, ["mac-update"])

    assert code == 0, output
    assert "update-my-mac" in version_of("mac-update", tmp_path / "bin", home)


def test_running_again_with_the_same_name_is_fine(tmp_path):
    home = empty_home(tmp_path)
    run_setup(tmp_path, home, "--name", "mac-update")

    result = run_setup(tmp_path, home, "--name", "mac-update")

    assert result.returncode == 0, result.stderr


def test_a_name_that_is_not_a_plain_name_is_refused(tmp_path):
    home = empty_home(tmp_path)

    result = run_setup(tmp_path, home, "--name", "../escaped")

    assert result.returncode == 1
    assert "not a usable command name" in result.stderr
    assert not (tmp_path / "escaped").exists()


def test_an_unusable_name_is_asked_for_again(tmp_path):
    home = empty_home(tmp_path)

    code, output = run_setup_answering(tmp_path, home, ["../x", "mac-update"])

    assert code == 0, output
    assert "not a usable command name" in output
    assert (tmp_path / "bin" / "mac-update").exists()


def test_an_existing_command_is_never_overwritten(tmp_path):
    home = empty_home(tmp_path)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "some-tool").write_text("#!/bin/sh\necho the real one\n")

    result = run_setup(tmp_path, home, "--name", "some-tool")

    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert (tmp_path / "bin" / "some-tool").read_text() == "#!/bin/sh\necho the real one\n"


def test_an_existing_alias_is_pointed_out(tmp_path):
    home = home_with_alias(tmp_path)
    before = (home / ".zshrc").read_text()

    result = run_setup(tmp_path, home)

    assert result.returncode == 0, result.stderr
    assert "'update' is already an alias in" in result.stdout
    # Nobody was there to ask, so the file is untouched.
    assert (home / ".zshrc").read_text() == before


def test_an_alias_can_be_avoided_by_choosing_another_name(tmp_path):
    home = home_with_alias(tmp_path)

    code, output = run_setup_answering(tmp_path, home, ["", "1", "mac-update"])

    assert code == 0, output
    # The alias is someone's, so it stays exactly as it was.
    assert 'alias update="~/apply_updates.sh"' in (home / ".zshrc").read_text()
    assert "update-my-mac" in version_of("mac-update", tmp_path / "bin", home)


def test_an_alias_can_be_commented_out(tmp_path):
    home = home_with_alias(tmp_path)

    code, output = run_setup_answering(tmp_path, home, ["", "2"])

    assert code == 0, output
    assert "# alias update=" in (home / ".zshrc").read_text()
    backups = list(home.glob(".zshrc.bak-*"))
    assert len(backups) == 1
    assert "\nalias update=" in backups[0].read_text()


def test_an_alias_can_be_left_alone(tmp_path):
    home = home_with_alias(tmp_path)
    before = (home / ".zshrc").read_text()

    code, output = run_setup_answering(tmp_path, home, ["", "3"])

    assert code == 0, output
    assert (home / ".zshrc").read_text() == before


def run_setup_from_zsh(tmp_path, home, **extra_env):
    # "; true" keeps zsh from exec-ing setup.sh, so zsh really is its parent.
    return subprocess.run(
        ["zsh", "-f", "-c", f"'{SETUP}' --name update; true"],
        env={**setup_env(home, tmp_path / "bin", tmp_path / "tools"), **extra_env},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="relies on BSD date and stat")
@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_a_terminal_older_than_its_config_is_warned_about(tmp_path):
    home = empty_home(tmp_path)
    zshrc = home / ".zshrc"
    zshrc.write_text("# changed after this terminal was opened\n")
    in_an_hour = time.time() + 3600
    os.utime(zshrc, (in_an_hour, in_an_hour))

    result = run_setup_from_zsh(tmp_path, home)

    assert result.returncode == 0, result.stderr
    assert "alias update >/dev/null 2>&1 && unalias update; hash -r" in result.stdout


@pytest.mark.skipif(sys.platform != "darwin", reason="relies on BSD date and stat")
@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_a_fresh_terminal_gets_no_warning(tmp_path):
    home = empty_home(tmp_path)
    zshrc = home / ".zshrc"
    zshrc.write_text("# unchanged for a long time\n")
    long_ago = time.time() - 86400
    os.utime(zshrc, (long_ago, long_ago))

    result = run_setup_from_zsh(tmp_path, home)

    assert result.returncode == 0, result.stderr
    assert "unalias" not in result.stdout


@pytest.mark.skipif(sys.platform != "darwin", reason="relies on BSD date and stat")
@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_the_warning_works_in_any_language(tmp_path):
    # ps writes "Mo. 21 Sep." in German, which date -j can't parse unless forced.
    home = empty_home(tmp_path)
    zshrc = home / ".zshrc"
    zshrc.write_text("# changed after this terminal was opened\n")
    in_an_hour = time.time() + 3600
    os.utime(zshrc, (in_an_hour, in_an_hour))

    result = run_setup_from_zsh(tmp_path, home, LC_ALL="de_DE.UTF-8", LANG="de_DE.UTF-8")

    assert result.returncode == 0, result.stderr
    assert "unalias update" in result.stdout


def test_a_name_another_program_already_has_is_refused(tmp_path):
    # ls is on PATH, and a link called ls here could hide the real one.
    home = empty_home(tmp_path)

    result = run_setup(tmp_path, home, "--name", "ls")

    assert result.returncode == 1
    # /bin/ls on macOS, /usr/bin/ls on most Linux.
    assert "'ls' is already /" in result.stderr
    assert not (tmp_path / "bin" / "ls").exists()


def test_a_shell_builtin_is_refused(tmp_path):
    home = empty_home(tmp_path)

    result = run_setup(tmp_path, home, "--name", "cd")

    assert result.returncode == 1
    assert "already a shell builtin" in result.stderr


def test_a_taken_name_is_asked_for_again(tmp_path):
    home = empty_home(tmp_path)

    code, output = run_setup_answering(tmp_path, home, ["ls", "mac-update"])

    assert code == 0, output
    assert "'ls' is already /" in output
    assert (tmp_path / "bin" / "mac-update").exists()
    assert not (tmp_path / "bin" / "ls").exists()


def test_a_stray_answer_in_the_alias_menu_asks_again(tmp_path):
    home = home_with_alias(tmp_path)
    before = (home / ".zshrc").read_text()

    code, output = run_setup_answering(tmp_path, home, ["", "x", "3"])

    assert code == 0, output
    assert "Please answer 1, 2 or 3" in output
    assert (home / ".zshrc").read_text() == before


def test_a_dot_in_the_name_is_matched_literally(tmp_path):
    # "mac.update" must not treat an alias called macXupdate as its own.
    home = empty_home(tmp_path)
    (home / ".zshrc").write_text('alias macXupdate="something else"\n')

    result = run_setup(tmp_path, home, "--name", "mac.update")

    assert result.returncode == 0, result.stderr
    assert "already an alias" not in result.stdout
