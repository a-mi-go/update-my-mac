"""Sequencing the steps of a run, independent of how the flags were parsed."""

from update_my_mac import apply_updates, package_managers, report, shell


def _exit_code(reports):
    # Outdated packages are the normal case, so only a check that could not run
    # is worth a non-zero exit — a scheduled caller needs to tell those apart.
    return 1 if any(r.error_message for r in reports) else 0


def run_check_mode():
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)
    return _exit_code(reports)


def run_interactive_mode():
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)
    failed = apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(reports)
