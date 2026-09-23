"""Deciding to leave an app alone, and bringing it back, through the real CLI."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
MOCKS = HERE / "mocks"
FIXTURES = HERE / "fixtures"


def make_app(directory, name, version):
    contents = directory / f"{name}.app" / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        b'<plist version="1.0"><dict><key>CFBundleShortVersionString</key>'
        + f"<string>{version}</string>".encode()
        + b"</dict></plist>\n"
    )


def run(tmp_path, home, *args, answer=""):
    return subprocess.run(
        [sys.executable, "-m", "update_my_mac", *args],
        env={
            "PATH": f"{MOCKS}:/usr/bin:/bin",
            "MOCK_FIXTURES": str(FIXTURES / "clean"),
            "HOME": str(home),
            "TERM": "dumb",
            "UPDATE_MY_MAC_PREFIXES": "",
            "UPDATE_MY_MAC_APP_DIRS": str(tmp_path / "Applications"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        },
        input=answer,
        capture_output=True,
        text=True,
        timeout=120,
    )


def decisions_file(tmp_path):
    return tmp_path / "state" / "update-my-mac" / "apps.json"


def test_an_app_can_be_left_alone_and_stays_that_way(tmp_path, empty_home):
    apps = tmp_path / "Applications"
    apps.mkdir()
    make_app(apps, "TokenEater", "5.12.2")

    first = run(tmp_path, empty_home, answer="y\n1\n0\n")
    assert first.returncode == 0, first.stderr
    assert "TokenEater  5.12.2" in first.stdout

    stored = json.loads(decisions_file(tmp_path).read_text())
    assert stored["apps"]["TokenEater"]["decision"] == "ignore"

    # The next run says how many are left alone instead of listing them.
    second = run(tmp_path, empty_home, "--check")
    assert "TokenEater" not in second.stdout
    assert "1 more left alone on purpose" in second.stdout


def test_a_left_alone_app_can_be_brought_back(tmp_path, empty_home):
    apps = tmp_path / "Applications"
    apps.mkdir()
    make_app(apps, "TokenEater", "5.12.2")
    run(tmp_path, empty_home, answer="y\n1\n0\n")

    revisit = run(tmp_path, empty_home, "--retry-app", answer="1\n")
    assert revisit.returncode == 0, revisit.stderr
    assert "TokenEater will be listed again" in revisit.stdout

    assert "TokenEater  5.12.2" in run(tmp_path, empty_home, "--check").stdout


def test_a_check_never_asks_anything(tmp_path, empty_home):
    apps = tmp_path / "Applications"
    apps.mkdir()
    make_app(apps, "TokenEater", "5.12.2")

    result = run(tmp_path, empty_home, "--check")

    assert "Go through them now?" not in result.stdout
    assert not decisions_file(tmp_path).exists()
