"""Applying updates: the only module that changes the system."""

from dataclasses import dataclass, field

from rich.console import Console
from rich.markup import escape

from update_my_mac import package_managers, report
from update_my_mac import keys
from update_my_mac import prompting

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
    """One entry per manager with something outdated, then the apps."""
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

    return entries


def parse_menu_answer(answer, entries):
    """The chosen entries, or CANCEL, or None when the answer made no sense."""
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


def _updates_confirmed(console, ask):
    while True:
        try:
            said = _confirm_updates(console, ask)
        except KeyboardInterrupt:
            prompting.interrupted(console.print)
            continue
        prompting.answered()
        # A blank line, or the answer and what follows run together.
        console.print()
        return said


def _confirm_updates(console, ask):
    if keys.available():
        try:
            return bool(keys.confirm("Update them now?"))
        except keys.Unusable as failure:
            console.print(keys.unusable_message(failure))

    while True:
        try:
            # highlight=False, or rich prints the brackets bold.
            console.print(
                f"[cyan]{keys.QMARK}[/] [bold]Update them now?[/] \\[y/N] ",
                end="",
                highlight=False,
            )
            answer = ask("").strip().lower()
        except EOFError:
            console.print("\nNothing updated.")
            return False

        if answer in ("", "n", "no"):
            return False
        if answer in ("y", "yes"):
            return True
        console.print("[yellow]Didn't catch that.[/]")


def choose_what_to_update(entries, pick=keys.pick_several):
    """A multiple choice: the entries that were picked, or CANCEL."""
    picked = pick("What should be updated?", [(entry, entry.label) for entry in entries])
    return picked or CANCEL


def _run_each_manager(manager_keys, shell, console, announce, run_one):
    """What went through and what went badly."""
    done, failed = [], []
    for key in manager_keys:
        manager = package_managers.by_key(key)
        console.print(f"\n[bold]{announce} {manager.label}[/]")
        exit_code = run_one(manager, shell)
        if exit_code != 0:
            console.print(f"[yellow]{manager.label} exited with {exit_code}[/]")
            failed.append((key, f"exited with {exit_code}"))
        else:
            done.append(key)
    return done, failed


def upgrade_managers_themselves(manager_keys, shell, console):
    """Update the managers first, so the upgrades after them use current tools."""
    return _run_each_manager(manager_keys, shell, console, "Updating", package_managers.upgrade_self)


def upgrade_managers(manager_keys, shell, console):
    """Upgrade each manager's packages in turn."""
    return _run_each_manager(manager_keys, shell, console, "Upgrading", package_managers.upgrade)


def run_manager_menu(manager_updates, shell, console=None, ask=input):
    """Offer to update the managers, before anything is checked against them."""
    if not manager_updates:
        return []

    console = console or Console()
    named = ", ".join(update.label for update in manager_updates)
    console.print(f"\n[bold]The package managers can be updated[/]: {escape(named)}")
    console.print("[dim]Doing that first makes the rest of the check accurate.[/]")

    if not _updates_confirmed(console, ask):
        return []

    done, failed = upgrade_managers_themselves(
        [update.key for update in manager_updates], shell, console
    )
    say_what_happened(console, done, failed)
    return [key for key, _ in failed]


def run_upgrade_menu(reports, shell, console=None, ask=input):
    """Offer the update and run what was chosen. Returns what failed."""
    console = console or Console()
    entries = build_menu(reports)
    if not entries:
        return []

    if keys.available():
        while True:
            try:
                chosen = choose_what_to_update(entries)
            except KeyboardInterrupt:
                prompting.interrupted(console.print)
                continue
            except keys.Unusable as failure:
                console.print(keys.unusable_message(failure))
                break
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

    An upgrade writes straight to the terminal, so asking again is the only
    way to know what it did.
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
        report.print_as_list_or_grid(
            console, "    ", [report.Item(package) for package in remaining]
        )


def run_chosen(entries, shell, console):
    upgraded = [entry for entry in entries if entry.kind == PACKAGES]
    package_keys = [key for entry in upgraded for key in entry.keys]
    _, failed = upgrade_managers(package_keys, shell, console)
    say_what_changed(console, upgraded, shell)
    return [key for key, _ in failed]
