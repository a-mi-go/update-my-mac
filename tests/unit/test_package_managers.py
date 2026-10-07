import pytest

from update_my_mac import managers
from update_my_mac.managers import CheckFailed
from update_my_mac.system.shell import CommandResult

NPM_OUTDATED = """{
  "typescript": {"current": "5.4.2", "wanted": "5.4.5", "latest": "5.4.5"},
  "prettier": {"current": "3.2.0", "wanted": "3.3.0", "latest": "3.3.0"}
}"""

# npm exits 1 for this too, which is why the exit code alone can't classify it.
NPM_NETWORK_FAILURE = """{
  "error": {
    "code": "ENOTFOUND",
    "summary": "request to https://registry.npmjs.org/typescript failed"
  }
}"""


class FakeShell:
    """Stands in for the shell module: same two functions, no subprocesses."""

    def __init__(self, installed, result):
        self.installed = installed
        self.result = result
        self.calls = []

    def find_executable(self, command):
        return f"/fake/{command}" if command in self.installed else None

    def run_command(self, args, success_exit_codes=(0,), env=None):
        self.calls.append((args, env))
        return self.result


def manager(key):
    return next(m for m in managers.MANAGERS if m.key == key)


def test_npm_json_becomes_one_line_per_package():
    assert managers.parse_npm_outdated(NPM_OUTDATED) == [
        "prettier  3.2.0 → 3.3.0",
        "typescript  5.4.2 → 5.4.5",
    ]


def test_empty_json_object_is_up_to_date():
    assert managers.parse_pnpm_outdated("{}") == []
    assert managers.parse_npm_outdated("") == []


def test_npm_error_payload_is_a_failed_check():
    with pytest.raises(CheckFailed, match="ENOTFOUND|request to"):
        managers.parse_npm_outdated(NPM_NETWORK_FAILURE)


def test_unreadable_output_is_a_failed_check():
    with pytest.raises(CheckFailed):
        managers.parse_npm_outdated("npm error code ENOTFOUND")


def test_failing_npm_is_reported_as_an_error_not_a_package():
    shell = FakeShell(
        installed=("npm",), result=CommandResult(True, NPM_NETWORK_FAILURE, "")
    )

    report = managers.check_for_outdated(manager("npm"), shell)
    assert report.outdated_packages == []
    assert "ENOTFOUND" in report.error_message


def test_stderr_is_never_parsed_as_packages():
    shell = FakeShell(
        installed=("npm",),
        result=CommandResult(True, "{}", "npm warn config global deprecated"),
    )

    report = managers.check_for_outdated(manager("npm"), shell)
    assert report.outdated_packages == []
    assert report.error_message == ""


def test_missing_manager_is_skipped():
    shell = FakeShell(installed=(), result=CommandResult(True, "", ""))
    assert managers.check_for_outdated(manager("mas"), shell) is None


def test_nonzero_exit_is_reported_with_its_stderr():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(False, "", "brew: boom")
    )

    report = managers.check_for_outdated(manager("brew"), shell)
    assert report.error_message == "brew: boom"
    assert report.outdated_packages == []


def test_brew_runs_without_an_auto_update():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(True, "git (2.48.1) < 2.49.0", "")
    )

    managers.check_for_outdated(manager("brew"), shell)
    _, env = shell.calls[0]
    assert env["HOMEBREW_NO_AUTO_UPDATE"] == "1"


def test_check_installed_skips_everything_that_is_missing():
    shell = FakeShell(installed=(), result=CommandResult(True, "", ""))
    assert managers.check_installed(shell) == []


def test_silent_nonzero_exit_is_a_failure_not_up_to_date():
    # npm exits 1 both for "updates found" and for failures it doesn't phrase
    # as JSON; without output there is nothing to call up to date.
    shell = FakeShell(
        installed=("npm",),
        result=CommandResult(True, "", "npm error code E401", exit_code=1),
    )

    report = managers.check_for_outdated(manager("npm"), shell)
    assert report.outdated_packages == []
    assert "E401" in report.error_message


def test_silent_zero_exit_really_is_up_to_date():
    shell = FakeShell(installed=("mas",), result=CommandResult(True, "", ""))

    report = managers.check_for_outdated(manager("mas"), shell)
    assert report.outdated_packages == []
    assert report.error_message == ""

def test_each_manager_is_asked_the_right_question():
    asked = {}
    for entry in managers.MANAGERS:
        shell = FakeShell(installed=(entry.command,), result=CommandResult(True, "{}", ""))
        managers.check_for_outdated(entry, shell)
        args, env = shell.calls[0]
        asked[entry.key] = (args, env)

    # --verbose, because Homebrew prints bare names once its output is not a
    # terminal, and ours never is.
    assert asked["brew"][0] == ["/fake/brew", "outdated", "--verbose"]
    assert asked["mas"][0] == ["/fake/mas", "outdated"]
    assert asked["npm"][0] == ["/fake/npm", "outdated", "-g", "--json"]
    assert asked["pnpm"][0] == ["/fake/pnpm", "outdated", "-g", "--json"]


def test_only_homebrew_gets_an_environment_override():
    for entry in managers.MANAGERS:
        shell = FakeShell(installed=(entry.command,), result=CommandResult(True, "{}", ""))
        managers.check_for_outdated(entry, shell)
        _, env = shell.calls[0]
        if entry.key == "brew":
            assert env["HOMEBREW_NO_AUTO_UPDATE"] == "1"
        else:
            assert env is None


def test_a_manager_without_upgrade_arguments_is_not_run():
    shell = FakeShell(installed=("brew",), result=CommandResult(True, "", ""))
    shell.stream_command = lambda args, env=None: 0
    entry = managers.PackageManager("x", "X", "brew", ("outdated",))

    assert managers.upgrade(entry, shell) == -1


NPM_ITSELF_OUTDATED = """{
  "npm": {"current": "12.0.2", "wanted": "12.1.0", "latest": "12.1.0"}
}"""


def test_a_manager_that_cannot_update_itself_is_never_offered():
    shell = FakeShell({"mas"}, CommandResult(True, "", ""))

    assert managers.check_self(manager("mas"), shell) is None


def test_npm_reports_its_own_new_version():
    shell = FakeShell({"npm"}, CommandResult(True, NPM_ITSELF_OUTDATED, "", 1))

    update = managers.check_self(manager("npm"), shell)
    assert update.key == "npm"
    assert update.description == "npm  12.0.2 → 12.1.0"


def test_a_current_npm_is_not_offered():
    shell = FakeShell({"npm"}, CommandResult(True, "{}", ""))

    assert managers.check_self(manager("npm"), shell) is None


def test_other_packages_in_the_answer_are_not_mistaken_for_npm():
    # `npm outdated -g npm` should only answer about npm, but the reply is read
    # by name rather than trusted to hold nothing else.
    shell = FakeShell({"npm"}, CommandResult(True, NPM_OUTDATED, "", 1))

    assert managers.check_self(manager("npm"), shell) is None


def test_a_failed_self_check_is_reported_rather_than_raised():
    shell = FakeShell({"npm"}, CommandResult(True, NPM_NETWORK_FAILURE, "", 1))

    update = managers.check_self(manager("npm"), shell)
    assert "ENOTFOUND" in update.error_message


class HomebrewShell(FakeShell):
    def __init__(self, cache):
        super().__init__({"brew"}, CommandResult(True, str(cache), ""))


def homebrew_cache(tmp_path, age_in_days):
    import os
    import time

    api = tmp_path / "api"
    api.mkdir()
    marker = api / "formula_names.txt"
    marker.write_text("git\n")
    when = time.time() - age_in_days * 24 * 60 * 60
    os.utime(marker, (when, when))
    return tmp_path


def test_a_fresh_homebrew_index_is_not_offered(tmp_path):
    shell = HomebrewShell(homebrew_cache(tmp_path, age_in_days=0))

    assert managers.check_self(manager("brew"), shell) is None


def test_a_stale_homebrew_index_says_how_old_it_is(tmp_path):
    shell = HomebrewShell(homebrew_cache(tmp_path, age_in_days=3))

    update = managers.check_self(manager("brew"), shell)
    assert update.description == "index is 3 days old"


def test_one_day_is_written_in_the_singular(tmp_path):
    shell = HomebrewShell(homebrew_cache(tmp_path, age_in_days=1.5))

    assert managers.check_self(manager("brew"), shell).description == "index is 1 day old"


def test_a_cache_without_an_index_is_offered(tmp_path):
    (tmp_path / "api").mkdir()
    shell = HomebrewShell(tmp_path)

    update = managers.check_self(manager("brew"), shell)
    assert update.description == "index has never been fetched"


def test_a_brew_that_says_nothing_about_its_cache_is_left_alone():
    # An empty answer used to be read as the current directory.
    shell = HomebrewShell("")

    assert managers.check_self(manager("brew"), shell) is None


def test_only_installed_managers_are_asked_about_themselves():
    shell = FakeShell(set(), CommandResult(True, "{}", ""))

    assert managers.check_themselves(shell) == []


def test_a_homebrew_without_an_api_cache_is_left_alone(tmp_path):
    # Fetching formulae over git leaves no api directory, and then its age
    # says nothing about whether Homebrew is behind.
    shell = HomebrewShell(tmp_path)

    assert managers.check_self(manager("brew"), shell) is None


TAP_INFO = """[
  {"name": "anomalyco/tap", "trusted": false},
  {"name": "homebrew/core", "trusted": true}
]"""


class TwoAnswerShell(FakeShell):
    """Answers `outdated` with one result and `tap-info` with another."""

    def __init__(self, outdated, tap_info):
        super().__init__({"brew"}, outdated)
        self.tap_info = tap_info

    def run_command(self, args, success_exit_codes=(0,), env=None):
        self.calls.append((args, env))
        return self.tap_info if "tap-info" in args else self.result


def test_a_tap_homebrew_ignores_is_carried_into_the_report():
    # Without this the report looks complete while a whole tap is missing.
    outdated = CommandResult(True, "git (2.48.1) < 2.49.0", "Warning: taps are not trusted:")
    shell = TwoAnswerShell(outdated, CommandResult(True, TAP_INFO, ""))

    report = managers.check_for_outdated(manager("brew"), shell)
    assert report.ignored_taps == ["anomalyco/tap"]


def test_nothing_is_claimed_when_homebrew_did_not_complain():
    shell = TwoAnswerShell(CommandResult(True, "", ""), CommandResult(True, TAP_INFO, ""))

    assert managers.check_for_outdated(manager("brew"), shell).ignored_taps == []


def test_an_unreadable_tap_list_is_not_guessed_at():
    outdated = CommandResult(True, "", "Warning: taps are not trusted:")
    shell = TwoAnswerShell(outdated, CommandResult(True, "not json", ""))

    assert managers.check_for_outdated(manager("brew"), shell).ignored_taps == []


def test_homebrew_versions_are_read_off_its_verbose_output():
    # A formula is "name (old) < new", a cask "name (old) != new".
    packages = managers.parse_brew_outdated(
        "tcl-tk (9.0.4) < 9.0.4_1\nchatgpt (26.917.71314) != 26.924.22138\n"
    )

    assert packages == ["tcl-tk  9.0.4 → 9.0.4_1", "chatgpt  26.917.71314 → 26.924.22138"]


def test_a_homebrew_line_in_no_known_shape_is_kept_as_it_is():
    assert managers.parse_brew_outdated("something odd\n") == ["something odd"]


def test_the_app_store_says_both_versions_without_its_id():
    packages = managers.parse_mas_outdated("6469021132  PDFgear  (2.27 -> 2.28)\n")

    assert packages == ["PDFgear  2.27 → 2.28"]


def behind_update(key, error_message=""):
    return managers.ManagerUpdate(key, key, "a newer one exists", error_message)


def test_a_manager_that_refreshed_is_no_longer_behind():
    still = managers.still_behind([behind_update("brew"), behind_update("npm")], ["brew"])

    assert [one.key for one in still] == ["npm"]


def test_a_manager_nobody_could_ask_stays_behind_even_once_it_refreshed():
    still = managers.still_behind([behind_update("brew", "boom")], ["brew"])

    assert [one.key for one in still] == ["brew"]


def test_refreshing_nothing_leaves_every_manager_behind():
    behind = [behind_update("brew"), behind_update("npm")]

    assert managers.still_behind(behind, []) == behind
