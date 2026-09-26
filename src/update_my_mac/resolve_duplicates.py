"""Deciding which copy of a doubly installed command to keep.

Nothing here decides on its own. Both copies work, and which one is right
depends on what the person wants, so the only thing this does is lay out who
installed what and run the uninstall that was picked.
"""

from rich.markup import escape

from update_my_mac.prompting import Stopped, answer as _answer, printer as _printer


def run_duplicate_menu(duplicates, remove, ask=input, out=None, interactive=True):
    """Offer to drop one copy of each doubled command. Returns how many went."""
    console_print = _printer(out)
    if not duplicates or not interactive:
        return 0

    console_print()
    counted = "command" if len(duplicates) == 1 else "commands"
    console_print(f"Going through {len(duplicates)} {counted} that exist twice.")

    removed = 0
    try:
        for duplicate in duplicates:
            console_print()
            console_print(f"[bold]{escape(duplicate.command)}[/]")
            console_print(f"  runs now:   {escape(duplicate.winner.describe())}")
            for copy in duplicate.shadowed:
                console_print(f"  never used: {escape(copy.describe())}")

            for number, copy in enumerate(duplicate.copies, start=1):
                console_print(
                    f"  [bold cyan]{number})[/] remove the {escape(copy.manager)} one"
                )
            console_print(f"  [bold cyan]{len(duplicate.copies) + 1})[/] leave both")
            console_print(f"  [bold cyan]{len(duplicate.copies) + 2})[/] stop going through them")

            choice = _answer(ask, "> ")
            if choice == str(len(duplicate.copies) + 2):
                break
            if not choice.isdigit() or not 1 <= int(choice) <= len(duplicate.copies):
                continue

            if _remove_one(duplicate.copies[int(choice) - 1], remove, console_print):
                removed += 1
    except Stopped:
        console_print()

    return removed


def _remove_one(copy, remove, console_print):
    if not copy.remove_with:
        console_print("  [yellow]Nothing here says how that one was installed.[/]")
        return False

    console_print(f"\n[bold]Removing {escape(copy.package)}[/]")
    try:
        exit_code = remove(copy)
    except KeyboardInterrupt:
        console_print("\n[yellow]Stopped.[/]")
        raise Stopped

    if exit_code != 0:
        console_print(f"  [yellow]That exited with {exit_code}.[/]")
        return False
    return True
