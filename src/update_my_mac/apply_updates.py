"""Applying updates: the only module that changes the system."""

from rich.console import Console

from update_my_mac import package_managers

CANCEL = "cancel"
EVERYTHING = "everything"


def upgradable_manager_keys(reports):
    return [report.manager for report in reports if report.outdated_packages]


def parse_menu_answer(answer, keys):
    """Turn what was typed into a manager key, EVERYTHING, CANCEL, or None.

    None means "didn't understand", which the caller turns into another prompt.
    """
    answer = answer.strip().lower()
    if answer in ("", "0", "c", "q", "cancel"):
        return CANCEL
    if answer in ("1", "a", "all"):
        return EVERYTHING

    if answer.isdigit():
        index = int(answer) - 2
        if 0 <= index < len(keys):
            return keys[index]
    return None


def print_menu(keys, console):
    console.print("\nWhat should be upgraded?")
    if len(keys) == 1:
        # "Everything" and the only candidate would be the same choice.
        console.print(f"  1) {package_managers.by_key(keys[0]).label}")
    else:
        console.print("  1) Everything")
        for number, key in enumerate(keys, start=2):
            console.print(f"  {number}) {package_managers.by_key(key).label}")
    console.print("  0) Cancel")


def upgrade_managers(keys, shell, console):
    """Upgrade each manager in turn, reporting any that exit badly."""
    for key in keys:
        manager = package_managers.by_key(key)
        console.print(f"\n[bold]Upgrading {manager.label}[/]")
        exit_code = package_managers.upgrade(manager, shell)
        if exit_code != 0:
            console.print(f"[yellow]{manager.label} exited with {exit_code}[/]")


def run_upgrade_menu(reports, shell, console=None, ask=input):
    """Offer the upgrade, then run whatever was chosen. Returns the keys used."""
    console = console or Console()
    keys = upgradable_manager_keys(reports)
    if not keys:
        return []

    while True:
        print_menu(keys, console)
        choice = parse_menu_answer(ask("> "), keys)
        if choice is None:
            console.print("[yellow]Didn't catch that.[/]")
            continue
        if choice == CANCEL:
            return []
        chosen = keys if choice == EVERYTHING else [choice]
        upgrade_managers(chosen, shell, console)
        return chosen
