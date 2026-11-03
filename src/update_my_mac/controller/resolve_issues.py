"""Resolve issues interactively before updating."""

from dataclasses import dataclass

from update_my_mac.view import output
from update_my_mac.view.prompting import WAY_OUT, Markup, Step, Stopped

QUESTION = "Should we sort things out before updating?"
QUESTION_WITHOUT_UPDATES = "Nothing to update, but should we sort some things out?"
FIX_EVERYTHING = Markup("⎷ [bold]FIX EVERYTHING[/]......... I trust you !!! [red](use at your own risk)[/]")
NOT_NOW = Markup("↳ I'll take care of that later, lets go [bold]update[/]")
NOT_NOW_COUNTED = "↳ I'll take care of that later, lets go [bold]update[/] ({})"
NOT_NOW_NAMED = "↳ I'll take care of that later, [bold]update[/] {} ({})"
EXIT = f"{WAY_OUT}Exit"


@dataclass
class Problem:
    label: str
    walk_through: object
    fix_all: object
    # Called before the menu is drawn: updates the label and says whether
    # anything is left to deal with.
    refresh: object = None


def ask_what_to_fix(problems, step=None, above=None, updates=None):
    """Offers to deal with what turned up, with `above` printed over the first menu. Returns how many were dealt with."""
    step = step or Step()
    if not problems:
        _print(above)
        return 0

    dealt_with = 0
    asked_before = False
    try:
        while True:
            problems = [one for one in problems if one.refresh is None or one.refresh(one)]
            if not problems:
                break
            nothing_to_update = updates is not None and updates.count() == 0
            options = _options(problems, updates, nothing_to_update)

            # The first time it follows the report, which is divider enough.
            if asked_before:
                step.set_next_menu_apart()
            elif above is None:
                step.print_empty_line()
            asked_before = True
            chosen = step.choose(options, QUESTION_WITHOUT_UPDATES if nothing_to_update else QUESTION, above=above)
            above = output.already_printed(above)

            if chosen == NOT_NOW:
                if updates is not None and not nothing_to_update:
                    updates.skip_to_updating()
                break
            before = dealt_with
            if chosen == FIX_EVERYTHING:
                for problem in problems:
                    dealt_with += problem.fix_all(step.inside())
            else:
                dealt_with += chosen.walk_through(step.inside())
            if updates is not None and dealt_with > before:
                updates.something_changed()
            if chosen == FIX_EVERYTHING:
                break
    except Stopped:
        step.print_empty_line()

    _print(above)
    return dealt_with


def _options(problems, updates, nothing_to_update):
    options = [(problem, problem.label) for problem in problems]
    if len(problems) > 1:
        options.append((FIX_EVERYTHING, FIX_EVERYTHING))
    options.append((NOT_NOW, EXIT if nothing_to_update else _not_now(updates)))
    return options


def _not_now(updates):
    if updates is None:
        return NOT_NOW
    what = updates.what_the_only_manager_updates()
    if what is not None:
        return Markup(NOT_NOW_NAMED.format(what, updates.count()))
    return Markup(NOT_NOW_COUNTED.format(updates.count()))


def _print(above):
    if above is not None and not output.is_already_printed(above):
        output.print_above(above)
