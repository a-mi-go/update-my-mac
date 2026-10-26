"""The exit status, which is the only thing a scheduled caller can read."""

from pathlib import Path

from update_my_mac import managers
from update_my_mac.controller import app

from fake_run import use_shell, RecordingShell, printed_by
from update_my_mac.managers import ManagerReport, ManagerUpdate


def test_outdated_packages_are_not_a_failure():
    reports = [ManagerReport("brew", "Homebrew", ["git 2.48.1 → 2.49.0"])]

    assert app._exit_code(reports) == 0


def test_a_check_that_could_not_run_is_a_failure():
    reports = [ManagerReport("npm", "npm (global)", [], "ENOTFOUND")]

    assert app._exit_code(reports) == 1


def test_a_manager_that_could_not_answer_about_itself_counts_too():
    # It was printed as a failure but --check still exited 0.
    reports = [ManagerReport("brew", "Homebrew", [])]
    managers_behind = [ManagerUpdate("npm", "npm (global)", error_message="ENOTFOUND")]

    assert app._exit_code(reports, managers_behind) == 1


def test_a_manager_update_that_is_merely_available_is_not_a_failure():
    managers_behind = [ManagerUpdate("npm", "npm (global)", "npm  12.0.2 → 12.1.0")]

    assert app._exit_code([], managers_behind) == 0


class QuietShell:
    """A Mac with nothing installed, so no check has anything to ask."""

    def find_executable(self, command):
        return None


def test_updates_only_asks_the_managers_and_nothing_else(monkeypatch):
    # The checks that look at apps are what take the time, and none of them
    # says anything about what a manager would upgrade.
    looked = []
    for name in ("find_untracked", "find_all", "owned_by_someone_else"):
        monkeypatch.setattr(app.installed_apps, name,
                            lambda *a, **k: looked.append(name) or [])
    monkeypatch.setattr(app.appcast, "check", lambda *a, **k: looked.append("feeds") or {})
    monkeypatch.setattr(app.casks, "load", lambda *a, **k: looked.append("casks") or {})
    use_shell(QuietShell())

    assert app.run_updates_only_mode() == 0
    assert looked == []


def behind(key, error_message=""):
    return ManagerUpdate(key, key, "a newer one exists", error_message)


def test_check_mode_still_asks_the_managers_about_themselves(monkeypatch):
    # The answer has to reach the exit code, or a manager nobody could ask
    # would read as nothing to do.
    for name in ("find_untracked", "find_all", "owned_by_someone_else"):
        monkeypatch.setattr(app.installed_apps, name, lambda *a, **k: [])
    monkeypatch.setattr(app.appcast, "check", lambda *a, **k: {})
    monkeypatch.setattr(app.casks, "load", lambda *a, **k: {})
    use_shell(QuietShell())
    monkeypatch.setattr(app.managers, "check_themselves",
                        lambda installed: [behind("brew", "boom")])

    assert app.run_check_mode() == 1


def test_updates_only_reports_a_manager_nobody_could_ask(monkeypatch):
    use_shell(QuietShell())
    monkeypatch.setattr(app.managers, "check_themselves",
                        lambda installed: [behind("brew", "boom")])
    monkeypatch.setattr(app.self_update, "update_managers",
                        lambda *a, **k: app.self_update.SelfUpdateResult())

    assert app.run_updates_only_mode() == 1


class NothingIgnored:
    def is_ignored(self, name):
        return False


def quiet_mac(monkeypatch):
    """A Mac where every check answers nothing, so a test can set one of them."""
    for name in ("find_untracked", "find_all", "owned_by_someone_else"):
        monkeypatch.setattr(app.installed_apps, name, lambda *a, **k: [])
    monkeypatch.setattr(app.appcast, "check", lambda *a, **k: {})
    monkeypatch.setattr(app.casks, "load", lambda *a, **k: {})
    use_shell(QuietShell())


def test_every_check_lands_in_the_field_the_report_reads(monkeypatch):
    # Findings takes any attribute, so a typo in one of these assignments
    # would leave its section silently empty rather than fail.
    quiet_mac(monkeypatch)
    monkeypatch.setattr(app.behind_the_recipe, "find", lambda *a, **k: ["an old cask"])
    monkeypatch.setattr(app.duplicate_installations, "find", lambda *a, **k: ["a doubled command"])
    monkeypatch.setattr(app.running_apps, "find", lambda *a, **k: ["still running old"])

    findings = app._check_the_mac([], NothingIgnored())

    assert findings.apps_behind == ["an old cask"]
    assert findings.doubled == ["a doubled command"]
    assert findings.stale == ["still running old"]


def a_self_update_that(monkeypatch, found, updated=(), failed=()):
    """Stubs the step so only its result reaches the mode under test."""
    quiet_mac(monkeypatch)
    monkeypatch.setattr(app.managers, "check_themselves", lambda installed: list(found))
    monkeypatch.setattr(
        app.self_update, "update_managers",
        lambda behind, *a, **k: app.self_update.SelfUpdateResult(list(updated), list(failed)),
    )
    monkeypatch.setattr(app.resolve_issues, "ask_what_to_fix", lambda *a, **k: 0)
    monkeypatch.setattr(app.apply_updates, "ask_what_to_update", lambda *a, **k: [])


def test_a_failed_self_update_exits_non_zero(monkeypatch):
    a_self_update_that(monkeypatch, [behind("brew")], failed=["brew"])

    assert app.run_interactive_mode() == 1


def test_a_manager_that_updated_itself_is_not_held_against_the_run(monkeypatch):
    a_self_update_that(monkeypatch, [behind("brew")], updated=["brew"])

    assert app.run_interactive_mode() == 0


def test_a_manager_nobody_could_ask_exits_non_zero_even_once_it_updated(monkeypatch):
    a_self_update_that(monkeypatch, [behind("brew", "boom")], updated=["brew"])

    assert app.run_interactive_mode() == 1


def test_declining_the_self_update_is_not_a_failure(monkeypatch):
    a_self_update_that(monkeypatch, [behind("brew")])

    assert app.run_interactive_mode() == 0


def test_a_failed_self_update_exits_non_zero_in_updates_only(monkeypatch):
    a_self_update_that(monkeypatch, [behind("brew")], failed=["brew"])

    assert app.run_updates_only_mode() == 1


def test_a_manager_nobody_could_ask_exits_non_zero_in_updates_only(monkeypatch):
    a_self_update_that(monkeypatch, [behind("brew", "boom")], updated=["brew"])

    assert app.run_updates_only_mode() == 1


def replaced_app(name):
    from pathlib import Path

    from update_my_mac.checks import running_apps

    return running_apps.StillRunningOld(name, Path(f"/Applications/{name}.app"), 1, 0.0, 1.0)


def test_the_apps_an_update_replaced_get_a_restart_but_not_the_ones_offered_before(monkeypatch):
    before, after = replaced_app("Chrome"), replaced_app("Gemini")
    monkeypatch.setattr(app.running_apps, "find", lambda: [before, after])
    offered = []
    monkeypatch.setattr(
        app.restart_apps, "ask_after_the_update",
        lambda apps, *a, **k: offered.append(apps),
    )

    app._offer_to_restart_what_the_updates_replaced([before])

    assert offered == [[after]]


def test_interactive_mode_offers_the_restart_after_the_updates(monkeypatch):
    a_self_update_that(monkeypatch, found=[])
    order = []
    monkeypatch.setattr(
        app.apply_updates, "ask_what_to_update", lambda *a, **k: order.append("updates") or []
    )
    monkeypatch.setattr(
        app, "_offer_to_restart_what_the_updates_replaced", lambda *a: order.append("restart")
    )

    app.run_interactive_mode()

    assert order == ["updates", "restart"]


def test_updates_only_offers_the_restart_after_the_updates(monkeypatch):
    a_self_update_that(monkeypatch, found=[])
    order = []
    monkeypatch.setattr(
        app.apply_updates, "ask_what_to_update", lambda *a, **k: order.append("updates") or []
    )
    monkeypatch.setattr(
        app, "_offer_to_restart_what_the_updates_replaced", lambda *a: order.append("restart")
    )

    app.run_updates_only_mode()

    assert order == ["updates", "restart"]


class BrewShell:
    def __init__(self, installed=True):
        self.installed = installed
        self.calls = []

    def find_executable(self, command):
        return f"/fake/{command}" if self.installed else None

    def stream_command(self, args, env=None, silent_status=None):
        self.calls.append((args, env))
        return 0


def test_the_catch_up_upgrade_leaves_running_apps_open_like_the_others(monkeypatch):
    brew = BrewShell()
    use_shell(brew)

    app.resolve_by_command.run_command(("brew", "upgrade", "--cask", "--greedy", "chatgpt"))

    _, env = brew.calls[0]
    assert env["HOMEBREW_NO_UPGRADE_QUIT_CASKS"] == "1"


def test_a_missing_brew_is_not_given_an_exit_code(monkeypatch):
    use_shell(BrewShell(installed=False))

    assert app.resolve_by_command.run_command(("brew", "upgrade")) is None


def test_brew_commands_get_homebrews_environment_and_others_do_not(monkeypatch):
    brew = BrewShell()
    use_shell(brew)

    app.resolve_by_command.run_command(("brew", "reinstall", "clerk"))
    app.resolve_by_command.run_command(("hdiutil", "detach", "-force", "/dev/disk8"))

    assert brew.calls[0][0] == ["/fake/brew", "reinstall", "clerk"]
    assert brew.calls[0][1]["HOMEBREW_NO_UPGRADE_QUIT_CASKS"] == "1"
    assert brew.calls[1] == (["/fake/hdiutil", "detach", "-force", "/dev/disk8"], None)


def test_a_missing_program_is_not_given_an_exit_code(monkeypatch):
    use_shell(BrewShell(installed=False))

    assert app.resolve_by_command.run_command(("hdiutil", "detach", "/dev/disk8")) is None


def test_everything_a_command_can_put_right_is_one_entry_in_the_menu(monkeypatch, tmp_path):
    monkeypatch.setattr(app.brew, "caskroom", lambda: None)
    from pathlib import Path
    from update_my_mac.checks import Findings
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.checks.installed_apps import InstalledApp
    from update_my_mac.managers.homebrew import behind_the_recipe, flagged, mounted_downloads
    from update_my_mac.managers.homebrew.casks import Cask

    findings = Findings(
        flagged=[
            flagged.Flagged("tap/clerk", flagged.DIFFERS, installed="64", available="3.4.1"),
            flagged.Flagged("old", flagged.DEPRECATED, installed="1"),
        ],
        mounted=[mounted_downloads.MountedImage(Path("/c/a--b.dmg"), "/dev/disk8")],
        apps_behind=[behind_the_recipe.Behind(
            InstalledApp("Foo", "1.0", Path("/Applications/Foo.app")),
            Cask("foo", "https://x.test/", "2.0"), "1.0")],
    )

    labels = [problem.label for problem in app._issues(findings, AppDecisions(tmp_path / "apps.json"))]

    assert labels == ["⎷ fix apps & packages Homebrew cannot update (3)"]


def test_what_a_fix_settled_is_no_longer_counted(monkeypatch, tmp_path):
    from update_my_mac.checks import Findings
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.managers.homebrew import flagged
    from fake_terminal import Terminal

    from update_my_mac.system.shell import CommandResult

    brew = BrewShell()
    brew.run_command = lambda *a, **k: CommandResult(True, "", "")
    use_shell(brew)
    findings = Findings(flagged=[
        flagged.Flagged("tap/a", flagged.DIFFERS, installed="1", available="2"),
        flagged.Flagged("tap/b", flagged.DIFFERS, installed="1", available="2"),
    ])
    (entry,) = app._issues(findings, AppDecisions(tmp_path / "apps.json"))
    assert entry.label.endswith("(2)")

    # Decide for each: run tap/a's reinstall, leave tap/b for now.
    entry.walk_through(Terminal("2", "1", "3").step)

    assert entry.refresh(entry)
    assert entry.label.endswith("(1)")
    entry.fix_all(Terminal().step)
    assert not entry.refresh(entry)
    assert [call[0][1:] for call in brew.calls] == [["reinstall", "tap/a"], ["reinstall", "tap/b"]]


def test_an_unused_copy_that_was_uninstalled_is_no_longer_offered(monkeypatch, tmp_path):
    from update_my_mac.checks import Findings
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.checks.duplicate_installations import Copy, Duplicate
    from update_my_mac.view.prompting import Step
    from fake_terminal import Terminal

    from update_my_mac.system.shell import CommandResult

    brew = BrewShell()
    brew.run_command = lambda *a, **k: CommandResult(True, "", "")
    use_shell(brew)
    doubled = Duplicate("codex", [
        Copy("Homebrew", Path("/opt/homebrew/bin/codex"), "codex", ("brew", "uninstall", "codex")),
        Copy("npm (global)", Path("/b/codex"), "@openai/codex", ("npm", "uninstall", "-g", "@openai/codex")),
    ])
    (entry,) = app._issues(Findings(doubled=[doubled]), AppDecisions(tmp_path / "apps.json"))
    assert entry.label.endswith("(1)")

    # The only doubled command goes straight to its own question; 2 drops npm's copy.
    assert entry.walk_through(Terminal("2").step) == 1

    assert not entry.refresh(entry)


def test_the_restart_entry_with_one_app_offers_no_cancel(monkeypatch, tmp_path):
    from update_my_mac.checks import Findings
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.checks.running_apps import StillRunningOld
    from update_my_mac.system.shell import CommandResult
    from fake_terminal import Terminal

    brew = BrewShell()
    brew.run_command = lambda *a, **k: CommandResult(True, "", "")
    use_shell(brew)
    stale = [StillRunningOld("Thing", tmp_path / "Thing.app", 42, 1.0, 2.0)]
    (entry,) = app._issues(Findings(stale=stale), AppDecisions(tmp_path / "apps.json"))
    terminal = Terminal("2")

    entry.walk_through(terminal.step)

    assert "cancel the walk-through" not in terminal.text
    assert "restart all" not in terminal.text


def test_an_app_opened_to_update_by_hand_stays_in_the_menu(monkeypatch, tmp_path):
    from update_my_mac.checks import Findings, app_updaters
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.checks.installed_apps import InstalledApp
    from update_my_mac.managers.homebrew import behind_the_recipe
    from update_my_mac.managers.homebrew.casks import Cask
    from update_my_mac.system.shell import CommandResult
    from fake_terminal import Terminal

    brew = BrewShell()
    brew.run_command = lambda *a, **k: CommandResult(True, "", "")
    use_shell(brew)
    behind = behind_the_recipe.Behind(
        InstalledApp("Foo", "1.0", Path("/Applications/Foo.app")),
        Cask("foo", "https://x.test/", "2.0"), "1.0")
    behind.updater = app_updaters.UpdaterStatus(app_updaters.SPARKLE, True)
    (entry,) = app._issues(Findings(apps_behind=[behind]), AppDecisions(tmp_path / "apps.json"))

    # The second option opens the app.
    assert entry.walk_through(Terminal("2").step) == 0

    assert brew.calls[0][0][0] == "/fake/open"
    assert entry.refresh(entry)


def test_homebrews_folder_is_only_asked_for_when_an_app_is_behind(monkeypatch, tmp_path):
    from update_my_mac.checks import Findings
    from update_my_mac.checks.app_decisions import AppDecisions

    asked = []
    monkeypatch.setattr(app.brew, "caskroom", lambda: asked.append("caskroom"))

    app._issues(Findings(), AppDecisions(tmp_path / "apps.json"))

    assert asked == []


def test_the_menu_leaves_the_runs_findings_as_they_were(monkeypatch, tmp_path):
    from update_my_mac.checks import Findings
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.checks.running_apps import StillRunningOld
    from fake_terminal import Terminal

    monkeypatch.setattr(app.restart_apps, "restart", lambda found: (True, "restarted"))
    findings = Findings(stale=[StillRunningOld("Thing", tmp_path / "Thing.app", 42, 1.0, 2.0)])
    (entry,) = app._issues(findings, AppDecisions(tmp_path / "apps.json"))

    entry.fix_all(Terminal().step)

    assert not entry.refresh(entry)
    assert len(findings.stale) == 1


def test_homebrew_is_cleaned_up_with_no_update_to_do(monkeypatch):
    shell = RecordingShell()
    use_shell(shell)

    app._clean_up(managers.installed())

    assert shell.streamed == [["/fake/brew", "cleanup"]]


def test_the_cleanup_ends_in_a_line_that_says_it_is_done(monkeypatch):
    shell = RecordingShell()
    use_shell(shell)

    printed = printed_by(lambda: app._clean_up(managers.installed()))

    line = next(line for line in printed.splitlines() if "Cleaning up Homebrew" in line)
    assert line.startswith("Cleaning up Homebrew ....")
    assert line.endswith(" done")


def test_a_cleanup_that_failed_says_how(monkeypatch):
    shell = RecordingShell(exit_code=1)
    use_shell(shell)

    printed = printed_by(lambda: app._clean_up(managers.installed()))

    assert "Cleaning up Homebrew" in printed
    assert "exited with 1" in printed
    assert "done" not in printed


def test_the_interactive_run_starts_on_a_screen_of_its_own(monkeypatch):
    from contextlib import contextmanager

    seen = []

    @contextmanager
    def full_screen():
        seen.append("entered")
        yield
        seen.append("left")

    monkeypatch.setattr(app.output, "full_screen", full_screen)
    monkeypatch.setattr(app, "_run_interactive", lambda: seen.append("ran") or 0)

    assert app.run_interactive_mode() == 0
    assert seen == ["entered", "ran", "left"]


def untracked_app(name, updater):
    from pathlib import Path
    from update_my_mac.checks.installed_apps import InstalledApp

    found = InstalledApp(name, "1.0", Path(f"/Applications/{name}.app"))
    found.updater = updater
    return found


def test_the_question_about_untracked_apps_leaves_out_the_ones_the_report_does_not_list(tmp_path):
    from pathlib import Path
    from update_my_mac.checks import Findings, app_updaters
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.managers.homebrew.casks import Cask

    nobody = app_updaters.UpdaterStatus(app_updaters.NONE, False)
    apps = [untracked_app(f"App{n}", nobody) for n in range(3)]
    apps.append(untracked_app("Current", nobody))
    findings = Findings(
        untracked=apps,
        find_cask=lambda found: Cask("current", "https://x.test/", "1.0") if found.file_stem == "Current" else None,
    )

    problem = app._untracked_problem(findings, AppDecisions(tmp_path / "apps.json"))

    assert problem.label == "⎷ go through untracked apps (3)"


def test_the_question_says_how_many_of_them_homebrew_has_a_recipe_for(monkeypatch, tmp_path):
    from update_my_mac.checks import Findings, app_updaters
    from update_my_mac.checks.app_decisions import AppDecisions

    monkeypatch.setattr(app.track_apps, "known_to_homebrew", lambda found: 2)
    findings = Findings(
        untracked=[untracked_app("App", app_updaters.UpdaterStatus(app_updaters.NONE, False))],
        find_cask=lambda found: None,
    )

    problem = app._untracked_problem(findings, AppDecisions(tmp_path / "apps.json"))

    assert problem.label == "⎷ go through untracked apps (1, 2 can be added to Homebrew)"



def test_every_option_of_the_first_menu_counts_what_its_group_in_the_report_lists(monkeypatch, tmp_path):
    from pathlib import Path
    from update_my_mac.checks import Findings, app_updaters
    from update_my_mac.checks.app_decisions import AppDecisions
    from update_my_mac.checks.duplicate_installations import Copy, Duplicate
    from update_my_mac.checks.installed_apps import InstalledApp
    from update_my_mac.checks.running_apps import StillRunningOld
    from update_my_mac.managers.homebrew import behind_the_recipe, flagged, mounted_downloads
    from update_my_mac.managers.homebrew.casks import Cask
    from update_my_mac.view import sections

    monkeypatch.setattr(app.brew, "caskroom", lambda: None)
    nobody = app_updaters.UpdaterStatus(app_updaters.NONE, False)
    findings = Findings(
        untracked=[untracked_app("Evoto", nobody), untracked_app("Orca", nobody)],
        flagged=[flagged.Flagged("tap/clerk", flagged.DIFFERS, installed="64", available="3.4.1")],
        mounted=[mounted_downloads.MountedImage(Path("/c/a--b.dmg"), "/dev/disk8")],
        apps_behind=[behind_the_recipe.Behind(
            InstalledApp("Foo", "1.0", Path("/Applications/Foo.app")),
            Cask("foo", "https://x.test/", "2.0"), "1.0")],
        doubled=[
            Duplicate(name, [Copy("Homebrew", Path("/a"), name, (), "1"), Copy("npm", Path("/b"), name, (), "2")])
            for name in ("codex", "claude")
        ],
        stale=[StillRunningOld("Gemini", Path("/Applications/Gemini.app"), 1, 0.0, 0.0)],
        foreign=[Path("/Applications/Zoom.app")],
        find_cask=lambda found: None,
    )

    problems = app._issues(findings, AppDecisions(tmp_path / "apps.json"))
    groups = [
        section for section in sections.of(findings)
        if section.part == sections.NEED_ATTENTION
    ]

    assert len(problems) == len(groups) == 5
    for problem, group in zip(problems, groups):
        assert f"({group.count}" in problem.label


def test_taking_over_an_app_makes_it_belong_to_whoever_runs_the_check():
    import getpass
    from pathlib import Path

    fix = app._take_over(Path("/Applications/Zoom.app"))

    assert fix.main.command == ("sudo", "chown", "-R", getpass.getuser(), "/Applications/Zoom.app")


def test_what_is_outdated_is_asked_again_only_after_something_changed(monkeypatch):
    asked = []

    def check():
        asked.append(True)
        return [app.managers.ManagerReport("brew", "Homebrew", ["git  1 → 2", "jq  1 → 2"])]

    monkeypatch.setattr(app.managers, "check_what_is_outdated", check)
    updates = app._Updates([app.managers.ManagerReport("brew", "Homebrew", ["git  1 → 2"])])

    assert updates.count() == 1
    assert asked == []

    updates.something_changed()
    assert updates.count() == 2
    assert updates.count() == 2
    assert asked == [True]
