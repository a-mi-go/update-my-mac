"""The exit status, which is the only thing a scheduled caller can read."""

from update_my_mac import app
from update_my_mac.package_managers import ManagerReport, ManagerUpdate


def test_outdated_packages_are_not_a_failure():
    reports = [ManagerReport("brew", "Homebrew", ["git 2.48.1 → 2.49.0"])]

    assert app._exit_code(reports) == 0


def test_a_check_that_could_not_run_is_a_failure():
    reports = [ManagerReport("npm", "npm (global)", [], "ENOTFOUND")]

    assert app._exit_code(reports) == 1


def test_a_manager_that_could_not_answer_about_itself_counts_too():
    # It was printed as a failure but --check still exited 0.
    reports = [ManagerReport("brew", "Homebrew", [])]
    manager_updates = [ManagerUpdate("npm", "npm (global)", error_message="ENOTFOUND")]

    assert app._exit_code(reports, manager_updates) == 1


def test_a_manager_update_that_is_merely_available_is_not_a_failure():
    manager_updates = [ManagerUpdate("npm", "npm (global)", "npm  12.0.2 → 12.1.0")]

    assert app._exit_code([], manager_updates) == 0


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
    monkeypatch.setattr(app.cask_index, "load", lambda *a, **k: looked.append("casks") or {})
    monkeypatch.setattr(app, "shell", QuietShell())

    assert app.run_updates_only_mode() == 0
    assert looked == []
