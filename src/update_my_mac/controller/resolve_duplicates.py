"""Deciding which copy of a doubly installed command to keep.

Both copies work, so this only lays out who installed what and runs the
uninstall that was picked.
"""

from rich.markup import escape

from update_my_mac.view.prompting import Step, Stopped

REMOVE_SHADOWED, DECIDE_FOR_EACH, NOTHING = "shadowed", "decide for each", "nothing"
KEEP_BOTH, CANCEL = "keep both", "cancel"

CHOICES = (
    (REMOVE_SHADOWED, "remove every copy that never runs"),
    (DECIDE_FOR_EACH, "decide for each"),
    (NOTHING, "nothing (move on to the next step)"),
)


def ask_what_to_do(duplicates, remove, step=None, interactive=True):
    """Offer to drop one copy of each doubled command. Returns how many went."""
    step = step or Step()
    if not duplicates or not interactive:
        return 0

    step.say()
    try:
        chosen = step.choose(CHOICES, "[bold]What should we do with them?[/]")
        if chosen == REMOVE_SHADOWED:
            return remove_shadowed(duplicates, remove, step)
        if chosen == DECIDE_FOR_EACH:
            return _walk_through(duplicates, remove, step.inside())
    except Stopped:
        step.say()
    return 0


def remove_shadowed(duplicates, remove, step):
    """Remove the copies PATH never reaches. Returns how many were removed."""
    each = step.inside()
    removed = 0
    for duplicate in duplicates:
        for copy in duplicate.shadowed:
            each.say()
            each.say(f"[bold]{escape(duplicate.command)}[/]")
            if _remove_one(copy, remove, each.inside()):
                removed += 1
    return removed


def _walk_through(duplicates, remove, step):
    """Ask about each doubled command in turn. Returns how many copies went.

    Ctrl-C ends the walk here, so a removal that already ran still counts.
    """
    said = step.inside()
    removed = 0
    try:
        for duplicate in duplicates:
            step.say()
            step.say(f"[bold]{escape(duplicate.command)}[/]")
            said.say(f"runs now:   {escape(duplicate.winner.describe())}")
            for copy in duplicate.shadowed:
                said.say(f"never used: {escape(copy.describe())}")

            chosen = step.choose(_copy_choices(duplicate), "[bold]What should we do with it?[/]")
            if chosen == CANCEL:
                break
            if chosen == KEEP_BOTH:
                continue
            if _remove_one(chosen, remove, said):
                removed += 1
    except Stopped:
        step.say()
    return removed


def _copy_choices(duplicate):
    """The copies as options, so what is picked is a copy and not a number."""
    return [
        (copy, f"remove the {copy.manager} one")
        for copy in duplicate.copies
    ] + [
        (KEEP_BOTH, "leave both"),
        (CANCEL, "cancel the walk-through"),
    ]


def _remove_one(copy, remove, step):
    if not copy.remove_with:
        step.say("[yellow]Nothing here says how that one was installed.[/]")
        return False

    step.say(f"Removing {escape(copy.package)}")
    exit_code = remove(copy)

    if exit_code != 0:
        step.say(f"[yellow]That exited with {exit_code}.[/]")
        return False
    return True
