"""Turning check results into something readable."""

import time
from dataclasses import dataclass
from itertools import zip_longest

from rich import box
from rich.cells import cell_len
from rich.console import Group
from rich.measure import Measurement
from rich.padding import Padding
from rich.panel import Panel
from rich.segment import Segment
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


# A mark as well as a colour, so the level survives a pipe and a log file.
# No variation selector after ⚠: rich counts that as two cells, the terminal as one.
MARK = {sections.CRITICAL: "🚨", sections.WARNING: "⚠ ", sections.INFO: "✅"}
CLEAN = "✅"
COLOUR = {sections.CRITICAL: "red", sections.WARNING: "yellow", sections.INFO: "green"}

# Wider than this the lines only get longer to read, not more informative.
REPORT_MAX_WIDTH = 100
PANEL_BORDER, PANEL_PADDING = 1, 2
PANEL_SIDES = 2 * (PANEL_BORDER + PANEL_PADDING)
# The corner and a dash on each side of a title in the frame's top or bottom line.
TITLE_EDGES = 4
# The fewest dashes between the two names in the top line, and either side of them.
MIN_DASHES = 3
# Between the time in the top line and the corner.
CORNER_DASHES = "──"
ROW_INDENT = "   "
CELL_GAP = 3
# Two columns of updates sit closer, and keep the room between them on top of that.
PAIR_GAP = 2
COLUMN_GAP = 3


def print_report(findings):
    print_to(output.console, findings)


def print_to(console, findings):
    """Prints every check result and finding, framed for a terminal, plain for a pipe."""
    found = sections.of(findings)
    framed = console.is_terminal
    outer = min(console.width, REPORT_MAX_WIDTH)
    width = outer - (PANEL_SIDES if framed else 0)

    body = []
    for part, count in zip(sections.PARTS, sections.count_findings(found)):
        within = [section for section in found if section.part == part]
        if not within:
            continue
        body += [Text.assemble((part.upper(), "bold"), " ", (str(count), "bold cyan")), Text()]
        for section in within:
            body += [_heading(section, width), _rows(section, width), Text()]
    body += _footer(findings, found, framed)

    console.print()
    if not framed:
        console.print(Text.assemble(("update-my-mac ", "bold"), (f"{_version} report", "dim")))
        console.print(Group(*body))
        return

    subtitle = Text(f" {_counted_by_part(found)} ", style="dim")
    # No wider than its content, so a short report has no long dash lines to wrap.
    content = Measurement.get(console, console.options.update(width=width), Group(*body)).maximum
    top = next(
        (needed for needed in (_centered_width(), _next_to_app_width()) if outer >= needed),
        _app_name().cell_len + TITLE_EDGES,
    )
    outer = min(outer, max(content + PANEL_SIDES, top, subtitle.cell_len + TITLE_EDGES))
    console.print(_WithTopLine(
        Panel(
            Group(*body),
            subtitle=subtitle,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, PANEL_PADDING),
            width=outer,
        ),
    ))


def _app_name():
    return Text.assemble(("╭──", "cyan"), " ", ("update-my-mac ", "bold"), (_version, "dim"), " ")


def _report_name():
    return Text.assemble(" ", ("STATUS REPORT", "bold"), " ")


def _time_stamp():
    return Text(time.strftime(" %Y-%m-%d %H:%M ", time.localtime(time.time())), style="dim")


def _centered_width():
    """Returns the width from which the report's name can sit in the middle."""
    return 2 * (_app_name().cell_len + MIN_DASHES) + _report_name().cell_len


def _next_to_app_width():
    """Returns the width from which the report's name fits behind the app's name."""
    return _app_name().cell_len + MIN_DASHES + _report_name().cell_len + 1


def _top_line(width):
    """Returns the top line: the app's name, the report's name in the middle, the time at the end."""
    app, report_name = _app_name(), _report_name()
    middle = (width - report_name.cell_len) // 2
    if middle - app.cell_len >= MIN_DASHES:
        gap = middle - app.cell_len
    elif width >= _next_to_app_width():
        gap = MIN_DASHES
    else:
        return Text.assemble(app, ("─" * (width - app.cell_len - 1) + "╮", "cyan"))

    line = Text.assemble(app, ("─" * gap, "cyan"), report_name)
    stamp = _time_stamp()
    # The time is left off where it would crowd the report's name.
    room = width - line.cell_len - stamp.cell_len - len(CORNER_DASHES) - 1
    if room >= MIN_DASHES:
        line.append_text(Text.assemble(("─" * room, "cyan"), stamp))
    return Text.assemble(line, ("─" * (width - line.cell_len - 1) + "╮", "cyan"))


class _WithTopLine:
    """A panel whose top line is replaced by the one with the names in it."""

    def __init__(self, panel):
        self.panel = panel

    def __rich_console__(self, console, options):
        lines = console.render_lines(self.panel, options, pad=False)
        yield _top_line(Segment.get_line_length(lines[0]))
        for line in lines[1:]:
            yield from line
            yield Segment.line()


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


def _heading(section, width):
    """Returns the section title, its count and its note, on one line."""
    heading = Text.assemble(
        (f"{MARK[section.level]} ", COLOUR[section.level]),
        (f"{section.title} ", f"bold {COLOUR[section.level]}"),
        (section.counted(), "cyan"),
    )
    room = width - heading.cell_len - len(section.note)
    if section.note and room >= 2:
        # Right behind the title, not padded out to the edge: a line filled to
        # the full width wraps at the first pixel the window loses.
        heading.append(f"  {section.note}", style="dim italic")
    return heading


def _rows(section, width):
    if section.part == sections.UPDATES_AVAILABLE:
        side_by_side = _in_two_columns([row for row in section.rows if not row.note], width)
        if side_by_side is not None:
            noted = [row for row in section.rows if row.note]
            return Group(side_by_side, _one_column(noted)) if noted else side_by_side
    return _one_column(section.rows)


def _one_column(rows):
    grid = Table.grid(padding=(0, CELL_GAP))
    grid.add_column(overflow="fold")
    grid.add_column(overflow="fold")
    grid.add_column(style="dim", overflow="fold")
    for row in rows:
        name, version, note = row.cells()
        grid.add_row(Text(f"{ROW_INDENT}{name}"), Text(version), Text(note))
    return grid


def _in_two_columns(rows, width):
    """Returns the rows as two columns read top to bottom, or None where they would not fit."""
    if len(rows) < 2:
        return None
    half = (len(rows) + 1) // 2
    halves = (rows[:half], rows[half:])
    names = [max(cell_len(row.name) for row in side) + len(ROW_INDENT) for side in halves]
    changes = [max(cell_len(row.version) for row in side) for side in halves]
    if sum(names) + sum(changes) + 3 * PAIR_GAP + COLUMN_GAP > width:
        return None

    grid = Table.grid(padding=(0, PAIR_GAP))
    grid.add_column(width=names[0], no_wrap=True)
    grid.add_column(width=changes[0] + COLUMN_GAP, no_wrap=True)
    grid.add_column(width=names[1], no_wrap=True)
    grid.add_column(width=changes[1], no_wrap=True)
    for left, right in zip_longest(*halves):
        cells = []
        for row in (left, right):
            cells += [Text(f"{ROW_INDENT}{row.name}"), Text(row.version)] if row else [Text(), Text()]
        grid.add_row(*cells)
    return grid


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
            (f"{CLEAN} ", ""), (f"{', '.join(clean)} : everything up to date", "green"),
        ))
    if findings.left_alone:
        lines.append(Text(
            f"{findings.left_alone} left alone on purpose, --retry-app lists one again",
            style="dim",
        ))
    if found and not framed:
        lines.append(Text(_counted_by_part(found), style="dim"))
    return lines


def _counted_by_part(found):
    attention, updates, info = sections.count_findings(found)
    counted = (
        f"{attention} need attention" if attention else "",
        f"{updates} update{'' if updates == 1 else 's'} available" if updates else "",
        f"{info} info" if info else "",
    )
    return " · ".join(part for part in counted if part)


def _print_what_was_left_out(report):
    """A manager that answered about only part of what it holds has to say so."""
    if not report.ignored_taps:
        return

    named = ", ".join(report.ignored_taps)
    output.print_plain(
        "    ", (f"Nothing from {named} was checked", "yellow"),
        ", Homebrew ignores a tap until you trust it.",
    )


DOTTED_WIDTH = 50


def dotted_line(label, result, succeeded=True):
    """Returns "label ..... result", the result in green or yellow."""
    dots = "." * max(3, DOTTED_WIDTH - len(label) - len(result) - 2)
    colour = "green" if succeeded else "yellow"
    return Text.assemble(label, " ", (dots, "dim"), " ", (result, colour))
