"""Applying updates: the only module that changes the system."""

from dataclasses import dataclass, field

from rich.console import Console
from rich.markup import escape

from update_my_mac.view import keys
from update_my_mac import managers
from update_my_mac.view import prompting
from update_my_mac.view import report

CANCEL = "cancel"
PACKAGES = "packages"


@dataclass
class MenuEntry:
    kind: str
    label: str
    keys: list = field(default_factory=list)
    # What was outdated when the menu was drawn, to compare against afterwards.
    outdated: list = field(default_factory=list)


def build_menu(reports):
    entries = []
    for report in reports:
        if not report.outdated_packages:
            continue
        count = len(report.outdated_packages)
        counted_as = managers.by_key(report.manager).counted_as
        entries.append(
            MenuEntry(
                PACKAGES,
                f"{report.label} ({count} {counted_as if count != 1 else counted_as[:-1]})",
                [report.manager],
                outdated=list(report.outdated_packages),
            )
        )

    return entries


def parse_menu_answer(answer, entries):
    """Returns the chosen entries, or CANCEL, or None when the answer made no sense."""
    answer = answer.strip().lower()
    if answer in ("", "q", "c", "cancel", "exit", "0"):
        return CANCEL

    # Every part has to make sense before any of it counts, otherwise
    # "1,garbage" would quietly pass as "everything".
    numbers = []
    for part in answer.split(","):
        part = part.strip()
        if not part.isdigit():
            return None
        numbers.append(int(part))

    nothing = len(entries) + 2
    if nothing in numbers:
        return CANCEL
    if any(not 1 <= number <= len(entries) + 1 for number in numbers):
        return None
    if 1 in numbers:
        return list(entries)

    chosen = []
    for number in numbers:
        entry = entries[number - 2]
        if entry not in chosen:
            chosen.append(entry)
    return chosen or None


def print_menu(entries, console):
    console.print("\nWhat should be updated?")
    labels = ["Everything"] + [entry.label for entry in entries] + ["Nothing (Exit)"]
    for number, label in enumerate(labels, start=1):
        console.print(f"  [bold cyan]{number})[/] {escape(label)}", highlight=False)
    console.print("[dim]One number, or several separated by commas.[/]")


def pick_what_to_update(entries, pick=keys.pick_several):
    """Returns the entries that were picked, or CANCEL."""
    picked = pick("What should be updated?", [(entry, entry.label) for entry in entries])
    return picked or CANCEL


def run_each_manager(manager_keys, shell, console, announce, run_one):
    done, failed = [], []
    for key in manager_keys:
        manager = managers.by_key(key)
        console.print(f"\n[bold]{announce} {manager.label}[/]")
        exit_code = run_one(manager, shell)
        if exit_code != 0:
            console.print(f"[yellow]{manager.label} exited with {exit_code}[/]")
            failed.append((key, f"exited with {exit_code}"))
        else:
            done.append(key)
    return done, failed


def upgrade_managers(manager_keys, shell, console):
    return run_each_manager(manager_keys, shell, console, "Upgrading", managers.upgrade)


def ask_what_to_update(reports, shell, console=None, ask=input):
    console = console or Console()
    entries = build_menu(reports)
    if not entries:
        return []

    if keys.available():
        while True:
            try:
                chosen = pick_what_to_update(entries)
            except KeyboardInterrupt:
                prompting.interrupted(console.print)
                continue
            except keys.Unusable as failure:
                console.print(keys.unusable_message(failure))
                break  # out of this loop only: the numbered menu below takes over
            prompting.answered()
            return [] if chosen == CANCEL else run_chosen(chosen, shell, console)

    while True:
        print_menu(entries, console)
        try:
            answer = ask("> ")
        except EOFError:
            # No more input. Silence is not consent to upgrade.
            console.print("\nNothing updated.")
            return []

        chosen = parse_menu_answer(answer, entries)
        if chosen is None:
            console.print("[yellow]Didn't catch that.[/]")
            continue
        if chosen == CANCEL:
            return []
        return run_chosen(chosen, shell, console)


def say_what_changed(console, entries, shell):
    """Returns the managers that could not be asked again."""
    # Asked again rather than taken from the upgrade's own output: a manager
    # can report success and still leave a package where it was.
    console.print()
    could_not_confirm = []
    for entry in entries:
        manager = managers.by_key(entry.keys[0])
        again = managers.check_for_outdated(manager, shell)
        if again is None or again.error_message:
            console.print(f"[yellow]{escape(manager.label)}: could not check again[/]")
            could_not_confirm.append(manager.key)
            continue

        remaining = again.outdated_packages
        updated = max(0, len(entry.outdated) - len(remaining))
        if not remaining:
            console.print(f"[green]{escape(manager.label)}[/]: {len(entry.outdated)} updated")
            continue

        console.print(
            f"[yellow]{escape(manager.label)}[/]: {updated} of {len(entry.outdated)} updated, "
            f"still outdated:"
        )
        report.print_as_list_or_grid(
            console, "    ", [report.Item(package) for package in remaining]
        )
    return could_not_confirm


def run_chosen(entries, shell, console):
    upgraded = [entry for entry in entries if entry.kind == PACKAGES]
    package_keys = [key for entry in upgraded for key in entry.keys]
    _, failed = upgrade_managers(package_keys, shell, console)
    could_not_confirm = say_what_changed(console, upgraded, shell)
    return [key for key, _ in failed] + could_not_confirm
