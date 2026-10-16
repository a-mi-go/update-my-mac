"""The flow every group of things to sort out goes through."""

from update_my_mac.view.prompting import BULLET

import pytest

from update_my_mac.controller import walkthrough
from fake_terminal import Terminal

ALL, EACH, CANCEL = "1", "2", "3"


def ask(terminal, things, all_label="do all"):
    seen = []
    result = walkthrough.batch_or_walkthrough(
        terminal.step,
        things,
        all_label,
        lambda step: seen.append("all") or 10,
        lambda step: seen.append("each") or 20,
    )
    return result, seen


def test_a_group_is_offered_all_each_or_a_way_back():
    terminal = Terminal(CANCEL)

    ask(terminal, ["a", "b"])

    assert f"1) {BULLET}do all" in terminal.text
    assert f"2) {BULLET}decide for each" in terminal.text
    assert "3) ↩ cancel (back to main menu)" in terminal.text


@pytest.mark.parametrize(
    "answer, result, route",
    [
        (ALL, 10, ["all"]),
        (EACH, 20, ["each"]),
        (CANCEL, [], []),
    ],
)
def test_each_answer_takes_its_own_route(answer, result, route):
    assert ask(Terminal(answer), ["a", "b"]) == (result, route)


def test_a_group_of_one_goes_straight_to_the_walk_through():
    terminal = Terminal()

    assert ask(terminal, ["a"]) == (20, ["each"])
    assert terminal.text == ""


def test_a_group_with_nothing_to_do_to_all_goes_straight_to_the_walk_through():
    assert ask(Terminal(), ["a", "b"], all_label=None) == (20, ["each"])


def test_the_way_out_of_a_walk_through_is_there_only_while_others_wait():
    entries = [("x", "do x")]

    assert walkthrough.options_for_single_item(entries, is_walkthrough=False) == entries
    assert (
        walkthrough.options_for_single_item(entries, is_walkthrough=True)[-1]
        == walkthrough.CANCEL_WALK_ENTRY
    )
