"""Deciding which copy of a doubly installed command to keep.

Both copies work, so this only lays out who installed what and runs the
uninstall that was picked.
"""

from update_my_mac.system import shell
from update_my_mac.system.shell import describe_exit
from update_my_mac.controller import walkthrough
from update_my_mac.controller.walkthrough import CANCEL
from update_my_mac.view.prompting import Step, Stopped

KEEP_BOTH = "keep both"


def ask_what_to_do(duplicates, step=None):
    """Offers to drop one copy of each doubled command. Returns the ones that lost a copy."""
    step = step or Step()
    if not duplicates:
        return []

    return walkthrough.batch_or_walkthrough(
        step, duplicates, "remove every copy that never runs",
        lambda step: remove_shadowed(duplicates, step),
        lambda step: _walk_through(duplicates, step),
    )


def remove_shadowed(duplicates, step):
    """Removes the copies PATH never reaches. Returns the commands that lost one."""
    per_item = step.inside()
    resolved = []
    for duplicate in duplicates:
        removed = False
        for copy in duplicate.shadowed:
            per_item.print_empty_line()
            per_item.print_indented(duplicate.command, style="bold")
            removed = _remove_one(copy, per_item.inside()) or removed
        if removed:
            resolved.append(duplicate)
    return resolved


def _walk_through(duplicates, step):
    """Asks about each doubled command in turn. Returns the ones that lost a copy."""
    results = step.inside()
    resolved = []
    try:
        for duplicate in duplicates:
            step.begin_menu()
            chosen = step.choose(
                _copy_choices(duplicate, len(duplicates) > 1),
                duplicate.command,
                note=_what_runs(duplicate),
            )
            if chosen == CANCEL:
                break
            if chosen != KEEP_BOTH and _remove_one(chosen, results):
                resolved.append(duplicate)
    except Stopped:
        step.print_empty_line()
    return resolved


def _copy_choices(duplicate, is_walkthrough):
    """Returns the copies as options, each carrying the copy it stands for."""
    return walkthrough.options_for_single_item(
        [(copy, f"remove the {copy.manager} one") for copy in duplicate.copies]
        + [(KEEP_BOTH, "leave both")],
        is_walkthrough,
    )


def _what_runs(duplicate):
    """Returns which copy PATH reaches and which ones it never does."""
    return "\n".join(
        [f"runs now:   {duplicate.winner.describe()}"]
        + [f"never used: {copy.describe()}" for copy in duplicate.shadowed]
    )


def _remove_one(copy, step):
    if not copy.remove_with:
        step.print_indented("Nothing here says how that one was installed.", style="yellow")
        return False

    step.print_indented(f"Removing {copy.package}")
    exit_code = _remove(copy)

    if exit_code != 0:
        step.print_indented(f"That {describe_exit(exit_code)}.", style="yellow")
        return False
    return True


def _remove(copy):
    executable = shell.find_executable(copy.remove_with[0])
    if executable is None:
        return None
    return shell.stream_command([executable, *copy.remove_with[1:]])
