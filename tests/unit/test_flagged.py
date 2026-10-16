"""Packages Homebrew has doubts about, and the disk images its upgrades leave attached."""

import plistlib
from fake_run import use_shell

from update_my_mac.managers.homebrew import flagged
from update_my_mac.managers.homebrew import mounted_downloads
from update_my_mac.system.shell import CommandResult


def formula(name, installed, stable, **more):
    return {
        "name": name, "full_name": f"tap/{name}", "versions": {"stable": stable},
        "installed": [{"version": version} for version in installed], **more,
    }


def test_a_new_version_scheme_is_flagged_though_homebrew_calls_it_current():
    # Build 64 reads as newer than 3.4.1, so `brew outdated` stays silent.
    found = flagged.find({"formulae": [formula("clerk", ["64"], "3.4.1")]})

    assert [(item.name, item.kind) for item in found] == [("tap/clerk", flagged.DIFFERS)]
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

