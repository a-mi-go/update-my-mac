"""Closing the running apps an update replaces, and offering to start them again afterwards."""

from update_my_mac.checks import installed_apps, running_apps
from update_my_mac.controller import restart_apps, walkthrough
from update_my_mac.controller.walkthrough import CANCEL
from update_my_mac.system import shell
from update_my_mac.view import report
from update_my_mac.view.prompting import Step, Stopped

RUNNING_AND_UPDATING = "Running, and about to be updated"
CLOSE_THIS_ONE, LEAVE_RUNNING = "close", "leave it running"
CLOSE_CHOICES = (
    (CLOSE_THIS_ONE, "close"),
    (LEAVE_RUNNING, "leave it running"),
)
START_AGAIN, LEAVE_CLOSED = "start", "leave it closed"
START_CHOICES = (
    (START_AGAIN, "start it again"),
    (LEAVE_CLOSED, "leave it closed"),
)


def app_file_names(entries):
    """Returns the file names of the apps these menu entries are about to update."""
    names = set()
    for entry in entries:
        packages = [package.partition("  ")[0] for package in entry.outdated]
        if "mas" in entry.keys:
            # The store names an app "Todoist: To-Do List", its bundle is Todoist.app.
            names |= {f"{name}.app" for name in packages}
            names |= {f"{name.partition(':')[0].strip()}.app" for name in packages}
        if "brew" in entry.keys:
            names |= installed_apps.app_names_of_casks(packages)
    return names


def ask_before_the_update(entries, step=None):
    """Offers to close the running apps the update replaces. Returns the closed ones."""
    with report.waiting_spinner("looking for running apps the update replaces"):
        running = running_apps.find_named(app_file_names(entries))
    if not running:
        return []

    step = step or Step()
    step.print_separator()
    step.print_indented(RUNNING_AND_UPDATING, style="bold")
    for app in running:
        step.inside().print_indented(app.display_name)
    return walkthrough.batch_or_walkthrough(
        step, running, "close all (WARNING: unsaved work can be lost)",
        lambda step: _close_all(running, step),
        lambda step: walkthrough.decide_for_each(running, step, CLOSE_CHOICES, CLOSE_THIS_ONE, _close_one),
    )


def _close_all(apps, step):
    per_item = step.inside()
    closed = []
    for app in apps:
        per_item.print_empty_line()
        per_item.print_indented(app.display_name, style="bold")
        if _close_one(app, per_item.inside()):
            closed.append(app)
    return closed


def _close_one(app, step):
    done, message = restart_apps.quit_app(app)
    step.print_indented(message, style="green" if done else "red")
    return done


def ask_to_start_again(apps, step=None):
    """Asks whether to start each closed app again. Returns the started ones."""
    if not apps:
        return []

    step = step or Step()
    step.print_separator()
    started = []
    try:
        for app in apps:
            step.set_next_menu_apart()
            chosen = step.choose(
                walkthrough.options_for_single_item(START_CHOICES, len(apps) > 1),
                f"Start {app.display_name} again?",
            )
            if chosen == CANCEL:
                break
            if chosen == START_AGAIN:
                opened = shell.open_application(app.bundle)
                step.inside().print_indented(
                    "Started." if opened else "Starting it did not work.",
                    style="green" if opened else "red",
                )
                if opened:
                    started.append(app)
    except Stopped:
        step.print_empty_line()
    return started
