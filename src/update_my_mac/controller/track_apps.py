"""Going through the apps no package manager tracks, and revisiting that later."""


from update_my_mac.managers.homebrew import adopting
from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.controller import walkthrough
from update_my_mac.system import shell
from update_my_mac.controller.walkthrough import CANCEL
from update_my_mac.view.prompting import Step, Stopped

ADOPT, WEBSITE, LAUNCH = "adopt", "website", "launch"
IGNORE, LATER = "ignore", "later"


def ask_what_to_do(
    apps,
    decisions,
    step=None,
    find_cask=None,
    offered=None,
):
    """Asks about the untracked apps. Returns the ones that were ignored or handed over."""
    step = step or Step()
    waiting = [app for app in apps if not decisions.is_ignored(app.name)]
    if not waiting:
        return []

    found = [(app, find_cask(app) if find_cask else None) for app in waiting]
    return walkthrough.batch_or_walkthrough(
        step, found, _adopt_all_label(found),
        lambda step: adopt_all(found, step),
        lambda step: _walk_through(found, decisions, offered or {}, step),
    )


def worth_sorting_out(app, cask, answer=None):
    """Returns whether this app is a problem at all."""
    if not app.updater.looks_after_itself:
        return True

    answer = answer or appcast.FeedAnswer()
    if answer.error or appcast.offers_newer(app, answer):
        return True
    return adopting.compare_to_app(app, cask) == adopting.NEWER


def known_to_homebrew(found):
    """Returns how many of the (app, cask) pairs Homebrew has a recipe for."""
    return sum(1 for app, cask in found if adopting.can_take_over(app, cask))


def ready_for_homebrew(found):
    """Returns how many Homebrew could take over without putting an older one back."""
    return sum(
        1 for app, cask in found
        if adopting.can_take_over(app, cask) and not adopting.would_downgrade(app, cask)
    )


def adopt_all(found, step):
    """Hands every app Homebrew has a recipe for over to it. Returns the ones it took."""
    per_item = step.inside()
    adopted = []
    for app, cask in found:
        # A downgrade is never done in bulk. It is a deliberate answer about
        # one app, not something to sweep up with the rest.
        if not adopting.can_take_over(app, cask) or adopting.would_downgrade(app, cask):
            continue
        per_item.print_empty_line()
        per_item.print_indented(app.name, style="bold")
        if _hand_to_homebrew(app, cask, per_item.inside()):
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
                decisions.ignore(app.name, app.version)
                if not decisions.save():
                    _print_that_it_was_not_written(decisions, step)
                dealt_with.append(app)
            elif chosen == ADOPT:
                dealt_with.append(app)
    except Stopped:
        step.print_empty_line()
    return dealt_with


def _ask_about(app, cask, offered, step, is_walkthrough=True):
    """Asks about one app until the answer decides something. Returns that answer."""
    results = step.inside()
    answer = appcast.answer_for(app, offered)
    vendor_site = app_updaters.vendor_site(app.updater.feed_url)
    can_ask_the_app = app.updater.kind != app_updaters.NONE

    while True:
        chosen = step.choose(
            _app_choices(app, cask, vendor_site, can_ask_the_app and not answer.error, is_walkthrough),
            f"{app.name} {app.version}",
            note=_what_is_known(app, cask, answer),
        )
        # Only a handover settles anything. Looking at a website or starting
        # the app leaves it exactly as undecided as it was.
        if chosen == WEBSITE:
            results.print_indented(vendor_site)
            if not shell.open_in_browser(vendor_site):
                results.print_indented("Could not open that in a browser.", style="yellow")
        elif chosen == LAUNCH:
            _ask_the_app_itself(app, results)
        elif chosen != ADOPT or _hand_to_homebrew(app, cask, results):
            return chosen


def _app_choices(app, cask, vendor_site, can_ask_the_app, is_walkthrough=True):
    choices = []
    handover = adopting.handover_label(app, cask)
    if handover:
        choices.append((ADOPT, handover))
    if can_ask_the_app:
        choices.append((LAUNCH, f"open {app.name} and let it update itself"))
    if vendor_site:
        choices.append((WEBSITE, f"download and install manually from {vendor_site}"))
    choices.append((IGNORE, "keep it untracked (don't ask again)"))
    choices.append((LATER, "leave it for now"))
    return walkthrough.options_for_single_item(choices, is_walkthrough)


def _what_is_known(app, cask, answer):
    """Everything this Mac has to say about an app, before the options."""
    told = []
    standing = adopting.homebrew_note(app, cask)
    if standing:
        told.append(standing)

    told.append(f"Built-in updater: {app.updater.update_method_note()}.")

    if appcast.offers_newer(app, answer):
        told.append(f"Update source offers {answer.version}.")
    if answer.error:
        told.append(f"But {answer.error}.")
    return ' '.join(told)


def _ask_the_app_itself(app, step):
    """Start the app, which is when an updater like Sparkle looks for a new version."""
    if not shell.open_application(app.path):
        step.print_indented("That app would not start.", style="yellow")
        return
    step.print_indented(
        "Started it. It looks for its update on startup, and anything it "
        "does not offer there is under its own menu.",
        style="green",
    )


def _hand_to_homebrew(app, cask, step):
    """Returns whether Homebrew took the app over."""
    taken, message = adopting.hand_to_homebrew(app, cask)
    colour = "green" if taken else "red"
    step.print_indented(message, style=colour)
    return taken


def _print_that_it_was_not_written(decisions, step):
    step.print_indented(
        f"Could not write {decisions.path}, so this won't be remembered.", style="yellow"
    )
