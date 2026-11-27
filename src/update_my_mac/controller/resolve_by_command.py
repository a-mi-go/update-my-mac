"""Putting things right with one command each, all at once or one by one."""

from dataclasses import dataclass

from update_my_mac import managers
from update_my_mac.controller import walkthrough
from update_my_mac.controller.walkthrough import CANCEL
from update_my_mac.system import shell
from update_my_mac.system.shell import describe_exit
from update_my_mac.view import prompting, report
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
    # The commands after `command`, each run only once the one before it worked.
    then: tuple = ()
    # Puts back what `command` changed; run when the first of `then` fails.
    undo: tuple = ()

    @property
    def commands(self):
        return (self.command, *self.then)

    @property
    def text(self):
        return _shown(self.commands)


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
    only_one_by_one: bool = False


def ask_what_to_do(fixes, step=None):
    """Offers to run the commands that put these right. Returns the fixes that worked."""
    step = step or Step()
    if not fixes:
        return []

    return walkthrough.batch_or_walkthrough(
        step, fixes, _all_at_once_label(fixes),
        lambda step: run_all(fixes, step),
        lambda step: _walk_through(fixes, step),
    )


def _all_at_once_label(fixes):
    """Returns the label for putting right all that may run at once, or None when none may."""
    at_once = sum(not fix.only_one_by_one for fix in fixes)
    if not at_once:
        return None
    if at_once == len(fixes):
        return f"put all {at_once} right"
    return f"put {at_once} of {len(fixes)} right, the rest only one by one"


def run_all(fixes, step):
    per_item = step.inside()
    left = [fix.label for fix in fixes if fix.only_one_by_one]
    if left:
        per_item.print_indented(f"Left to choose one at a time, in the menu now or on the next run: {', '.join(left)}", style="yellow")
    done = []
    for fix in (fix for fix in fixes if not fix.only_one_by_one):
        per_item.print_empty_line()
        per_item.print_indented(fix.main.text, style="bold")
        if _run_one(fix, fix.main, per_item.inside()):
            done.append(fix)
    return done


def run_command(command):
    """Runs a fix's command with the terminal attached. Returns its exit code, or None."""
    program, *arguments = command
    executable = shell.find_executable(program)
    if executable is None:
        return None
    environment = managers.by_key("brew").environment() if program == "brew" else None
    with prompting.warning_before_stopping():
        return shell.stream_command(
            [executable, *arguments], environment, status_while_silent=report.waiting_spinner(f"waiting for {program}")
        )


def _walk_through(fixes, step):
    results = step.inside()
    done = []
    try:
        for fix in fixes:
            step.set_next_menu_apart()
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
    choices = [(fix.main, fix.main.text)]
    choices += [(option, option.label or option.text) for option in fix.others]
    return walkthrough.options_for_single_item(choices + [(LATER, "next ⇥")], is_walkthrough)


def _run_one(fix, option, step):
    """Runs one way of dealing with it. Returns whether that dealt with it."""
    failed, exit_code = _run_in_order(option.commands)
    if failed is not None:
        if failed == 1 and option.undo:
            said = _put_back(option, exit_code, run_command(option.undo))
        else:
            said = _failure(option, failed, exit_code)
        step.print_indented(said, style="yellow")
        return False
    worked, result = fix.confirm(option.command) if fix.confirm else (True, None)
    step.print_indented(result or (f"{fix.label}: {option.done}", "green"))
    return worked and option.settles


def _run_in_order(commands):
    """Runs the commands until one fails. Returns its index and exit code, or (None, 0) when all worked."""
    for index, command in enumerate(commands):
        exit_code = run_command(command)
        if exit_code != 0:
            return index, exit_code
    return None, 0


def _failure(option, failed, exit_code):
    """Returns what to say about the command that failed, when nothing was put back."""
    if failed == 0:
        return f"That {describe_exit(exit_code)}."
    before = _shown(option.commands[:failed])
    return f"{_shown(option.commands[failed:failed + 1])} {describe_exit(exit_code)}, after {before} already ran."


def _put_back(option, exit_code, undo_code):
    """Returns what to say when the second command failed and `undo` ran."""
    failed, undo = _shown(option.commands[1:2]), _shown((option.undo,))
    if undo_code == 0:
        return f"{failed} {describe_exit(exit_code)}; ran {undo} to put things back as they were."
    return f"{failed} {describe_exit(exit_code)}, and {undo} {describe_exit(undo_code)}: run it yourself."


def _shown(commands):
    return " && ".join(" ".join(command) for command in commands)
