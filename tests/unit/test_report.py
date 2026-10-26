import time
from pathlib import Path

from rich.console import Console
from rich.text import Text

from update_my_mac import __version__
from update_my_mac.checks import Findings
from update_my_mac.checks import app_updaters
from update_my_mac.view import report
from update_my_mac.view import sections
from update_my_mac.checks.app_updaters import UpdaterStatus
from update_my_mac.checks.installed_apps import InstalledApp
from update_my_mac.managers import ManagerReport, ManagerUpdate

from fake_run import printed_by


def rendered(reports):
    return printed_by(lambda: report.print_outdated_summary(reports),
                      Console(width=200, no_color=True, soft_wrap=True))


def test_no_managers_at_all():
    assert "No supported package managers found" in rendered([])


def test_outdated_and_failed_managers_side_by_side():
    out = rendered(
        [
            ManagerReport("brew", "Homebrew", ["git 2.48.1 → 2.49.0"]),
            ManagerReport("npm", "npm (global)", [], "ENOTFOUND: registry is down"),
            ManagerReport("mas", "Mac App Store", []),
        ]
    )
    assert "Homebrew: 1 outdated" in out
    assert "npm (global): check failed (ENOTFOUND" in out
    assert "Mac App Store: up to date" in out
    assert "1 outdated in total" in out


def test_a_failed_check_is_not_summarised_as_up_to_date():
    out = rendered([ManagerReport("npm", "npm (global)", [], "boom")])
    assert "Everything is up to date" not in out
    assert "Nothing outdated in the checks that ran" in out


def test_brackets_in_an_error_are_text_not_markup():
    # rich would otherwise read [warn] as a style and swallow it.
    out = rendered([ManagerReport("npm", "npm (global)", [], "[warn] bad config")])
    assert "[warn] bad config" in out


def test_brackets_in_a_package_name_are_text_not_markup():
    out = rendered([ManagerReport("npm", "npm (global)", ["pkg [beta]  1.0 → 2.0"])])
    # The name and the versions become two columns, so they line up with the
    # rows above and below.
    assert "pkg [beta]" in out
    assert "1.0 → 2.0" in out


def outdated(count):
    return [ManagerReport("brew", "Homebrew", [f"package-{n}" for n in range(count)])]


def test_a_short_list_stays_one_per_line():
    printed = printed_by(
        lambda: report.print_outdated_summary(outdated(5)),
        Console(width=120, no_color=True),
    )
    assert "package-0" in printed.splitlines()[1]
    assert len([line for line in printed.splitlines() if "package-" in line]) == 5


def test_a_longer_list_goes_into_three_columns():
    printed = printed_by(
        lambda: report.print_outdated_summary(outdated(6)),
        Console(width=120, no_color=True),
    )

    rows = [line for line in printed.splitlines() if "package-" in line]
    assert len(rows) == 2
    assert rows[0].split() == ["package-0", "package-1", "package-2"]
    assert rows[1].split() == ["package-3", "package-4", "package-5"]


BRACKETS = ["oops[/]", "[bold]weird[/bold]"]


def test_a_short_list_prints_brackets_as_text():
    printed = printed_by(
        lambda: report.print_outdated_summary([ManagerReport("brew", "Homebrew", BRACKETS)]),
        Console(width=120, no_color=True),
    )
    assert "oops[/]" in printed
    assert "[bold]weird[/bold]" in printed


def test_the_columns_print_brackets_as_text():
    # As a plain string, "oops[/]" raised MarkupError and "[bold]x[/bold]"
    # vanished into styling, which is worse because nobody notices.
    packages = [f"package-{n}" for n in range(5)] + BRACKETS
    printed = printed_by(
        lambda: report.print_outdated_summary([ManagerReport("brew", "Homebrew", packages)]),
        Console(width=200, no_color=True),
    )
    assert "oops[/]" in printed
    assert "[bold]weird[/bold]" in printed


def test_a_manager_says_when_it_left_something_out():
    reports = [ManagerReport("brew", "Homebrew", [], ignored_taps=["anomalyco/tap", "clerk/stable"])]
    printed = printed_by(
        lambda: report.print_outdated_summary(reports),
        Console(width=120, no_color=True),
    )
    assert "Nothing from anomalyco/tap, clerk/stable was checked" in printed


def printed_list(items, width=100):
    printed = printed_by(lambda: report.print_as_list_or_grid("    ", items),
                         Console(width=width, no_color=True))
    return [line.rstrip() for line in printed.splitlines()]


def test_names_alone_take_one_column():
    lines = printed_list([report.Item("aom"), report.Item("cairo")])

    assert lines == ["    aom", "    cairo"]


def test_versions_line_up_under_each_other():
    lines = printed_list([report.Item("aom", "1.0"), report.Item("ca-certificates", "2026")])

    assert lines[0].index("1.0") == lines[1].index("2026")


def test_a_comment_gets_a_column_of_its_own():
    lines = printed_list([
        report.Item("Air", "262.5", "checks only"),
        report.Item("Dockish", "1.1", "state unknown"),
    ])

    assert lines[0].index("checks only") == lines[1].index("state unknown")


def test_a_column_nobody_fills_is_left_out():
    # Without a version there is no reason to leave a gap where one would be.
    lines = printed_list([
        report.Item("Google Drive", comment="running since 15 Sep"),
        report.Item("TickTick", comment="running since 16 Sep"),
    ])

    # The comments start where the second column starts, with no gap for a
    # version that none of these has.
    assert lines[0].index("running") == lines[1].index("running")
    assert lines[0].index("running") == len("    Google Drive") + 3


def test_a_long_list_of_bare_names_goes_into_three_columns():
    lines = printed_list([report.Item(f"app-{n}") for n in range(6)])

    assert len(lines) == 2
    assert lines[0].split() == ["app-0", "app-1", "app-2"]


def test_a_long_list_with_versions_goes_three_to_a_line_each_beside_its_version():
    items = [report.Item(f"app-{n}", f"1.{n}") for n in range(6)]
    lines = printed_list(items)

    assert len(lines) == 2
    assert lines[0].split() == ["app-0", "1.0", "app-1", "1.1", "app-2", "1.2"]


def test_fewer_items_go_to_a_line_where_three_would_wrap():
    items = [report.Item(f"application-{n}", f"1.2.{n} → 1.3.{n}") for n in range(6)]

    wide = printed_list(items, width=120)
    narrow = printed_list(items, width=80)
    tight = printed_list(items, width=40)

    assert [len(wide), len(narrow), len(tight)] == [2, 3, 6]
    assert max(len(line) for line in narrow) <= 80
    assert max(len(line) for line in tight) <= 40


def test_a_short_list_with_versions_stays_one_per_line():
    items = [report.Item(f"app-{n}", f"1.{n}") for n in range(5)]
    lines = printed_list(items)

    assert len(lines) == 5
    assert lines[0].split() == ["app-0", "1.0"]


def test_an_empty_list_prints_nothing():
    assert printed_list([]) == []


def with_feed(name, version, url="https://x.test/appcast.xml"):
    return InstalledApp(
        name, version, Path(f"/Applications/{name}.app"),
        UpdaterStatus(app_updaters.SPARKLE, True, False, "2026-08-16", url),
    )


def report_of(findings, width=80, terminal=False):
    return printed_by(lambda: report.print_report(findings),
                      Console(width=width, no_color=True, force_terminal=terminal or None))


def test_the_report_is_framed_for_someone_watching():
    findings = Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])]
    )

    framed = report_of(findings, terminal=True)

    assert "update-my-mac" in framed
    assert "╭" in framed
    assert "1 update available" in framed


def test_a_run_without_a_frame_still_says_what_wrote_it():
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", [])])

    assert f"update-my-mac {__version__}" in report_of(findings)


def test_the_frame_is_left_off_when_the_output_is_going_somewhere_else():
    # Every line would start with a border, which is only in the way in a
    # pipe or a log.
    findings = Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])]
    )

    plain = report_of(findings)

    assert "╭" not in plain
    assert "│" not in plain
    # The count the frame would have carried is said in words instead.
    assert "1 update available" in plain


def test_a_clean_run_says_which_managers_answered():
    # Silence about a manager reads as "not checked".
    findings = Findings(reports=[
        ManagerReport("brew", "Homebrew", []),
        ManagerReport("mas", "Mac App Store", []),
    ])

    printed = report_of(findings)

    assert "Everything is up to date." in printed
    assert "Homebrew, Mac App Store : everything up to date" in printed


def test_a_machine_with_no_managers_is_not_told_everything_is_fine():
    printed = report_of(Findings(any_manager_installed=False))

    assert "No supported package managers found." in printed
    assert "Everything is up to date" not in printed


def test_a_section_says_how_many_and_why_it_is_there():
    findings = Findings(
        reports=[ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"])]
    )

    heading = next(line for line in report_of(findings).splitlines() if "Mac App Store" in line)

    assert "Mac App Store 1" in heading
    assert "update from the menu below" in heading


def test_a_reason_that_would_not_fit_is_left_off_rather_than_wrapped():
    findings = Findings(
        reports=[ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"])]
    )

    printed = report_of(findings, width=40)

    assert "Mac App Store 1" in printed
    assert "update from the menu below" not in printed


def test_the_managers_that_are_current_are_said_so_in_green():
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", [])])
    printed = printed_by(lambda: report.print_report(findings),
                         Console(width=80, force_terminal=True))
    assert "✅" in printed
    # 32 is green, and this line is the only thing wearing it.
    assert "\x1b[32mHomebrew : everything up to date" in printed


def widest_line(findings, width):
    printed = report_of(findings, width=width, terminal=True)
    return max(Text.from_ansi(line).cell_len for line in printed.splitlines())


def test_the_frame_is_no_wider_than_what_is_in_it():
    findings = Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])]
    )

    assert widest_line(findings, width=200) < report.REPORT_MAX_WIDTH


def test_the_frame_stops_growing_at_a_readable_width():
    long_name = "a" * 150
    findings = Findings(
        reports=[ManagerReport("brew", "Homebrew", [f"{long_name}  1.0 → 2.0"])]
    )

    assert widest_line(findings, width=200) == report.REPORT_MAX_WIDTH


def test_the_count_in_a_heading_is_not_bold():
    section = sections.Section(
        sections.WARNING, "Homebrew", "", [sections.Row("git")], counted_as=sections.UPDATES
    )

    heading = report._heading(section, 80)

    styles = {heading.plain[span.start:span.end]: str(span.style) for span in heading.spans}
    assert styles[section.counted()] == "cyan"
    assert "bold" in styles["Homebrew "]


def test_the_top_line_names_the_app_and_the_report():
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])])

    top = Text.from_ansi(report_of(findings, width=100, terminal=True).splitlines()[1]).plain

    assert top.startswith(f"╭── update-my-mac {__version__} ─")
    assert " STATUS REPORT ─" in top
    assert top.endswith("╮")


def test_the_name_of_the_report_is_in_the_middle_of_the_top_line():
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])])

    # An odd width leaves the same room on both sides of the name.
    for width in (101, 121):
        top = Text.from_ansi(report_of(findings, width=width, terminal=True).splitlines()[1]).plain
        frame = len(top)
        name = " STATUS REPORT "
        assert top.index(name) == (frame - len(name)) // 2


def test_a_window_too_narrow_for_both_names_keeps_only_the_app_name():
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])])

    lines = report_of(findings, width=40, terminal=True).splitlines()

    assert "STATUS REPORT" not in lines[1]
    assert all(Text.from_ansi(line).cell_len <= 40 for line in lines)


def test_the_title_says_it_is_a_report_and_a_blank_line_comes_before_it():
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])])

    framed = report_of(findings, terminal=True)
    plain = report_of(findings)

    assert f"update-my-mac {__version__}" in Text.from_ansi(framed.splitlines()[1]).plain
    assert framed.startswith("\n")
    assert plain.startswith("\n")
    assert f"update-my-mac {__version__} report" in plain


def test_the_top_line_says_when_the_report_was_made(monkeypatch):
    monkeypatch.setattr(report.time, "time", lambda: time.mktime((2026, 10, 17, 14, 32, 0, 0, 0, -1)))
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])])

    top = Text.from_ansi(report_of(findings, width=100, terminal=True).splitlines()[1]).plain

    assert top.index(" STATUS REPORT ") < top.index(" 2026-10-17 14:32 ")
    # Two dashes between the time and the corner.
    assert top.endswith(" 2026-10-17 14:32 ──╮")


def test_a_window_with_no_room_for_the_time_leaves_it_off():
    findings = Findings(reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])])

    top = Text.from_ansi(report_of(findings, width=50, terminal=True).splitlines()[1]).plain

    assert " STATUS REPORT " in top
    assert ":" not in top


def test_every_mark_is_as_wide_for_rich_as_for_the_screen_it_is_scrolled_on():
    # A mark the two count differently leaves the frame's right edge a column off.
    from prompt_toolkit.utils import get_cwidth
    from rich.cells import cell_len

    for mark in report.MARK.values():
        assert cell_len(mark) == sum(get_cwidth(character) for character in mark), mark


def test_the_report_is_split_into_what_needs_attention_the_updates_and_the_info():
    from update_my_mac.managers.homebrew import flagged

    findings = Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  1 → 2"])],
        untracked=[InstalledApp("Evoto", "7.1.5", Path("/Applications/Evoto.app"))],
        flagged=[flagged.Flagged("old", flagged.DEPRECATED, installed="1")],
    )

    printed = report_of(findings, width=100, terminal=True)
    plain = Text.from_ansi(printed).plain

    assert plain.index("NEED ATTENTION 1") < plain.index("UPDATES AVAILABLE 1") < plain.index("INFO 1")
    assert "1 need attention · 1 update available · 1 info" in plain


def updates_report(width):
    packages = [f"package{n}  1.{n}.0 → 1.{n}.1" for n in range(5)]
    printed = report_of(Findings(reports=[ManagerReport("brew", "Homebrew", packages)]), width=width, terminal=True)
    return [Text.from_ansi(line).plain for line in printed.splitlines()]


def test_a_list_of_updates_is_split_into_two_columns_read_top_down_where_there_is_room():
    lines = updates_report(100)

    rows = [line for line in lines if "package" in line]
    assert [(row.count("package"), "package0" in row, "package3" in row) for row in rows] == [
        (2, True, True), (2, False, False), (1, False, False),
    ]
    assert "package1" in rows[1] and "package4" in rows[1]


def test_a_list_of_updates_stays_in_one_column_where_two_would_not_fit():
    lines = updates_report(40)

    assert all(line.count("package") <= 1 for line in lines)


def test_one_wide_entry_takes_room_only_in_its_own_column():
    # Measured across both columns these would need 99 cells; each column on its own, 63.
    packages = [
        "a  1 → 2", "b-very-long-name-xx  1 → 2",
        "c  2026-09-25 → 2026-10-20", "d  1 → 2",
    ]
    printed = report_of(Findings(reports=[ManagerReport("brew", "Homebrew", packages)]), width=70, terminal=True)

    rows = [Text.from_ansi(line).plain for line in printed.splitlines() if "→" in line]
    assert len(rows) == 2
