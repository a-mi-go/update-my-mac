"""The indenting and the numbering that every walk-through is built out of."""

from update_my_mac.view.prompting import STEP, WAY_OUT, Step, Stopped

from fake_terminal import Terminal


def test_a_step_prints_at_its_own_margin():
    terminal = Terminal()

    Step(terminal.out).say("What should we do with them?")
    Step(terminal.out).inside().say("What should we do with them?")

    assert terminal.lines == [
        "What should we do with them?",
        f"{STEP}What should we do with them?",
    ]


def test_a_blank_line_is_not_indented():
    # Indenting it would leave trailing spaces at the end of the line.
    terminal = Terminal()

    Step(terminal.out).inside().say()

    assert terminal.lines == [""]


def test_the_options_stand_one_step_inside_the_question():
    terminal = Terminal("1")

    Step(terminal.out, terminal.ask).choose([("a", "one"), ("b", "two")])

    assert terminal.lines[:2] == [f"{STEP}1) one", f"{STEP}2) {WAY_OUT}two"]


def test_the_prompt_stands_in_the_column_the_question_does():
    # What you type is a number, but the question is what you are answering.
    terminal = Terminal("1")

    Step(terminal.out, terminal.ask).inside().choose([("a", "one")])

    assert terminal.lines[-1] == f"{STEP}> "


def test_the_key_comes_back_rather_than_the_number():
    terminal = Terminal("2")

    assert Step(terminal.out, terminal.ask).choose([("a", "one"), ("b", "two")]) == "b"


def test_an_answer_outside_the_list_is_asked_again():
    terminal = Terminal("0", "9", "1")

    Step(terminal.out, terminal.ask).choose([("a", "one"), ("b", "two")])

    assert terminal.text.count("Didn't catch that") == 2


def test_the_end_of_the_input_stops_the_conversation():
    terminal = Terminal(then=EOFError)

    try:
        Step(terminal.out, terminal.ask).choose([("a", "one")])
    except Stopped:
        return
    raise AssertionError("the step should have stopped")


def test_going_inside_leaves_the_step_it_came_from_alone():
    terminal = Terminal()
    step = Step(terminal.out)

    step.inside().inside()
    step.say("still here")

    assert terminal.lines == ["still here"]


def test_a_menu_with_nothing_in_it_is_a_mistake():
    # Asking would loop forever, because no answer could ever be right.
    terminal = Terminal()

    try:
        Step(terminal.out, terminal.ask).choose([])
    except ValueError:
        return
    raise AssertionError("an empty menu should not be offered")


def test_the_menu_asks_the_question_it_was_given():
    terminal = Terminal("1")

    chosen = terminal.step.choose([("a", "one"), ("b", "two")], "[bold]Which one?[/]")

    assert chosen == "a"
    assert terminal.lines[0] == "Which one?"


def interrupting(*answers):
    """A terminal that presses Ctrl-C before each of these answers."""
    given = list(answers)

    def ask(_prompt):
        answer = given.pop(0)
        if answer is INTERRUPT:
            raise KeyboardInterrupt
        return answer

    return ask


INTERRUPT = object()


def test_the_first_ctrl_c_only_warns():
    terminal = Terminal()
    step = Step(terminal.out, interrupting(INTERRUPT, "1"))

    assert step.choose([("a", "one"), ("b", "two")]) == "a"
    assert "Press Ctrl-C again" in terminal.text


def test_the_second_ctrl_c_in_a_row_ends_the_run():
    step = Step(Terminal().out, interrupting(INTERRUPT, INTERRUPT))

    try:
        step.choose([("a", "one"), ("b", "two")])
    except KeyboardInterrupt:
        return
    raise AssertionError("the second one should have been left to end the run")


def test_an_answer_in_between_clears_the_warning():
    # One Ctrl-C is easy to hit by accident; an answer says it was not meant.
    terminal = Terminal()
    step = Step(terminal.out, interrupting(INTERRUPT, "1", INTERRUPT, "2"))

    assert step.choose([("a", "one"), ("b", "two")]) == "a"
    assert step.choose([("a", "one"), ("b", "two")]) == "b"
    assert terminal.text.count("Press Ctrl-C again") == 2
