"""Updating the apps Homebrew installed but has stopped reporting.

A cask marked `auto_updates` is never called outdated, and one Homebrew wrote
the wrong version down for is not even picked up by a greedy upgrade. Either
way the app sits there, older than the recipe, and nothing says so.
"""

from rich.markup import escape

from update_my_mac import behind_the_recipe
from update_my_mac.prompting import Step, Stopped

CATCH_UP_ALL, DECIDE_FOR_EACH, NOTHING = "all", "decide for each", "nothing"
CATCH_UP, LATER, CANCEL = "catch up", "later", "cancel"

REINSTALL = ("reinstall", "--cask")
UPGRADE = ("upgrade", "--cask", "--greedy")


def commands_for(behind):
    """The brew commands that cover these apps, grouped rather than one each."""
    grouped = []
    reinstall = behind_the_recipe.to_reinstall(behind)
    if reinstall:
        grouped.append(REINSTALL + tuple(reinstall))
    upgrade = behind_the_recipe.to_upgrade(behind)
    if upgrade:
        grouped.append(UPGRADE + tuple(upgrade))
    return grouped


def command_for(item):
    """The one command that puts a single app right."""
    return commands_for([item])[0] if commands_for([item]) else ()


def run_catch_up_menu(behind, run, step=None, interactive=True):
    """Offer to bring these apps up to their recipe. Returns how many went."""
    step = step or Step()
    if not behind or not interactive:
        return 0

    step.say()
    try:
        step.say("[bold]What should we do with them?[/]")
        chosen = step.choose(_choices(behind))
        if chosen == CATCH_UP_ALL:
            return catch_up_all(behind, run, step)
        if chosen == DECIDE_FOR_EACH:
            return _walk_through(behind, run, step.inside())
    except Stopped as stopped:
        step.say()
        return stopped.done
    return 0


def _choices(behind):
    return [
        (CATCH_UP_ALL, f"bring all {len(behind)} up to their recipe"),
        (DECIDE_FOR_EACH, "decide for each"),
        (NOTHING, "nothing (move on to the next step)"),
    ]


def catch_up_all(behind, run, step):
    """Run the grouped commands. Returns how many apps they covered.

    A command that fails does not stop the rest, because one group failing
    says nothing about the other. Ctrl-C does stop it, and takes the count so
    far with it rather than losing the group that already went through.
    """
    each = step.inside()
    done = 0
    for command in commands_for(behind):
        each.say()
        each.say(f"[bold]brew {escape(' '.join(command))}[/]")
        try:
            ran = _run_one(command, run, each.inside())
        except Stopped:
            raise Stopped(done)
        if ran:
            done += _how_many_apps(command)
    return done


def _how_many_apps(command):
    """How many apps one grouped command covers, which is all but its flags."""
    return len([part for part in command if not part.startswith("-")]) - 1


def _walk_through(behind, run, step):
    """Ask about each app in turn. Returns how many were brought up to date."""
    said = step.inside()
    done = 0
    try:
        for item in behind:
            step.say()
            step.say(f"[bold]{escape(item.app.name)}[/]  {escape(item.version_change())}")
            if item.false_version_recorded:
                said.say(
                    "[dim]Homebrew wrote down a version it never installed, so no "
                    "upgrade will touch this one.[/]"
                )
            chosen = step.choose(_app_choices(item))
            if chosen == CANCEL:
                break
            if chosen == CATCH_UP and _run_one(command_for(item), run, said):
                done += 1
    except Stopped:
        step.say()
    return done


def _app_choices(item):
    return [
        (CATCH_UP, f"brew {' '.join(command_for(item))}"),
        (LATER, "leave it for now"),
        (CANCEL, "cancel the walk-through and move on to the next step"),
    ]


def _run_one(command, run, step):
    try:
        exit_code = run(command)
    except KeyboardInterrupt:
        step.say("[yellow]Stopped.[/]")
        raise Stopped

    if exit_code != 0:
        step.say(f"[yellow]That exited with {exit_code}.[/]")
        return False
    return True
