"""Going through the apps no package manager tracks, and revisiting that later."""

from rich.markup import escape

from update_my_mac import adopt_apps, app_updaters, appcast, versions
from update_my_mac.prompting import Step, Stopped

ADOPT_ALL, DECIDE_FOR_EACH, NOTHING = "adopt all", "decide for each", "nothing"
ADOPT, WEBSITE, LAUNCH = "adopt", "website", "launch"
IGNORE, LATER, CANCEL = "ignore", "later", "cancel"


def run_untracked_menu(
    apps,
    decisions,
    step=None,
    interactive=True,
    find_cask=None,
    adopt=None,
    open_url=None,
    open_app=None,
    offered=None,
):
    """Ask what to do about the untracked apps. Returns how many were dealt with.

    Dealt with means Homebrew took it over or it was left alone on purpose;
    either way the app is not asked about again.
    """
    step = step or Step()
    waiting = [app for app in apps if not decisions.is_ignored(app.name)]
    if not waiting or not interactive:
        return 0

    found = [(app, find_cask(app) if find_cask else None) for app in waiting]
    choices = _choices(found, adopt)
    walk = lambda: _walk_through(
        found, decisions, adopt, open_url, open_app, offered or {}, step.inside()
    )

    ignored, adopted = 0, 0
    step.say()
    try:
        if not _worth_asking(choices):
            # Going one at a time is the only thing left to offer, and the
            # walk-through has its own way out.
            ignored, adopted = walk()
        else:
            step.say("[bold]What should we do with them?[/]")
            chosen = step.choose(choices)
            if chosen == ADOPT_ALL:
                adopted = adopt_all(found, adopt, step)
            elif chosen == DECIDE_FOR_EACH:
                ignored, adopted = walk()
    except Stopped:
        step.say()

    if ignored and not decisions.save():
        _say_it_was_not_written(decisions, step)
    return ignored + adopted


def worth_sorting_out(app, cask, answer=None):
    """Whether this app is a problem at all.

    An app that looks after itself is doing the job, and saying otherwise is
    how a list of twenty apps becomes worth ignoring. It only counts once
    something says it has stopped: its own feed offering a version it never
    installed, a feed that no longer answers, or a recipe that has gone past
    it. Codex running ahead of its recipe is none of those.
    """
    if not app.updater.looks_after_itself:
        return True

    answer = answer or appcast.FeedAnswer()
    if answer.error or appcast.offers_newer(app, answer):
        return True
    return cask is not None and versions.is_newer(cask.version, than=app.version)


def known_to_homebrew(found):
    """How many of the (app, cask) pairs Homebrew has a recipe for at all.

    Going back a version is a way in too, so an app counts here even when it
    is left out of the step that hands over several at once.
    """
    return sum(1 for app, cask in found if adopt_apps.can_take_over(app, cask))


def ready_for_homebrew(found):
    """How many of the (app, cask) pairs Homebrew could take over without loss.

    An app whose recipe is behind it can still be handed over, but only by
    putting an older version in its place, which nobody should be counted
    into without saying so.
    """
    return sum(
        1 for app, cask in found
        if adopt_apps.can_take_over(app, cask) and not adopt_apps.would_downgrade(app, cask)
    )


def _worth_asking(choices):
    """Whether the menu offers more than going through them one at a time."""
    return len(choices) > 2


def _choices(found, adopt):
    ready = ready_for_homebrew(found)
    choices = []
    if adopt is not None and ready:
        choices.append((ADOPT_ALL, f"add all to Homebrew ({ready} of {len(found)})"))
    choices.append((DECIDE_FOR_EACH, "decide for each"))
    choices.append((NOTHING, "nothing (move on to the next step)"))
    return choices


def adopt_all(found, adopt, step):
    """Hand every app Homebrew has a recipe for over to it. Returns how many went.

    """
    each = step.inside()
    adopted = 0
    for app, cask in found:
        # A downgrade is never done in bulk. It is a deliberate answer about
        # one app, not something to sweep up with the rest.
        if not adopt_apps.can_take_over(app, cask) or adopt_apps.would_downgrade(app, cask):
            continue
        each.say()
        each.say(f"[bold]{escape(app.name)}[/]")
        if _hand_to_homebrew(app, adopt, each.inside()):
            adopted += 1
    return adopted


def _walk_through(found, decisions, adopt, open_url, open_app, offered, step):
    """Ask about each app in turn. Returns how many were ignored and adopted.

    Ctrl-C ends the walk here rather than further out, so what was decided
    before it still counts and still gets written.
    """
    ignored, adopted = 0, 0
    try:
        for app, cask in found:
            step.say()
            step.say(f"[bold]{escape(app.name)}[/]  {escape(app.version)}")

            chosen = _ask_about(app, cask, adopt, open_url, open_app, offered, step)
            if chosen == CANCEL:
                break
            if chosen == IGNORE:
                decisions.ignore(app.name, app.version)
                ignored += 1
            elif chosen == ADOPT:
                adopted += 1
    except Stopped:
        step.say()
    return ignored, adopted


def _ask_about(app, cask, adopt, open_url, open_app, offered, step):
    """Ask about one app until the answer decides something. Returns that answer."""
    said = step.inside()
    answer = appcast.answer_for(app, offered)
    site = app_updaters.site_behind(app.updater.feed_url)
    can_ask_the_app = open_app is not None and app.updater.kind != app_updaters.NONE
    _say_what_is_known(app, cask, answer, said)

    while True:
        chosen = step.choose(_app_choices(app, cask, adopt, site, can_ask_the_app and not answer.error))
        # Only a handover settles anything. Looking at a website or starting
        # the app leaves it exactly as undecided as it was.
        if chosen == WEBSITE:
            said.say(escape(site))
            if open_url is not None and not open_url(site):
                said.say("[yellow]Could not open that in a browser.[/]")
        elif chosen == LAUNCH:
            _ask_the_app_itself(app, open_app, said)
        elif chosen != ADOPT or _hand_to_homebrew(app, adopt, said):
            return chosen


def _ask_the_app_itself(app, open_app, step):
    """Start the app, which is when an updater like Sparkle looks for a new version."""
    if not open_app(app.path):
        step.say("[yellow]That app would not start.[/]")
        return
    step.say(
        "[green]Started it. It looks for its update on startup, and anything it "
        "does not offer there is under its own menu.[/]"
    )


def _say_what_is_known(app, cask, answer, step):
    """Everything this Mac has to say about an app, before the options."""
    told = []
    standing = adopt_apps.homebrew_note(app, cask)
    if standing:
        told.append(standing)

    if app.updater.kind == app_updaters.NONE:
        told.append("Nothing in it says how it updates.")
    else:
        told.append(f"It {app.updater.describe()}.")

    if answer.error:
        told.append(f"But {answer.error}.")
    elif appcast.offers_newer(app, answer):
        told.append(f"Its own feed offers {answer.version}.")
    step.say(f"[dim]{escape(' '.join(told))}[/]")


def _app_choices(app, cask, adopt, site, can_ask_the_app):
    choices = []
    handover = adopt_apps.handover_label(app, cask) if adopt is not None else ""
    if handover:
        choices.append((ADOPT, handover))
    if can_ask_the_app:
        choices.append((LAUNCH, f"open {app.name} and let it update itself"))
    if site:
        choices.append((WEBSITE, f"download and install manually from {site}"))
    choices.append((IGNORE, "keep it untracked (don't ask again)"))
    choices.append((LATER, "leave it for now"))
    choices.append((CANCEL, "cancel the walk-through and move on to the next step"))
    return choices


def _hand_to_homebrew(app, adopt, step):
    """Returns whether Homebrew took the app over."""
    taken, message = adopt(app)
    colour = "green" if taken else "red"
    step.say(f"[{colour}]{escape(message)}[/{colour}]")
    return taken


def run_revisit_menu(decisions, step=None, interactive=True):
    """Bring an app back into the list. Returns how many came back."""
    step = step or Step()
    names = decisions.ignored_names()

    if not names:
        step.say("No apps are being left alone.")
        return 0

    step.say("Apps being left alone:")
    listed = step.inside()
    if not interactive:
        for name in names:
            listed.say(escape(name))
        return 0

    for number, name in enumerate(names, start=1):
        listed.say(f"[bold cyan]{number})[/] {escape(name)}")
    listed.say("[bold cyan]0)[/] none of them")

    try:
        answer = step.read("List one of them again? ")
    except Stopped:
        return 0

    if answer in ("0", ""):
        return 0
    if not answer.isdigit() or not 1 <= int(answer) <= len(names):
        step.say(f"[yellow]Answer a number from 1 to {len(names)}, or 0 for none.[/]")
        return 0

    name = names[int(answer) - 1]
    decisions.forget(name)
    if not decisions.save():
        _say_it_was_not_written(decisions, step)
        return 0
    step.say(f"[bold]{escape(name)}[/] will be listed again.")
    return 1


def _say_it_was_not_written(decisions, step):
    step.say(
        f"[yellow]Could not write {escape(str(decisions.path))}, "
        f"so this won't be remembered.[/]"
    )
