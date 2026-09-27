"""Restarting an app that is still running the version it was started with.

The new version is already on disk, so there is nothing to download and
nothing to install. The app only has to be started again, and the one thing
that matters is that it gets to ask about unsaved work first.
"""

import time

from rich.markup import escape

from update_my_mac import app_updaters
from update_my_mac.prompting import Stopped, answer as _answer, printer as _printer

WAIT_SECONDS = 20
LOOK_AGAIN_EVERY = 0.5


def restart(app, shell, pause=time.sleep):
    """Ask the app to quit, wait for it to go, then start it again.

    Returns a sentence saying what happened. An app that does not quit is
    left alone: it is either asking about unsaved work or ignoring us, and
    neither is a reason to take the decision away from the person.
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


def run_restart_menu(apps, restart_one, ask=input, out=None, interactive=True):
    """Ask what to do about the apps running an old version. Returns how many went.

    The answer is usually the same for all of them, so it is asked once. Going
    one at a time is there for the app that has something unsaved in it.
    """
    console_print = _printer(out)
    if not apps or not interactive:
        return 0

    console_print()
    try:
        choice = _ask_how_to_deal(apps, ask, console_print)
        if choice == "1":
            return _restart_all(apps, restart_one, console_print)
        if choice == "2":
            return _walk_through(apps, restart_one, ask, console_print)
    except Stopped:
        console_print()

    return 0


def _ask_how_to_deal(apps, ask, console_print):
    counted = "app" if len(apps) == 1 else "apps"
    console_print(f"{len(apps)} {counted} running an old version. What now?")
    console_print("  [bold cyan]1)[/] quit all of them and start them again")
    console_print("  [bold cyan]2)[/] go through them one at a time")
    console_print("  [bold cyan]3)[/] leave them all running")

    while True:
        # Asked again rather than guessed at, because guessing wrong here quits
        # an app that was about to ask about unsaved work.
        choice = _answer(ask, "> ")
        if choice in ("1", "2", "3"):
            return choice


def _restart_all(apps, restart_one, console_print):
    restarted = 0
    for app in apps:
        console_print()
        console_print(f"[bold]{escape(app.name)}[/]")
        if _restart_one(app, restart_one, console_print):
            restarted += 1
    return restarted


def _walk_through(apps, restart_one, ask, console_print):
    """One question per app, for when the answer is not the same for all."""
    restarted = 0
    for app in apps:
        console_print()
        console_print(f"[bold]{escape(app.name)}[/]")
        console_print(f"  {escape(app.describe())}")
        console_print("  [bold cyan]1)[/] quit it and start it again")
        console_print("  [bold cyan]2)[/] leave it running")
        console_print("  [bold cyan]3)[/] stop going through them")

        choice = _answer(ask, "> ")
        if choice == "3":
            break
        if choice == "1" and _restart_one(app, restart_one, console_print):
            restarted += 1
    return restarted


def _restart_one(app, restart_one, console_print):
    done, message = restart_one(app)
    console_print(f"  {'' if done else '[yellow]'}{escape(message)}{'' if done else '[/]'}")
    return done
