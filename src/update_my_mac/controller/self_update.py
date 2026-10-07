"""The package managers renewing themselves, before anything is checked.

Homebrew answers every later check from the index it last fetched, and nothing
else in the run fetches one.
"""

from dataclasses import dataclass, field

from rich.console import Console
from rich.markup import escape

from update_my_mac import managers
from update_my_mac.controller.apply_updates import run_each_manager
from update_my_mac.view import keys
from update_my_mac.view import prompting


def _confirmed(console, ask):
    while True:
        try:
            said = _pick_yes_or_no(console, ask, "Update them now?")
        except KeyboardInterrupt:
            prompting.interrupted(console.print)
            continue
        except prompting.Stopped:
            console.print("\nNothing updated.")
            said = False
        else:
            prompting.answered()
        # A blank line, or the answer and what follows run together.
        console.print()
        return said

def _pick_yes_or_no(console, ask, question, default=False):
    if keys.available():
        try:
            return bool(keys.confirm(question, default=default))
        except keys.Unusable as failure:
            console.print(keys.unusable_message(failure))

    hint = "Y/n" if default else "y/N"
    while True:
        try:
            console.print(
                f"[cyan]{keys.QMARK}[/] [bold]{escape(question)}[/] \\[{hint}] ",
                end="",
                highlight=False,
            )
            answer = ask("").strip().lower()
        except EOFError:
            raise prompting.Stopped

        if answer == "":
            return default
        if answer in ("n", "no"):
            return False
        if answer in ("y", "yes"):
            return True
        console.print("[yellow]Didn't catch that.[/]")

@dataclass
class SelfUpdateResult:
    updated: list = field(default_factory=list)
    failed: list = field(default_factory=list)

def pick_managers(behind, console=None, ask=input):
    """Returns the managers to renew now, picked from the ones that are behind."""
    if not behind:
        return []

    console = console or Console()
    named = ", ".join(update.label for update in behind)
    console.print(f"\n[bold]The package managers can be updated[/]: {escape(named)}")
    console.print("[dim]Doing that first makes the rest of the check accurate.[/]")

    return list(behind) if _confirmed(console, ask) else []

def update(picked, shell, console=None):
    if not picked:
        return SelfUpdateResult()

    console = console or Console()
    updated, failed = run_each_manager(
        [update.key for update in picked], shell, console,
        "Updating", managers.upgrade_self,
    )
    say_what_happened(console, updated, failed)
    return SelfUpdateResult(updated, [key for key, _ in failed])

def say_what_happened(console, done, failed):
    """A closing word for a step that has nothing to count, like a self-update."""
    if not done and not failed:
        return

    console.print()
    if done:
        names = ", ".join(managers.by_key(key).label for key in done)
        console.print(f"[green]Updated[/]: {escape(names)}")
    for key, why in failed:
        console.print(f"[yellow]{escape(managers.by_key(key).label)}: {why}[/]")
