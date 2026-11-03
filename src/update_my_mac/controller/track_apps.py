"""Going through the apps no package manager tracks, and revisiting that later."""


from update_my_mac.managers.homebrew import adopting
from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.controller import walkthrough
from update_my_mac.system import shell
from update_my_mac.controller.walkthrough import CANCEL
from update_my_mac.view import prompting
from update_my_mac.view import report
from update_my_mac.view.prompting import Step, Stopped

ADOPT, WEBSITE, LAUNCH = "adopt", "website", "launch"
IGNORE, LATER, TRASH = "ignore", "later", "trash"


def ask_what_to_do(
    apps,
    decisions,
    step=None,
    find_cask=None,
    offered=None,
):
    """Asks about the untracked apps. Returns the ones that were ignored or handed over."""
    step = step or Step()
    waiting = [app for app in apps if not decisions.is_ignored(app.file_stem)]
    if not waiting:
        return []

    found = [(app, find_cask(app) if find_cask else None) for app in waiting]
    return walkthrough.batch_or_walkthrough(
        step, found, _adopt_all_label(found),
        lambda step: adopt_all(found, step),
        lambda step: _walk_through(found, decisions, offered or {}, step),
    )


def known_to_homebrew(found):
    """Returns how many of the (app, cask) pairs Homebrew has a recipe for."""
    return sum(1 for app, cask in found if adopting.has_a_recipe(cask))


def ready_for_homebrew(found):
    """Returns how many the bulk step would hand over to Homebrew."""
    return sum(1 for app, cask in found if adopting.can_join_the_bulk_takeover(app, cask))


def adopt_all(found, step):
    """Hands over to Homebrew every app that fits the bulk step. Returns the ones it took."""
    per_item = step.inside()
    adopted = []
    for app, cask in found:
        if not adopting.can_join_the_bulk_takeover(app, cask):
            continue
        per_item.print_empty_line()
        per_item.print_indented(app.display_name, style="bold")
        if _take_over_with_homebrew(app, cask, per_item.inside()):
            adopted.append(app)
    return adopted


def ask_about_the_ignored(decisions, step=None):
    """Brings an app back into the list. Returns how many came back."""
    step = step or Step()
    names = decisions.ignored_names()

    if not names:
        step.print_indented("No apps are being left alone.")
        return 0

    step.print_indented("Apps being left alone:")
    listed_items = step.inside()
    for number, name in enumerate(names, start=1):
        listed_items.print_indented((f"{number})", "cyan"), " ", name)
    listed_items.print_indented(("0)", "cyan"), " none of them")

    try:
        answer = step.read("List one of them again? ")
    except Stopped:
        return 0

    if answer in ("0", ""):
        return 0
    if not answer.isdigit() or not 1 <= int(answer) <= len(names):
        step.print_indented(f"Answer a number from 1 to {len(names)}, or 0 for none.", style="yellow")
        return 0

    name = names[int(answer) - 1]
    decisions.forget(name)
    if not decisions.save():
        _print_that_it_was_not_written(decisions, step)
        return 0
    step.print_indented((name, "bold"), " will be listed again.")
    return 1


def _adopt_all_label(found):
    """Returns what the bulk step is called, or None where it has nothing to do."""
    ready = ready_for_homebrew(found)
    if not ready:
        return None
    return f"add all to Homebrew ({ready} of {len(found)})"


def _walk_through(found, decisions, offered, step):
    """Asks about each app in turn. Returns the ones that were ignored or handed over."""
    dealt_with = []
    try:
        for app, cask in found:
            step.begin_menu()
            chosen = _ask_about(app, cask, offered, step, len(found) > 1)
            if chosen == CANCEL:
                break
            if chosen == IGNORE:
                decisions.ignore(app.file_stem, app.version)
                if not decisions.save():
                    _print_that_it_was_not_written(decisions, step)
                dealt_with.append(app)
            elif chosen in (ADOPT, TRASH):
                dealt_with.append(app)
    except Stopped:
        step.print_empty_line()
    return dealt_with


def _ask_about(app, cask, offered, step, is_walkthrough=True):
    """Asks about one app until the answer decides something. Returns that answer."""
    results = step.inside()
    answer = appcast.answer_for(app, offered)
    vendor_site = app_updaters.vendor_site(app.updater.feed_url)

    while True:
        chosen = step.choose(
            _app_choices(app, cask, vendor_site, not answer.error, is_walkthrough),
            f"{app.display_name} {app.version}",
            note=_what_is_known(app, cask, answer),
        )
        if chosen == WEBSITE:
            results.print_indented(vendor_site)
            if not shell.open_in_browser(vendor_site):
                results.print_indented("Could not open that in a browser.", style="yellow")
        elif chosen == LAUNCH:
            if shell.open_application(app.path):
                _print_that_it_started(results)
                return chosen
            results.print_indented("That app would not start.", style="yellow")
        elif chosen == TRASH:
            if _move_to_the_trash(app, step, results):
                return chosen
        elif chosen != ADOPT or _take_over_with_homebrew(app, cask, results):
            return chosen


def _app_choices(app, cask, vendor_site, can_ask_the_app, is_walkthrough=True):
    choices = []
    takeover = _takeover_choice(app, cask)
    if takeover:
        choices.append((ADOPT, takeover))
    if can_ask_the_app:
        choices.append((LAUNCH, f"open {app.display_name} and check for updates there"))
    if vendor_site:
        choices.append((WEBSITE, f"download and install manually from {vendor_site}"))
    choices.append((TRASH, f"move {app.display_name} to the Trash"))
    choices.append((IGNORE, "keep it untracked (don't ask again)"))
    choices.append((LATER, "next ⇥"))
    return walkthrough.options_for_single_item(choices, is_walkthrough)


def _takeover_choice(app, cask):
    """Returns the takeover as a menu label with its detail in grey, or "" without a recipe."""
    offer, detail = adopting.homebrew_takeover_of(app, cask)
    return prompting.label_with_note(offer, detail)


def _what_is_known(app, cask, answer):
    """Everything this Mac has to say about an app, before the options."""
    known = []
    standing = adopting.homebrew_note(app, cask)
    if standing:
        known.append(standing)

    known.append(f"Built-in updater: {app.updater.how_it_updates()}.")

    if appcast.offers_newer(app, answer):
        known.append(f"Update source offers {answer.version}.")
    if answer.error:
        known.append(f"But {answer.error}.")
    return ' '.join(known)


def _print_that_it_started(step):
    step.print_indented(
        "Started it. It looks for its update on startup, and anything it "
        "does not offer there is under its own menu.",
        style="green",
    )


def _move_to_the_trash(app, step, results):
    if not step.yes_or_no(f"Move {app.display_name} to the Trash? Quit it first if it is running.", default=False):
        return False
    moved = shell.move_to_trash(app.path)
    results.print_indented(
        f"{app.display_name} is in the Trash." if moved else f"Could not move {app.display_name} to the Trash.",
        style="green" if moved else "red",
    )
    return moved


def _take_over_with_homebrew(app, cask, step):
    """Returns whether Homebrew took the app over."""
    with prompting.warning_before_stopping():
        taken, message = adopting.take_over_with_homebrew(app, cask, status=report.waiting_spinner("waiting for Homebrew"))
    color = "green" if taken else "red"
    step.print_indented(message, style=color)
    return taken


def _print_that_it_was_not_written(decisions, step):
    step.print_indented(
        f"Could not write {decisions.path}, so this won't be remembered.", style="yellow"
    )
