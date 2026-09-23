import json
import plistlib

from update_my_mac import installed_apps
from update_my_mac.shell import CommandResult


class FakeShell:
    """A brew that answers with whatever the test says it has installed."""

    def __init__(self, casks=None, brew=True):
        self.casks = casks
        self.brew = brew

    def find_executable(self, command):
        return f"/fake/{command}" if self.brew else None

    def run_command(self, args, success_exit_codes=(0,), env=None):
        self.env = env
        if self.casks is None:
            return CommandResult(False, "", "brew: boom", 1)
        return CommandResult(True, json.dumps({"casks": self.casks}), "")


def make_app(directory, name, version="1.0", from_app_store=False):
    app = directory / f"{name}.app"
    contents = app / "Contents"
    contents.mkdir(parents=True)
    with open(contents / "Info.plist", "wb") as plist:
        plistlib.dump({"CFBundleShortVersionString": version}, plist)
    if from_app_store:
        (contents / "_MASReceipt").mkdir()
    return app


def cask_with(app_file_name):
    return {"token": "whatever", "artifacts": [{"app": [app_file_name]}]}


def env_for(directory, **extra):
    return {"HOME": str(directory), "UPDATE_MY_MAC_APP_DIRS": str(directory), **extra}


def test_an_app_nobody_tracks_is_found(tmp_path):
    make_app(tmp_path, "TokenEater", "5.12.2")

    found = installed_apps.find_untracked(FakeShell(casks=[]), env_for(tmp_path))

    assert [(app.name, app.version) for app in found] == [("TokenEater", "5.12.2")]


def test_an_app_store_app_is_left_out(tmp_path):
    make_app(tmp_path, "Xcode", from_app_store=True)

    assert installed_apps.find_untracked(FakeShell(casks=[]), env_for(tmp_path)) == []


def test_an_app_homebrew_installed_is_left_out(tmp_path):
    make_app(tmp_path, "Firefox")
    shell = FakeShell(casks=[cask_with("Firefox.app")])

    assert installed_apps.find_untracked(shell, env_for(tmp_path)) == []


def test_homebrew_is_asked_without_refreshing_its_index(tmp_path):
    make_app(tmp_path, "Firefox")
    shell = FakeShell(casks=[])

    installed_apps.find_untracked(shell, env_for(tmp_path))

    assert shell.env["HOMEBREW_NO_AUTO_UPDATE"] == "1"


def test_without_brew_every_app_counts_as_untracked(tmp_path):
    make_app(tmp_path, "Firefox")

    found = installed_apps.find_untracked(FakeShell(brew=False), env_for(tmp_path))

    assert [app.name for app in found] == ["Firefox"]


def test_a_failing_brew_does_not_lose_the_scan(tmp_path):
    # Rather than report nothing, list everything and let the user judge.
    make_app(tmp_path, "Firefox")

    found = installed_apps.find_untracked(FakeShell(casks=None), env_for(tmp_path))

    assert [app.name for app in found] == ["Firefox"]


def test_an_app_without_a_readable_version(tmp_path):
    (tmp_path / "Broken.app" / "Contents").mkdir(parents=True)

    found = installed_apps.find_untracked(FakeShell(casks=[]), env_for(tmp_path))

    assert [(app.name, app.version) for app in found] == [("Broken", "?")]


def test_the_build_number_stands_in_when_there_is_no_version(tmp_path):
    app = tmp_path / "Odd.app" / "Contents"
    app.mkdir(parents=True)
    with open(app / "Info.plist", "wb") as plist:
        plistlib.dump({"CFBundleVersion": "2026.3"}, plist)

    found = installed_apps.find_untracked(FakeShell(casks=[]), env_for(tmp_path))

    assert found[0].version == "2026.3"


def test_several_directories_are_searched(tmp_path):
    first = tmp_path / "Applications"
    second = tmp_path / "home" / "Applications"
    first.mkdir()
    second.mkdir(parents=True)
    make_app(first, "One")
    make_app(second, "Two")

    env = {"HOME": str(tmp_path), "UPDATE_MY_MAC_APP_DIRS": f"{first}:{second}"}
    found = installed_apps.find_untracked(FakeShell(casks=[]), env)

    assert [app.name for app in found] == ["One", "Two"]


def test_a_directory_that_is_not_there_is_skipped(tmp_path):
    env = {"HOME": str(tmp_path), "UPDATE_MY_MAC_APP_DIRS": str(tmp_path / "nowhere")}

    assert installed_apps.find_untracked(FakeShell(casks=[]), env) == []


def test_the_home_directory_is_filled_in(tmp_path):
    apps = tmp_path / "Applications"
    apps.mkdir()
    make_app(apps, "Mine")

    env = {"HOME": str(tmp_path), "UPDATE_MY_MAC_APP_DIRS": "~/Applications"}
    found = installed_apps.find_untracked(FakeShell(casks=[]), env)

    assert [app.name for app in found] == ["Mine"]


def cask_removing(paths):
    """A cask that ships a pkg names its app only in what it would remove."""
    return {"token": "whatever", "artifacts": [{"uninstall": [{"delete": paths}]}]}


def test_an_app_from_a_pkg_cask_is_left_out(tmp_path):
    # zoom installs a pkg, so it has no app stanza to match against.
    make_app(tmp_path, "zoom.us")
    shell = FakeShell(casks=[cask_removing(["/Applications/zoom.us.app"])])

    assert installed_apps.find_untracked(shell, env_for(tmp_path)) == []


def test_a_single_path_written_as_text_is_understood(tmp_path):
    # Safari Technology Preview writes one path as a string, not a list.
    make_app(tmp_path, "Safari Technology Preview")
    shell = FakeShell(
        casks=[cask_removing("/Applications/Safari Technology Preview.app")]
    )

    assert installed_apps.find_untracked(shell, env_for(tmp_path)) == []


def test_an_app_named_in_a_zap_stanza_is_left_out(tmp_path):
    make_app(tmp_path, "Something")
    cask = {"token": "x", "artifacts": [{"zap": [{"trash": ["/Applications/Something.app"]}]}]}

    assert installed_apps.find_untracked(FakeShell(casks=[cask]), env_for(tmp_path)) == []


def test_an_app_belonging_to_macos_is_left_out(tmp_path, monkeypatch):
    # Safari lives in /Applications like anything else; the restricted flag is
    # what tells it apart, and that can't be set in a test without root.
    make_app(tmp_path, "Safari")
    monkeypatch.setattr(installed_apps, "belongs_to_macos", lambda path: True)

    assert installed_apps.find_untracked(FakeShell(casks=[]), env_for(tmp_path)) == []


def test_a_normal_app_does_not_look_like_a_system_one(tmp_path):
    app = make_app(tmp_path, "TokenEater")

    assert not installed_apps.belongs_to_macos(app)
