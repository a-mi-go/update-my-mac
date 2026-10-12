"""Turning check results into something readable."""

from dataclasses import dataclass

from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from update_my_mac import __version__ as _version
from update_my_mac.view import sections


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
    """Prints one item per line, or a grid when the items are bare names."""
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
    """Returns a manager's "name  1.2.3 → 1.2.4" line split so the arrows line up."""
    name, _, change = package.partition("  ")
    return Item(name, change.strip())


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
    """Prints every check result and finding, framed for a terminal, plain for a pipe."""
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
    """Returns what was checked and found clean, and what is not in the list above."""
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
    """Returns the section title, its count and its note, on one line."""
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
