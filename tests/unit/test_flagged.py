"""Packages Homebrew has doubts about, and the disk images its upgrades leave attached."""

import plistlib

from fake_run import use_shell

from update_my_mac.managers.homebrew import flagged, mounted_downloads
from update_my_mac.system.shell import CommandResult


def formula(name, installed, stable, **more):
    return {
        "name": name, "full_name": f"user/tap/{name}", "versions": {"stable": stable},
        "installed": [{"version": version} for version in installed], **more,
    }


def test_a_new_version_scheme_is_flagged_though_homebrew_calls_it_current():
    # Build 64 reads as newer than 3.4.1, so `brew outdated` stays silent.
    found = flagged.find({"formulae": [formula("clerk", ["64"], "3.4.1")]})

    assert [(item.name, item.kind) for item in found] == [("user/tap/clerk", flagged.DIFFERS)]
    assert (found[0].installed, found[0].available) == ("64", "3.4.1")


def test_a_version_newer_than_the_recipe_is_not_flagged():
    # Reinstalling would go back to the recipe's older version.
    assert flagged.find({"formulae": [formula("clerk", ["3.5.0"], "3.4.1")]}) == []


def test_a_package_at_the_recipes_version_is_not_flagged():
    installed = {"formulae": [
        formula("git", ["2.49.0"], "2.49.0"),
        formula("wget", ["1.25.0_1"], "1.25.0"),
    ]}

    assert flagged.find(installed) == []


def test_what_homebrew_already_calls_outdated_pinned_or_head_is_left_alone():
    installed = {"formulae": [
        formula("old", ["1"], "2", outdated=True),
        formula("held", ["1"], "2", pinned=True),
        formula("edge", ["HEAD-abc"], "2"),
    ]}

    assert flagged.find(installed) == []


def test_a_package_nothing_installed_is_not_flagged():
    assert flagged.find({"formulae": [formula("git", [], "2.49.0")]}) == []


def test_a_name_the_outdated_list_already_gave_is_not_said_twice():
    installed = {"formulae": [formula("clerk", ["64"], "3.4.1")]}

    assert flagged.find(installed, already_reported={"clerk"}) == []


def test_a_disabled_cask_says_why():
    installed = {"casks": [{
        "token": "google-trends", "installed": "1.0", "disabled": True,
        "disable_reason": "fails_gatekeeper_check", "disable_date": "2026-10-12",
    }]}

    (found,) = flagged.find(installed)

    assert (found.kind, found.is_cask) == (flagged.DISABLED, True)
    assert found.reason == "fails gatekeeper check since 2026-10-12"


def test_a_deprecated_package_is_named_with_why():
    (found,) = flagged.find({"formulae": [
        formula("old", ["1"], "1", deprecated=True, deprecation_reason="unmaintained"),
    ]})

    assert found.kind == flagged.DEPRECATED
    assert found.reason == "unmaintained"


def cask_missing_its_app(target, **more):
    return {"token": "charles", "installed": "5.2.1", "outdated": True,
            "artifacts": [{"uninstall": []}, {"app": ["Charles.app"], "target": str(target)}], **more}


def test_a_cask_whose_app_was_thrown_away_is_flagged(tmp_path):
    (found,) = flagged.find({"casks": [cask_missing_its_app(tmp_path / "Charles.app")]})

    assert (found.name, found.kind, found.is_cask, found.installed) == ("charles", flagged.APP_MISSING, True, "5.2.1")


def test_a_cask_whose_app_is_in_place_is_not_flagged(tmp_path):
    (tmp_path / "Charles.app").mkdir()

    assert flagged.find({"casks": [cask_missing_its_app(tmp_path / "Charles.app")]}) == []


def test_a_cask_without_an_app_is_not_flagged():
    cask = {"token": "font-x", "installed": "1", "artifacts": [{"font": ["X.ttf"], "target": "/nowhere/X.ttf"}]}

    assert flagged.find({"casks": [cask]}) == []


def test_a_cask_that_is_not_installed_is_not_flagged():
    assert flagged.find({"casks": [{"token": "x", "installed": None, "disabled": True}]}) == []


class DiskShell:
    def __init__(self, images, cache="/home/Caches/Homebrew"):
        self.images = images
        self.cache = cache

    def find_executable(self, command):
        return f"/fake/{command}"

    def run_command(self, args, success_exit_codes=(0,), env=None):
        if args[1:] == ["--cache"]:
            return CommandResult(True, self.cache, "")
        return CommandResult(True, plistlib.dumps({"images": self.images}).decode(), "")


def image(path, device="/dev/disk8"):
    return {"image-path": path, "system-entities": [{"dev-entry": device}, {"dev-entry": device + "s1"}]}


def test_a_download_left_attached_is_found():
    shell = DiskShell([image("/home/Caches/Homebrew/downloads/5ba7--charles-proxy-5.2.2.dmg")])

    use_shell(shell)
    (found,) = mounted_downloads.find()

    assert found.path.name == "5ba7--charles-proxy-5.2.2.dmg"
    assert found.device == "/dev/disk8"


def test_an_image_from_anywhere_else_is_not_touched():
    shell = DiskShell([image("/Users/me/Downloads/pycharm.dmg")])

    use_shell(shell)
    assert mounted_downloads.find() == []


def test_an_unreadable_answer_means_nothing_is_found():
    class Garbled(DiskShell):
        def run_command(self, args, success_exit_codes=(0,), env=None):
            return CommandResult(True, "/home/Caches/Homebrew" if "--cache" in args else "not a plist", "")

    use_shell(Garbled([]))
    assert mounted_downloads.find() == []



def test_the_casks_among_the_described_packages_whose_app_is_missing_are_named_by_token(tmp_path):
    (tmp_path / "Here.app").mkdir()
    here = cask_missing_its_app(tmp_path / "Here.app", token="here")

    described = {"casks": [cask_missing_its_app(tmp_path / "Charles.app"), here], "formulae": [{"name": "git"}]}
    missing = flagged.casks_missing_their_app(described)

    assert missing == {"charles"}


def third_party(name, installed, stable, tap="anomalyco/tap", **more):
    return {**formula(name, [installed], stable, **more), "tap": tap, "full_name": f"{tap}/{name}"}


TAP = {"name": "anomalyco/tap", "formula_names": [
    "anomalyco/tap/opencode", "anomalyco/tap/opencode-v2", "anomalyco/tap/sst",
]}


def test_a_later_major_version_under_a_new_name_in_the_same_tap_is_flagged():
    installed = {"formulae": [third_party("opencode", "1.19.6", "1.19.6")]}

    (found,) = flagged.successors_in_tap(installed, [TAP])

    assert (found.name, found.kind, found.installed) == ("anomalyco/tap/opencode", flagged.SUCCESSOR, "1.19.6")
    assert found.switch_to == "anomalyco/tap/opencode-v2"
    assert found.reason == "a later major version is the formula opencode-v2"


def test_the_latest_of_several_later_majors_is_the_one_offered():
    tap = {"name": "clerk/stable", "formula_names": [
        "clerk/stable/clerk", "clerk/stable/clerk@2", "clerk/stable/clerk@4", "clerk/stable/clerk@3",
    ]}
    installed = {"formulae": [third_party("clerk", "1.0.0", "1.0.0", tap="clerk/stable")]}

    (found,) = flagged.successors_in_tap(installed, [tap])

    assert found.switch_to == "clerk/stable/clerk@4"


def test_a_versioned_name_that_is_not_later_is_no_successor():
    tap = {"name": "clerk/stable", "formula_names": ["clerk/stable/clerk", "clerk/stable/clerk@3"]}
    installed = {"formulae": [third_party("clerk", "3.4.1", "3.4.1", tap="clerk/stable")]}

    assert flagged.successors_in_tap(installed, [tap]) == []


def test_a_formula_already_on_a_versioned_name_is_left_on_that_line():
    tap = {"name": "clerk/stable", "formula_names": ["clerk/stable/clerk@2", "clerk/stable/clerk@3"]}
    installed = {"formulae": [third_party("clerk@2", "2.1.0", "2.1.0", tap="clerk/stable")]}

    assert flagged.successors_in_tap(installed, [tap]) == []


def test_a_build_number_is_never_taken_for_a_major_with_a_successor():
    installed = {"formulae": [third_party("opencode", "64", "64")]}

    assert flagged.successors_in_tap(installed, [TAP]) == []


def test_homebrew_core_formulae_have_no_successor_looked_for():
    core = {"name": "homebrew/core", "formula_names": ["python@3.12", "python@3.13"]}
    installed = {"formulae": [third_party("python", "3.12.1", "3.12.1", tap="homebrew/core")]}

    assert flagged.successors_in_tap(installed, [core]) == []


def test_a_successor_for_a_name_the_outdated_list_gave_is_not_said_twice():
    installed = {"formulae": [third_party("opencode", "1.19.6", "1.19.6")]}

    assert flagged.successors_in_tap(installed, [TAP], already_reported={"opencode"}) == []


CORE = {"name": "homebrew/core", "formula_names": ["git", "opencode"]}


def test_only_third_party_formulae_homebrew_core_has_as_well_are_looked_up_there():
    installed = {"formulae": [
        third_party("opencode", "1.19.6", "1.19.6"),
        third_party("sst", "3.0.0", "3.0.0"),
        third_party("git", "2.49.0", "2.49.0", tap="homebrew/core"),
    ]}

    assert flagged.names_also_in_core(installed, [TAP, CORE]) == {"opencode"}


def test_a_later_version_in_homebrew_core_is_flagged_with_the_formula_to_switch_to():
    installed = {"formulae": [third_party("opencode", "1.19.6", "1.19.6")]}
    in_core = {"formulae": [formula("opencode", [], "2.4.1")]}

    (found,) = flagged.newer_in_core(installed, in_core)

    assert (found.name, found.kind, found.installed, found.available) == (
        "anomalyco/tap/opencode", flagged.NEWER_IN_CORE, "1.19.6", "2.4.1")
    assert found.switch_to == "homebrew/core/opencode"


def test_an_older_or_equal_version_in_homebrew_core_is_not_flagged():
    installed = {"formulae": [third_party("opencode", "2.4.1", "2.4.1")]}

    assert flagged.newer_in_core(installed, {"formulae": [formula("opencode", [], "2.4.1")]}) == []
    assert flagged.newer_in_core(installed, {"formulae": [formula("opencode", [], "1.19.6")]}) == []


def test_a_later_version_of_the_same_major_in_homebrew_core_is_not_flagged():
    installed = {"formulae": [third_party("opencode", "2.3.2", "2.3.2")]}

    assert flagged.newer_in_core(installed, {"formulae": [formula("opencode", [], "2.4.1")]}) == []


def test_a_pinned_formula_is_offered_no_switch():
    installed = {"formulae": [third_party("opencode", "1.19.6", "1.19.6", pinned=True)]}
    in_core = {"formulae": [formula("opencode", [], "2.4.1")]}

    assert flagged.successors_in_tap(installed, [TAP]) == []
    assert flagged.newer_in_core(installed, in_core) == []
