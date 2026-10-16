"""Offer package managers updates, before the checks."""

from dataclasses import dataclass, field
from update_my_mac import managers
from update_my_mac.controller.apply_updates import run_each_manager
from update_my_mac.view import output
from update_my_mac.view import prompting


@dataclass
class SelfUpdateResult:
    updated: list = field(default_factory=list)
    failed: list = field(default_factory=list)


def update_managers(managers_behind):
    """Offers to update the managers that are behind. Returns what was updated."""
    # A manager whose check failed is in the report, not in this offer.
    behind = [update for update in managers_behind if not update.error_message]
    if not _confirm_updates(behind):
        return SelfUpdateResult()
    return _update(behind)


def _confirm_updates(behind):
    """Returns whether the managers that are behind should be updated"""
    if not behind:
        return False

    named = ", ".join(update.label for update in behind)
    output.print_plain("\n", ("These package managers can be updated:", "yellow"), " ", named)
    output.console.print("[dim]Doing that first makes the rest of the check accurate.[/]")
    return _ask_yes_or_no()


def _ask_yes_or_no():
    step = prompting.Step()
    try:
        answer = step.yes_or_no("Update them now?")
    except prompting.Stopped:
        output.console.print("\nNothing updated.")
        answer = False
    output.console.print()
    return answer


def _update(picked):
    updated, failed = run_each_manager(
        [update.key for update in picked],
        "Updating", lambda manager, status: manager.upgrade_self(status),
    )
    _print_result(updated, failed)
    return SelfUpdateResult(updated, [key for key, _ in failed])


def _print_result(done, failed):
    if not done and not failed:
        return

    output.console.print()
    if done:
        names = ", ".join(managers.by_key(key).label for key in done)
        output.print_plain(("Updated", "green"), ": ", names)
    for key, why in failed:
        output.print_plain(f"{managers.by_key(key).label}: {why}", style="yellow")
