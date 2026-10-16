"""The package managers renewing themselves, and the question before it."""

import pytest

from update_my_mac.controller import self_update
from update_my_mac.managers import ManagerUpdate

from update_my_mac.view import arrow_menu
from update_my_mac.view.prompting import BULLET

from fake_run import use_shell, MANAGER_UPDATES, RecordingShell, answer_with, answers, printed_by, raising


UPDATE, NOT_NOW = "1", "2"


def pick_and_update(behind, shell, ask):
    answer_with(ask)
    use_shell(shell)
    return self_update.update_managers(behind)

def test_no_manager_update_means_no_question():
    shell = RecordingShell()
    asked = []

    def record(prompt):
        asked.append(prompt)
        return UPDATE

    assert pick_and_update([], shell, record).failed == []
    assert asked == []

def test_saying_yes_updates_every_manager_that_is_behind():
    shell = RecordingShell()
    run = pick_and_update(MANAGER_UPDATES, shell, answers(UPDATE))

    assert run.failed == []
    assert run.updated == ["brew", "npm"]
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]

def test_an_empty_answer_is_not_taken_for_yes():
    shell = RecordingShell()
    run = pick_and_update(MANAGER_UPDATES, shell, answers("", NOT_NOW))

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
    run = pick_and_update(MANAGER_UPDATES, shell, answers(UPDATE))

    assert run.failed == ["brew", "npm"]
    assert run.updated == []

def test_the_manager_question_asks_again_when_it_is_not_understood():
    shell = RecordingShell()
    run = pick_and_update(MANAGER_UPDATES, shell, answers("maybe", UPDATE)
    )

    assert run.failed == []
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]

def test_saying_no_outright_leaves_them_alone():
    shell = RecordingShell()

    run = pick_and_update(MANAGER_UPDATES, shell, answers(NOT_NOW))

    assert run.failed == []
    assert shell.streamed == []

def test_the_manager_step_closes_the_same_way():
    shell = RecordingShell(exit_code=2)
    printed = printed_by(
        lambda: pick_and_update(MANAGER_UPDATES, shell, answers(UPDATE))
    )

    assert "Homebrew: exited with 2" in printed

def test_a_manager_that_never_ran_is_not_given_an_exit_code():
    shell = RecordingShell(exit_code=None)
    printed = printed_by(
        lambda: pick_and_update(MANAGER_UPDATES, shell, answers(UPDATE))
    )

    assert "Homebrew: could not be run" in printed
    assert "None" not in printed

def test_without_arrow_keys_the_question_is_answered_by_number():
    answer_with(answers(NOT_NOW))
    printed = printed_by(self_update._ask_yes_or_no)

    assert "Update them now?" in printed
    assert f"1) {BULLET}yes" in printed
    assert f"2) {BULLET}no" in printed


def test_the_arrow_keys_are_used_where_the_terminal_allows_it(monkeypatch):
    seen = []
    monkeypatch.setattr(arrow_menu, "can_be_drawn", lambda: True)
    monkeypatch.setattr(arrow_menu, "yes_or_no",
                        lambda question, default: seen.append((question, default)) or True)

    assert self_update._ask_yes_or_no()
    assert seen == [("Update them now?", True)]


def test_a_menu_that_will_not_draw_falls_back_to_numbers(monkeypatch):
    def refuse(question, default):
        raise arrow_menu.Unusable("no terminal capability")

    monkeypatch.setattr(arrow_menu, "can_be_drawn", lambda: True)
    monkeypatch.setattr(arrow_menu, "yes_or_no", refuse)
    said = []
    answer_with(answers(UPDATE))
    printed = printed_by(lambda: said.append(self_update._ask_yes_or_no()))

    assert said == [True]
    assert "could not be drawn" in printed


def test_a_line_is_broken_after_the_answer():
    # The question is printed without a line break, because the answer is
    # typed on the same line. In a terminal the Enter that ends the answer
    # breaks it; here nothing does, so this is the one that gets printed.
    answer_with(answers(NOT_NOW))
    printed = printed_by(self_update._ask_yes_or_no)

    assert printed.endswith("\n\n")


def test_a_manager_whose_check_failed_is_not_offered():
    shell = RecordingShell()
    behind = [ManagerUpdate("npm", "npm (global)", error_message="ENOTFOUND")]

    run = pick_and_update(behind, shell, answers(UPDATE))

    assert run.updated == []
    assert shell.streamed == []
