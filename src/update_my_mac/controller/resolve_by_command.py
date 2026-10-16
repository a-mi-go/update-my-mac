"""Putting things right with one command each, all at once or one by one."""

from dataclasses import dataclass
from update_my_mac import managers
from update_my_mac.system import shell
from update_my_mac.system.shell import describe_exit
from update_my_mac.controller import walkthrough
from update_my_mac.controller.walkthrough import CANCEL
from update_my_mac.view.prompting import Step, Stopped

LATER = "later"


@dataclass(frozen=True)
class Option:
    label: str
    command: tuple
    # What it did, said after it worked, such as "uninstalled".
    done: str
    # Whether the thing is dealt with once it worked. Opening an app to update
    # it there is not.
    settles: bool = True


@dataclass
class Fix:
    label: str
    note: str
    main: Option
    # Other ways to deal with it. An empty label shows the command itself.
    others: tuple = ()
    # Called with the command that ran. Returns whether it really worked and
    # the line to print, an empty one to fall back on what the option did.
    confirm: object = None


def ask_what_to_do(fixes, step=None):
    """Offers to run the commands that put these right. Returns the fixes that worked."""
    step = step or Step()
    if not fixes:
        return []

    return walkthrough.batch_or_walkthrough(
        step, fixes, f"put all {len(fixes)} right",
        lambda step: run_all(fixes, step),
        lambda step: _walk_through(fixes, step),
    )


def run_all(fixes, step):
    per_item = step.inside()
    done = []
    for fix in fixes:
        per_item.print_empty_line()
        per_item.print_indented(" ".join(fix.main.command), style="bold")
        if _run_one(fix, fix.main, per_item.inside()):
            done.append(fix)
    return done


def _walk_through(fixes, step):
    results = step.inside()
    done = []
    try:
        for fix in fixes:
            step.begin_menu()
            chosen = step.choose(
                _choices_for(fix, len(fixes) > 1),
                fix.label,
                note=fix.note,
            )
            if chosen == CANCEL:
                break
            if isinstance(chosen, Option) and _run_one(fix, chosen, results):
                done.append(fix)
    except Stopped:
        step.print_empty_line()
    return done


def _choices_for(fix, is_walkthrough):
    choices = [(fix.main, " ".join(fix.main.command))]
    choices += [(option, option.label or " ".join(option.command)) for option in fix.others]
    return walkthrough.options_for_single_item(choices + [(LATER, "leave it for now")], is_walkthrough)


def _run_one(fix, option, step):
    """Runs one way of dealing with it. Returns whether that dealt with it."""
    exit_code = run_command(option.command)
    if exit_code != 0:
        step.print_indented(f"That {describe_exit(exit_code)}.", style="yellow")
        return False
    worked, result = fix.confirm(option.command) if fix.confirm else (True, None)
    step.print_indented(result or (f"{fix.label}: {option.done}", "green"))
    return worked and option.settles


def run_command(command):
    """Runs a fix's command with the terminal attached. Returns its exit code, or None."""
    program, *arguments = command
    executable = shell.find_executable(program)
    if executable is None:
        return None
    environment = managers.by_key("brew").environment() if program == "brew" else None
    return shell.stream_command([executable, *arguments], environment)
