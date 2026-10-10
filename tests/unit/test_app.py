"""The exit status, which is the only thing a scheduled caller can read."""

from update_my_mac.controller import app
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
    monkeypatch.setattr(app, "shell", QuietShell())

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
    monkeypatch.setattr(app, "shell", QuietShell())
    monkeypatch.setattr(app.managers, "check_themselves",
                        lambda shell, installed: [behind("brew", "boom")])

    assert app.run_check_mode() == 1


def test_updates_only_reports_a_manager_nobody_could_ask(monkeypatch):
    monkeypatch.setattr(app, "shell", QuietShell())
    monkeypatch.setattr(app.managers, "check_themselves",
                        lambda shell, installed: [behind("brew", "boom")])
    monkeypatch.setattr(app.self_update, "pick_managers", lambda *a, **k: [])

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
    monkeypatch.setattr(app, "shell", QuietShell())


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
    monkeypatch.setattr(app.managers, "check_themselves", lambda shell, installed: list(found))
    monkeypatch.setattr(app.self_update, "pick_managers", lambda offered, *a, **k: list(offered))
    monkeypatch.setattr(
        app.self_update, "update",
        lambda picked, shell, *a, **k: app.self_update.SelfUpdateResult(list(updated), list(failed)),
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
