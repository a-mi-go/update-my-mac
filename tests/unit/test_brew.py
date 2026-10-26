"""What Homebrew is asked about this Mac and the casks it installed."""

import json

from update_my_mac.managers.homebrew import brew
from update_my_mac.system.shell import CommandResult

from fake_run import use_shell


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
