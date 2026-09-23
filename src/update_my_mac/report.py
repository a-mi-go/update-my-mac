"""Turning check results into something readable."""

from rich.console import Console
from rich.markup import escape


def count_outdated_packages(reports):
    return sum(len(report.outdated_packages) for report in reports)


def print_untracked_apps(apps, console=None):
    """Apps no package manager accounts for, so nothing else will mention them."""
    console = console or Console(highlight=False, soft_wrap=True)
    if not apps:
        return

    console.print()
    console.print(f"[bold]Not tracked by any package manager[/]: {len(apps)}")
    for app in apps:
        console.print(f"    {app.describe()}", markup=False, highlight=False)


def print_outdated_summary(reports, console=None):
    # soft_wrap keeps a package manager's own table columns from being rewrapped
    # into nonsense; markup=False because package names may contain brackets.
    console = console or Console(soft_wrap=True)

    if not reports:
        console.print("No supported package managers found.")
        return

    for report in reports:
        if report.error_message:
            # The message comes from another tool, so brackets in it are text.
            console.print(
                f"[yellow]{report.label}: check failed[/] ({escape(report.error_message)})"
            )
        elif report.outdated_packages:
            count = len(report.outdated_packages)
            console.print(f"[bold]{report.label}[/]: {count} outdated")
            for package in report.outdated_packages:
                console.print(f"    {package}", markup=False, highlight=False)
        else:
            console.print(f"[green]{report.label}[/]: up to date")

    total = count_outdated_packages(reports)
    failures = sum(1 for report in reports if report.error_message)
    console.print()
    if total:
        console.print(f"[bold]{total}[/] outdated in total.")
    elif failures:
        console.print("Nothing outdated in the checks that ran.")
    else:
        console.print("Everything is up to date.")
