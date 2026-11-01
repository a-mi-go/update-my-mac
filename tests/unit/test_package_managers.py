import pytest

from update_my_mac import managers
from update_my_mac.managers import CheckFailed
from update_my_mac.system import shell as real_shell
from update_my_mac.system.shell import CommandResult
from fake_run import swap, use_shell

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
    assert manager("npm").parse_outdated(NPM_OUTDATED) == [
        "prettier  3.2.0 → 3.3.0",
        "typescript  5.4.2 → 5.4.5",
    ]


def test_empty_json_object_is_up_to_date():
    assert manager("pnpm").parse_outdated("{}") == []
    assert manager("npm").parse_outdated("") == []


def test_npm_error_payload_is_a_failed_check():
    with pytest.raises(CheckFailed, match="ENOTFOUND|request to"):
        manager("npm").parse_outdated(NPM_NETWORK_FAILURE)


def test_unreadable_output_is_a_failed_check():
    with pytest.raises(CheckFailed):
        manager("npm").parse_outdated("npm error code ENOTFOUND")


def test_failing_npm_is_reported_as_an_error_not_a_package():
    shell = FakeShell(
        installed=("npm",), result=CommandResult(True, NPM_NETWORK_FAILURE, "")
    )

    use_shell(shell)
    report = manager("npm").outdated()
    assert report.outdated_packages == []
    assert "ENOTFOUND" in report.error_message


def test_stderr_is_never_parsed_as_packages():
    shell = FakeShell(
        installed=("npm",),
        result=CommandResult(True, "{}", "npm warn config global deprecated"),
    )

    use_shell(shell)
    report = manager("npm").outdated()
    assert report.outdated_packages == []
    assert report.error_message == ""


def test_missing_manager_is_skipped():
    shell = FakeShell(installed=(), result=CommandResult(True, "", ""))
    use_shell(shell)
    assert manager("mas").outdated() is None


def test_nonzero_exit_is_reported_with_its_stderr():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(False, "", "brew: boom")
    )

    use_shell(shell)
    report = manager("brew").outdated()
    assert report.error_message == "brew: boom"
    assert report.outdated_packages == []


def test_brew_runs_without_an_auto_update():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(True, "git (2.48.1) < 2.49.0", "")
    )

    use_shell(shell)
    manager("brew").outdated()
    _, env = shell.calls[0]
    assert env["HOMEBREW_NO_AUTO_UPDATE"] == "1"


def test_brew_runs_without_its_ask_mode():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(True, "git (2.48.1) < 2.49.0", "")
    )

    use_shell(shell)
    manager("brew").outdated()
    _, env = shell.calls[0]
    assert env["HOMEBREW_NO_ASK"] == "1"


def test_checking_what_is_outdated_skips_what_is_missing():
    shell = FakeShell(installed=(), result=CommandResult(True, "", ""))
    use_shell(shell)
    assert managers.check_what_is_outdated() == []


def test_silent_nonzero_exit_is_a_failure_not_up_to_date():
    # npm exits 1 both for "updates found" and for failures it doesn't phrase
    # as JSON; without output there is nothing to call up to date.
    shell = FakeShell(
        installed=("npm",),
        result=CommandResult(True, "", "npm error code E401", exit_code=1),
    )

    use_shell(shell)
    report = manager("npm").outdated()
    assert report.outdated_packages == []
    assert "E401" in report.error_message


def test_silent_zero_exit_really_is_up_to_date():
    shell = FakeShell(installed=("mas",), result=CommandResult(True, "", ""))

    use_shell(shell)
    report = manager("mas").outdated()
    assert report.outdated_packages == []
    assert report.error_message == ""

def test_each_manager_is_asked_the_right_question():
    asked = {}
    for entry in managers.MANAGERS:
        shell = FakeShell(installed=(entry.command,), result=CommandResult(True, "{}", ""))
        use_shell(shell)
        entry.outdated()
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
        use_shell(shell)
        entry.outdated()
        _, env = shell.calls[0]
        if entry.key == "brew":
            assert env["HOMEBREW_NO_AUTO_UPDATE"] == "1"
        else:
            assert env is None


def test_a_manager_without_upgrade_arguments_is_not_run():
    shell = FakeShell(installed=("brew",), result=CommandResult(True, "", ""))
    shell.stream_command = lambda args, env=None, silent_status=None, rewrite=None: 0
    class WithoutUpgradeArguments(managers.PackageManager):
        key, label, command = "x", "X", "brew"
        outdated_args = ("outdated",)

    entry = WithoutUpgradeArguments()

    use_shell(shell)
    assert entry.upgrade() is None


NPM_ITSELF_OUTDATED = """{
  "npm": {"current": "12.0.2", "wanted": "12.1.0", "latest": "12.1.0"}
}"""


def test_a_manager_that_cannot_update_itself_is_never_offered():
    shell = FakeShell({"mas"}, CommandResult(True, "", ""))

    use_shell(shell)
    assert manager("mas").check_self() is None


def test_npm_reports_its_own_new_version():
    shell = FakeShell({"npm"}, CommandResult(True, NPM_ITSELF_OUTDATED, "", 1))

    use_shell(shell)
    update = manager("npm").check_self()
    assert update.key == "npm"
    assert update.description == "npm  12.0.2 → 12.1.0"


def test_a_current_npm_is_not_offered():
    shell = FakeShell({"npm"}, CommandResult(True, "{}", ""))

    use_shell(shell)
    assert manager("npm").check_self() is None


def test_other_packages_in_the_answer_are_not_mistaken_for_npm():
    # `npm outdated -g npm` should only answer about npm, but the reply is read
    # by name rather than trusted to hold nothing else.
    shell = FakeShell({"npm"}, CommandResult(True, NPM_OUTDATED, "", 1))

    use_shell(shell)
    assert manager("npm").check_self() is None


def test_a_failed_self_check_is_reported_rather_than_raised():
    shell = FakeShell({"npm"}, CommandResult(True, NPM_NETWORK_FAILURE, "", 1))

    use_shell(shell)
    update = manager("npm").check_self()
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

    use_shell(shell)
    assert manager("brew").check_self() is None


def test_a_stale_homebrew_index_says_how_old_it_is(tmp_path):
    shell = HomebrewShell(homebrew_cache(tmp_path, age_in_days=3))

    use_shell(shell)
    update = manager("brew").check_self()
    assert update.description == "index is 3 days old"


def test_one_day_is_written_in_the_singular(tmp_path):
    shell = HomebrewShell(homebrew_cache(tmp_path, age_in_days=1.5))

    use_shell(shell)
    assert manager("brew").check_self().description == "index is 1 day old"


def test_a_cache_without_an_index_is_offered(tmp_path):
    (tmp_path / "api").mkdir()
    shell = HomebrewShell(tmp_path)

    use_shell(shell)
    update = manager("brew").check_self()
    assert update.description == "index has never been fetched"


def test_a_brew_that_says_nothing_about_its_cache_is_left_alone():
    # An empty answer used to be read as the current directory.
    shell = HomebrewShell("")

    use_shell(shell)
    assert manager("brew").check_self() is None


def test_only_installed_managers_are_asked_about_themselves():
    shell = FakeShell(set(), CommandResult(True, "{}", ""))

    use_shell(shell)
    assert managers.check_themselves(managers.MANAGERS) == []
    assert shell.calls == []


def test_a_homebrew_without_an_api_cache_is_left_alone(tmp_path):
    # Fetching formulae over git leaves no api directory, and then its age
    # says nothing about whether Homebrew is behind.
    shell = HomebrewShell(tmp_path)

    use_shell(shell)
    assert manager("brew").check_self() is None


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

    use_shell(shell)
    report = manager("brew").outdated()
    assert report.ignored_taps == ["anomalyco/tap"]


def test_nothing_is_claimed_when_homebrew_did_not_complain():
    shell = TwoAnswerShell(CommandResult(True, "", ""), CommandResult(True, TAP_INFO, ""))

    use_shell(shell)
    assert manager("brew").outdated().ignored_taps == []


def test_an_unreadable_tap_list_is_not_guessed_at():
    outdated = CommandResult(True, "", "Warning: taps are not trusted:")
    shell = TwoAnswerShell(outdated, CommandResult(True, "not json", ""))

    use_shell(shell)
    assert manager("brew").outdated().ignored_taps == []


def test_homebrew_versions_are_read_off_its_verbose_output():
    # A formula is "name (old) < new", a cask "name (old) != new".
    packages = manager("brew").parse_outdated(
        "tcl-tk (9.0.4) < 9.0.4_1\nchatgpt (26.917.71314) != 26.924.22138\n"
    )

    assert packages == ["tcl-tk  9.0.4 → 9.0.4_1", "chatgpt  26.917.71314 → 26.924.22138"]


def test_a_homebrew_line_in_no_known_shape_is_kept_as_it_is():
    assert manager("brew").parse_outdated("something odd\n") == ["something odd"]


def test_the_app_store_says_both_versions_without_its_id():
    packages = manager("mas").parse_outdated("6469021132  PDFgear  (2.27 -> 2.28)\n")

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


def test_brew_leaves_running_apps_open_while_it_upgrades():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(True, "git (2.48.1) < 2.49.0", "")
    )

    use_shell(shell)
    manager("brew").outdated()
    _, env = shell.calls[0]
    assert env["HOMEBREW_NO_UPGRADE_QUIT_CASKS"] == "1"


class StreamingShell:
    def __init__(self, codes):
        self.codes = list(codes)
        self.streamed = []

    def find_executable(self, command):
        return f"/fake/{command}"

    def stream_command(self, args, env=None, silent_status=None, rewrite=None):
        self.streamed.append(args[1:])
        return self.codes.pop(0)


def test_homebrew_clears_out_what_it_no_longer_needs():
    shell = StreamingShell([0])

    use_shell(shell)
    assert managers.by_key("brew").cleanup() == 0
    assert shell.streamed == [["cleanup"]]


def test_a_manager_with_nothing_to_clear_out_runs_nothing():
    shell = StreamingShell([])

    use_shell(shell)
    assert managers.by_key("npm").cleanup() is None
    assert shell.streamed == []


def test_the_app_store_names_the_apps_it_started_no_download_for():
    mas = managers.by_key("mas")
    mas.parse_outdated("6469021132  PDFgear  (2.27 -> 2.28)\n585829637  Todoist  (9.30.0 -> 9.31.0)\n")
    use_shell(StreamingShell([1]))
    swap(
        real_shell, "output_of_last_streamed_command",
        lambda: "Error: No downloads initiated for ADAM ID 6469021132\nError: No downloads initiated for ADAM ID 1\n",
    )

    mas.upgrade()

    assert mas.refused_in_last_upgrade == {"PDFgear"}


def test_homebrew_upgrade_output_loses_the_builds_after_a_comma():
    brew = managers.by_key("brew")
    written = (
        b"==> Upgrading 2 outdated packages:\r\n"
        b"cursor   3.25.6,f0df777c412b670d09e3eaf214967d779e67c088 -> 3.27.14,69b724ebc67e  (190 MB)\r\n"
        b"charles  5.2.1                                           -> 5.2.2\r\n"
        b"  3.25.6,f0df777c412b670d09e3eaf214967d779e67c088 -> 3.27.14,69b724ebc67e\r\n"
        b"Moving App 'Cursor.app' to '/Applications/Cursor.app', 1,2 -> 3\r\n"
        b"cursor   3.25.6,f0df -> 3.27"
    )

    assert brew.shorten_output(written).split(b"\n") == [
        b"==> Upgrading 2 outdated packages:\r",
        b"cursor   3.25.6 -> 3.27.14  (190 MB)\r",
        b"charles  5.2.1  -> 5.2.2\r",
        b"  3.25.6 -> 3.27.14\r",
        b"Moving App 'Cursor.app' to '/Applications/Cursor.app', 1,2 -> 3\r",
        b"cursor   3.25.6,f0df -> 3.27",
    ]


def test_homebrew_download_progress_loses_the_build_after_a_comma():
    written = (
        b"\xe2\x9c\x94\xef\xb8\x8e Cask cursor (3.27.22,b1aa50cb6db84fd3e8c808259cb172ea73425c1f)  Verified\r\n"
        b"\xe2\x9c\x94\xef\xb8\x8e Formula git (2.51.0)  Verified\r\n"
    )

    assert managers.by_key("brew").shorten_output(written).split(b"\n") == [
        b"\xe2\x9c\x94\xef\xb8\x8e Cask cursor (3.27.22)  Verified\r",
        b"\xe2\x9c\x94\xef\xb8\x8e Formula git (2.51.0)  Verified\r",
        b"",
    ]


def test_homebrew_upgrade_output_without_builds_keeps_its_own_layout():
    written = b"signal  8.31.0       -> 8.32.0\nzoom    7.1.5.84650  -> 7.2.2.88465\n"

    assert managers.by_key("brew").shorten_output(written) == written


def test_other_managers_show_their_upgrade_output_as_it_is():
    assert managers.by_key("npm").shorten_output(b"a 1,2 -> 3,4\n") == b"a 1,2 -> 3,4\n"


def behind_its_recipe(token, app_version, cask_version, recorded=None):
    from pathlib import Path
    from update_my_mac.checks.installed_apps import InstalledApp
    from update_my_mac.managers.homebrew import behind_the_recipe
    from update_my_mac.managers.homebrew.casks import Cask

    app = InstalledApp(token.title(), app_version, Path(f"/Applications/{token.title()}.app"))
    return behind_the_recipe.Behind(app, Cask(token, "https://x.test/", cask_version), recorded or app_version)


def test_homebrew_lists_the_apps_only_a_greedy_upgrade_reaches_with_its_own():
    from update_my_mac.managers import homebrew

    brew = managers.by_key("brew")
    swap(brew, "_greedy", [])
    asked = []
    swap(homebrew, "apps_only_a_greedy_upgrade_reaches",
         lambda named: asked.append(named) or [behind_its_recipe("cursor", "3.25.6", "3.27.14,69b724")])
    use_shell(FakeShell(installed=("brew",), result=CommandResult(True, "git (2.48.1) < 2.49.0", "")))

    report = brew.outdated()

    assert report.outdated_packages == ["git  2.48.1 → 2.49.0", "cursor  3.25.6 → 3.27.14"]
    assert asked == [{"git"}]


def test_homebrew_adds_nothing_to_a_check_that_failed():
    from update_my_mac.managers import homebrew

    brew = managers.by_key("brew")
    swap(brew, "_greedy", [])
    swap(homebrew, "apps_only_a_greedy_upgrade_reaches", lambda named: [behind_its_recipe("cursor", "3", "4")])
    use_shell(FakeShell(installed=("brew",), result=CommandResult(False, "", "boom")))

    assert brew.outdated().outdated_packages == []


def test_the_homebrew_upgrade_runs_greedy_for_exactly_those_apps_after_the_plain_one():
    brew = managers.by_key("brew")
    swap(brew, "_greedy", [behind_its_recipe("cursor", "3", "4"), behind_its_recipe("firefox", "1", "2")])
    shell = use_shell(StreamingShell([0, 0]))

    assert brew.upgrade() == 0
    assert shell.streamed == [["upgrade"], ["upgrade", "--cask", "--greedy", "cursor", "firefox"]]


def test_a_failure_in_either_homebrew_upgrade_is_reported():
    brew = managers.by_key("brew")
    swap(brew, "_greedy", [behind_its_recipe("cursor", "3", "4")])

    use_shell(StreamingShell([1, 0]))
    assert brew.upgrade() == 1
    use_shell(StreamingShell([0, 1]))
    assert brew.upgrade() == 1


def test_without_such_apps_the_homebrew_upgrade_is_the_plain_one():
    brew = managers.by_key("brew")
    swap(brew, "_greedy", [])
    shell = use_shell(StreamingShell([0]))

    brew.upgrade()
    assert shell.streamed == [["upgrade"]]


def test_a_greedy_upgrade_is_not_enough_where_homebrew_recorded_the_recipes_version_or_macos_updates_the_app():
    from update_my_mac.checks import app_updaters

    assert behind_its_recipe("cursor", "3", "4").needs_greedy
    assert not behind_its_recipe("cursor", "3", "4", recorded="4").needs_greedy
    by_macos = behind_its_recipe("safari", "18", "19")
    by_macos.app.updater = app_updaters.UpdaterStatus(app_updaters.HOST_APP)
    assert not by_macos.needs_greedy


def test_the_app_store_notice_about_progress_is_dropped_from_what_upgrade_shows():
    written = b"Update progress cannot be displayed\nInstalling CotEditor\n"

    assert managers.by_key("mas").shorten_output(written) == b"Installing CotEditor\n"
