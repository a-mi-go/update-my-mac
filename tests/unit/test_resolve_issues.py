"""The one question that offers everything the run found to sort out."""

import pytest
from rich.rule import Rule
from rich.text import Text

from update_my_mac.controller import resolve_issues
from update_my_mac.view import prompting
from fake_terminal import Terminal


def problem(label, walked=None, fixed=None, count=1):
    def note(seen):
        def called(_step):
            if seen is not None:
                seen.append(label)
            return count

        return called

    return resolve_issues.Problem(label, note(walked), note(fixed))


def test_nothing_found_means_nothing_is_asked():
    terminal = Terminal()

    assert resolve_issues.run_resolve_menu([], terminal.step) == 0
    assert terminal.text == ""


def test_only_what_turned_up_is_offered():
    terminal = Terminal("2")

    resolve_issues.run_resolve_menu([problem("untracked apps")], terminal.step)

    assert "1) untracked apps" in terminal.text
    assert "2) " + resolve_issues.FIX_EVERYTHING in terminal.text
    assert f"3) {prompting.WAY_OUT}{resolve_issues.NOT_NOW}" in terminal.text


def test_picking_one_opens_its_walk_through():
    walked = []
    terminal = Terminal("1", "4")

    dealt_with = resolve_issues.run_resolve_menu(
        [problem("apps", walked), problem("copies", walked)], terminal.step
    )

    assert walked == ["apps"]
    assert dealt_with == 1


def test_the_question_comes_back_until_someone_is_done():
    # One kind of trouble sorted out says nothing about the others.
    walked = []
    terminal = Terminal("1", "2", "4")

    resolve_issues.run_resolve_menu(
        [problem("apps", walked), problem("copies", walked)], terminal.step
    )

    assert walked == ["apps", "copies"]


def test_fixing_everything_asks_nothing_further():
    fixed = []
    terminal = Terminal("3")

    dealt_with = resolve_issues.run_resolve_menu(
        [problem("apps", fixed=fixed, count=8), problem("copies", fixed=fixed)],
        terminal.step,
    )

    assert fixed == ["apps", "copies"]
    assert dealt_with == 9


def test_saying_no_leaves_everything_as_it_is():
    walked, fixed = [], []
    terminal = Terminal("3")

    dealt_with = resolve_issues.run_resolve_menu(
        [problem("apps", walked, fixed)], terminal.step
    )

    assert (walked, fixed, dealt_with) == ([], [], 0)


def test_without_a_terminal_nothing_is_asked():
    terminal = Terminal()

    resolve_issues.run_resolve_menu([problem("apps")], terminal.step, interactive=False)

    assert terminal.text == ""


def test_ctrl_c_is_left_to_end_the_run():
    # Nothing below the top catches it, so a question stops everything.
    terminal = Terminal(then=KeyboardInterrupt)

    with pytest.raises(KeyboardInterrupt):
        resolve_issues.run_resolve_menu([problem("apps")], terminal.step)


def test_a_line_closes_the_phase():
    # The question and everything under it belong together, and the update
    # menu below is a different part of the run.
    for answers in (("3",), ("1", "3")):
        terminal = Terminal(*answers)

        resolve_issues.run_resolve_menu([problem("apps")], terminal.step)

        assert "-" * prompting.CLOSING_WIDTH in terminal.text


def test_the_line_comes_after_what_was_fixed():
    terminal = Terminal("2")

    def took_it_over(step):
        step.say("took it over")
        return 1

    resolve_issues.run_resolve_menu([resolve_issues.Problem("apps", None, took_it_over)], terminal.step)

    line = "-" * prompting.CLOSING_WIDTH
    assert terminal.text.index(line) > terminal.text.index("took it over")


def test_the_line_is_dashed_white_and_at_most_84_wide():
    # Drawn with characters="-" rather than Rule("-"), whose first argument is
    # the title, so it would come out with a dash in the middle of it.
    drawn = []
    prompting.Step(lambda rule, **options: drawn.append((rule, options))).close_section()

    rule, options = drawn[0]
    assert (rule.characters, rule.style) == ("-", "white")
    assert options["width"] == 84
    assert prompting.CLOSING_WIDTH == 84


def stopping(exception):
    def fix_all(_step):
        raise exception

    return fix_all


def test_an_interruption_keeps_what_fixing_everything_already_did():
    # What came before it still happened, and the run has to know, because
    # that is what decides whether the managers are checked again.
    def sorted_out(_step):
        return 2

    terminal = Terminal("3")
    dealt_with = resolve_issues.run_resolve_menu(
        [
            resolve_issues.Problem("apps", None, sorted_out),
            resolve_issues.Problem("copies", None, stopping(prompting.Stopped)),
        ],
        terminal.step,
    )

    assert dealt_with == 2


def test_a_step_that_ran_out_of_input_does_not_take_the_others_with_it():
    def out_of_input(_step):
        raise prompting.Stopped

    terminal = Terminal("2")

    assert resolve_issues.run_resolve_menu(
        [resolve_issues.Problem("apps", None, out_of_input)], terminal.step
    ) == 0
