"""The commands that put right what Homebrew cannot update by itself."""

from pathlib import Path

from update_my_mac.controller import homebrew_fixes
from update_my_mac.managers.homebrew import behind_the_recipe
from update_my_mac.managers.homebrew import flagged
from update_my_mac.managers.homebrew.casks import Cask
from update_my_mac.managers.homebrew.mounted_downloads import MountedImage
from update_my_mac.checks.installed_apps import InstalledApp


def item(name="BetterDisplay", app_version="5.0.5", cask_version="5.0.6", recorded="5.0.6",
         token=None):
    app = InstalledApp(name, app_version, Path(f"/Applications/{name}.app"))
    return behind_the_recipe.Behind(
        app, Cask(token or name.lower(), "https://x.test/", cask_version), recorded
    )


def test_a_false_version_recorded_version_is_reinstalled():
    fix = homebrew_fixes.fix_for_behind(item())

    assert fix.main.command == ("brew", "reinstall", "--cask", "betterdisplay")
    assert "wrote down a version it never installed" in fix.note
    assert fix.label == "BetterDisplay 5.0.5 → 5.0.6"


def test_a_cask_homebrew_knows_is_old_is_upgraded_greedily():
    fix = homebrew_fixes.fix_for_behind(item(recorded="5.0.5"))

    assert fix.main.command == ("brew", "upgrade", "--cask", "--greedy", "betterdisplay")
    assert fix.note == ""


def commands_of(fix):
    return [option.command for option in fix.others]


def test_an_app_behind_its_recipe_can_be_uninstalled_instead():
    assert ("brew", "uninstall", "--cask", "betterdisplay") in commands_of(
        homebrew_fixes.fix_for_behind(item()))


def test_an_app_with_its_own_updater_can_be_opened_to_update_there():
    from update_my_mac.checks import app_updaters

    behind = item()
    behind.updater = app_updaters.UpdaterStatus(app_updaters.SPARKLE, True)

    assert ("open", "-a", str(behind.app.path)) in commands_of(homebrew_fixes.fix_for_behind(behind))
    assert not any(c[0] == "open" for c in commands_of(homebrew_fixes.fix_for_behind(item())))


def test_opening_the_app_never_counts_as_dealing_with_it():
    from update_my_mac.checks import app_updaters

    behind = item()
    behind.updater = app_updaters.UpdaterStatus(app_updaters.SPARKLE, True)
    (opening,) = [o for o in homebrew_fixes.fix_for_behind(behind).others if o.command[0] == "open"]

    assert not opening.settles


def test_homebrews_record_can_go_while_the_app_stays(tmp_path):
    (tmp_path / "betterdisplay").mkdir()

    fix = homebrew_fixes.fix_for_behind(item(), str(tmp_path))

    assert ("rm", "-r", str(tmp_path / "betterdisplay")) in commands_of(fix)


def test_nothing_is_offered_to_forget_what_homebrew_has_no_record_of(tmp_path):
    assert not any(c[0] == "rm" for c in commands_of(homebrew_fixes.fix_for_behind(item(), str(tmp_path))))
    assert not any(c[0] == "rm" for c in commands_of(homebrew_fixes.fix_for_behind(item())))


def test_a_token_that_is_no_plain_cask_name_is_never_removed(tmp_path):
    caskroom = tmp_path / "Caskroom"
    (caskroom / "sub").mkdir(parents=True)

    for token in ("..", ".", "sub/..", "../Caskroom"):
        fix = homebrew_fixes.fix_for_behind(item(token=token), str(caskroom))
        assert not any(c[0] == "rm" for c in commands_of(fix)), token


def bundle_at(tmp_path, version):
    import plistlib

    path = tmp_path / "BetterDisplay.app"
    (path / "Contents").mkdir(parents=True, exist_ok=True)
    (path / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": version}))
    return path


def test_an_upgrade_is_confirmed_with_the_version_now_on_disk(tmp_path):
    behind = item()
    behind.app.path = bundle_at(tmp_path, "5.0.6")

    said = homebrew_fixes.fix_for_behind(behind).confirm(("brew", "upgrade", "--cask", "x"))

    assert said == (True, ("BetterDisplay: updated 5.0.5 → 5.0.6", "green"))


def test_an_upgrade_that_changed_nothing_says_so_and_did_not_work(tmp_path):
    behind = item()
    behind.app.path = bundle_at(tmp_path, "5.0.5")

    worked, said = homebrew_fixes.fix_for_behind(behind).confirm(("brew", "reinstall", "--cask", "x"))

    assert not worked
    assert said == ("BetterDisplay: the command finished, but the app is still 5.0.5", "yellow")


def test_the_other_ways_out_are_left_to_the_plain_confirmation():
    assert homebrew_fixes.fix_for_behind(item()).confirm(("brew", "uninstall", "--cask", "x")) == (True, None)


def test_a_package_that_differs_is_reinstalled_or_can_be_uninstalled():
    fix = homebrew_fixes.fix_for_flagged(
        flagged.Flagged("tap/clerk", flagged.DIFFERS, installed="64", available="3.4.1"))

    assert fix.label == "tap/clerk  64 → 3.4.1"
    assert fix.note == "versions cannot be compared"
    assert fix.main.command == ("brew", "reinstall", "tap/clerk")
    assert commands_of(fix) == [("brew", "uninstall", "tap/clerk")]


def test_a_disabled_cask_is_uninstalled_and_says_why():
    fix = homebrew_fixes.fix_for_flagged(flagged.Flagged(
        "google-trends", flagged.DISABLED, True, "1.0", reason="fails gatekeeper check"))

    assert fix.main.command == ("brew", "uninstall", "--cask", "google-trends")
    assert fix.note == "fails gatekeeper check"
    assert fix.others == ()


def test_nothing_is_run_for_a_deprecated_package():
    assert homebrew_fixes.fix_for_flagged(flagged.Flagged("old", flagged.DEPRECATED)) is None


def test_an_attached_download_is_detached_and_named_without_its_hash():
    fix = homebrew_fixes.fix_for_image(
        MountedImage(Path("/c/downloads/5ba7--charles-proxy-5.2.2.dmg"), "/dev/disk8"))

    assert fix.label == "charles-proxy-5.2.2.dmg"
    assert fix.main.command == ("hdiutil", "detach", "-force", "/dev/disk8")
