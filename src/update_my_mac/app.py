"""Sequencing the steps of a run, independent of how the flags were parsed."""

from update_my_mac import package_managers, report, shell


def run_check_mode():
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)
    # Outdated packages are the normal case, so only a check that could not run
    # is worth a non-zero exit — a scheduled caller needs to tell those apart.
    return 1 if any(r.error_message for r in reports) else 0
