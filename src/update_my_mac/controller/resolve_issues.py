"""Resolve issues interactively before updating."""

from dataclasses import dataclass

from update_my_mac.view.prompting import Markup, Step, Stopped

QUESTION = "Should we sort things out before updating?"
FIX_EVERYTHING = Markup("⎷ [bold]FIX EVERYTHING[/]......... I trust you !!! [red](use at your own risk)[/]")
NOT_NOW = Markup("↳ I'll take care of that later, lets go [bold]update[/]!")


@dataclass
class Problem:
    label: str
    walk_through: object
    fix_all: object
    # Called before the menu is drawn: updates the label and says whether
    # anything is left to deal with.
    refresh: object = None


def ask_what_to_fix(problems, step=None):
    """Offers to deal with what turned up. Returns how many issues were dealt with."""
    step = step or Step()
    if not problems:
        return 0

    dealt_with = 0
    asked_before = False
    try:
        while True:
            problems = [one for one in problems if one.refresh is None or one.refresh(one)]
            if not problems:
                break
            options = [(problem, problem.label) for problem in problems]
            options += [(FIX_EVERYTHING, FIX_EVERYTHING), (NOT_NOW, NOT_NOW)]

            # The first time it follows the report, which is divider enough.
            step.begin_menu() if asked_before else step.print_empty_line()
            asked_before = True
            chosen = step.choose(options, QUESTION)

            if chosen == NOT_NOW:
                break
            if chosen == FIX_EVERYTHING:
                for problem in problems:
                    dealt_with += problem.fix_all(step.inside())
                break
            dealt_with += chosen.walk_through(step.inside())
    except Stopped:
        step.print_empty_line()

    return dealt_with
