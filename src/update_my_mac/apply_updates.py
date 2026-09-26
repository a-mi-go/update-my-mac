"""Applying updates: the only module that changes the system."""

from dataclasses import dataclass, field

from rich.console import Console
from rich.markup import escape

from update_my_mac import package_managers, report

CANCEL = "cancel"
PACKAGES = "packages"
UNTRACKED_APPS = "untracked"
DOUBLED = "doubled"


@dataclass
class MenuEntry:
    kind: str
    label: str
    keys: list = field(default_factory=list)
    apps: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    # What was outdated when the menu was drawn, to compare against afterwards.
    outdated: list = field(default_factory=list)


def build_menu(reports, untracked_apps=(), duplicates=()):
    """One entry per manager with something outdated, then the apps.

    The managers themselves are not in here. They are dealt with before this
    menu, so that what it lists comes from tools that are already current.
    """
    entries = []
    for report in reports:
        if not report.outdated_packages:
            continue
        count = len(report.outdated_packages)
        counted_as = package_managers.by_key(report.manager).counted_as
        entries.append(
            MenuEntry(
                PACKAGES,
                f"{report.label} ({count} {counted_as if count != 1 else counted_as[:-1]})",
                [report.manager],
                outdated=list(report.outdated_packages),
            )
        )

    if untracked_apps:
        entries.append(
            MenuEntry(
                UNTRACKED_APPS,
                f"untracked apps ({len(untracked_apps)} to go through)",
                apps=list(untracked_apps),
            )
        )

    if duplicates:
        entries.append(
            MenuEntry(
                DOUBLED,
                f"apps installed twice ({len(duplicates)} to go through)",
                duplicates=list(duplicates),
            )
        )
    return entries


def parse_menu_answer(answer, entries):
    """Turn what was typed into the chosen entries, or CANCEL, or None.

    None means "didn't understand", which the caller turns into another prompt.
    Everything is always 1, the entries follow it, and Nothing sits last, so
    its number depends on how many entries there are.
    """
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
    # Numbers in cyan on purpose. Left to rich's highlighter they'd get the same
    # colour, but so would every bracket and number in a label.
    def option(number, text):
        console.print(f"  [bold cyan]{number})[/] {escape(text)}", highlight=False)

    console.print("\nWhat should be updated?")
    option(1, "Everything")
    for number, entry in enumerate(entries, start=2):
        option(number, entry.label)
    option(len(entries) + 2, "Nothing (Exit)")
    console.print("[dim]One number, or several separated by commas.[/]")


def _run_each(keys, shell, console, announce, run_one):
    """What went through, what went badly, and whether Ctrl-C ended the run.

    Ctrl-C reaches us as well as the command, since it runs in the foreground.
    It has to stop everything that was queued, not just the step it landed in.
    """
    done, failed = [], []
    for key in keys:
        manager = package_managers.by_key(key)
        console.print(f"\n[bold]{announce} {manager.label}[/]")
        try:
            exit_code = run_one(manager, shell)
        except KeyboardInterrupt:
            console.print(f"\n[yellow]Stopped during {manager.label}.[/]")
            return done, failed + [(key, "stopped")], True

        if exit_code != 0:
            console.print(f"[yellow]{manager.label} exited with {exit_code}[/]")
            failed.append((key, f"exited with {exit_code}"))
        else:
            done.append(key)
    return done, failed, False


def upgrade_managers_themselves(keys, shell, console):
    """Update the managers first, so the upgrades after them use current tools."""
    return _run_each(keys, shell, console, "Updating", package_managers.upgrade_self)


def upgrade_managers(keys, shell, console):
    """Upgrade each manager's packages in turn."""
    return _run_each(keys, shell, console, "Upgrading", package_managers.upgrade)


def run_manager_menu(manager_updates, shell, console=None, ask=input):
    """Offer to update the managers, before anything is checked against them."""
    if not manager_updates:
        return []

    console = console or Console()
    named = ", ".join(update.label for update in manager_updates)
    console.print(f"\n[bold]The package managers can be updated[/]: {escape(named)}")
    console.print("[dim]Doing that first makes the rest of the check accurate.[/]")

    while True:
        try:
            answer = ask("Update them now? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\nNothing updated.")
            return []

        if answer in ("", "n", "no"):
            return []
        if answer in ("y", "yes"):
            break
        console.print("[yellow]Didn't catch that.[/]")

    done, failed, _ = upgrade_managers_themselves(
        [update.key for update in manager_updates], shell, console
    )
    say_what_happened(console, done, failed)
    return [key for key, _ in failed]


def run_upgrade_menu(
    reports,
    shell,
    console=None,
    ask=input,
    untracked_apps=(),
    go_through_apps=None,
    duplicates=(),
    go_through_duplicates=None,
):
    """Offer the update and run what was chosen. Returns what failed."""
    console = console or Console()
    entries = build_menu(reports, untracked_apps, duplicates)
    if not entries:
        return []

    while True:
        print_menu(entries, console)
        try:
            answer = ask("> ")
        except (EOFError, KeyboardInterrupt):
            # No terminal, or Ctrl-C. Silence is not consent to upgrade.
            console.print("\nNothing updated.")
            return []

        chosen = parse_menu_answer(answer, entries)
        if chosen is None:
            console.print("[yellow]Didn't catch that.[/]")
            continue
        if chosen == CANCEL:
            return []
        return run_chosen(
            chosen,
            shell,
            console,
            ask,
            go_through_apps,
            go_through_duplicates,
        )


def say_what_happened(console, done, failed):
    """A closing word for a step that has nothing to count, like a self-update."""
    if not done and not failed:
        return

    console.print()
    if done:
        names = ", ".join(package_managers.by_key(key).label for key in done)
        console.print(f"[green]Updated[/]: {escape(names)}")
    for key, why in failed:
        console.print(f"[yellow]{escape(package_managers.by_key(key).label)}: {why}[/]")


def say_what_changed(console, entries, shell):
    """Ask each manager again, and report the difference.

    An upgrade writes straight to the terminal, so we never see what it did.
    Asking again afterwards is the only honest way to say what actually
    changed, and it is what answers the question a person really has: did the
    thing I wanted updated get updated?
    """
    console.print()
    for entry in entries:
        manager = package_managers.by_key(entry.keys[0])
        again = package_managers.check_for_outdated(manager, shell)
        if again is None or again.error_message:
            console.print(f"[yellow]{escape(manager.label)}: could not check again[/]")
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
        report.print_list(console, remaining)


def run_chosen(
    entries,
    shell,
    console,
    ask=input,
    go_through_apps=None,
    go_through_duplicates=None,
):
    # Questions before updates, so everything that needs an answer is over
    # before the first long-running command starts.
    for entry in entries:
        if entry.kind == UNTRACKED_APPS and go_through_apps is not None:
            go_through_apps(entry.apps, ask, console.print)
        elif entry.kind == DOUBLED and go_through_duplicates is not None:
            go_through_duplicates(entry.duplicates, ask, console.print)

    upgraded = [entry for entry in entries if entry.kind == PACKAGES]
    package_keys = [key for entry in upgraded for key in entry.keys]
    _, failed, stopped = upgrade_managers(package_keys, shell, console)
    if not stopped:
        say_what_changed(console, upgraded, shell)
    return [key for key, _ in failed]
