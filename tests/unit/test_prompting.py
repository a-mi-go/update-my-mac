"""The indenting and the numbering that every walk-through is built out of."""

from update_my_mac.prompting import STEP, Step, Stopped

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

    assert terminal.lines[:3] == [f"{STEP}1) one", f"{STEP}-----", f"{STEP}2) two"]


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
