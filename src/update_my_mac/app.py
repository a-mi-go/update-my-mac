"""Sequencing the steps of a run, independent of how the flags were parsed."""

from update_my_mac import package_managers, report, shell


def run_check_mode():
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)
    return 0
