"""Closing the running apps an update replaces, and starting them again afterwards."""

from pathlib import Path
from types import SimpleNamespace

from fake_run import swap, use_shell
from fake_terminal import Terminal

from update_my_mac.checks import installed_apps, running_apps
from update_my_mac.checks.running_apps import RunningApp
from update_my_mac.controller import close_apps, restart_apps


def entry(keys, *outdated):
    return SimpleNamespace(keys=keys, outdated=list(outdated))


def apps(*names):
    return [RunningApp(name, Path(f"/Applications/{name}.app"), pid) for pid, name in enumerate(names)]


def quitting(closed, done=True):
    def quit_app(app):
        closed.append(app.file_stem)
        return done, "Quit." if done else "It is still running."

    return quit_app


class Opener:
    def __init__(self, opens=True):
        self.opens = opens
        self.opened = []

    def open_application(self, path):
        self.opened.append(path.stem)
        return self.opens


def test_an_app_store_name_also_counts_up_to_its_colon():
    names = close_apps.app_file_names([entry(["mas"], "Todoist: To-Do List  9.0 → 9.1")])

    assert names == {"Todoist: To-Do List.app", "Todoist.app"}


def test_homebrew_packages_are_named_by_the_apps_their_casks_install():
    asked = []
    swap(installed_apps, "app_names_of_casks", lambda packages: asked.extend(packages) or {"Firefox.app"})

    names = close_apps.app_file_names([entry(["brew"], "firefox  140 → 141", "jq  1.7 → 1.8")])

    assert names == {"Firefox.app"}
    assert asked == ["firefox", "jq"]


def test_nothing_running_asks_nothing():
    terminal = Terminal()
    swap(running_apps, "find_named", lambda names: [])

    assert close_apps.ask_before_the_update([entry(["mas"], "Todoist  9.0 → 9.1")], terminal.step) == []
    assert terminal.text == ""


def test_closing_all_takes_one_answer_and_returns_the_apps_that_quit():
    terminal = Terminal("1")
    closed = []
    swap(running_apps, "find_named", lambda names: apps("Firefox", "Todoist"))
    swap(restart_apps, "quit_app", quitting(closed))

    result = close_apps.ask_before_the_update([entry(["brew"])], terminal.step)

    assert [app.file_stem for app in result] == ["Firefox", "Todoist"]
    assert closed == ["Firefox", "Todoist"]
    assert "unsaved work can be lost" in terminal.text
    assert terminal.text.count("> ") == 1


def test_an_app_that_would_not_quit_is_not_returned():
    terminal = Terminal("1")
    swap(running_apps, "find_named", lambda names: apps("Firefox", "Todoist"))
    swap(restart_apps, "quit_app", quitting([], done=False))

    assert close_apps.ask_before_the_update([entry(["brew"])], terminal.step) == []


def test_going_through_them_closes_only_the_ones_chosen():
    terminal = Terminal("2", "1", "2")
    closed = []
    swap(running_apps, "find_named", lambda names: apps("Firefox", "Todoist"))
    swap(restart_apps, "quit_app", quitting(closed))

    result = close_apps.ask_before_the_update([entry(["brew"])], terminal.step)

    assert [app.file_stem for app in result] == ["Firefox"]
    assert closed == ["Firefox"]


def test_a_single_app_is_asked_about_without_the_question_about_all():
    terminal = Terminal("1")
    closed = []
    swap(running_apps, "find_named", lambda names: apps("Firefox"))
    swap(restart_apps, "quit_app", quitting(closed))

    close_apps.ask_before_the_update([entry(["brew"])], terminal.step)

    assert closed == ["Firefox"]
    assert "close all" not in terminal.text


def test_each_closed_app_is_offered_to_start_again():
    terminal = Terminal("1", "2")
    shell = use_shell(Opener())

    started = close_apps.ask_to_start_again(apps("Firefox", "Todoist"), terminal.step)

    assert [app.file_stem for app in started] == ["Firefox"]
    assert shell.opened == ["Firefox"]
    assert "Start Firefox again?" in terminal.text
    assert "Started." in terminal.text


def test_an_app_that_does_not_start_again_says_so():
    terminal = Terminal("1")
    use_shell(Opener(opens=False))

    assert close_apps.ask_to_start_again(apps("Firefox"), terminal.step) == []
    assert "Starting it did not work." in terminal.text


def test_nothing_closed_asks_nothing_afterwards():
    terminal = Terminal()

    assert close_apps.ask_to_start_again([], terminal.step) == []
    assert terminal.text == ""
