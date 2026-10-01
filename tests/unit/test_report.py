from pathlib import Path

from rich.console import Console

from update_my_mac import __version__, app_updaters, appcast, report, sections
from update_my_mac.app_updaters import UpdaterStatus
from update_my_mac.installed_apps import InstalledApp
from update_my_mac.package_managers import ManagerReport, ManagerUpdate


def rendered(reports):
    console = Console(width=200, no_color=True, soft_wrap=True)
    with console.capture() as captured:
        report.print_outdated_summary(reports, console)
    return captured.get()


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


def test_untracked_apps_are_listed_with_their_versions():
    console = Console(width=200, no_color=True, soft_wrap=True)
    apps = [
        InstalledApp("TokenEater", "5.12.2", Path("/Applications/TokenEater.app")),
        InstalledApp("Some [beta] App", "1.0", Path("/Applications/Some [beta] App.app")),
    ]

    with console.capture() as captured:
        report.print_untracked_apps(apps, console)
    out = captured.get()

    assert "Not tracked by any package manager: 2" in out
    assert "TokenEater" in out
    assert "5.12.2" in out
    # Brackets in a name are text, not colour markup.
    assert "Some [beta] App" in out


def test_nothing_is_said_when_every_app_is_tracked():
    console = Console(width=200, no_color=True)
    with console.capture() as captured:
        report.print_untracked_apps([], console)

    assert captured.get() == ""


def test_the_managers_are_listed_before_anything_else(capsys):
    report.print_manager_updates(
        [
            ManagerUpdate("brew", "Homebrew", "index is 3 days old"),
            ManagerUpdate("npm", "npm (global)", "npm  12.0.2 → 12.1.0"),
        ],
        Console(width=200, no_color=True),
    )

    printed = capsys.readouterr().out
    assert "Package managers" in printed
    assert "Homebrew: index is 3 days old" in printed
    assert "npm (global): npm  12.0.2 → 12.1.0" in printed


def test_current_managers_are_said_to_be_current(capsys):
    report.print_manager_updates([], Console(width=200, no_color=True))

    assert "Package managers: up to date" in capsys.readouterr().out


def test_a_machine_with_no_managers_is_not_told_they_are_current(capsys):
    report.print_manager_updates([], Console(width=200, no_color=True), any_installed=False)

    assert capsys.readouterr().out == ""


def test_a_failed_manager_check_says_so(capsys):
    report.print_manager_updates(
        [ManagerUpdate("npm", "npm (global)", error_message="ENOTFOUND")],
        Console(width=200, no_color=True),
    )

    assert "check failed" in capsys.readouterr().out


def untracked(name, version, updater=None):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"),
                        updater or UpdaterStatus())


def test_untracked_apps_are_split_by_who_looks_after_them(capsys):
    report.print_untracked_apps(
        [
            untracked("Docker", "4.91.0"),
            untracked("Air", "262.579.44",
                      UpdaterStatus(app_updaters.SPARKLE, True, last_checked="2026-09-24")),
            untracked("Dockish", "1.1", UpdaterStatus(app_updaters.SPARKLE, None)),
        ],
        Console(width=200, no_color=True),
    )

    printed = capsys.readouterr().out
    assert "Not tracked by any package manager: 3" in printed
    assert "Possibly don't update at all: 1" in printed
    assert "They have an updater, nobody answered for it: 1" in printed
    assert "These update themselves: 1" in printed
    assert "Air" in printed
    assert "checks only, last checked 2026-09-24" in printed


def test_a_group_nobody_falls_into_is_not_printed(capsys):
    report.print_untracked_apps([untracked("Docker", "4.91.0")], Console(width=200, no_color=True))

    printed = capsys.readouterr().out
    assert "Possibly don't update at all: 1" in printed
    assert "update themselves" not in printed


def outdated(count):
    return [ManagerReport("brew", "Homebrew", [f"package-{n}" for n in range(count)])]


def test_a_short_list_stays_one_per_line(capsys):
    report.print_outdated_summary(outdated(5), Console(width=120, no_color=True))

    printed = capsys.readouterr().out
    assert "package-0" in printed.splitlines()[1]
    assert len([line for line in printed.splitlines() if "package-" in line]) == 5


def test_a_longer_list_goes_into_four_columns(capsys):
    report.print_outdated_summary(outdated(6), Console(width=120, no_color=True))

    rows = [line for line in capsys.readouterr().out.splitlines() if "package-" in line]
    assert len(rows) == 2
    assert rows[0].split() == ["package-0", "package-1", "package-2", "package-3"]
    assert rows[1].split() == ["package-4", "package-5"]


def test_a_long_list_of_apps_keeps_its_versions(capsys):
    # A version belongs next to the app it belongs to, however long the list.
    apps = [untracked(f"App{n}", "1.2.3") for n in range(6)]
    report.print_untracked_apps(apps, Console(width=120, no_color=True))

    printed = capsys.readouterr().out
    assert "App0" in printed
    assert printed.count("1.2.3") == 6


def test_a_short_list_of_apps_keeps_its_versions(capsys):
    report.print_untracked_apps(
        [untracked("Docker", "4.91.0")], Console(width=120, no_color=True)
    )

    printed = capsys.readouterr().out
    assert "Docker" in printed
    assert "4.91.0" in printed


BRACKETS = ["oops[/]", "[bold]weird[/bold]"]


def test_a_short_list_prints_brackets_as_text(capsys):
    report.print_outdated_summary(
        [ManagerReport("brew", "Homebrew", BRACKETS)], Console(width=120, no_color=True)
    )

    printed = capsys.readouterr().out
    assert "oops[/]" in printed
    assert "[bold]weird[/bold]" in printed


def test_the_columns_print_brackets_as_text(capsys):
    # As a plain string, "oops[/]" raised MarkupError and "[bold]x[/bold]"
    # vanished into styling, which is worse because nobody notices.
    packages = [f"package-{n}" for n in range(5)] + BRACKETS
    report.print_outdated_summary(
        [ManagerReport("brew", "Homebrew", packages)], Console(width=200, no_color=True)
    )

    printed = capsys.readouterr().out
    assert "oops[/]" in printed
    assert "[bold]weird[/bold]" in printed


def test_an_app_name_with_brackets_survives_the_columns(capsys):
    apps = [untracked(f"App{n}", "1.0") for n in range(5)] + [untracked("Foo [beta]", "2.0")]
    report.print_untracked_apps(apps, Console(width=200, no_color=True))

    assert "Foo [beta]" in capsys.readouterr().out


def test_a_switched_off_updater_is_not_called_unknown(capsys):
    # "Switched off" is a claim; "nobody answered" is the absence of one.
    report.print_untracked_apps(
        [
            untracked("Off", "1.0", UpdaterStatus(app_updaters.SPARKLE, False)),
            untracked("Unanswered", "1.0", UpdaterStatus(app_updaters.SPARKLE, None)),
        ],
        Console(width=200, no_color=True),
    )

    printed = capsys.readouterr().out
    assert "Their updater is switched off: 1" in printed
    assert "They have an updater, nobody answered for it: 1" in printed


def test_apps_owned_by_someone_else_come_with_a_way_out(capsys):
    report.print_foreign_owners(
        [Path("/Applications/Firefox.app"), Path("/Applications/Disk Drill.app")],
        Console(width=120, no_color=True),
    )

    printed = capsys.readouterr().out
    assert "Owned by another user: 2" in printed
    assert "Firefox.app" in printed
    assert 'sudo chown -R $(id -un) "/Applications/Firefox.app"' in printed


def test_nothing_is_printed_when_every_app_is_mine(capsys):
    report.print_foreign_owners([], Console(width=120, no_color=True))

    assert capsys.readouterr().out == ""


def test_a_manager_says_when_it_left_something_out(capsys):
    reports = [ManagerReport("brew", "Homebrew", [], ignored_taps=["anomalyco/tap", "clerk/stable"])]
    report.print_outdated_summary(reports, Console(width=120, no_color=True))

    printed = capsys.readouterr().out
    assert "Nothing from anomalyco/tap, clerk/stable was checked" in printed


def printed_list(items, width=100):
    console = Console(width=width, no_color=True)
    with console.capture() as captured:
        report.print_as_list_or_grid(console, "    ", items)
    return [line.rstrip() for line in captured.get().splitlines()]


def test_names_alone_take_one_column():
    lines = printed_list([report.Item("aom"), report.Item("cairo")])

    assert lines == ["    aom", "    cairo"]


def test_versions_line_up_under_each_other():
    lines = printed_list([report.Item("aom", "1.0"), report.Item("ca-certificates", "2026")])

    assert lines[0].index("1.0") == lines[1].index("2026")


def test_a_comment_gets_a_column_of_its_own():
    lines = printed_list([
        report.Item("Air", "262.5", "checks only"),
        report.Item("Dockish", "1.1", "never answered"),
    ])

    assert lines[0].index("checks only") == lines[1].index("never answered")


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


def test_a_long_list_of_bare_names_goes_into_four_columns():
    lines = printed_list([report.Item(f"app-{n}") for n in range(6)])

    assert len(lines) == 2
    assert lines[0].split() == ["app-0", "app-1", "app-2", "app-3"]


def test_a_long_list_with_versions_stays_one_per_line():
    items = [report.Item(f"app-{n}", f"1.{n}") for n in range(6)]
    lines = printed_list(items)

    assert len(lines) == 6
    assert lines[0].split() == ["app-0", "1.0"]


def test_an_empty_list_prints_nothing():
    assert printed_list([]) == []


def with_feed(name, version, url="https://x.test/appcast.xml"):
    return InstalledApp(
        name, version, Path(f"/Applications/{name}.app"),
        UpdaterStatus(app_updaters.SPARKLE, True, False, "2026-08-16", url),
    )


def test_an_app_whose_feed_went_quiet_is_listed_once(capsys):
    # By what it does now, not by what its settings still claim it does.
    url = "https://x.test/appcast.xml"
    report.print_untracked_apps(
        [with_feed("Air", "262.579.44", url)],
        Console(width=200, no_color=True),
        offered={url: appcast.FeedAnswer(error="its feed answers 403")},
    )

    printed = capsys.readouterr().out
    assert "Cannot update themselves any more: 1" in printed
    assert "its feed answers 403" in printed
    assert "These update themselves" not in printed


def report_of(findings, width=80, terminal=False):
    console = Console(width=width, no_color=True, force_terminal=terminal or None)
    with console.capture() as captured:
        report.print_report(findings, console)
    return captured.get()


def test_the_report_is_framed_for_someone_watching():
    findings = sections.Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])]
    )

    framed = report_of(findings, terminal=True)

    assert "update-my-mac" in framed
    assert "╭" in framed
    assert "1 need your attention, 0 can wait" in framed


def test_a_run_without_a_frame_still_says_what_wrote_it():
    findings = sections.Findings(reports=[ManagerReport("brew", "Homebrew", [])])

    assert f"update-my-mac {__version__}" in report_of(findings)


def test_the_frame_is_left_off_when_the_output_is_going_somewhere_else():
    # Every line would start with a border, which is only in the way in a
    # pipe or a log.
    findings = sections.Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])]
    )

    plain = report_of(findings)

    assert "╭" not in plain
    assert "│" not in plain
    # The count the frame would have carried is said in words instead.
    assert "1 need your attention, 0 can wait" in plain


def test_a_clean_run_says_which_managers_answered():
    # Silence about a manager reads as "not checked".
    findings = sections.Findings(reports=[
        ManagerReport("brew", "Homebrew", []),
        ManagerReport("mas", "Mac App Store", []),
    ])

    printed = report_of(findings)

    assert "Everything is up to date." in printed
    assert "up to date: Homebrew, Mac App Store" in printed


def test_a_machine_with_no_managers_is_not_told_everything_is_fine():
    printed = report_of(sections.Findings(any_manager_installed=False))

    assert "No supported package managers found." in printed
    assert "Everything is up to date" not in printed


def test_a_section_says_how_many_and_why_it_is_there():
    findings = sections.Findings(
        reports=[ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"])]
    )

    heading = next(line for line in report_of(findings).splitlines() if "Mac App Store" in line)

    assert "Mac App Store 1" in heading
    assert "one menu answer away" in heading


def test_a_reason_that_would_not_fit_is_left_off_rather_than_wrapped():
    findings = sections.Findings(
        reports=[ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"])]
    )

    printed = report_of(findings, width=40)

    assert "Mac App Store 1" in printed
    assert "one menu answer away" not in printed


def test_the_managers_that_are_current_are_said_so_in_green():
    findings = sections.Findings(reports=[ManagerReport("brew", "Homebrew", [])])
    console = Console(width=80, force_terminal=True)
    with console.capture() as captured:
        report.print_report(findings, console)

    printed = captured.get()
    assert "✅" in printed
    # 32 is green, and this line is the only thing wearing it.
    assert "\x1b[32mup to date: Homebrew" in printed
