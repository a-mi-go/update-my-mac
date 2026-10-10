"""The package managers renewing themselves, and the question before it."""

import pytest
from rich.console import Console

from update_my_mac.controller import self_update
from update_my_mac.managers import ManagerUpdate

from fake_run import MANAGER_UPDATES, RecordingShell, answers, printed_by, quiet_console, raising


def pick_and_update(behind, shell, ask, console=None):
    console = console or quiet_console()
    picked = self_update.pick_managers(behind, console, ask)
    return self_update.update(picked, shell, console)

def test_no_manager_update_means_no_question():
    shell = RecordingShell()
    asked = []

    def record(prompt):
        asked.append(prompt)
        return "y"

    assert pick_and_update([], shell, record).failed == []
    assert asked == []

def test_saying_yes_updates_every_manager_that_is_behind():
    shell = RecordingShell()
    run = pick_and_update(MANAGER_UPDATES, shell, answers("y"))

    assert run.failed == []
    assert run.updated == ["brew", "npm"]
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]

def test_anything_but_yes_leaves_the_managers_alone():
    shell = RecordingShell()
    run = pick_and_update(MANAGER_UPDATES, shell, answers(""))

    assert run.failed == []
    # Declining is not the same as every manager being up to date.
    assert run.updated == []
    assert shell.streamed == []

def test_no_terminal_leaves_the_managers_alone():
    shell = RecordingShell()
    pick_and_update(MANAGER_UPDATES, shell, raising(EOFError()))

    assert shell.streamed == []

def test_a_manager_that_fails_to_update_is_reported_back():
    shell = RecordingShell(exit_code=2)
    run = pick_and_update(MANAGER_UPDATES, shell, answers("yes"))

    assert run.failed == ["brew", "npm"]
    assert run.updated == []

def test_the_manager_question_asks_again_when_it_is_not_understood():
    shell = RecordingShell()
    run = pick_and_update(MANAGER_UPDATES, shell, answers("maybe", "y")
    )

    assert run.failed == []
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]

def test_saying_no_outright_leaves_them_alone():
    shell = RecordingShell()

    run = pick_and_update(MANAGER_UPDATES, shell, answers("n"))

    assert run.failed == []
    assert shell.streamed == []

def test_the_manager_step_closes_the_same_way():
    shell = RecordingShell(exit_code=2)
    printed = printed_by(
        lambda console: pick_and_update(MANAGER_UPDATES, shell, answers("y"), console)
    )

    assert "Homebrew: exited with 2" in printed

def test_a_manager_that_never_ran_is_not_given_an_exit_code():
    shell = RecordingShell(exit_code=None)
    printed = printed_by(
        lambda console: pick_and_update(MANAGER_UPDATES, shell, answers("y"), console)
    )

    assert "Homebrew: could not be run" in printed
    assert "None" not in printed

def test_the_question_is_coloured_rather_than_handed_to_input():
    # input() writes its prompt raw, so markup there would be shown as text.
    console = Console(width=80, force_terminal=True)
    asked = []

    with console.capture() as captured:
        self_update._confirmed(console, lambda prompt: asked.append(prompt) or "n")

    assert asked == [""]
    # 36 is cyan, and the whole question wears it.
    assert "\x1b[36m" in captured.get()
    assert "Update them now?" in captured.get()

def test_the_keys_are_asked_first_where_the_terminal_allows_it(monkeypatch):
    monkeypatch.setattr(self_update.keys, "available", lambda: True)
    monkeypatch.setattr(self_update.keys, "confirm", lambda question, default: True)

    assert self_update._confirmed(Console(width=80), None)

def test_a_menu_that_will_not_draw_falls_back_to_the_question(monkeypatch):
    def refuse(question, default):
        raise self_update.keys.Unusable("no terminal capability")

    monkeypatch.setattr(self_update.keys, "available", lambda: True)
    monkeypatch.setattr(self_update.keys, "confirm", refuse)
    console = Console(width=80)

    with console.capture() as captured:
        said = self_update._confirmed(console, lambda prompt: "y")

    assert said
    assert "could not be drawn" in captured.get()

def test_the_yes_or_no_hint_survives_the_markup():
    # rich reads [y/N] as a style and swallows it unless the bracket is escaped.
    console = Console(width=80, no_color=True)

    with console.capture() as captured:
        self_update._confirmed(console, lambda prompt: "n")

    assert "[y/N]" in captured.get()

def test_the_question_is_bold_and_the_marker_coloured():
    # rich's own highlighter picks brackets out of a line and bolds them.
    console = Console(width=80, force_terminal=True)

    with console.capture() as captured:
        self_update._confirmed(console, lambda prompt: "n")

    # The question is bold, the marker is cyan, and the hint is neither:
    # dimmed it was barely readable.
    printed = captured.get()
    assert "\x1b[1mUpdate them now?" in printed
    assert "\x1b[36m" in printed
    assert "\x1b[2m" not in printed

def test_a_question_that_defaults_to_yes_says_so_and_takes_an_empty_answer():
    console = Console(width=80, no_color=True)

    with console.capture() as captured:
        said = self_update._pick_yes_or_no(console, lambda prompt: "", "Keep it?", default=True)

    assert said
    assert "[Y/n]" in captured.get()

def test_a_line_is_broken_after_the_answer():
    # The question is printed without a line break, because the answer is
    # typed on the same line. In a terminal the Enter that ends the answer
    # breaks it; here nothing does, so this is the one that gets printed.
    console = Console(width=80, no_color=True)

    with console.capture() as captured:
        self_update._confirmed(console, lambda prompt: "n")

    assert captured.get().endswith("\n")
    assert captured.get().count("\n") == 1
