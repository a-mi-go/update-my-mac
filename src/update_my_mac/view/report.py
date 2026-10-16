"""Turning check results into something readable."""

from dataclasses import dataclass

from rich import box
from rich.cells import cell_len
from rich.console import Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from update_my_mac import __version__ as _version
from update_my_mac.checks import versions
from update_my_mac.view import output
from update_my_mac.view import sections


# The spinner every wait is shown with.
SPINNER = "dots"

# Beyond this items count a list is printed as a grid for better readability
PRINT_MAX_LIST_ITEMS = 5
PRINT_GRID_COLUMNS = 3
GRID_GAP = 3


@dataclass
class Item:
    """One line of a list: what it is, which version, and anything to add."""
    name: str
    version: str = ""
    comment: str = ""

    def fields(self):
        return (self.name, self.version, self.comment)


def _items_per_line(indent, cells):
    """Returns how many items fit to a line, up to PRINT_GRID_COLUMNS, with none wrapped."""
    for per_line in range(PRINT_GRID_COLUMNS, 1, -1):
        widest = {}
        for number, cell in enumerate(cells):
            for place, text in enumerate(cell):
                column = (number % per_line) * len(cell) + place
                widest[column] = max(widest.get(column, 0), cell_len(text))
        needed = len(indent) + sum(widest.values()) + GRID_GAP * (len(widest) - 1)
        if needed <= output.console.width:
            return per_line
    return 1


def print_as_list_or_grid(indent, items):
    """Prints one item per line, or up to PRINT_GRID_COLUMNS items to a line when there are many."""
    if not items:
        return

    # A column nobody fills would only be empty space between the others.
    used = [place for place in range(3) if any(item.fields()[place] for item in items)]
    cells = [[item.fields()[place] for place in used] for item in items]

    per_line = _items_per_line(indent, cells) if len(items) > PRINT_MAX_LIST_ITEMS else 1
    rows = [sum(cells[start : start + per_line], []) for start in range(0, len(cells), per_line)]
    width = per_line * len(used)

    table = Table.grid(padding=(0, GRID_GAP))
    for _ in range(width):
        table.add_column(overflow="fold")
    for row in rows:
        row = list(row) + [""] * (width - len(row))
        # Text rather than str: a cell is a name, and a name with brackets in
        # it would otherwise be read as markup and silently disappear.
        table.add_row(*(Text(cell) for cell in row))
    output.console.print(Padding(table, (0, 0, 0, len(indent))))


def item_for_package(package):
    """Returns a manager's "name  1.2.3 → 1.2.4" line split so the arrows line up."""
    name, _, change = package.partition("  ")
    return Item(name, versions.change_without_builds(change))


def count_outdated_packages(reports):
    return sum(len(report.outdated_packages) for report in reports)


# A mark as well as a colour, so the level survives a pipe and a log file.
MARK = {sections.CRITICAL: "🔴", sections.WARNING: "⚠️ ", sections.INFO: "ℹ️ "}
CLEAN = "✅"
COLOUR = {sections.CRITICAL: "red", sections.WARNING: "yellow", sections.INFO: "blue"}

# A terminal re-wraps what is already printed when its window shrinks, which
# tears a frame apart. A frame that stops growing at this width survives every
# resize that leaves the window wider than it.
REPORT_MAX_WIDTH = 88
PANEL_BORDER, PANEL_PADDING = 1, 2
PANEL_SIDES = 2 * (PANEL_BORDER + PANEL_PADDING)
ROW_INDENT = "   "


def print_report(findings):
    """Prints every check result and finding, framed for a terminal, plain for a pipe."""
    console = output.console
    found = sections.of(findings)
    framed = console.is_terminal
    outer = min(console.width, REPORT_MAX_WIDTH)
    width = outer - (PANEL_SIDES if framed else 0)

    body = []
    for section in found:
        body += [_heading(section, width), _rows(section), Text()]
    body += _footer(findings, found, framed)

    console.print()
    if not framed:
        console.print(Text.assemble(("update-my-mac ", "bold"), (f"{_version} report", "dim")))
        console.print(Group(*body))
        return

    needs_you, can_wait = sections.count_findings(found)
    console.print(Panel(
        Group(*body),
        title=Text.assemble((" update-my-mac ", "bold"), (f"{_version} report ", "dim")),
        title_align="left",
        subtitle=Text(f" {needs_you} need your attention, {can_wait} can wait ", style="dim"),
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, PANEL_PADDING),
        width=outer,
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
        (section.counted(), "cyan"),
    )
    room = width - heading.cell_len - len(section.note)
    if section.note and room >= 2:
        # Right behind the title, not padded out to the edge: a line filled to
        # the full width wraps at the first pixel the window loses.
        heading.append(f"  {section.note}", style="dim italic")
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


def _print_what_was_left_out(report):
    """A manager that answered about only part of what it holds has to say so."""
    if not report.ignored_taps:
        return

    named = ", ".join(report.ignored_taps)
    output.print_plain(
        "    ", (f"Nothing from {named} was checked", "yellow"),
        ", Homebrew ignores a tap until you trust it.",
    )


def print_outdated_summary(reports):
    console = output.console

    if not reports:
        console.print("No supported package managers found.")
        return

    for report in reports:
        if report.error_message:
            output.print_plain((f"{report.label}: check failed", "yellow"), f" ({report.error_message})")
        elif report.outdated_packages:
            count = len(report.outdated_packages)
            console.print(f"[bold]{report.label}[/]: {count} outdated")
            print_as_list_or_grid(
                "    ",
                [item_for_package(package) for package in report.outdated_packages],
            )
        else:
            console.print(f"[green]{report.label}[/]: up to date")
        _print_what_was_left_out(report)

    total = count_outdated_packages(reports)
    failures = sum(1 for report in reports if report.error_message)
    console.print()
    if total:
        console.print(f"[bold]{total}[/] outdated in total.")
    elif failures:
        console.print("Nothing outdated in the checks that ran.")
    else:
        console.print("Everything is up to date.")


DOTTED_WIDTH = 50


def dotted_line(label, result, succeeded=True):
    """Returns "label ..... result", the result in green or yellow."""
    dots = "." * max(3, DOTTED_WIDTH - len(label) - len(result) - 2)
    colour = "green" if succeeded else "yellow"
    return Text.assemble(label, " ", (dots, "dim"), " ", (result, colour))
