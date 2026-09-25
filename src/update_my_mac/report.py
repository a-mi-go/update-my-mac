"""Turning check results into something readable."""

from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from update_my_mac import app_updaters


# A handful reads fine one per line. Beyond that the list pushes everything
# else off the screen, so it goes into columns instead.
LIST_FITS_ON_LINES = 5
COLUMNS = 4


def print_list(console, items, indent="    ", names=None):
    """One per line while the list is short, four columns once it isn't.

    The columns hold names alone. Versions belong to a list you read line by
    line, and in a grid they push the names apart until nothing lines up.
    """
    if len(items) <= LIST_FITS_ON_LINES:
        for item in items:
            console.print(f"{indent}{item}", markup=False, highlight=False)
        return

    cells = list(names or items)
    table = Table.grid(padding=(0, 3))
    for _ in range(COLUMNS):
        table.add_column(overflow="fold")
    for start in range(0, len(cells), COLUMNS):
        row = cells[start : start + COLUMNS]
        row += [""] * (COLUMNS - len(row))
        # Text rather than str: a cell is a name, and a name with brackets in
        # it would otherwise be read as markup and silently disappear.
        table.add_row(*(Text(cell) for cell in row))
    console.print(Padding(table, (0, 0, 0, len(indent))))


def count_outdated_packages(reports):
    return sum(len(report.outdated_packages) for report in reports)


def print_manager_updates(updates, console=None, any_installed=True):
    """The package managers themselves, checked before the packages they hold."""
    console = console or Console(soft_wrap=True)
    if not updates:
        # Silence here would read as "not checked" rather than "nothing to do".
        if any_installed:
            console.print("[green]Package managers[/]: up to date\n")
        return

    console.print("[bold]Package managers[/]")
    for update in updates:
        if update.error_message:
            console.print(
                f"    [yellow]{update.label}: check failed[/] "
                f"({escape(update.error_message)})"
            )
        elif update.description:
            console.print(f"    {update.label}: {escape(update.description)}")
        else:
            # Nothing asked it, because nothing can without fetching first.
            console.print(f"    {update.label}: [dim]can be refreshed[/]")
    console.print()


def _print_group(console, heading, apps, with_updater=True):
    if not apps:
        return
    console.print(f"  {heading}: [bold cyan]{len(apps)}[/]")
    lines = []
    for app in apps:
        line = app.describe()
        if with_updater:
            line = f"{line}  ({app.updater.describe()})"
        lines.append(line)
    print_list(console, lines, "      ", [app.name for app in apps])


def print_untracked_apps(apps, console=None, left_alone=0):
    """Apps no package manager accounts for, so nothing else will mention them."""
    console = console or Console(highlight=False, soft_wrap=True)
    if not apps and not left_alone:
        return

    console.print()
    if apps:
        console.print(
            f"[bold]Not tracked by any package manager[/]: [bold cyan]{len(apps)}[/]"
        )
        unattended, self_updating, unclear = app_updaters.group_by_status(apps)
        _print_group(console, "Nothing looks after these", unattended, with_updater=False)
        _print_group(console, "Updater found, but not switched on", unclear)
        _print_group(console, "These update themselves", self_updating)
    if left_alone:
        console.print(
            f"[dim]{left_alone} more left alone on purpose. "
            f"Run with --retry-app to list one again.[/]"
        )


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
            print_list(console, report.outdated_packages)
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
