"""Running one command per thing that needs putting right."""

import pytest

from fake_run import swap

from update_my_mac.controller import resolve_by_command
from update_my_mac.controller.resolve_by_command import Fix, Option
from fake_terminal import Terminal

FIX_ALL, DECIDE = "1", "2"
RUN, LATER, CANCEL = "1", "2", "3"


class Runner:
    def __init__(self, exit_code=0):
        self.ran = []
        self.exit_code = exit_code

    def __call__(self, command):
        self.ran.append(command)
        return self.exit_code


def fixes():
    return [
        Fix("clerk  64 → 3.4.1", "versions cannot be compared",
            Option("", ("brew", "reinstall", "clerk"), "reinstalled")),
        Fix("google-trends", "disabled",
            Option("", ("brew", "uninstall", "--cask", "google-trends"), "uninstalled")),
    ]


FIXES = fixes()


def test_everything_can_be_put_right_at_once():
    runner = Runner()

    swap(resolve_by_command, "run_command", runner)
    done = resolve_by_command.ask_what_to_do(FIXES, Terminal(FIX_ALL).step)

    assert len(done) == 2
    assert runner.ran == [fix.main.command for fix in FIXES]


def test_each_can_be_decided_on_its_own():
    runner = Runner()
    terminal = Terminal(DECIDE, LATER, RUN)

    swap(resolve_by_command, "run_command", runner)
    done = resolve_by_command.ask_what_to_do(FIXES, terminal.step)

    assert len(done) == 1
    assert runner.ran == [FIXES[1].main.command]
    assert "versions cannot be compared" in terminal.text


def test_cancelling_the_walk_through_stops_asking():
    runner = Runner()

    swap(resolve_by_command, "run_command", runner)
    done = resolve_by_command.ask_what_to_do(FIXES, Terminal(DECIDE, CANCEL).step)

    assert len(done) == 0
    assert runner.ran == []


def test_a_command_that_fails_is_said_and_not_counted():
    terminal = Terminal(FIX_ALL)

    swap(resolve_by_command, "run_command", Runner(1))
    done = resolve_by_command.ask_what_to_do(FIXES, terminal.step)

    assert len(done) == 0
    assert "exited with 1" in terminal.text


def test_nothing_to_put_right_asks_nothing():
    swap(resolve_by_command, "run_command", Runner())
    assert resolve_by_command.ask_what_to_do([], Terminal().step) == []




def test_ctrl_c_is_left_to_end_the_run():
    with pytest.raises(KeyboardInterrupt):
        swap(resolve_by_command, "run_command", Runner())
        resolve_by_command.ask_what_to_do(FIXES, Terminal(then=KeyboardInterrupt).step)


def test_ctrl_c_during_a_command_ends_the_run():
    ran = []

    def run(command):
        ran.append(command[1])
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        swap(resolve_by_command, "run_command", run)
        resolve_by_command.ask_what_to_do(FIXES, Terminal(FIX_ALL).step)
    assert ran == ["reinstall"]


REMOVE_IT = "2"


def removable():
    return Fix("Foo 1.0 → 2.0", "", Option("", ("brew", "upgrade", "foo"), "updated"),
               (Option("", ("brew", "uninstall", "--cask", "foo"), "uninstalled"),))


def test_an_app_can_be_uninstalled_instead_of_fixed():
    runner = Runner()

    swap(resolve_by_command, "run_command", runner)
    done = resolve_by_command.ask_what_to_do([removable()], Terminal(REMOVE_IT).step)

    assert len(done) == 1
    assert runner.ran == [("brew", "uninstall", "--cask", "foo")]


def test_fixing_all_never_uninstalls():
    runner = Runner()

    swap(resolve_by_command, "run_command", runner)
    resolve_by_command.ask_what_to_do([removable(), removable()], Terminal(FIX_ALL).step)

    assert runner.ran == [("brew", "upgrade", "foo")] * 2


def test_no_uninstall_is_offered_where_the_fix_is_already_one():
    terminal = Terminal(LATER)

    swap(resolve_by_command, "run_command", Runner())
    resolve_by_command.ask_what_to_do([FIXES[1]], terminal.step)

    assert "uninstall --cask google-trends" in terminal.text
    assert terminal.text.count("uninstall") == 1


def test_a_walk_through_of_one_has_nothing_to_cancel():
    one, many = Terminal(LATER), Terminal(DECIDE, LATER, LATER)

    swap(resolve_by_command, "run_command", Runner())
    resolve_by_command.ask_what_to_do(FIXES[:1], one.step)
    swap(resolve_by_command, "run_command", Runner())
    resolve_by_command.ask_what_to_do(FIXES, many.step)

    assert "cancel the walk-through" not in one.text
    assert "cancel the walk-through" in many.text


def test_a_command_that_worked_says_what_it_did_to_what():
    terminal = Terminal(FIX_ALL)

    swap(resolve_by_command, "run_command", Runner())
    resolve_by_command.ask_what_to_do(FIXES, terminal.step)

    assert "clerk  64 → 3.4.1: reinstalled" in terminal.text
    assert "google-trends: uninstalled" in terminal.text


def test_a_command_that_failed_is_not_confirmed():
    terminal = Terminal(FIX_ALL)

    swap(resolve_by_command, "run_command", Runner(1))
    resolve_by_command.ask_what_to_do(FIXES, terminal.step)

    assert "reinstalled" not in terminal.text


def test_only_what_worked_is_returned():
    runner = Runner()
    left = fixes()

    swap(resolve_by_command, "run_command", runner)
    done = resolve_by_command.ask_what_to_do(left, Terminal(DECIDE, RUN, LATER).step)

    assert done == [left[0]]


def test_a_command_that_failed_returns_nothing():
    left = fixes()

    swap(resolve_by_command, "run_command", Runner(1))

    assert resolve_by_command.ask_what_to_do(left, Terminal(FIX_ALL).step) == []


def test_a_command_that_ran_but_changed_nothing_is_not_returned():
    fix = Fix("Foo 1.0 → 2.0", "", Option("", ("brew", "upgrade", "foo"), "updated"),
              confirm=lambda command: (False, ("Foo: still 1.0", "yellow")))
    terminal = Terminal(RUN)

    swap(resolve_by_command, "run_command", Runner())
    done = resolve_by_command.ask_what_to_do([fix], terminal.step)

    assert done == []
    assert "Foo: still 1.0" in terminal.text


def test_opening_an_app_says_so_but_leaves_it_waiting():
    opening = Option("open Foo and update it manually", ("open", "-a", "/Applications/Foo.app"),
                     "opened", settles=False)
    fix = Fix("Foo 1.0 → 2.0", "", Option("", ("brew", "upgrade", "foo"), "updated"), (opening,))
    terminal = Terminal(REMOVE_IT)

    swap(resolve_by_command, "run_command", Runner())
    done = resolve_by_command.ask_what_to_do([fix], terminal.step)

    assert done == []
    assert "Foo 1.0 → 2.0: opened" in terminal.text
    assert "open Foo and update it manually" in terminal.text
