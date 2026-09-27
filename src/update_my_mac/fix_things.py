"""The question before the updates: shall we sort anything out first?

The run finds several kinds of trouble that are not updates at all, and asking
about each of them in turn is three questions too many. They are offered
together, and only the kinds that actually turned up.
"""

from dataclasses import dataclass

from update_my_mac.prompting import Step, Stopped

FIX_EVERYTHING = "yes, just fix everything, I trust you"
NOT_NOW = "No, I'm here for the updates (I'll take care of this next time)"
QUESTION = "[bold]Should we sort things out before updating?[/]"


@dataclass
class Problem:
    label: str
    walk_through: object
    fix_all: object


def run_fix_menu(problems, step=None, interactive=True):
    """Offer to deal with what turned up. Returns how many things were dealt with."""
    step = step or Step()
    if not problems or not interactive:
        return 0

    options = [(problem, problem.label) for problem in problems]
    options += [(FIX_EVERYTHING, FIX_EVERYTHING), (NOT_NOW, NOT_NOW)]

    dealt_with = 0
    try:
        while True:
            step.say()
            step.say(QUESTION)
            chosen = step.choose(options)

            if chosen == NOT_NOW:
                break
            if chosen == FIX_EVERYTHING:
                # Counted one at a time, so a Ctrl-C partway through does not
                # throw away what the earlier ones already did.
                for problem in problems:
                    dealt_with += problem.fix_all(step.inside())
                break
            dealt_with += chosen.walk_through(step.inside())
    except Stopped as stopped:
        step.say()
        dealt_with += stopped.done
    except KeyboardInterrupt:
        # A step that knows what it had done turns Ctrl-C into Stopped. One
        # that does not lets it through as itself.
        step.say()

    # However it ended, a line closes the phase so the update menu below is
    # not read as part of it.
    step.say()
    step.close_section()
    return dealt_with
