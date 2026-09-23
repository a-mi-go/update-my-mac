from pathlib import Path

from rich.text import Text

from update_my_mac import app_decisions, track_apps
from update_my_mac.installed_apps import InstalledApp


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


def app(name, version="1.0"):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"))


def decisions_in(tmp_path):
    return app_decisions.AppDecisions(tmp_path / "apps.json")


def test_nothing_is_asked_when_every_app_is_accounted_for(tmp_path):
    terminal = Terminal()

    ignored = track_apps.run_untracked_menu([], decisions_in(tmp_path), terminal.ask, terminal.out)

    assert ignored == 0
    assert terminal.text == ""


def test_declining_to_go_through_them_changes_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("")

    ignored = track_apps.run_untracked_menu([app("TokenEater")], decisions, terminal.ask, terminal.out)

    assert ignored == 0
    assert decisions.ignored_names() == []
    assert not (tmp_path / "apps.json").exists()


def test_leaving_an_app_alone_is_remembered(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("y", "1")

    ignored = track_apps.run_untracked_menu([app("TokenEater", "5.12.2")], decisions, terminal.ask, terminal.out)

    assert ignored == 1
    assert decisions_in(tmp_path).is_ignored("TokenEater")


def test_keeping_an_app_listed_writes_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("y", "2")

    track_apps.run_untracked_menu([app("TokenEater")], decisions, terminal.ask, terminal.out)

    assert not (tmp_path / "apps.json").exists()


def test_stopping_partway_keeps_what_was_decided_so_far(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("y", "1", "3")

    ignored = track_apps.run_untracked_menu(
        [app("First"), app("Second"), app("Third")], decisions, terminal.ask, terminal.out
    )

    assert ignored == 1
    stored = decisions_in(tmp_path)
    assert stored.ignored_names() == ["First"]
    assert not stored.is_ignored("Third")


def test_apps_already_left_alone_are_not_asked_about_again(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("TokenEater", "5.12.2")
    terminal = Terminal()

    ignored = track_apps.run_untracked_menu([app("TokenEater")], decisions, terminal.ask, terminal.out)

    assert ignored == 0
    assert terminal.text == ""


def test_without_a_terminal_nothing_is_asked(tmp_path):
    terminal = Terminal()

    track_apps.run_untracked_menu(
        [app("TokenEater")], decisions_in(tmp_path), terminal.ask, terminal.out, interactive=False
    )

    assert terminal.text == ""


def test_revisiting_says_so_when_there_is_nothing_to_revisit(tmp_path):
    terminal = Terminal()

    track_apps.run_revisit_menu(decisions_in(tmp_path), terminal.ask, terminal.out)

    assert "No apps are being left alone" in terminal.text


def test_an_app_can_be_brought_back(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.ignore("Beta", "2.0")
    decisions.save()
    terminal = Terminal("2")

    brought_back = track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out)

    assert brought_back == 1
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]
    assert "Beta will be listed again" in terminal.text


def test_answering_nothing_leaves_the_list_as_it_is(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal("0")

    brought_back = track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out)

    assert brought_back == 0
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def test_without_a_terminal_it_only_lists(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal()

    track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out, interactive=False)

    assert "Alpha" in terminal.text
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def raising(exception):
    def ask(_prompt):
        raise exception

    return ask


def test_no_more_input_stops_instead_of_crashing(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal()

    ignored = track_apps.run_untracked_menu(
        [app("TokenEater")], decisions, raising(EOFError()), terminal.out
    )

    assert ignored == 0
    assert not (tmp_path / "apps.json").exists()


def test_ctrl_c_partway_keeps_what_was_decided(tmp_path):
    decisions = decisions_in(tmp_path)
    answers = iter(["y", "1"])

    def ask(_prompt):
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt

    ignored = track_apps.run_untracked_menu(
        [app("First"), app("Second")], decisions, ask, Terminal().out
    )

    assert ignored == 1
    assert decisions_in(tmp_path).ignored_names() == ["First"]


def test_ctrl_c_while_revisiting_changes_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()

    brought_back = track_apps.run_revisit_menu(
        decisions, raising(KeyboardInterrupt()), Terminal().out
    )

    assert brought_back == 0
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]
