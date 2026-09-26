"""Handing an app to Homebrew, and checking that it really took."""

import plistlib

from update_my_mac import adopt_apps
from update_my_mac.app_updaters import UpdaterStatus
from update_my_mac.cask_index import Cask
from update_my_mac.installed_apps import InstalledApp
from update_my_mac.shell import CommandResult

CASK = Cask("betterdisplay", "https://betterdisplay.pro/", "5.0.6")


def bundle(tmp_path, name, version):
    app = tmp_path / f"{name}.app"
    (app / "Contents").mkdir(parents=True)
    with open(app / "Contents" / "Info.plist", "wb") as plist:
        plistlib.dump({"CFBundleShortVersionString": version}, plist)
    return InstalledApp(name, version, app, UpdaterStatus())


class BrewShell:
    """A Homebrew that adopts, and afterwards reports what it wrote down."""

    def __init__(self, recorded, exit_code=0, installed=True):
        self.recorded = recorded
        self.exit_code = exit_code
        self.installed = installed
        self.streamed = []

    def find_executable(self, command):
        return f"/fake/{command}" if self.installed else None

    def stream_command(self, args, env=None):
        self.streamed.append(args)
        return self.exit_code

    def run_command(self, args, success_exit_codes=(0,), env=None):
        return CommandResult(True, self.recorded, "")


def test_a_matching_app_is_handed_over(tmp_path):
    app = bundle(tmp_path, "BetterDisplay", "5.0.6")
    shell = BrewShell("betterdisplay 5.0.6")

    taken, message = adopt_apps.hand_to_homebrew(app, CASK, shell)
    assert taken
    assert "looks after it now" in message
    assert shell.streamed == [["/fake/brew", "install", "--cask", "betterdisplay", "--adopt"]]


def test_an_older_app_is_not_even_attempted(tmp_path):
    # Homebrew would download the whole cask and then refuse.
    app = bundle(tmp_path, "BetterDisplay", "5.0.5")
    shell = BrewShell("")

    taken, message = adopt_apps.hand_to_homebrew(app, CASK, shell)
    assert not taken
    assert "yours is 5.0.5" in message
    assert shell.streamed == []


def test_homebrew_writing_down_a_version_it_did_not_install_is_caught(tmp_path):
    # It reports success for adopting an app it never looked inside, and from
    # then on nothing would call the app outdated.
    app = bundle(tmp_path, "BetterDisplay", "5.0.6")
    app.path.joinpath("Contents", "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": "5.0.5"})
    )
    shell = BrewShell("betterdisplay 5.0.6")

    taken, message = adopt_apps.hand_to_homebrew(app, CASK, shell)
    assert not taken
    assert "wrote down betterdisplay 5.0.6, but the app is still 5.0.5" in message
    assert "brew reinstall --cask betterdisplay" in message


def test_a_build_number_after_the_comma_is_not_a_difference(tmp_path):
    app = bundle(tmp_path, "Docker", "4.92.0")
    cask = Cask("docker-desktop", "https://docker.com/", "4.92.0,240144")
    shell = BrewShell("docker-desktop 4.92.0,240144")

    assert adopt_apps.hand_to_homebrew(app, cask, shell)[0]


def test_an_app_no_cask_ships_is_said_so(tmp_path):
    app = bundle(tmp_path, "TokenEater", "5.13.0")

    taken, message = adopt_apps.hand_to_homebrew(app, None, BrewShell(""))
    assert not taken
    assert "no recipe" in message


def test_without_homebrew_nothing_is_attempted(tmp_path):
    app = bundle(tmp_path, "BetterDisplay", "5.0.6")
    shell = BrewShell("", installed=False)

    taken, message = adopt_apps.hand_to_homebrew(app, CASK, shell)
    assert not taken
    assert "not installed" in message


def test_a_failed_handover_is_reported(tmp_path):
    app = bundle(tmp_path, "BetterDisplay", "5.0.6")
    shell = BrewShell("betterdisplay 5.0.6", exit_code=1)

    taken, message = adopt_apps.hand_to_homebrew(app, CASK, shell)
    assert not taken
    assert "exited with 1" in message


def test_an_unreadable_record_is_not_treated_as_a_mismatch(tmp_path):
    # Saying nothing beats inventing a problem out of a missing answer.
    app = bundle(tmp_path, "BetterDisplay", "5.0.6")

    assert adopt_apps.hand_to_homebrew(app, CASK, BrewShell(""))[0]
