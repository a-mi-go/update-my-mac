"""The indenting and the numbering that every walk-through is built out of."""

from update_my_mac.view.prompting import BULLET

from update_my_mac.view import prompting
from update_my_mac.view.prompting import STEP, WAY_OUT, Markup, Stopped

from fake_terminal import Terminal


def test_a_step_prints_at_its_own_margin():
    terminal = Terminal()

    terminal.step.print_indented("What should we do with them?")
    terminal.step.inside().print_indented("What should we do with them?")

    assert terminal.lines == [
        "What should we do with them?",
        f"{STEP}What should we do with them?",
    ]


def test_a_blank_line_is_not_indented():
    # Indenting it would leave trailing spaces at the end of the line.
    terminal = Terminal()

    terminal.step.inside().print_empty_line()

    assert terminal.lines == [""]


def test_the_options_stand_one_step_inside_the_question():
    terminal = Terminal("1")

    terminal.step.choose([("a", "one"), ("b", "two")], "Which one?")

    assert terminal.lines[:4] == [
        "Which one?",
        "",
        f"{STEP}1) {BULLET}one",
        f"{STEP}2) {BULLET}two",
    ]


def test_the_last_option_is_not_marked_for_being_the_last():
    terminal = Terminal("1")

    terminal.step.choose(
        [("a", "one"), ("b", f"{WAY_OUT}cancel"), ("c", "something else")], "Which one?"
    )

    assert f"{STEP}2) {WAY_OUT}cancel" in terminal.text
    assert f"{STEP}3) {BULLET}something else" in terminal.text


def test_a_menu_without_a_question_still_takes_the_line_for_it():
    terminal = Terminal("1")

    terminal.step.choose([("a", "one"), ("b", "two")])

    assert terminal.lines[:2] == ["", f"{STEP}1) {BULLET}one"]


def test_the_prompt_stands_in_the_column_the_question_does():
    # What you type is a number, but the question is what you are answering.
    terminal = Terminal("1")

    terminal.step.inside().choose([("a", "one")])

    assert terminal.lines[-1] == f"{STEP}> "


def test_the_key_comes_back_rather_than_the_number():
    terminal = Terminal("2")

    assert terminal.step.choose([("a", "one"), ("b", "two")]) == "b"


def test_an_answer_outside_the_list_is_asked_again():
    terminal = Terminal("0", "9", "1")

    terminal.step.choose([("a", "one"), ("b", "two")])

    assert terminal.text.count("Didn't catch that") == 2


def test_the_end_of_the_input_stops_the_conversation():
    terminal = Terminal(then=EOFError)

    try:
        terminal.step.choose([("a", "one")])
    except Stopped:
        return
    raise AssertionError("the step should have stopped")


def test_going_inside_leaves_the_step_it_came_from_alone():
    terminal = Terminal()
    step = terminal.step

    step.inside().inside()
    step.print_indented("still here")

    assert terminal.lines == ["still here"]


def test_a_menu_with_nothing_in_it_is_a_mistake():
    # Asking would loop forever, because no answer could ever be right.
    terminal = Terminal()

    try:
        terminal.step.choose([])
    except ValueError:
        return
    raise AssertionError("an empty menu should not be offered")


def test_the_menu_asks_the_question_it_was_given():
    terminal = Terminal("1")

    chosen = terminal.step.choose([("a", "one"), ("b", "two")], "Which one?")

    assert chosen == "a"
    assert terminal.lines[0] == "Which one?"


def interrupting(*answers):
    """A terminal that presses Ctrl-C before each of these answers."""
    given = list(answers)

    def ask(_prompt):
        answer = given.pop(0)
        if answer is INTERRUPT:
            raise KeyboardInterrupt
        if answer is NO_MORE_INPUT:
            raise EOFError
        return answer

    return ask


INTERRUPT = object()
NO_MORE_INPUT = object()


def test_the_first_ctrl_c_only_warns():
    terminal = Terminal()
    step = terminal.answering(interrupting(INTERRUPT, "1"))

    assert step.choose([("a", "one"), ("b", "two")]) == "a"
    assert "Press Ctrl-C again" in terminal.text


def test_the_second_ctrl_c_in_a_row_ends_the_run():
    step = Terminal().answering(interrupting(INTERRUPT, INTERRUPT))

    try:
        step.choose([("a", "one"), ("b", "two")])
    except KeyboardInterrupt:
        return
    raise AssertionError("the second one should have been left to end the run")


def test_an_answer_in_between_clears_the_warning():
    # One Ctrl-C is easy to hit by accident; an answer says it was not meant.
    terminal = Terminal()
    step = terminal.answering(interrupting(INTERRUPT, "1", INTERRUPT, "2"))

    assert step.choose([("a", "one"), ("b", "two")]) == "a"
    assert step.choose([("a", "one"), ("b", "two")]) == "b"
    assert terminal.text.count("Press Ctrl-C again") == 2


def test_a_question_that_ran_out_of_input_clears_the_warning():
    terminal = Terminal()
    step = terminal.answering(interrupting(INTERRUPT, NO_MORE_INPUT, INTERRUPT, "1"))

    try:
        step.choose([("a", "one"), ("b", "two")])
    except Stopped:
        pass

    assert step.choose([("a", "one"), ("b", "two")]) == "a"
    assert terminal.text.count("Press Ctrl-C again") == 2


def test_a_markup_label_is_drawn_styled_in_the_numbered_menu():
    terminal = Terminal("1")

    terminal.step.choose(
        [("a", Markup("just [bold]fix[/] it")), ("b", "no")]
    )

    assert f"1) {BULLET}just fix it" in terminal.text


def test_a_plain_label_that_looks_like_markup_is_still_shown_as_it_is():
    terminal = Terminal("1")

    terminal.step.choose(
        [("a", "[bold]fix[/]"), ("b", "no")]
    )

    assert f"1) {BULLET}[bold]fix[/]" in terminal.text


def test_a_note_sits_on_the_questions_line():
    terminal = Terminal("1")

    terminal.step.choose(
        [("a", "yes"), ("b", "no")], "Which one?", note="seen before"
    )

    assert terminal.lines[0] == "Which one?  seen before"


def test_a_note_is_shown_as_it_is_not_read_as_markup():
    terminal = Terminal("1")

    terminal.step.choose(
        [("a", "yes"), ("b", "no")], "Which one?", note="check failed [warn]"
    )

    assert terminal.lines[0] == "Which one?  check failed [warn]"


def test_a_note_of_several_lines_stays_one_line_each_in_the_numbered_menu():
    terminal = Terminal("1")

    terminal.step.choose(
        [("a", "yes"), ("b", "no")], "Which one?", note="runs now: one\nnever used: two"
    )

    assert terminal.lines[:2] == ["Which one?  runs now: one", f"{STEP}never used: two"]


def test_a_blank_line_stands_between_the_question_and_the_first_option():
    terminal = Terminal("1")

    terminal.step.choose(
        [("a", "yes"), ("b", "no")], "Which one?", note="seen before"
    )

    assert terminal.lines[:3] == [
        "Which one?  seen before",
        "",
        f"{STEP}1) {BULLET}yes",
    ]


def test_an_option_without_a_symbol_gets_a_bullet_so_the_texts_line_up():
    terminal = Terminal("1")

    terminal.step.choose(
        [
            ("a", "restart"),
            ("b", "↩ cancel"),
            ("c", Markup("⎷ [bold]fix[/]")),
            ("d", Markup("[bold]leave[/] it")),
        ]
    )

    assert f"{STEP}1) {BULLET}restart" in terminal.text
    assert f"{STEP}2) ↩ cancel" in terminal.text
    assert f"{STEP}3) ⎷ fix" in terminal.text
    assert f"{STEP}4) {BULLET}leave it" in terminal.text


def test_an_option_that_already_has_the_bullet_does_not_get_a_second():
    assert prompting._bulleted(f"{BULLET}restart") == f"{BULLET}restart"
    assert prompting._bulleted("⏭ later") == "⏭ later"
    assert prompting._bulleted("(none)") == f"{BULLET}(none)"


def test_a_menu_without_a_question_leaves_an_empty_line_without_spaces():
    terminal = Terminal("1")

    terminal.step.inside().choose([("a", "one"), ("b", "two")])

    assert terminal.lines[0] == ""
