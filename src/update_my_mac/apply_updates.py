"""Applying updates: the only module that changes the system."""

from rich.console import Console
from rich.markup import escape

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
    # Numbers in cyan on purpose. Left to rich's highlighter they'd get the same
    # colour, but so would every bracket and number in a label.
    def option(number, text):
        console.print(f"  [bold cyan]{number})[/] {escape(text)}", highlight=False)

    console.print("\nWhat should be upgraded?")
    if len(keys) == 1:
        # "Everything" and the only candidate would be the same choice.
        option(1, package_managers.by_key(keys[0]).label)
    else:
        option(1, "Everything")
        for number, key in enumerate(keys, start=2):
            option(number, package_managers.by_key(key).label)
    option(0, "Cancel")


def upgrade_managers(keys, shell, console):
    """Upgrade each manager in turn. Returns the ones that exited badly."""
    failed = []
    for key in keys:
        manager = package_managers.by_key(key)
        console.print(f"\n[bold]Upgrading {manager.label}[/]")
        try:
            exit_code = package_managers.upgrade(manager, shell)
        except KeyboardInterrupt:
            # Ctrl-C reaches us as well as the command, since it runs in the
            # foreground. Stop here rather than starting the next upgrade.
            console.print(f"\n[yellow]Stopped during {manager.label}.[/]")
            failed.append(key)
            return failed

        if exit_code != 0:
            console.print(f"[yellow]{manager.label} exited with {exit_code}[/]")
            failed.append(key)
    return failed


def run_upgrade_menu(reports, shell, console=None, ask=input):
    """Offer the upgrade and run what was chosen. Returns the managers that failed."""
    console = console or Console()
    keys = upgradable_manager_keys(reports)
    if not keys:
        return []

    while True:
        print_menu(keys, console)
        try:
            answer = ask("> ")
        except (EOFError, KeyboardInterrupt):
            # No terminal, or Ctrl-C. Silence is not consent to upgrade.
            console.print("\nNothing upgraded.")
            return []

        choice = parse_menu_answer(answer, keys)
        if choice is None:
            console.print("[yellow]Didn't catch that.[/]")
            continue
        if choice == CANCEL:
            return []
        chosen = keys if choice == EVERYTHING else [choice]
        return upgrade_managers(chosen, shell, console)
