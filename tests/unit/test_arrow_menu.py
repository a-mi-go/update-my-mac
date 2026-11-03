"""Answering a menu with the arrow keys, and not doing so anywhere else."""

import pytest

from update_my_mac.view.prompting import BULLET

from update_my_mac.view import arrow_menu
from update_my_mac.view import output
from update_my_mac.view import prompt_toolkit_internals
from update_my_mac.view import prompting

from fake_terminal import Terminal


def test_the_keys_are_not_offered_without_a_terminal():
    # Every test and every pipe runs here, and every one of them types.
    assert not arrow_menu.can_be_drawn()


def test_a_step_types_by_default_where_there_is_no_terminal():
    terminal = Terminal("1")

    assert terminal.step.choose([("a", "one")]) == "a"


def test_a_missing_library_means_typing_rather_than_crashing(monkeypatch):
    # An installed command from before the library was added would otherwise
    # fall over in the middle of a run.
    monkeypatch.setattr(arrow_menu.importlib.util, "find_spec", lambda name: None)

    assert not arrow_menu.can_be_drawn()


def answers(key):
    """A menu that returns this answer, whatever is shown."""
    return lambda question, entries, note="": key


def choices():
    return [
        ("adopt", "get them back on track"),
        ("all", "fix everything"),
        ("no", "not now"),
    ]


def test_a_line_the_cursor_skips_sets_the_way_out_apart(monkeypatch):
    seen = []
    monkeypatch.setattr(
        arrow_menu,
        "pick_one",
        lambda question, entries, note="": seen.append(entries) or "adopt",
    )

    Terminal().with_arrows().choose(
        [
            ("adopt", "get them back on track"),
            ("all", "fix everything"),
            ("no", "↩ not now"),
        ]
    )

    # None is drawn as a separator, which questionary will not land on.
    assert seen[0][2] is None
    assert [entry[0] for entry in seen[0] if entry] == ["adopt", "all", "no"]


def test_without_a_way_out_there_is_no_separator(monkeypatch):
    seen = []
    monkeypatch.setattr(
        arrow_menu,
        "pick_one",
        lambda question, entries, note="": seen.append(entries) or "adopt",
    )

    Terminal().with_arrows().choose(
        [("adopt", "restart"), ("no", "leave it running")]
    )

    assert None not in seen[0]


def test_the_answer_comes_straight_back(monkeypatch):
    # Each choice carries the answer it stands for, so nothing is counted
    # back around the line.
    monkeypatch.setattr(arrow_menu, "pick_one", answers("no"))

    assert Terminal().with_arrows().choose(choices()) == "no"


def test_backing_out_stops_the_step(monkeypatch):
    monkeypatch.setattr(arrow_menu, "pick_one", lambda question, entries, note="": None)

    try:
        Terminal().with_arrows().choose(choices())
    except prompting.Stopped:
        return
    raise AssertionError("escape should stop the step")


def test_the_question_is_handed_to_the_menu_that_draws_it(monkeypatch):
    asked = []
    monkeypatch.setattr(
        arrow_menu,
        "pick_one",
        lambda question, entries, note="": asked.append(question) or "adopt",
    )

    Terminal().with_arrows().choose(choices(), "What should we do?")

    assert asked == ["What should we do?"]


def test_a_menu_that_will_not_draw_falls_back_to_typing(monkeypatch):
    # Whatever went wrong in the library, there is always the other way.
    def refuse(question, entries, note=""):
        raise arrow_menu.Unusable("no terminal capability")

    monkeypatch.setattr(arrow_menu, "pick_one", refuse)
    terminal = Terminal("3")

    chosen = terminal.with_arrows().choose(
        choices()
    )

    assert chosen == "no"
    assert "could not be drawn" in terminal.text


def resolved(part):
    """What a part of a question actually looks like once drawn.

    questionary merges its own style under ours, so what matters is the
    result rather than what was asked for.
    """
    from prompt_toolkit.styles import merge_styles
    from questionary.constants import DEFAULT_STYLE

    merged = merge_styles([DEFAULT_STYLE, arrow_menu._style()])
    return merged.get_attrs_for_style_str(f"class:{part}")


def test_the_question_stays_bold_and_plain():
    # A question looks like a question; the color belongs to what the
    # cursor is on.
    attrs = resolved("question")

    assert attrs.color == ""
    assert attrs.bold


def test_the_cursor_is_what_wears_the_color():
    # The terminal's own cyan, as in the report, and not bold.
    for part in ("qmark", "pointer", "highlighted"):
        assert resolved(part).color == "ansicyan", part
        assert not resolved(part).bold, part


def test_the_answer_is_orange_but_not_bold():
    # questionary would paint it orange and bold.
    attrs = resolved("answer")

    assert attrs.color == "f2a900"
    assert not attrs.bold


def test_the_hint_is_readable_rather_than_dimmed():
    # Grey on a dark terminal was barely there.
    attrs = resolved("instruction")

    assert attrs.color == ""
    assert not attrs.bold


def test_markup_becomes_pieces_that_carry_their_own_style():
    assert arrow_menu.styled("just [bold]FIX EVERYTHING[/] now") == [
        ("", "just "),
        ("bold", "FIX EVERYTHING"),
        ("", " now"),
    ]


def test_a_label_without_markup_is_one_unstyled_piece():
    assert arrow_menu.styled("plain words") == [("", "plain words")]


def test_a_markup_label_reaches_the_menu_as_pieces_and_a_plain_one_as_text(monkeypatch):
    seen = []
    monkeypatch.setattr(
        arrow_menu, "pick_one", lambda question, entries, note="": seen.append(entries) or "a"
    )

    Terminal().with_arrows().choose(
        [
            ("a", "plain"),
            ("b", prompting.Markup("[bold]fix[/] all")),
            ("c", "not now"),
        ]
    )

    assert seen[0][0] == ("a", f"{BULLET}plain")
    assert seen[0][1] == ("b", [("", f"{BULLET}"), ("bold", "fix"), ("", " all")])


def test_a_note_goes_to_the_menu_apart_from_the_question(monkeypatch):
    seen = []
    monkeypatch.setattr(
        arrow_menu,
        "pick_one",
        lambda question, entries, note="": seen.append((question, note)) or "a",
    )

    Terminal().with_arrows().choose(
        [("a", "yes"), ("b", "no")], "Which one?", note="seen before"
    )

    assert seen == [("Which one?", "seen before")]


import questionary

REAL_SELECT = questionary.select
REAL_CHECKBOX = questionary.checkbox


class FakePrompt:
    def __init__(self):
        self.application = REAL_SELECT("q", choices=["a"]).application

    def unsafe_ask(self):
        return "a"


def drawn_with(monkeypatch, note, question="Which one?"):
    import questionary

    seen = {}
    monkeypatch.setattr(
        questionary,
        "select",
        lambda *args, **kwargs: seen.update(kwargs) or FakePrompt(),
    )
    arrow_menu.pick_one(question, [("a", "yes")], note)
    return seen


def test_a_note_is_drawn_beside_the_question(monkeypatch):
    seen = drawn_with(monkeypatch, "seen before")

    assert seen["instruction"] == " seen before"


def test_without_a_note_the_hint_stays_blank(monkeypatch):
    assert drawn_with(monkeypatch, "")["instruction"] == " "


def test_only_a_note_is_lighter_than_the_text():
    from prompt_toolkit.styles import merge_styles
    from questionary.constants import DEFAULT_STYLE

    with_note = merge_styles([DEFAULT_STYLE, arrow_menu._style(for_note=True)])
    attrs = with_note.get_attrs_for_style_str("class:instruction")

    assert attrs.color == "999999"


def test_a_note_of_several_lines_continues_under_the_first(monkeypatch):
    seen = drawn_with(monkeypatch, "runs now:   one\nnever used: two")

    assert seen["instruction"] == " runs now:   one\n   never used: two"


class AbortedApp:
    def __init__(self):
        self.erase_when_done = False
        self.exited_with = None
        self.redrawn = False

    def invalidate(self):
        self.redrawn = True

    def exit(self, exception=None, style=None):
        self.exited_with = exception


def abort_with_ctrl_c(prompt):
    from types import SimpleNamespace

    from prompt_toolkit.keys import Keys

    handlers = prompt.application.key_bindings.get_bindings_for_keys((Keys.ControlC,))
    app = AbortedApp()
    handlers[-1].handler(SimpleNamespace(app=app))
    return app


def test_a_menu_without_a_question_has_no_mark_in_front_of_it(monkeypatch):
    assert drawn_with(monkeypatch, "", question="")["qmark"] == ""


def test_a_menu_with_a_question_keeps_its_mark(monkeypatch):
    assert drawn_with(monkeypatch, "")["qmark"] == arrow_menu.QMARK


def a_menu_prompt(blank_line):
    prompt = FakePrompt()
    arrow_menu._ask_twice_before_aborting(prompt, warn_in_menu=True, blank_line=blank_line)
    return prompt


def warning_row(prompt):
    return prompt.application.layout.container.children[-1]


def after_a_key(prompt):
    """What the key processor announces after every key it has handled."""
    prompt.application.key_processor.after_key_press.fire()


def test_the_first_ctrl_c_only_warns_inside_a_menu():
    prompt = a_menu_prompt(blank_line=True)

    app = abort_with_ctrl_c(prompt)

    assert app.exited_with is None
    assert app.redrawn
    assert arrow_menu.pressed_ctrl_c()


def test_the_second_ctrl_c_takes_the_menu_off_the_screen():
    prompt = a_menu_prompt(blank_line=True)
    arrow_menu.press_ctrl_c()

    app = abort_with_ctrl_c(prompt)

    assert app.erase_when_done
    assert app.exited_with is KeyboardInterrupt


def test_a_prompt_without_options_ends_at_the_first_ctrl_c():
    prompt = FakePrompt()
    arrow_menu._ask_twice_before_aborting(prompt)

    app = abort_with_ctrl_c(prompt)

    assert app.erase_when_done
    assert app.exited_with is KeyboardInterrupt


def test_a_menu_that_is_answered_stays_on_the_screen():
    prompt = a_menu_prompt(blank_line=True)

    assert not prompt.application.erase_when_done


def a_checkbox():
    from questionary import Choice, Separator

    return REAL_CHECKBOX(
        "q",
        choices=[
            Choice("one", value="one", checked=True),
            Choice("two", value="two"),
            Separator(),
            Choice("go", value="go"),
            Choice("quit", value="quit"),
        ],
    )


def press(prompt, key, pointing_at=0, ticked=()):
    """Presses a key in a checkbox and returns what the menu ended with, and its rows."""
    from types import SimpleNamespace

    from questionary.prompts.common import InquirerControl

    rows = next(
        c
        for c in prompt.application.layout.find_all_controls()
        if isinstance(c, InquirerControl)
    )
    rows.pointed_at = pointing_at
    rows.selected_options = list(ticked)
    ended = []
    app = SimpleNamespace(exit=lambda result=None, **options: ended.append(result))
    handlers = prompt.application.key_bindings.get_bindings_for_keys((key,))
    handlers[-1].handler(SimpleNamespace(app=app))
    return ended, rows


def shaped():
    prompt = a_checkbox()
    arrow_menu._shape_checkbox(prompt, ends_menu=("quit",), confirm="go")
    return prompt


ONE, TWO, GO, QUIT = 0, 1, 3, 4


def test_enter_on_a_row_that_ends_the_menu_answers_with_that_row_alone():
    from prompt_toolkit.keys import Keys

    ended, _ = press(shaped(), Keys.ControlM, pointing_at=QUIT, ticked=["one"])

    assert ended == [["quit"]]


def test_enter_on_the_confirming_row_answers_with_what_is_ticked():
    from prompt_toolkit.keys import Keys

    ended, _ = press(shaped(), Keys.ControlM, pointing_at=GO, ticked=["one", "two"])

    assert ended == [["one", "two"]]


def test_enter_on_an_ordinary_row_answers_with_what_is_ticked():
    from prompt_toolkit.keys import Keys

    ended, _ = press(shaped(), Keys.ControlM, pointing_at=ONE, ticked=["one"])

    assert ended == [["one"]]


def test_space_ticks_and_unticks_an_ordinary_row():
    prompt = shaped()

    _, rows = press(prompt, " ", pointing_at=TWO, ticked=["one"])
    assert rows.selected_options == ["one", "two"]

    _, rows = press(prompt, " ", pointing_at=TWO, ticked=["one", "two"])
    assert rows.selected_options == ["one"]


def test_space_leaves_the_rows_that_act_alone():
    for row in (GO, QUIT):
        _, rows = press(shaped(), " ", pointing_at=row, ticked=["one"])
        assert rows.selected_options == ["one"]


def test_toggling_every_row_and_inverting_do_nothing():
    for key in ("a", "i"):
        ended, rows = press(shaped(), key, ticked=["one"])
        assert ended == []
        assert rows.selected_options == ["one"]


def test_a_row_that_acts_is_drawn_without_a_box():
    boxes = ("[x] ", "[ ] ")
    button = [
        ("class:text", "   "),
        ("class:text", "[ ] "),
        ("class:text", "go"),
        ("", "\n"),
    ]
    ordinary = [
        ("class:text", "   "),
        ("class:text", "[ ] "),
        ("class:text", "two"),
        ("", "\n"),
    ]

    assert [t[1] for t in arrow_menu._without_box(button, {"go"}, boxes)] == [
        "   ",
        "go",
        "\n",
    ]
    assert arrow_menu._without_box(ordinary, {"go"}, boxes) == ordinary


def test_a_blank_line_is_a_separator_with_nothing_in_it():
    from questionary import Separator

    blank = arrow_menu._choices([arrow_menu.BLANK_LINE])[0]

    assert isinstance(blank, Separator)
    assert blank.title == " "


def test_the_rows_named_as_checked_start_ticked():
    choices = arrow_menu._choices([("a", "A"), ("b", "B")], checked=["a"])

    assert [choice.checked for choice in choices] == [True, False]


def test_the_multi_select_starts_ticked_on_the_row_it_was_told_to_and_draws_plain_boxes(
    monkeypatch,
):
    from questionary.prompts import common

    monkeypatch.setattr(common, "INDICATOR_SELECTED", common.INDICATOR_SELECTED)
    monkeypatch.setattr(common, "INDICATOR_UNSELECTED", common.INDICATOR_UNSELECTED)
    seen = {}
    monkeypatch.setattr(
        questionary,
        "checkbox",
        lambda *args, **kwargs: seen.update(kwargs) or REAL_CHECKBOX(*args, **kwargs),
    )
    monkeypatch.setattr(arrow_menu, "_answer_to", lambda prompt, **options: ["done"])

    arrow_menu.pick_several(
        "q", [("a", "A"), ("go", "go")], confirm="go", checked=["a"], start_at="go"
    )

    assert seen["initial_choice"] == "go"
    assert seen["instruction"] == "(Use arrow keys to move, <space> to select)"
    assert (common.INDICATOR_SELECTED, common.INDICATOR_UNSELECTED) == ("[x]", "[ ]")


def test_a_ticked_row_is_plain_where_the_pointer_is_not():
    row = [
        ("class:text", "   "),
        ("class:selected", "[x] "),
        ("class:selected", "one"),
        ("", "\n"),
    ]

    assert arrow_menu._cyan_only_under_the_pointer(row) == [
        ("class:text", "   "),
        ("class:text", "[x] "),
        ("class:text", "one"),
        ("", "\n"),
    ]


def test_the_row_under_the_pointer_is_highlighted_ticked_or_not():
    ticked = [
        ("class:pointer", " ❯ "),
        ("[SetCursorPosition]", ""),
        ("class:selected", "[x] "),
        ("class:selected", "one"),
        ("", "\n"),
    ]
    unticked = [
        ("class:pointer", " ❯ "),
        ("[SetCursorPosition]", ""),
        ("class:text", "[ ] "),
        ("class:highlighted", "two"),
        ("", "\n"),
    ]

    for row in (ticked, unticked):
        shown = arrow_menu._cyan_only_under_the_pointer(row)
        assert shown[:2] == row[:2]
        assert [token[0] for token in shown[2:4]] == [
            "class:highlighted",
            "class:highlighted",
        ]
        assert shown[4] == ("", "\n")


def test_the_x_of_a_ticked_box_is_yellow_and_the_rest_of_the_row_is_not():
    row = [("class:text", "   "), ("class:text", "[x] "), ("class:text", "one"), ("", "\n")]

    assert arrow_menu._yellow_tick(row) == [
        ("class:text", "   "),
        ("class:text", "["),
        ("class:tick", "x"),
        ("class:text", "] "),
        ("class:text", "one"),
        ("", "\n"),
    ]
    assert resolved("tick").color == "ansiyellow"


def test_a_ticked_row_has_no_color_of_its_own():
    attrs = resolved("selected")

    assert attrs.color == ""
    assert not attrs.bold


def test_a_menu_that_asks_for_a_blank_line_gets_one_under_the_question():
    with_blank = a_menu_prompt(blank_line=True)
    without = a_menu_prompt(blank_line=False)

    assert len(with_blank.application.layout.container.children) == (
        len(without.application.layout.container.children) + 1
    )
    assert with_blank.application.layout.container.children[1].filter()


def test_the_warning_shows_under_the_options_only_after_a_ctrl_c():
    for blank_line in (True, False):
        prompt = a_menu_prompt(blank_line)
        assert not warning_row(prompt).filter()

        arrow_menu.press_ctrl_c()
        assert warning_row(prompt).filter()
        arrow_menu.forget_ctrl_c()


def test_the_options_do_not_stretch_so_the_warning_sits_right_under_them():
    from questionary.prompts.common import InquirerControl

    prompt = a_menu_prompt(blank_line=True)

    options = next(
        window
        for window in prompt.application.layout.find_all_windows()
        if isinstance(window.content, InquirerControl)
    )
    assert options.dont_extend_height()


def test_the_key_that_raised_the_warning_does_not_take_it_back():
    prompt = a_menu_prompt(blank_line=True)

    abort_with_ctrl_c(prompt)
    after_a_key(prompt)

    assert arrow_menu.pressed_ctrl_c()


def test_any_other_key_takes_the_warning_back():
    prompt = a_menu_prompt(blank_line=True)

    abort_with_ctrl_c(prompt)
    after_a_key(prompt)
    after_a_key(prompt)

    assert not arrow_menu.pressed_ctrl_c()
    assert not warning_row(prompt).filter()


def test_a_ctrl_c_after_another_key_warns_again_instead_of_ending_the_run():
    prompt = a_menu_prompt(blank_line=True)
    abort_with_ctrl_c(prompt)
    after_a_key(prompt)
    after_a_key(prompt)

    app = abort_with_ctrl_c(prompt)

    assert app.exited_with is None
    assert arrow_menu.pressed_ctrl_c()


def test_the_key_that_ends_the_run_does_not_take_the_state_back_for_whoever_asks_next():
    prompt = a_menu_prompt(blank_line=True)
    abort_with_ctrl_c(prompt)
    after_a_key(prompt)

    app = abort_with_ctrl_c(prompt)
    after_a_key(prompt)

    assert app.exited_with is KeyboardInterrupt
    assert arrow_menu.pressed_ctrl_c()


def test_a_mistake_in_our_own_menu_code_is_not_hidden_as_an_unusable_terminal(monkeypatch):
    def broken(prompt, warn_in_menu=False, blank_line=False):
        raise AttributeError("ours")

    monkeypatch.setattr(arrow_menu, "_ask_twice_before_aborting", broken)

    with pytest.raises(AttributeError):
        arrow_menu._answer_to(object())


def test_a_library_that_cannot_draw_the_menu_is_unusable(monkeypatch):
    class Refusing:
        def unsafe_ask(self):
            raise OSError("no terminal capability")

    monkeypatch.setattr(arrow_menu, "_ask_twice_before_aborting", lambda *a, **k: None)

    with pytest.raises(arrow_menu.Unusable):
        arrow_menu._answer_to(Refusing())


def answered_with(*pressed, default=True):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as typed, create_app_session(input=typed, output=DummyOutput()):
        typed.send_text("".join(pressed))
        return arrow_menu.yes_or_no("Update them now?", default=default)


LEFT, RIGHT, ENTER = "\x1b[D", "\x1b[C", "\r"


def test_enter_takes_the_default_yes():
    assert answered_with(ENTER) is True


def test_the_arrows_move_between_yes_and_no():
    assert answered_with(RIGHT, ENTER) is False
    assert answered_with(RIGHT, LEFT, ENTER) is True


def test_y_and_n_pick_directly():
    assert answered_with("n", ENTER) is False
    assert answered_with("n", "y", ENTER) is True


def test_a_no_default_starts_on_no():
    assert answered_with(ENTER, default=False) is False


def picked_below(*pressed):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    def print_report(console):
        for number in range(100):
            console.print(f"line {number}")

    with create_pipe_input() as typed, create_app_session(input=typed, output=DummyOutput()):
        typed.send_text("".join(pressed))
        return arrow_menu.pick_one_below(
            print_report, "Which one?", [("a", "one"), ("b", "two"), ("c", "three")]
        )


PAGE_DOWN, PAGE_UP, END, DOWN = "\x1b[6~", "\x1b[5~", "\x1b[F", "\x1b[B"


def test_a_menu_below_a_report_is_answered_like_any_other():
    assert picked_below(ENTER) == "a"
    assert picked_below(DOWN, DOWN, ENTER) == "c"


def test_the_page_keys_scroll_the_report_and_leave_the_menu_alone():
    assert picked_below(PAGE_DOWN, END, PAGE_UP, ENTER) == "a"


def test_the_screen_is_the_whole_terminal_while_the_menu_below_a_report_asks():
    # Decided when an Application is made, so it is set on the menu's own.
    import questionary

    seen = []

    def run(prompt):
        seen.append(prompt.application.full_screen)
        return "a"

    original = arrow_menu._run
    arrow_menu._run = run
    try:
        arrow_menu.pick_one_below(lambda console: None, "Which one?", [("a", "one")])
    finally:
        arrow_menu._run = original

    assert seen == [True]


def test_a_menu_below_a_report_leaves_the_screen_to_whoever_entered_it(monkeypatch):
    monkeypatch.setattr(output, "_in_full_screen", True)
    seen = []
    original = arrow_menu._run
    arrow_menu._run = lambda prompt: seen.append(prompt.application.output) or "a"
    try:
        arrow_menu.pick_one_below(lambda console: None, "Which one?", [("a", "one")])
    finally:
        arrow_menu._run = original

    screen = seen[0]
    # Neither writes the codes, and the rest is the real output's.
    screen.enter_alternate_screen()
    screen.quit_alternate_screen()
    assert screen.get_size() is not None


def test_the_terminal_gets_the_mouse_back_while_the_menu_below_a_report_asks(monkeypatch):
    seen = []
    original = arrow_menu._run
    arrow_menu._run = lambda prompt: seen.append(prompt.application.mouse_support) or "a"
    try:
        arrow_menu.pick_one_below(lambda console: None, "Which one?", [("a", "one")])
    finally:
        arrow_menu._run = original

    assert seen[0]() is True



def test_a_blank_row_separates_the_report_from_the_question_on_the_screen_below_it():
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    rows = []

    def run(prompt):
        app = prompt.application

        def look(_app):
            screen = app.renderer._last_screen
            if screen is not None and not rows:
                rows.extend(
                    "".join(screen.data_buffer[y][x].char for x in range(40)).rstrip() for y in range(40)
                )
                typed.send_text("\r")

        app.after_render += look
        return prompt.unsafe_ask()

    original = arrow_menu._run
    arrow_menu._run = run
    try:
        with create_pipe_input() as typed, create_app_session(input=typed, output=DummyOutput()):
            typed.send_text("\x1b[F")
            arrow_menu.pick_one_below(
                lambda console: console.print("the report"), "Which one?", [("a", "one")]
            )
    finally:
        arrow_menu._run = original

    at = next(i for i, row in enumerate(rows) if "Which one?" in row)
    assert rows[at - 1] == ""
    assert "the report" in rows[at - 2]


def first_screen_below_a_long_report():
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    rows = []

    def run(prompt):
        app = prompt.application

        def look(_app):
            screen = app.renderer._last_screen
            if screen is not None and not rows:
                rows.extend(
                    "".join(screen.data_buffer[y][x].char for x in range(60)).rstrip() for y in range(40)
                )
                typed.send_text("\r")

        app.after_render += look
        return prompt.unsafe_ask()

    original = arrow_menu._run
    arrow_menu._run = run
    try:
        with create_pipe_input() as typed, create_app_session(input=typed, output=DummyOutput()):
            arrow_menu.pick_one_below(
                lambda console: [console.print(f"line {n}") for n in range(100)],
                "Which one?", [("a", "one"), ("b", "two")],
            )
    finally:
        arrow_menu._run = original
    return rows


def test_a_long_report_starts_scrolled_to_the_menu_below_it():
    rows = first_screen_below_a_long_report()

    assert any("Which one?" in row for row in rows)
    assert any(row.strip().endswith("two") for row in rows)
    assert "line 99" in "\n".join(rows)


def test_a_blank_row_separates_the_last_option_from_the_line_with_the_keys():
    rows = first_screen_below_a_long_report()

    last = max(i for i, row in enumerate(rows) if row.strip().endswith("two"))
    assert rows[last + 1] == ""
    assert "Up/Down choose" in rows[last + 2]


def test_pointed_row_with_styled_pieces_is_highlighted_and_others_are_not():
    prompt = arrow_menu._select("Q", [("a", "plain"), ("b", arrow_menu.styled("[bold]styled[/]"))], "")
    control = arrow_menu._menu_window(prompt).content

    control.pointed_at = 1
    assert ("class:highlighted bold", "styled") in control.text()

    control.pointed_at = 0
    assert ("bold", "styled") in control.text()


def test_a_row_longer_than_the_terminal_continues_under_its_label(monkeypatch):
    import questionary
    from questionary.prompts.common import InquirerControl

    label = "reinstall with Homebrew's installer (replace 2026.1.1.70276 with 14.0.8.69494)"
    prompt = FakePrompt()
    prompt.application = REAL_SELECT("q", choices=[label]).application
    monkeypatch.setattr(questionary, "select", lambda *args, **kwargs: prompt)
    arrow_menu.pick_one("Which one?", [("a", label)])

    window = next(w for w in prompt.application.layout.find_all_windows() if isinstance(w.content, InquirerControl))
    assert window.preferred_height(40, 20).preferred > 1
    assert window.get_line_prefix(0, 0) == ""
    assert window.get_line_prefix(0, 1) == "   "


def test_a_long_row_is_continued_at_a_space_never_inside_a_word():
    label = "let Homebrew take over (replace 2026.1.1.70276 with 14.0.8.69494, the versions can't be compared)"
    tokens = [("class:pointer", " ❯ "), ("class:text", label), ("", "\n")]

    shown = "".join(text for _, text, *_ in arrow_menu._wrapped_at_spaces(tokens, 50, 3))
    lines = shown.rstrip("\n").split("\n")

    assert len(lines) > 1
    assert all(len(line) <= 50 for line in lines)
    assert all(line.startswith("   ") for line in lines[1:])
    assert " ".join(line.strip() for line in lines).replace("❯ ", "") == label


def test_a_resize_on_the_screen_of_its_own_prints_everything_again_before_the_menu(monkeypatch):
    prompt = FakePrompt()
    app = prompt.application
    calls = []
    monkeypatch.setattr(output, "in_full_screen", lambda: True)
    monkeypatch.setattr(output, "clear_and_replay", lambda: calls.append("replay"))
    monkeypatch.setattr(app.renderer, "reset", lambda **kwargs: calls.append("reset"))
    monkeypatch.setattr(app, "_request_absolute_cursor_position", lambda: calls.append("position"))
    monkeypatch.setattr(app, "_redraw", lambda: calls.append("draw"))
    monkeypatch.setattr(questionary, "select", lambda *args, **kwargs: prompt)

    arrow_menu.pick_one("Which one?", [("a", "yes")])
    app._on_resize()

    assert calls == ["replay", "reset", "position", "draw"]


def screen_with_lines(*lines):
    from prompt_toolkit.layout.screen import Char, Screen

    screen = Screen()
    for y, line in enumerate(lines):
        for x, character in enumerate(line):
            screen.data_buffer[y][x] = Char(character)
    return screen


def test_a_line_wider_than_the_terminal_takes_the_rows_it_wraps_to():
    screen = screen_with_lines("a" * 100, "b" * 10, "")

    assert [prompt_toolkit_internals.rows_taken(screen.data_buffer[y], 40) for y in range(3)] == [3, 1, 1]


def test_a_resize_outside_the_screen_of_its_own_erases_from_where_the_wrapped_menu_starts(monkeypatch):
    from types import SimpleNamespace

    from prompt_toolkit.data_structures import Point, Size

    moves = []

    class Out:
        def get_size(self):
            return Size(rows=30, columns=40)

        def __getattr__(self, name):
            return lambda *args: moves.append((name, *args))

    renderer = SimpleNamespace(_cursor_pos=Point(x=45, y=2), _last_screen=screen_with_lines("a" * 100, "b" * 10, "c"))
    monkeypatch.setattr(output, "in_full_screen", lambda: False)

    prompt_toolkit_internals.erase_the_wrapped_menu(SimpleNamespace(renderer=renderer, output=Out()))

    # 3 rows for the first line, 1 for the second, 1 more for the cursor 45 columns into its own.
    assert ("cursor_up", 5) in moves
    assert [name for name, *_ in moves][-1] == "flush"


def test_a_last_word_that_fills_the_line_exactly_stays_on_it():
    tokens = [("", " ❯ "), ("", "aaaa bbbbbbbbbb"), ("", "\n")]

    shown = "".join(text for _, text, *_ in arrow_menu._wrapped_at_spaces(tokens, 18, 3))

    assert shown == " ❯ aaaa bbbbbbbbbb\n"


def test_a_double_width_character_counts_as_two_columns_when_wrapping():
    tokens = [("", " ❯ "), ("", "🚨 aaaa bbbb"), ("", "\n")]

    shown = "".join(text for _, text, *_ in arrow_menu._wrapped_at_spaces(tokens, 14, 3))

    assert shown == " ❯ 🚨 aaaa \n   bbbb\n"


def test_a_menu_that_cannot_be_drawn_is_not_on_a_screen_of_its_own(monkeypatch):
    monkeypatch.setattr(arrow_menu, "can_be_drawn", lambda: False)
    monkeypatch.setattr(arrow_menu, "can_fill_the_screen", lambda option_count: True)
    monkeypatch.setattr(output, "in_full_screen", lambda: False)

    assert not arrow_menu.runs_on_its_own_screen(3)


def test_a_menu_is_on_a_screen_of_its_own_only_in_a_terminal_that_is_not_already_in_one(monkeypatch):
    monkeypatch.setattr(arrow_menu, "_is_a_terminal", lambda: True)
    monkeypatch.setattr(arrow_menu, "can_fill_the_screen", lambda option_count: True)
    monkeypatch.setattr(output, "in_full_screen", lambda: False)
    assert arrow_menu.runs_on_its_own_screen(3)

    monkeypatch.setattr(output, "in_full_screen", lambda: True)
    assert not arrow_menu.runs_on_its_own_screen(3)

    monkeypatch.setattr(output, "in_full_screen", lambda: False)
    monkeypatch.setattr(arrow_menu, "can_fill_the_screen", lambda option_count: False)
    assert not arrow_menu.runs_on_its_own_screen(3)


def test_a_menu_that_runs_on_a_screen_of_its_own_is_made_full_screen(monkeypatch):
    prompt = FakePrompt()
    monkeypatch.setattr(questionary, "select", lambda *args, **kwargs: prompt)
    monkeypatch.setattr(arrow_menu, "runs_on_its_own_screen", lambda option_count: True)

    arrow_menu.pick_one("Which one?", [("a", "yes")])

    assert prompt.application.full_screen
    assert prompt.application.renderer.full_screen
    assert "_on_resize" not in vars(prompt.application)
