"""Restarting an app that is running a version no longer on disk."""

from update_my_mac.view.prompting import BULLET
from fake_run import swap, use_shell

import plistlib

import pytest

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from update_my_mac.view import prompting
from update_my_mac.controller import restart_apps
from update_my_mac.checks.running_apps import StillRunningOld
from fake_terminal import Terminal

WIDTH = 60


def app_at(tmp_path, bundle_id="com.example.thing", name="Thing"):
    app = tmp_path / f"{name}.app"
    (app / "Contents").mkdir(parents=True, exist_ok=True)
    if bundle_id:
        with open(app / "Contents" / "Info.plist", "wb") as plist:
            plistlib.dump({"CFBundleIdentifier": bundle_id}, plist)
    return StillRunningOld(name, app, 42, 1000.0, 2000.0)


class AppleShell:
    def __init__(self, quits=True, stops=True, opens=True):
        self.quits = quits
        self.stops = stops
        self.opens = opens
        self.asked_to_quit = False
        self.opened = False
        self.looks = 0

    def ask_application_to_quit(self, bundle_id):
        self.asked_to_quit = True
        return self.quits

    def is_running(self, pid):
        self.looks += 1
        # Gone from the second look, so the waiting loop is exercised.
        return not (self.stops and self.looks > 1)

    def open_application(self, path):
        self.opened = True
        return self.opens


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(restart_apps.time, "sleep", lambda seconds: None)


def test_an_app_is_quit_and_started_again(tmp_path):
    shell = AppleShell()

    use_shell(shell)
    done, message = restart_apps.restart(app_at(tmp_path))
    assert done
    assert shell.asked_to_quit and shell.opened
    assert "running the version on disk" in message


def test_an_app_that_will_not_quit_is_left_alone(tmp_path):
    # Usually a dialog about unsaved work, which is not ours to answer.
    shell = AppleShell(stops=False)

    use_shell(shell)
    done, message = restart_apps.restart(app_at(tmp_path))
    assert not done
    assert not shell.opened
    assert "unsaved work" in message


def test_an_app_that_refuses_the_request_is_not_forced(tmp_path):
    shell = AppleShell(quits=False)

    use_shell(shell)
    done, message = restart_apps.restart(app_at(tmp_path))
    assert not done
    assert "would not take the request" in message


def test_an_app_without_a_bundle_id_is_not_guessed_at(tmp_path):
    shell = AppleShell()

    use_shell(shell)
    done, message = restart_apps.restart(
        app_at(tmp_path, bundle_id=""))
    assert not done
    assert not shell.asked_to_quit


def test_a_restart_that_does_not_come_back_says_so(tmp_path):
    shell = AppleShell(opens=False)

    use_shell(shell)
    done, message = restart_apps.restart(app_at(tmp_path))
    assert not done
    assert "starting it again did not work" in message


def restarting(done, message="done"):
    def restart(_app):
        return done, message

    return restart


def recording(restarted, done=True, message="done"):
    """A restart that remembers which app it was asked about."""

    def restart(app):
        restarted.append(app.file_stem)
        return done, message

    return restart


def two_apps(tmp_path):
    return [app_at(tmp_path), app_at(tmp_path, name="Other")]


def test_the_menu_offers_restarting_all_deciding_or_cancelling(tmp_path):
    terminal = Terminal("3")

    swap(restart_apps, "restart", restarting(True))
    restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    assert f"1) {BULLET}restart all" in terminal.text
    assert f"2) {BULLET}decide for each" in terminal.text
    assert f"3) {prompting.WAY_OUT}cancel (back to main menu)" in terminal.text
    # The old walk-through wording is what this question replaced.
    assert "Going through" not in terminal.text


def test_the_menu_does_not_repeat_the_count(tmp_path):
    # The heading above it has already said how many, and how they are running.
    terminal = Terminal("3")

    swap(restart_apps, "restart", restarting(True))
    restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    assert "apps running an old version" not in terminal.text


def test_restarting_everyone_at_once_takes_a_single_answer(tmp_path):
    terminal = Terminal("1")
    restarted = []

    swap(restart_apps, "restart", recording(restarted))
    count = restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    assert len(count) == 2
    assert restarted == ["Thing", "Other"]
    assert terminal.text.count("> ") == 1


def test_leaving_them_all_running_restarts_nothing(tmp_path):
    terminal = Terminal("3")
    restarted = []

    swap(restart_apps, "restart", recording(restarted))
    count = restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    assert len(count) == 0
    assert restarted == []
    # One question, not one per app: the answer covered all of them.
    assert terminal.text.count("> ") == 1


def test_going_through_them_one_at_a_time(tmp_path):
    terminal = Terminal("2", "1", "2")
    restarted = []

    swap(restart_apps, "restart", recording(restarted))
    count = restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    assert len(count) == 1
    assert restarted == ["Thing"]
    assert f"1) {BULLET}restart" in terminal.text
    assert f"2) {BULLET}leave it running" in terminal.text
    assert f"3) {prompting.WAY_OUT}cancel the walk-through" in terminal.text


def test_a_restart_that_worked_is_green_and_one_that_did_not_is_red(tmp_path):
    # The colour is the fastest way to see which apps still need attention.
    console = Console(force_terminal=True, color_system="standard", width=200)

    def printed(answer, done, message):
        prompting.print_unwrapped = lambda renderable, **options: console.print(renderable, **options)
        prompting.read_answer = Terminal(answer).ask
        with console.capture() as captured:
            swap(restart_apps, "restart", restarting(done, message))
            restart_apps.ask_what_to_do([app_at(tmp_path)], prompting.Step())
        return captured.get()

    assert "\x1b[32mQuit and started again." in printed(
        "1", True, "Quit and started again."
    )
    assert "\x1b[31mIt is still running." in printed("1", False, "It is still running.")


def test_nothing_to_restart_means_nothing_is_asked():
    terminal = Terminal("3")

    swap(restart_apps, "restart", restarting(True))
    restart_apps.ask_what_to_do([], terminal.step)

    assert terminal.text == ""


def test_stopping_partway_leaves_the_rest(tmp_path):
    terminal = Terminal("2", "1", "3")
    restarted = []

    swap(restart_apps, "restart", recording(restarted))
    count = restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    assert len(count) == 1
    assert restarted == ["Thing"]


def test_an_answer_that_means_nothing_is_asked_again(tmp_path):
    terminal = Terminal("", "yes", "1")
    restarted = []

    swap(restart_apps, "restart", recording(restarted))
    count = restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    # An empty line must not be taken for a decision, least of all to quit apps.
    assert len(count) == 2
    assert terminal.text.count("> ") == 3


def test_nothing_to_answer_with_stops_the_question(tmp_path):
    terminal = Terminal(then=EOFError)

    swap(restart_apps, "restart", restarting(True))
    assert (
        restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)
        == []
    )
    # Asked once, then left alone rather than asked again about every app.
    assert len([line for line in terminal.lines if line.endswith("> ")]) == 1


def test_a_restart_that_failed_is_not_counted(tmp_path):
    terminal = Terminal("1")

    swap(restart_apps, "restart", restarting(False, "it would not quit"))
    restarted = restart_apps.ask_what_to_do([app_at(tmp_path)], terminal.step)

    assert len(restarted) == 0
    assert "it would not quit" in terminal.text


def test_one_refusing_does_not_stop_the_others(tmp_path):
    terminal = Terminal("1")

    def restart(app):
        return (
            app.file_stem != "Other",
            "done" if app.file_stem != "Other" else "it would not quit",
        )

    swap(restart_apps, "restart", restart)
    restarted = restart_apps.ask_what_to_do(two_apps(tmp_path), terminal.step)

    assert len(restarted) == 1




def printed_lines(terminal, apps, restart_one=None):
    """Run the menu on these apps, and hand back the printed lines."""
    swap(restart_apps, "restart", restart_one or restarting(True, "restarted"))
    restart_apps.ask_what_to_do(apps, terminal.step)
    return terminal.lines


def indent_of(line):
    return len(line) - len(line.lstrip())


def test_a_result_is_printed_in_line_with_the_question_it_answers(tmp_path):
    # It used to be written at its own hardcoded indent, so in the walk-through
    # the result sat left of the question it belonged to.
    terminal = Terminal("1")
    lines = printed_lines(terminal, [app_at(tmp_path)])

    # "1) ◇ restart" on its own is the walk-through's, the top menu says
    # "1) ◇ restart all", so the options are not confused for one another.
    option = next(
        line for line in lines if line.rstrip().endswith(f"1) {BULLET}restart")
    )
    result = next(line for line in lines if "restarted" in line)
    heading = next(line for line in lines if "Thing" in line)

    # The result stands where the options stood, and the app's name one step
    # out from both, which is where the question that opened them stands.
    assert indent_of(result) == indent_of(option)
    assert indent_of(heading) == indent_of(option) - 2


def test_restarting_them_all_prints_results_under_their_names(tmp_path):
    terminal = Terminal("1")
    lines = printed_lines(terminal, [app_at(tmp_path)])

    name = next(line for line in lines if "Thing" in line)
    result = next(line for line in lines if "restarted" in line)

    assert indent_of(result) == indent_of(name) + 2


def test_after_an_update_the_replaced_apps_are_named_above_the_menu(tmp_path):
    terminal = Terminal("3")

    swap(restart_apps, "restart", restarting(True))
    restart_apps.ask_after_the_update(two_apps(tmp_path), terminal.step)

    assert terminal.lines[2] == "Updated but the old version is still running"
    assert [line.strip() for line in terminal.lines[3:5]] == ["Thing", "Other"]
    assert f"1) {BULLET}restart all" in terminal.text


def test_nothing_is_said_when_no_update_replaced_a_running_app():
    terminal = Terminal()

    swap(restart_apps, "restart", restarting(True))
    assert restart_apps.ask_after_the_update([], terminal.step) == []
    assert terminal.text == ""


def test_a_single_app_goes_straight_to_its_own_question(tmp_path):
    terminal = Terminal("2")

    swap(restart_apps, "restart", restarting(True, "restarted"))
    restart_apps.ask_what_to_do([app_at(tmp_path)], terminal.step)

    assert "restart all" not in terminal.text
    assert "Thing" in terminal.text


def test_one_app_has_no_walk_through_to_cancel(tmp_path):
    one, two = Terminal("2"), Terminal("2", "2", "2")

    swap(restart_apps, "restart", restarting(True, "restarted"))
    restart_apps.ask_what_to_do([app_at(tmp_path)], one.step)
    swap(restart_apps, "restart", restarting(True, "restarted"))
    restart_apps.ask_what_to_do([app_at(tmp_path, name="A"), app_at(tmp_path, name="B")], two.step)

    assert "cancel the walk-through" not in one.text
    assert "cancel the walk-through" in two.text


def test_what_the_old_process_has_been_doing_stands_on_the_apps_own_line(tmp_path):
    terminal = Terminal("2")

    swap(restart_apps, "restart", restarting(True, "restarted"))
    restart_apps.ask_what_to_do([app_at(tmp_path)], terminal.step)

    line = next(line for line in terminal.lines if "Thing" in line)
    assert "running since" in line


def test_the_numbered_menu_keeps_the_note_on_the_apps_line(tmp_path):
    terminal = Terminal("2")

    swap(restart_apps, "restart", restarting(True, "restarted"))
    restart_apps.ask_what_to_do([app_at(tmp_path)], terminal.step)

    line = next(line for line in terminal.lines if "Thing" in line)
    assert "running since" in line


def test_the_offer_after_an_update_is_set_apart_by_a_line(tmp_path):
    terminal = Terminal("3")

    swap(restart_apps, "restart", restarting(True))
    restart_apps.ask_after_the_update(two_apps(tmp_path), terminal.step)

    assert prompting.SEPARATOR_CHARACTER in terminal.lines[1]


def test_each_app_in_a_walk_through_starts_after_a_line(tmp_path):
    terminal = Terminal("2", "2", "2")

    swap(restart_apps, "restart", restarting(True, "restarted"))
    restart_apps.ask_what_to_do([app_at(tmp_path, name="A"), app_at(tmp_path, name="B")], terminal.step)

    # Blank line, the line, then the app's question.
    first = next(
        i
        for i, line in enumerate(terminal.lines)
        if "A" in line and "running since" in line
    )
    assert prompting.SEPARATOR_CHARACTER in terminal.lines[first - 1]
    assert terminal.lines[first - 2] == ""
