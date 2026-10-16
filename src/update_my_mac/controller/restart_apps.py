"""Restart apps that are still running old versions after the updates"""

import time


from update_my_mac.checks import app_updaters
from update_my_mac.controller import walkthrough
from update_my_mac.controller.walkthrough import CANCEL
from update_my_mac.view.prompting import Step, Stopped
from update_my_mac.view.sections import NOT_RESTARTED
from update_my_mac.system import shell

WAIT_SECONDS = 20
LOOK_AGAIN_EVERY = 0.5

RESTART_THIS_ONE, LEAVE_IT_RUNNING = "restart", "leave it"
WALK_CHOICES = (
    (RESTART_THIS_ONE, "restart"),
    (LEAVE_IT_RUNNING, "leave it running"),
)


def restart(app):
    """Quits the app and starts it again. Returns whether it worked, and a sentence."""
    info = app_updaters.read_bundle_info(app.bundle)
    bundle_id = info.get("CFBundleIdentifier", "")
    if not bundle_id:
        return False, "Nothing in the app says what it is called internally."

    if not shell.ask_application_to_quit(bundle_id):
        return False, "It would not take the request to quit."

    waited = 0.0
    while shell.is_running(app.pid) and waited < WAIT_SECONDS:
        time.sleep(LOOK_AGAIN_EVERY)
        waited += LOOK_AGAIN_EVERY

    if shell.is_running(app.pid):
        return False, "It is still running, probably asking about unsaved work."

    if not shell.open_application(app.bundle):
        return False, "It quit, but starting it again did not work."
    return True, "Quit and started again, now running the version on disk."


def ask_after_the_update(apps, step=None):
    """Offers to restart the apps an update replaced while they ran. Returns the restarted ones."""
    step = step or Step()
    if not apps:
        return []

    step.print_empty_line()
    step.print_separator()
    step.print_indented(NOT_RESTARTED, style="bold")
    for app in apps:
        step.inside().print_indented(app.name)
    return ask_what_to_do(apps, step)


def ask_what_to_do(apps, step=None):
    """Asks about the apps running an old version. Returns the restarted ones."""
    step = step or Step()
    if not apps:
        return []

    return walkthrough.batch_or_walkthrough(
        step, apps, "restart all (WARNING: unsaved work can be lost)",
        lambda step: _restart_all(apps, step),
        lambda step: _walk_through(apps, step),
    )


def _restart_all(apps, step):
    per_item = step.inside()
    restarted = []
    for app in apps:
        per_item.print_empty_line()
        per_item.print_indented(app.name, style="bold")
        if _restart_one(app, per_item.inside()):
            restarted.append(app)
    return restarted


def _restart_one(app, step):
    done, message = restart(app)
    # Which of the two it is, is the whole point of the line: green for an app
    # that is back on the version on disk, red for one still running the old one.
    colour = "green" if done else "red"
    step.print_indented(message, style=colour)
    return done


def _walk_through(apps, step):
    """Lets the user decide how to deal with each app. Returns the restarted ones."""
    results = step.inside()
    restarted = []
    try:
        for app in apps:
            step.begin_menu()
            chosen = step.choose(
                walkthrough.options_for_single_item(WALK_CHOICES, len(apps) > 1),
                app.title(),
                note=app.comment(),
            )
            if chosen == CANCEL:
                break
            if chosen == RESTART_THIS_ONE and _restart_one(app, results):
                restarted.append(app)
    except Stopped:
        step.print_empty_line()
    return restarted
