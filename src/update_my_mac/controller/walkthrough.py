"""The menus and flow shared by every group of things to sort out."""

from update_my_mac.view.prompting import WAY_OUT, Stopped

ALL, EACH, CANCEL = "all", "decide for each", "cancel"

CANCEL_ENTRY = (CANCEL, f"{WAY_OUT}cancel (back to main menu)")
CANCEL_WALK_ENTRY = (CANCEL, f"{WAY_OUT}cancel the walk-through")


def batch_or_walkthrough(step, things, all_label, do_all, walk):
    """Asks whether to handle the group at once, item by item, or not at all.

    Returns the items that were dealt with.
    """
    try:
        # Nothing to choose between: go straight to the single item(s).
        if len(things) == 1 or all_label is None:
            return walk(step.inside())
        chosen = step.choose([(ALL, all_label), (EACH, "decide for each"), CANCEL_ENTRY])
        if chosen == ALL:
            return do_all(step)
        if chosen == EACH:
            return walk(step.inside())
    except Stopped:
        step.print_empty_line()
    return []


def decide_for_each(things, step, choices, act_choice, act):
    """Asks about each thing and acts on those answered with act_choice. Returns the ones where it worked."""
    results = step.inside()
    dealt_with = []
    try:
        for thing in things:
            step.set_next_menu_apart()
            chosen = step.choose(
                options_for_single_item(choices, len(things) > 1), thing.title(), note=thing.comment()
            )
            if chosen == CANCEL:
                break
            if chosen == act_choice and act(thing, results):
                dealt_with.append(thing)
    except Stopped:
        step.print_empty_line()
    return dealt_with


def options_for_single_item(options, is_walkthrough):
    """Returns one thing's options, plus cancel when others are waiting."""
    return list(options) + ([CANCEL_WALK_ENTRY] if is_walkthrough else [])
