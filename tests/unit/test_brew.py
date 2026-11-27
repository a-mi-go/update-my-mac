"""What Homebrew is asked about this Mac and the casks it installed."""

import json

from fake_run import use_shell

from update_my_mac.managers.homebrew import brew
from update_my_mac.system.shell import CommandResult


class Homebrew:
    def __init__(self, answer, success=True):
        self.answer = answer
        self.success = success
        self.asked = []

    def find_executable(self, command):
        return "/fake/brew"

    def run_command(self, args, success_exit_codes=(0,), env=None, timeout=120):
        self.asked.append(args)
        return CommandResult(self.success, self.answer, "")


def test_an_apple_silicon_mac_looks_for_its_own_variation_first():
    use_shell(Homebrew("arm64 tahoe\n"))

    assert brew.variations_for_this_mac() == ("arm64_tahoe", "tahoe")


def test_an_intel_mac_looks_for_the_variation_named_after_the_macos():
    use_shell(Homebrew("x86_64 sequoia\n"))

    assert brew.variations_for_this_mac() == ("sequoia",)


def test_homebrew_that_cannot_say_leaves_the_recipes_own_version():
    use_shell(Homebrew("", success=False))

    assert brew.variations_for_this_mac() == ()


def test_the_versions_homebrew_would_install_come_from_its_own_recipes():
    use_shell(Homebrew(json.dumps({"casks": [
        {"token": "onyx", "version": "5.0.5"},
        {"token": "brave-browser", "version": "1.98.60.0"},
    ]})))

    assert brew.versions_homebrew_would_install() == {"onyx": "5.0.5", "brave-browser": "1.98.60.0"}


def test_an_answer_that_is_not_json_means_nothing_is_known():
    use_shell(Homebrew("not json"))

    assert brew.versions_homebrew_would_install() == {}


def test_the_installed_taps_are_the_dicts_homebrew_describes():
    use_shell(Homebrew(json.dumps([{"name": "homebrew/core", "formula_names": ["git"]}, "stray"])))

    assert brew.installed_taps() == [{"name": "homebrew/core", "formula_names": ["git"]}]


def test_an_answer_about_taps_that_is_not_a_list_means_no_taps():
    use_shell(Homebrew(json.dumps({"name": "homebrew/core"})))

    assert brew.installed_taps() == []


def test_formulae_are_looked_up_in_homebrew_core_by_their_full_name():
    homebrew = Homebrew(json.dumps({"formulae": []}))

    use_shell(homebrew)
    brew.describe_in_core({"sst", "opencode"}, None)

    assert homebrew.asked == [["/fake/brew", "info", "--json=v2", "homebrew/core/opencode", "homebrew/core/sst"]]


def test_nothing_is_asked_when_there_are_no_names():
    homebrew = Homebrew("{}")

    use_shell(homebrew)

    assert brew.describe_in_core(set()) == {}
    assert homebrew.asked == []


def test_a_name_loses_its_tap_but_an_npm_scope_is_kept():
    assert brew.without_tap("anomalyco/tap/opencode") == "opencode"
    assert brew.without_tap("@scope/pkg") == "@scope/pkg"
    assert brew.without_tap("git") == "git"


def test_the_names_on_an_outdated_list_are_given_without_their_taps():
    lines = ["anomalyco/tap/opencode  1.19.6 → 1.19.7", "git  2.48.1 → 2.49.0"]

    assert brew.reported_names(lines) == {"opencode", "git"}
