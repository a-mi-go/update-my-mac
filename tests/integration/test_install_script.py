"""install.sh unpacks a release archive and hands over to the setup.sh inside it."""

import io
import subprocess
import tarfile
from pathlib import Path

import pytest

INSTALL = Path(__file__).resolve().parents[2] / "install.sh"
SETUP_THAT_WRITES_ITS_ARGUMENTS = '#!/bin/bash\nprintf "%s\\n" "$@" > "$(dirname "$0")/arguments"\n'


def build_archive(path, setup_script=SETUP_THAT_WRITES_ITS_ARGUMENTS):
    with tarfile.open(path, "w:gz") as archive:
        script = setup_script.encode()
        entry = tarfile.TarInfo("update-my-mac/setup.sh")
        entry.size, entry.mode = len(script), 0o755
        archive.addfile(entry, io.BytesIO(script))
    return path


@pytest.fixture
def machine(tmp_path):
    data = tmp_path / "data"
    return {"data": data, "target": data / "update-my-mac", "archive": tmp_path / "release.tar.gz", "home": tmp_path}


def install(machine, *args):
    return subprocess.run(
        [str(INSTALL), *args],
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(machine["home"]),
            "XDG_DATA_HOME": str(machine["data"]),
            "UPDATE_MY_MAC_ARCHIVE_URL": machine["archive"].as_uri(),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_archive_is_unpacked_and_its_setup_gets_the_arguments(machine):
    build_archive(machine["archive"])

    result = install(machine, "--name", "upd")

    assert result.returncode == 0, result.stderr
    assert (machine["target"] / "arguments").read_text().split() == ["--name", "upd"]


def test_running_it_again_replaces_what_the_last_run_left(machine):
    build_archive(machine["archive"])
    install(machine)
    (machine["target"] / "left_over").write_text("from the last release")

    result = install(machine)

    assert result.returncode == 0, result.stderr
    assert not (machine["target"] / "left_over").exists()
    assert list(machine["data"].iterdir()) == [machine["target"]]


def test_a_git_clone_is_left_alone(machine):
    build_archive(machine["archive"])
    (machine["target"] / ".git").mkdir(parents=True)

    result = install(machine)

    assert result.returncode == 1
    assert "git clone" in result.stderr
    assert not (machine["target"] / "setup.sh").exists()


def test_a_download_that_fails_keeps_what_is_installed(machine):
    build_archive(machine["archive"])
    install(machine)
    machine["archive"].write_bytes(b"not an archive")

    result = install(machine)

    assert result.returncode != 0
    assert (machine["target"] / "setup.sh").exists()
