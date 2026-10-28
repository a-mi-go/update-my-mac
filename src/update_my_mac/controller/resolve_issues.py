"""Resolve issues interactively before updating."""

from dataclasses import dataclass

from update_my_mac.view import output
from update_my_mac.view.prompting import Markup, Step, Stopped

QUESTION = "Should we sort things out before updating?"
FIX_EVERYTHING = Markup("⎷ [bold]FIX EVERYTHING[/]......... I trust you !!! [red](use at your own risk)[/]")
NOT_NOW = Markup("↳ I'll take care of that later, lets go [bold]update[/]!")
NOT_NOW_COUNTED = "↳ I'll take care of that later, lets go [bold]update[/] ({})!"


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
            options = [(problem, problem.label) for problem in problems]
            options += [(FIX_EVERYTHING, FIX_EVERYTHING), (NOT_NOW, _not_now(updates))]

            # The first time it follows the report, which is divider enough.
            if asked_before:
                step.begin_menu()
            elif above is None:
                step.print_empty_line()
            asked_before = True
            chosen = step.choose(options, QUESTION, above=above)
            above = None

            if chosen == NOT_NOW:
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


def _not_now(updates):
    return NOT_NOW if updates is None else Markup(NOT_NOW_COUNTED.format(updates.count()))


def _print(above):
    if above is not None:
        output.print_above(above)
