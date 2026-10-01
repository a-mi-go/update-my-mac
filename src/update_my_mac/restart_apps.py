"""Restarting an app that is still running the version it was started with.

The new version is already on disk, so there is nothing to download and
nothing to install. The app only has to be started again, and the one thing
that matters is that it gets to ask about unsaved work first.
"""

import time

from rich.markup import escape

from update_my_mac import app_updaters
from update_my_mac.prompting import Step, Stopped

WAIT_SECONDS = 20
LOOK_AGAIN_EVERY = 0.5

RESTART_ALL, DECIDE_FOR_EACH, NOTHING = "restart all", "decide for each", "nothing"
RESTART_THIS_ONE, LEAVE_IT_RUNNING, CANCEL_WALK = "restart", "leave it", "cancel"

CHOICES = (
    (RESTART_ALL, "restart all (WARNING: unsaved work can be lost)"),
    (DECIDE_FOR_EACH, "decide for each"),
    (NOTHING, "nothing (move on to the next step)"),
)
WALK_CHOICES = (
    (RESTART_THIS_ONE, "restart"),
    (LEAVE_IT_RUNNING, "leave it running"),
    (CANCEL_WALK, "cancel the walk-through and move on to the next step"),
)


def restart(app, shell, pause=time.sleep):
    """Ask the app to quit, wait for it to go, then start it again.

    Returns whether it worked and a sentence saying what happened. An app
    that does not quit is left alone, because it is asking about unsaved work.
    """
    info = app_updaters.read_bundle_info(app.bundle)
    bundle_id = info.get("CFBundleIdentifier", "")
    if not bundle_id:
        return False, "Nothing in the app says what it is called internally."

    if not shell.ask_application_to_quit(bundle_id):
        return False, "It would not take the request to quit."

    waited = 0.0
    while shell.is_running(app.pid) and waited < WAIT_SECONDS:
        pause(LOOK_AGAIN_EVERY)
        waited += LOOK_AGAIN_EVERY

    if shell.is_running(app.pid):
        return False, "It is still running, probably asking about unsaved work."

    if not shell.open_application(app.bundle):
        return False, "It quit, but starting it again did not work."
    return True, "Quit and started again, now running the version on disk."


def run_restart_menu(apps, restart_one, step=None, interactive=True):
    """Ask what to do about the apps running an old version. Returns how many went.

    The answer is usually the same for all of them, so it is asked once. Going
    one at a time is there for the app that has something unsaved in it.
    """
    step = step or Step()
    if not apps or not interactive:
        return 0

    step.say()
    try:
        chosen = step.choose(CHOICES, "[bold]What should we do with them?[/]")
        if chosen == RESTART_ALL:
            return _restart_all(apps, restart_one, step)
        if chosen == DECIDE_FOR_EACH:
            return _walk_through(apps, restart_one, step.inside())
    except Stopped:
        step.say()
    return 0


def _restart_all(apps, restart_one, step):
    each = step.inside()
    restarted = 0
    for app in apps:
        each.say()
        each.say(f"[bold]{escape(app.name)}[/]")
        if _restart_one(app, restart_one, each.inside()):
            restarted += 1
    return restarted


def _walk_through(apps, restart_one, step):
    """Let the user decide how to deal with each app. Returns how many were restarted."""
    said = step.inside()
    restarted = 0
    try:
        for app in apps:
            step.say()
            step.say(f"[bold]{escape(app.describe())}[/]")
            chosen = step.choose(WALK_CHOICES, "[bold]What should we do with it?[/]")
            if chosen == CANCEL_WALK:
                break
            if chosen == RESTART_THIS_ONE and _restart_one(app, restart_one, said):
                restarted += 1
    except Stopped:
        step.say()
    return restarted


def _restart_one(app, restart_one, step):
    done, message = restart_one(app)
    # Which of the two it is, is the whole point of the line: green for an app
    # that is back on the version on disk, red for one still running the old one.
    colour = "green" if done else "red"
    step.say(f"[{colour}]{escape(message)}[/{colour}]")
    return done
