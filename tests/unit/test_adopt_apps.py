"""Handing an app to Homebrew, and checking that it really took."""

import plistlib

from update_my_mac import adopt_apps, versions
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


def test_an_older_app_gets_the_recipe_version_put_over_it(tmp_path):
    # --force rather than --adopt, which Homebrew refuses for anything but an
    # identical copy, and the two cannot be combined.
    app = bundle(tmp_path, "BetterDisplay", "5.0.5")
    shell = BrewShell("")

    taken, _ = adopt_apps.hand_to_homebrew(app, CASK, shell)
    assert taken
    assert shell.streamed == [["/fake/brew", "install", "--cask", "betterdisplay", "--force"]]


def test_an_app_newer_than_the_recipe_is_put_back_when_that_is_asked_for(tmp_path):
    # Going back a version is a deliberate answer about one app. What keeps it
    # from happening by accident is the menu, which calls it a downgrade and
    # leaves it out of the bulk step.
    app = bundle(tmp_path, "BetterDisplay", "5.0.7")
    shell = BrewShell("")

    taken, _ = adopt_apps.hand_to_homebrew(app, CASK, shell)
    assert taken
    assert shell.streamed == [["/fake/brew", "install", "--cask", "betterdisplay", "--force"]]


def test_what_the_handover_would_do_is_said_in_the_menu(tmp_path):
    matching = bundle(tmp_path / "same", "BetterDisplay", "5.0.6")
    older = bundle(tmp_path / "old", "BetterDisplay", "5.0.5")
    newer = bundle(tmp_path / "new", "BetterDisplay", "5.0.7")

    assert adopt_apps.handover_label(matching, CASK) == "add to Homebrew (betterdisplay 5.0.6)"
    assert adopt_apps.handover_label(older, CASK) == (
        "update to betterdisplay 5.0.6 and let Homebrew take over"
    )
    assert adopt_apps.handover_label(newer, CASK) == (
        "let Homebrew take over (downgrade 5.0.7 → 5.0.6)"
    )
    assert adopt_apps.handover_label(matching, None) == ""


def test_two_version_schemes_are_not_called_newer_or_older(tmp_path):
    # Foxit reports 2026.1.1.70276 where its recipe says 14.0.8.69494. Neither
    # is ahead of the other, they are counted differently.
    app = bundle(tmp_path, "Foxit PDF Editor", "2026.1.1.70276")
    cask = Cask("foxit-pdf-editor", "https://foxit.com/", "14.0.8.69494")

    assert adopt_apps.compare_to_app(app, cask) == adopt_apps.UNCLEAR
    assert adopt_apps.handover_label(app, cask) == (
        "let Homebrew take over (replace 2026.1.1.70276 with 14.0.8.69494, "
        "no telling which is newer)"
    )
    # Offered all the same, because refusing leaves the app untracked forever.
    assert adopt_apps.can_take_over(app, cask)
    assert not adopt_apps.would_downgrade(app, cask)


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


def test_a_recipe_that_lags_the_app_says_so_in_the_option(tmp_path):
    # The Codex cask sat weeks behind the installed app. Taking it over is
    # still allowed, as long as the menu calls it what it is.
    app = bundle(tmp_path, "Codex", "26.831.21537")
    cask = Cask("codex-app", "https://openai.com/codex", "26.623.141536")

    assert adopt_apps.would_downgrade(app, cask)
    assert adopt_apps.handover_label(app, cask) == (
        "let Homebrew take over (downgrade 26.831.21537 → 26.623.141536)"
    )


def test_which_way_round_the_versions_are():
    assert versions.is_newer("26.831.21537", than="26.623.141536")
    assert versions.is_newer("5.0.6", than="5.0.5")
    # A recipe carries a build number the app never mentions.
    assert not versions.is_newer("5.0.6,1234", than="5.0.6")


def test_a_recipe_behind_the_app_says_what_taking_it_over_would_cost(tmp_path):
    app = bundle(tmp_path, "Codex", "26.831.21537")
    cask = Cask("codex-app", "https://openai.com/codex", "26.623.141536")

    note = adopt_apps.homebrew_note(app, cask)

    assert "still 26.623.141536" in note
    assert "older than the 26.831.21537 you have" in note
    assert "put that older build back" in note


def test_two_schemes_say_that_neither_is_newer(tmp_path):
    app = bundle(tmp_path, "Foxit PDF Editor", "2026.1.1.70276")
    cask = Cask("foxit-pdf-editor", "https://foxit.com/", "14.0.8.69494")

    assert "neither one is clearly the newer" in adopt_apps.homebrew_note(app, cask)


def test_a_recipe_that_matches_or_leads_needs_no_note(tmp_path):
    # The option says "add to Homebrew" or "update to", which is the whole story.
    assert adopt_apps.homebrew_note(bundle(tmp_path / "a", "BD", "5.0.6"), CASK) == ""
    assert adopt_apps.homebrew_note(bundle(tmp_path / "b", "BD", "5.0.5"), CASK) == ""


def test_an_app_homebrew_never_heard_of_says_so(tmp_path):
    app = bundle(tmp_path, "TokenEater", "1.0")

    assert adopt_apps.homebrew_note(app, None) == "Homebrew has no recipe for this app."
