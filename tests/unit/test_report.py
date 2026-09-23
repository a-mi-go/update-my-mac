from pathlib import Path

from rich.console import Console

from update_my_mac import report
from update_my_mac.installed_apps import InstalledApp
from update_my_mac.package_managers import ManagerReport


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
    assert "pkg [beta]  1.0 → 2.0" in out


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
    assert "TokenEater  5.12.2" in out
    # Brackets in a name are text, not colour markup.
    assert "Some [beta] App  1.0" in out


def test_nothing_is_said_when_every_app_is_tracked():
    console = Console(width=200, no_color=True)
    with console.capture() as captured:
        report.print_untracked_apps([], console)

    assert captured.get() == ""
