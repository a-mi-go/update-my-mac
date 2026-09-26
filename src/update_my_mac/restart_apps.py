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
    """Offer to restart each app. Returns how many were restarted."""
    console_print = _printer(out)
    if not apps or not interactive:
        return 0

    console_print()
    counted = "app" if len(apps) == 1 else "apps"
    console_print(f"Going through {len(apps)} {counted} running an old version.")

    restarted = 0
    try:
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
            if choice != "1":
                continue

            done, message = restart_one(app)
            console_print(f"  {'' if done else '[yellow]'}{escape(message)}{'' if done else '[/]'}")
            restarted += 1 if done else 0
    except Stopped:
        console_print()

    return restarted
