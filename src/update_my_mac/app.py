"""Sequencing the steps of a run, independent of how the flags were parsed."""

from update_my_mac import (
    app_decisions,
    apply_updates,
    installed_apps,
    package_managers,
    report,
    shell,
    track_apps,
)


def _exit_code(reports):
    # Outdated packages are the normal case, so only a check that could not run
    # is worth a non-zero exit. A scheduled caller needs to tell those apart.
    return 1 if any(r.error_message for r in reports) else 0


def _untracked_apps(decisions):
    """Untracked apps, minus the ones the user asked not to see again."""
    found = installed_apps.find_untracked(shell)
    listed = [app for app in found if not decisions.is_ignored(app.name)]
    return listed, len(found) - len(listed)


def run_check_mode():
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)

    listed, left_alone = _untracked_apps(app_decisions.load())
    report.print_untracked_apps(listed, left_alone=left_alone)
    return _exit_code(reports)


def run_interactive_mode():
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)

    decisions = app_decisions.load()
    listed, left_alone = _untracked_apps(decisions)
    report.print_untracked_apps(listed, left_alone=left_alone)
    track_apps.run_untracked_menu(listed, decisions)

    failed = apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(reports)


def run_retry_app_mode():
    track_apps.run_revisit_menu(app_decisions.load())
    return 0
