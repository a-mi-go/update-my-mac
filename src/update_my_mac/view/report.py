"""Turning check results into something readable."""

from update_my_mac import __version__

from dataclasses import dataclass

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from update_my_mac import __version__ as _version
from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.view import sections
from update_my_mac.checks import versions


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
    """One item per line, or a grid when there is nothing but names to print.

    A version belongs next to the thing it belongs to, so a list that carries
    one stays a list however long it is. Bare names are worth packing into a
    grid, because a column of them wastes most of the terminal.
    """
    if not items:
        return

    # A column nobody fills would only be empty space between the others.
    used = [place for place in range(3) if any(item.fields()[place] for item in items)]

    if used == [0] and len(items) > PRINT_MAX_LIST_ITEMS:
        rows = [
            [item.name for item in items[start : start + PRINT_GRID_COLUMNS]]
            for start in range(0, len(items), PRINT_GRID_COLUMNS)
        ]
        width = PRINT_GRID_COLUMNS
    else:
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


def _split_name_and_change(package):
    """A manager's "name  1.2.3 → 1.2.4" line, split so the arrows line up."""
    name, _, versions = package.partition("  ")
    return Item(name, versions.strip())


def count_outdated_packages(reports):
    return sum(len(report.outdated_packages) for report in reports)


# A mark as well as a colour, so the level survives a pipe and a log file.
MARK = {sections.CRITICAL: "🔴", sections.WARNING: "⚠️ ", sections.INFO: "ℹ️ "}
CLEAN = "✅"
COLOUR = {sections.CRITICAL: "red", sections.WARNING: "yellow", sections.INFO: "blue"}

PANEL_BORDER, PANEL_PADDING = 1, 2
PANEL_SIDES = 2 * (PANEL_BORDER + PANEL_PADDING)
ROW_INDENT = "   "


def print_report(findings, console=None):
    """All check results and issue findings, in one place.

    Framed for a terminal, plain for a pipe or a log, where a border on every
    line is only in the way.
    """
    console = console or Console(highlight=False, soft_wrap=True)
    found = sections.of(findings)
    framed = console.is_terminal
    width = console.width - (PANEL_SIDES if framed else 0)

    body = []
    for section in found:
        body += [_heading(section, width), _rows(section), Text()]
    body += _footer(findings, found, framed)

    if not framed:
        console.print(Text.assemble(("update-my-mac ", "bold"), (_version, "dim")))
        console.print(Group(*body))
        return

    needs_you, can_wait = sections.count_findings(found)
    console.print(Panel(
        Group(*body),
        title=Text.assemble((" update-my-mac ", "bold"), (f"{_version} ", "dim")),
        title_align="left",
        subtitle=Text(f" {needs_you} need your attention, {can_wait} can wait ", style="dim"),
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    ))


def _footer(findings, found, framed):
    """What was checked and found clean, and what is not in the list above."""
    lines = []
    if not findings.any_manager_installed:
        # Saying everything is fine would claim something nobody checked.
        lines.append(Text("No supported package managers found.", style="yellow"))
    elif not found:
        lines.append(Text("Everything is up to date.", style="green"))
    clean = sections.clean_managers(findings)
    if clean:
        lines.append(Text.assemble(
            (f"{CLEAN} ", ""), (f"up to date: {', '.join(clean)}", "green"),
        ))
    if findings.left_alone:
        lines.append(Text(
            f"{findings.left_alone} left alone on purpose, --retry-app lists one again",
            style="dim",
        ))
    if found and not framed:
        needs_you, can_wait = sections.count_findings(found)
        lines.append(Text(f"{needs_you} need your attention, {can_wait} can wait", style="dim"))
    return lines


def _heading(section, width):
    """The section title, its count, and the reason it exists, on one line."""
    heading = Text.assemble(
        (f"{MARK[section.level]} ", ""),
        (f"{section.title} ", f"bold {COLOUR[section.level]}"),
        (section.counted(), "bold cyan"),
    )
    room = width - heading.cell_len - len(section.note)
    if section.note and room >= 2:
        heading.pad_right(room)
        heading.append(section.note, style="dim italic")
    return heading


def _rows(section):
    grid = Table.grid(padding=(0, 3))
    grid.add_column(overflow="fold")
    grid.add_column(overflow="fold")
    grid.add_column(style="dim", overflow="fold")
    for row in section.rows:
        name, version, note = row.cells()
        grid.add_row(Text(f"{ROW_INDENT}{name}"), Text(version), Text(note))
    return grid


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


def _print_group(console, heading, apps, with_updater=True, offered=None, find_cask=None):
    if not apps:
        return
    console.print(f"  {heading}: [bold cyan]{len(apps)}[/]")
    print_as_list_or_grid(
        console,
        "      ",
        [
            Item(
                app.name,
                _version_column(app, offered, find_cask),
                app.updater.update_method_note() if with_updater else "",
            )
            for app in apps
        ],
    )


def _version_column(app, offered, find_cask=None):
    """The installed version, and the newer one on offer for it.

    An app that no manager tracks has two places that could know of one: its
    own update feed, and a Homebrew recipe that could take it over.
    """
    answer = appcast.answer_for(app, offered or {})
    if appcast.offers_newer(app, answer):
        return f"{app.version} → {answer.version}"

    cask = find_cask(app) if find_cask else None
    if cask and versions.is_newer(cask.version, than=app.version):
        return f"{app.version} → {cask.version}"
    return app.version


def print_still_running_old(apps, console=None):
    """Apps upgraded underneath a running process, which nothing else notices."""
    if not apps:
        return

    console = console or Console(highlight=False, soft_wrap=True)
    console.print()
    console.print(f"[yellow]Updated but not restarted (running an old version)[/]: [bold cyan]{len(apps)}[/]")
    print_as_list_or_grid(
        console,
        "    ",
        [Item(app.name, app.version, app.comment()) for app in apps],
    )


def print_behind_the_recipe(behind, console=None):
    """Apps older than Homebrew's recipe, which Homebrew itself never says."""
    if not behind:
        return

    console = console or Console(highlight=False, soft_wrap=True)
    console.print()
    console.print(f"[yellow]Older than Homebrew's recipe[/]: [bold cyan]{len(behind)}[/]")
    console.print(
        "    [dim]Homebrew reports none of these, because it trusts each app to "
        "update itself.[/]"
    )
    print_as_list_or_grid(
        console, "    ", [Item(item.app.name, item.version_change()) for item in behind]
    )


def print_duplicate_installations(duplicates, console=None):
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


def print_untracked_apps(apps, console=None, left_alone=0, offered=None, find_cask=None):
    """Apps not tracked by any of the supported package managers."""
    console = console or Console(highlight=False, soft_wrap=True)
    if not apps and not left_alone:
        return

    console.print()
    if apps:
        console.print(
            f"[bold]Not tracked by any package manager[/]: [bold cyan]{len(apps)}[/]"
        )
        # An app whose feed has gone quiet is listed by what it does now, not
        # by what its settings still claim it does.
        quiet, rest = [], []
        for app in apps:
            side = quiet if appcast.answer_for(app, offered or {}).error else rest
            side.append(app)

        unattended, switched_off, unclear, self_updating = app_updaters.group_by_status(rest)
        _print_group(console, "Possibly don't update at all", unattended,
                     with_updater=False, offered=offered, find_cask=find_cask)
        _print_group(console, "Their updater is switched off", switched_off,
                     offered=offered, find_cask=find_cask)
        _print_group(console, "They have an updater, nobody answered for it", unclear,
                     offered=offered, find_cask=find_cask)
        _print_group(console, "These update themselves", self_updating,
                     offered=offered, find_cask=find_cask)
        _say_which_feeds_went_quiet(console, quiet, offered)
    if left_alone:
        console.print(
            f"[dim]{left_alone} more left alone on purpose. "
            f"Run with --retry-app to list one again.[/]"
        )


def _say_which_feeds_went_quiet(console, quiet, offered):
    """Apps whose update feed stopped answering, so they update no more.

    Sparkle reports this as an improperly signed update, because a host that
    dropped the feed serves its own error page in its place.
    """
    if not quiet:
        return

    console.print(f"  [yellow]Cannot update themselves any more[/]: [bold cyan]{len(quiet)}[/]")
    print_as_list_or_grid(
        console,
        "      ",
        [
            Item(app.name, app.version, appcast.answer_for(app, offered).error)
            for app in quiet
        ],
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
                console,
                "    ",
                [_split_name_and_change(package) for package in report.outdated_packages],
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
