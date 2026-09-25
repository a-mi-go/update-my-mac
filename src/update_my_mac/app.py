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


def _exit_code(reports, manager_updates=()):
    # Outdated packages are the normal case, so only a check that could not run
    # is worth a non-zero exit. A scheduled caller needs to tell those apart,
    # and a manager that could not answer about itself is such a check.
    failed = [thing for thing in list(reports) + list(manager_updates) if thing.error_message]
    return 1 if failed else 0


def _untracked_apps(decisions):
    """Untracked apps, minus the ones the user asked not to see again."""
    found = installed_apps.find_untracked(shell)
    listed = [app for app in found if not decisions.is_ignored(app.name)]
    return listed, len(found) - len(listed)


def run_check_mode():
    # The managers come first: an outdated manager is what everything else
    # below it depends on.
    installed = package_managers.installed_managers(shell)
    manager_updates = package_managers.check_managers_themselves(shell, installed)
    report.print_manager_updates(manager_updates, any_installed=bool(installed))

    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)

    listed, left_alone = _untracked_apps(app_decisions.load())
    report.print_untracked_apps(listed, left_alone=left_alone)
    return _exit_code(reports, manager_updates)


def run_interactive_mode():
    installed = package_managers.installed_managers(shell)
    manager_updates = package_managers.check_managers_themselves(shell, installed)
    report.print_manager_updates(manager_updates, any_installed=bool(installed))
    failed = apply_updates.run_manager_menu(manager_updates, shell)

    # Everything below is checked afterwards, so the list is what the current
    # tools report rather than what the old ones knew.
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)

    decisions = app_decisions.load()
    listed, left_alone = _untracked_apps(decisions)
    report.print_untracked_apps(listed, left_alone=left_alone)

    failed += apply_updates.run_upgrade_menu(
        reports, shell, untracked_apps=listed, decisions=decisions
    )
    return 1 if failed else _exit_code(reports, manager_updates)


def run_retry_app_mode():
    track_apps.run_revisit_menu(app_decisions.load())
    return 0
