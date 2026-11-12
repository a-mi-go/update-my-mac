"""Restart apps that are still running old versions after the updates"""

import time

from update_my_mac.checks import app_updaters
from update_my_mac.controller import walkthrough
from update_my_mac.system import shell
from update_my_mac.view import report
from update_my_mac.view.prompting import Markup, Step
from update_my_mac.view.sections import NOT_RESTARTED

WAIT_SECONDS = 20
LOOK_AGAIN_EVERY = 0.5

RESTART_ALL = Markup("restart all [yellow](WARNING: unsaved work can be lost)[/]")
RESTART_THIS_ONE, LEAVE_IT_RUNNING = "restart", "leave it"
WALK_CHOICES = (
    (RESTART_THIS_ONE, "restart"),
    (LEAVE_IT_RUNNING, "leave it running"),
)


def quit_app(app):
    """Asks the app to quit and waits for it. Returns whether it is gone, and a sentence."""
    info = app_updaters.read_bundle_info(app.bundle)
    bundle_id = info.get("CFBundleIdentifier", "")
    if not bundle_id:
        return False, "Nothing in the app says what it is called internally."

    if not shell.ask_application_to_quit(bundle_id):
        return False, "It would not take the request to quit."

    waited = 0.0
    with report.waiting_spinner(f"waiting for {app.display_name} to quit"):
        while shell.is_running(app.pid) and waited < WAIT_SECONDS:
            time.sleep(LOOK_AGAIN_EVERY)
            waited += LOOK_AGAIN_EVERY

    if shell.is_running(app.pid):
        return False, "It is still running, probably asking about unsaved work."
    return True, "Quit."


def restart(app):
    """Quits the app and starts it again. Returns whether it worked, and a sentence."""
    gone, message = quit_app(app)
    if not gone:
        return False, message
    if not shell.open_application(app.bundle):
        return False, "It quit, but starting it again did not work."
    return True, "Quit and started again, now running the version on disk."


def ask_after_the_update(apps, step=None):
    """Offers to restart the apps an update replaced while they ran. Returns the restarted ones."""
    step = step or Step()
    if not apps:
        return []

    step.print_separator()
    step.print_indented(NOT_RESTARTED, style="bold")
    for app in apps:
        step.inside().print_indented(app.display_name)
    return ask_what_to_do(apps, step)


def ask_what_to_do(apps, step=None):
    """Asks about the apps running an old version. Returns the restarted ones."""
    step = step or Step()
    if not apps:
        return []

    return walkthrough.batch_or_walkthrough(
        step, apps, RESTART_ALL,
        lambda step: _restart_all(apps, step),
        # Asked at the level of the list, so the results line up with it.
        lambda _: walkthrough.decide_for_each(apps, step, WALK_CHOICES, RESTART_THIS_ONE, _restart_one),
    )


def _restart_all(apps, step):
    per_item = step.inside()
    return [app for app in apps if _restart_one(app, per_item)]


def _restart_one(app, step):
    done, message = restart(app)
    # Which of the two it is, is the whole point of the line: green for an app
    # that is back on the version on disk, red for one still running the old one.
    color = "green" if done else "red"
    step.print_indented(f"{app.display_name} - ", (message, color))
    return done
