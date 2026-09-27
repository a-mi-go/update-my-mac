"""Turning check results into something readable."""

from update_my_mac import __version__

from dataclasses import dataclass

from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from update_my_mac import app_updaters


# Beyond this items count a list is printed as a grid for better readability
PRINT_MAX_LIST_ITEMS = 5
PRINT_GRID_COLUMNS = 4


@dataclass
class Item:
    """One line of a list: what it is, which version, and anything to add."""
    name: str
    version: str = ""
    comment: str = ""

    def fields(self):
        return (self.name, self.version, self.comment)


def print_as_list_or_grid(console, indent, items):
    """A short set of items is printed line by line with versions and comments (if supplied).
    A long one as a grid with names only.
    """
    if not items:
        return

    if len(items) > PRINT_MAX_LIST_ITEMS:
        rows = [
            [item.name for item in items[start : start + PRINT_GRID_COLUMNS]]
            for start in range(0, len(items), PRINT_GRID_COLUMNS)
        ]
        width = PRINT_GRID_COLUMNS
    else:
        # A column nobody fills would only be empty space between the others.
        used = [
            place
            for place in range(3)
            if any(item.fields()[place] for item in items)
        ]
        rows = [[item.fields()[place] for place in used] for item in items]
        width = len(used)

    table = Table.grid(padding=(0, 3))
    for _ in range(width):
        table.add_column(overflow="fold")
    for row in rows:
        row = list(row) + [""] * (width - len(row))
        # Text rather than str: a cell is a name, and a name with brackets in
        # it would otherwise be read as markup and silently disappear.
        table.add_row(*(Text(cell) for cell in row))
    console.print(Padding(table, (0, 0, 0, len(indent))))


def count_outdated_packages(reports):
    return sum(len(report.outdated_packages) for report in reports)


def print_header(console=None):
    """A line across the terminal, so a run is easy to find when scrolling back."""
    console = console or Console(highlight=False)
    console.rule(f"[bold]update-my-mac[/] {__version__}", style="cyan")


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
    print_as_list_or_grid(
        console,
        "      ",
        [
            Item(app.name, app.version, app.updater.describe() if with_updater else "")
            for app in apps
        ],
    )


def print_still_running_old(apps, console=None):
    """Apps upgraded underneath a running process, which nothing else notices."""
    if not apps:
        return

    console = console or Console(highlight=False, soft_wrap=True)
    console.print()
    console.print(f"[yellow]Running an old version[/]: [bold cyan]{len(apps)}[/]")
    print_as_list_or_grid(
        console, "    ", [Item(app.name, comment=app.comment()) for app in apps]
    )
    console.print(
        "    [dim]The new versions are already installed. These only need restarting.[/]"
    )


def print_behind_the_recipe(behind, console=None):
    """Apps older than Homebrew's recipe, which Homebrew itself never says."""
    if not behind:
        return

    console = console or Console(highlight=False, soft_wrap=True)
    console.print()
    console.print(f"[yellow]Older than Homebrew's recipe[/]: [bold cyan]{len(behind)}[/]")
    print_as_list_or_grid(
        console,
        "    ",
        [Item(item.app.name, item.version_change()) for item in behind],
    )
    console.print(
        "    [dim]Homebrew reports none of these, because it trusts each app to "
        "update itself:[/]"
    )
    console.print("    brew upgrade --cask --greedy", markup=False, highlight=False)


def print_duplicate_commands(duplicates, console=None):
    """Commands two managers installed, where PATH quietly picks the winner."""
    if not duplicates:
        return

    console = console or Console(highlight=False, soft_wrap=True)
    console.print()
    console.print(f"[yellow]Installed twice[/]: [bold cyan]{len(duplicates)}[/]")
    for duplicate in duplicates:
        console.print(f"    {escape(duplicate.command)}")
        console.print(f"        runs now:   {escape(duplicate.winner.describe())}")
        for copy in duplicate.shadowed:
            console.print(f"        never used: {escape(copy.describe())}")


def print_foreign_owners(apps, console=None):
    """Apps a Homebrew upgrade would break on, with the way out."""
    if not apps:
        return

    console = console or Console(highlight=False, soft_wrap=True)
    console.print()
    console.print(f"[yellow]Owned by another user[/]: [bold cyan]{len(apps)}[/]")
    print_as_list_or_grid(console, "    ", [Item(path.name) for path in apps])
    console.print(
        "    [dim]Homebrew cannot upgrade these until they are yours. "
        "Take them over with:[/]"
    )
    quoted = " ".join(f'"{path}"' for path in apps)
    console.print(f"    sudo chown -R $(id -un) {quoted}", markup=False, highlight=False)


def print_untracked_apps(apps, console=None, left_alone=0):
    """Apps not tracked by any of the supported package managers."""
    console = console or Console(highlight=False, soft_wrap=True)
    if not apps and not left_alone:
        return

    console.print()
    if apps:
        console.print(
            f"[bold]Not tracked by any package manager[/]: [bold cyan]{len(apps)}[/]"
        )
        unattended, switched_off, unclear, self_updating = app_updaters.group_by_status(apps)
        _print_group(console, "Possibly don't update at all", unattended, with_updater=False)
        _print_group(console, "Their updater is switched off", switched_off)
        _print_group(console, "They have an updater, nobody answered for it", unclear)
        _print_group(console, "These update themselves", self_updating)
    if left_alone:
        console.print(
            f"[dim]{left_alone} more left alone on purpose. "
            f"Run with --retry-app to list one again.[/]"
        )


def _say_what_was_left_out(console, report):
    """A manager that answered about only part of what it holds has to say so."""
    if not report.ignored_taps:
        return

    named = ", ".join(report.ignored_taps)
    console.print(
        f"    [yellow]Nothing from {escape(named)} was checked[/], "
        f"Homebrew ignores a tap until you trust it."
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
            print_as_list_or_grid(
                console, "    ", [Item(package) for package in report.outdated_packages]
            )
        else:
            console.print(f"[green]{report.label}[/]: up to date")
        _say_what_was_left_out(console, report)

    total = count_outdated_packages(reports)
    failures = sum(1 for report in reports if report.error_message)
    console.print()
    if total:
        console.print(f"[bold]{total}[/] outdated in total.")
    elif failures:
        console.print("Nothing outdated in the checks that ran.")
    else:
        console.print("Everything is up to date.")
