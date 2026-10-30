"""The one question that offers everything the run found to sort out."""

from update_my_mac.view.prompting import BULLET

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

    assert resolve_issues.ask_what_to_fix([], terminal.step) == 0
    assert terminal.text == ""


def test_only_what_turned_up_is_offered():
    terminal = Terminal("2")

    resolve_issues.ask_what_to_fix([problem("untracked apps")], terminal.step)

    assert f"1) {BULLET}untracked apps" in terminal.text
    assert (
        "2) " + Text.from_markup(resolve_issues.FIX_EVERYTHING).plain in terminal.text
    )
    assert "3) " + Text.from_markup(resolve_issues.NOT_NOW).plain in terminal.text


def test_picking_one_opens_its_walk_through():
    walked = []
    terminal = Terminal("1", "4")

    dealt_with = resolve_issues.ask_what_to_fix(
        [problem("apps", walked), problem("copies", walked)], terminal.step
    )

    assert walked == ["apps"]
    assert dealt_with == 1


def test_the_question_comes_back_until_someone_is_done():
    # One kind of trouble sorted out says nothing about the others.
    walked = []
    terminal = Terminal("1", "2", "4")

    resolve_issues.ask_what_to_fix(
        [problem("apps", walked), problem("copies", walked)], terminal.step
    )

    assert walked == ["apps", "copies"]


def test_fixing_everything_asks_nothing_further():
    fixed = []
    terminal = Terminal("3")

    dealt_with = resolve_issues.ask_what_to_fix(
        [problem("apps", fixed=fixed, count=8), problem("copies", fixed=fixed)],
        terminal.step,
    )

    assert fixed == ["apps", "copies"]
    assert dealt_with == 9


def test_saying_no_leaves_everything_as_it_is():
    walked, fixed = [], []
    terminal = Terminal("3")

    dealt_with = resolve_issues.ask_what_to_fix(
        [problem("apps", walked, fixed)], terminal.step
    )

    assert (walked, fixed, dealt_with) == ([], [], 0)




def test_ctrl_c_is_left_to_end_the_run():
    # Nothing below the top catches it, so a question stops everything.
    terminal = Terminal(then=KeyboardInterrupt)

    with pytest.raises(KeyboardInterrupt):
        resolve_issues.ask_what_to_fix([problem("apps")], terminal.step)


def test_the_next_menu_draws_the_line_not_this_one():
    terminal = Terminal("3")

    resolve_issues.ask_what_to_fix([problem("apps")], terminal.step)

    assert prompting.SEPARATOR_CHARACTER not in terminal.text


def test_the_line_is_thin_grey_like_the_menu_separators_and_at_most_84_wide():
    # Drawn with characters=... rather than Rule("─"), whose first argument is
    # the title, so it would come out with a character in the middle of it.
    drawn = []
    prompting.print_unwrapped = lambda rule, **options: drawn.append((rule, options))
    prompting.Step().print_separator()

    rule, options = drawn[0]
    assert (rule.characters, rule.style) == ("─", "#666666")
    assert options["width"] == 84
    assert prompting.SEPARATOR_WIDTH == 84


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
    dealt_with = resolve_issues.ask_what_to_fix(
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

    assert (
        resolve_issues.ask_what_to_fix(
            [resolve_issues.Problem("apps", None, out_of_input)], terminal.step
        )
        == 0
    )


def shrinking(things):
    """An entry whose walk-through settles one thing each time it is opened."""

    def refresh(one):
        one.label = f"fix things ({len(things)})"
        return bool(things)

    def walk(_step):
        things.pop()
        return 1

    return resolve_issues.Problem(f"fix things ({len(things)})", walk, walk, refresh)


def test_the_count_follows_what_has_been_dealt_with():
    things = ["a", "b", "c"]
    # Open it, then open it again, then leave.
    terminal = Terminal("1", "1", "3")

    resolve_issues.ask_what_to_fix([shrinking(things)], terminal.step)

    assert terminal.text.count(f"1) {BULLET}fix things (3)") == 1
    assert terminal.text.count(f"1) {BULLET}fix things (2)") == 1
    assert terminal.text.count(f"1) {BULLET}fix things (1)") == 1


def test_an_entry_with_nothing_left_is_no_longer_offered():
    things = ["a"]
    terminal = Terminal("1")

    dealt_with = resolve_issues.ask_what_to_fix([shrinking(things)], terminal.step)

    assert dealt_with == 1
    assert terminal.text.count("Should we sort things out") == 1


def test_the_menu_comes_back_after_a_line_but_does_not_open_with_one():
    terminal = Terminal("1", "2")
    walked = []

    resolve_issues.ask_what_to_fix([problem("apps", walked)], terminal.step)

    first, second = terminal.text.split(
        resolve_issues.QUESTION.replace("[bold]", "").replace("[/]", "")
    )[1:3]
    assert prompting.SEPARATOR_CHARACTER not in terminal.text.split("1) ")[0]
    assert prompting.SEPARATOR_CHARACTER in first


def test_the_report_is_printed_above_the_first_menu_only():
    shown = []
    terminal = Terminal("1", "3")

    resolve_issues.ask_what_to_fix(
        [problem("apps")], terminal.step, above=lambda console: shown.append("report")
    )

    assert shown == ["report"]


def test_the_report_is_printed_even_when_there_is_nothing_to_ask():
    shown = []

    resolve_issues.ask_what_to_fix(
        [], Terminal().step, above=lambda console: shown.append("report")
    )

    assert shown == ["report"]


class Updates:
    def __init__(self, *counts):
        self.counts = list(counts)
        self.changed = 0

    def count(self):
        return self.counts[0]

    def something_changed(self):
        self.changed += 1
        self.counts.pop(0)


def test_the_way_out_says_how_many_updates_the_next_menu_offers_and_follows_a_fix():
    terminal = Terminal("1", "3")
    updates = Updates(5, 3)

    resolve_issues.ask_what_to_fix([problem("apps")], terminal.step, updates=updates)

    way_out = [line for line in terminal.lines if "take care of that later" in line]
    assert "update (5)!" in way_out[0]
    assert "update (3)!" in way_out[1]
    assert updates.changed == 1


def test_a_step_that_dealt_with_nothing_leaves_the_count_alone():
    terminal = Terminal("1", "3")
    updates = Updates(5)

    resolve_issues.ask_what_to_fix([problem("apps", count=0)], terminal.step, updates=updates)

    assert updates.changed == 0
