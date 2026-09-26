"""Restarting an app that is running a version no longer on disk."""

import plistlib

from rich.text import Text

from update_my_mac import restart_apps
from update_my_mac.running_apps import StillRunningOld


class Terminal:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.lines = []

    def ask(self, prompt):
        self.lines.append(prompt)
        return self.answers.pop(0)

    def out(self, *parts, **_):
        self.lines.append(Text.from_markup(" ".join(str(part) for part in parts)).plain)

    @property
    def text(self):
        return "\n".join(self.lines)


def app_at(tmp_path, bundle_id="com.example.thing", name="Thing"):
    app = tmp_path / f"{name}.app"
    (app / "Contents").mkdir(parents=True)
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


def no_waiting(_seconds):
    pass


def test_an_app_is_quit_and_started_again(tmp_path):
    shell = AppleShell()

    done, message = restart_apps.restart(app_at(tmp_path), shell, no_waiting)
    assert done
    assert shell.asked_to_quit and shell.opened
    assert "running the version on disk" in message


def test_an_app_that_will_not_quit_is_left_alone(tmp_path):
    # Usually a dialog about unsaved work, which is not ours to answer.
    shell = AppleShell(stops=False)

    done, message = restart_apps.restart(app_at(tmp_path), shell, no_waiting)
    assert not done
    assert not shell.opened
    assert "unsaved work" in message


def test_an_app_that_refuses_the_request_is_not_forced(tmp_path):
    shell = AppleShell(quits=False)

    done, message = restart_apps.restart(app_at(tmp_path), shell, no_waiting)
    assert not done
    assert "would not take the request" in message


def test_an_app_without_a_bundle_id_is_not_guessed_at(tmp_path):
    shell = AppleShell()

    done, message = restart_apps.restart(app_at(tmp_path, bundle_id=""), shell, no_waiting)
    assert not done
    assert not shell.asked_to_quit


def test_a_restart_that_does_not_come_back_says_so(tmp_path):
    shell = AppleShell(opens=False)

    done, message = restart_apps.restart(app_at(tmp_path), shell, no_waiting)
    assert not done
    assert "starting it again did not work" in message


def restarting(done, message="done"):
    return lambda _app: (done, message)


def test_the_menu_offers_a_restart(tmp_path):
    terminal = Terminal("1")
    restarted = restart_apps.run_restart_menu(
        [app_at(tmp_path)], restarting(True), terminal.ask, terminal.out
    )

    assert restarted == 1
    assert "1) quit it and start it again" in terminal.text


def test_leaving_it_running_restarts_nothing(tmp_path):
    terminal = Terminal("2")

    assert restart_apps.run_restart_menu(
        [app_at(tmp_path)], restarting(True), terminal.ask, terminal.out
    ) == 0


def test_stopping_partway_leaves_the_rest(tmp_path):
    terminal = Terminal("3")

    assert restart_apps.run_restart_menu(
        [app_at(tmp_path), app_at(tmp_path, name="Other")],
        restarting(True),
        terminal.ask,
        terminal.out,
    ) == 0


def test_a_restart_that_failed_is_not_counted(tmp_path):
    terminal = Terminal("1")

    restarted = restart_apps.run_restart_menu(
        [app_at(tmp_path)], restarting(False, "it would not quit"), terminal.ask, terminal.out
    )
    assert restarted == 0
    assert "it would not quit" in terminal.text


def test_no_terminal_means_nothing_is_asked(tmp_path):
    terminal = Terminal()

    assert restart_apps.run_restart_menu(
        [app_at(tmp_path)], restarting(True), terminal.ask, terminal.out, interactive=False
    ) == 0
    assert terminal.text == ""
