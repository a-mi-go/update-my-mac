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


def test_a_build_number_after_a_comma_is_not_a_different_version():
    # Casks write "4.92.0,240144" where the app reports only "4.92.0".
    assert app._same_version("4.92.0", "4.92.0,240144")
    assert app._same_version("5.0.6", "5.0.6")


def test_a_genuinely_different_version_is_seen_as_different():
    assert not app._same_version("5.0.5", "5.0.6")
    assert not app._same_version("26.831.21537", "26.623.141536")
