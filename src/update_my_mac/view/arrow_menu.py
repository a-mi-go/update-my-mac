"""The menu answered with the arrow keys. Where it cannot be drawn, prompting.py
prints numbered options and reads a typed number instead.
"""

import importlib.util
import math
import shutil
import sys

from rich.cells import cell_len

from update_my_mac.view import output, prompt_toolkit_internals

POINTER = "❯"
QMARK = "፧፧"
TICKED, UNTICKED = "[x]", "[ ]"
SEPARATOR = "─" * 24
SEPARATOR_COLOR = "#666666"
# The note under a question, lighter than the separator and darker than the text.
NOTE_COLOR = "#999999"
# Where the labels start, so the note lines up with the rows below it.
NOTE_INDENT = "   "
LABEL_COLUMN = len(POINTER) + 2
CHECKBOX_LABEL_COLUMN = LABEL_COLUMN + len(TICKED) + 1
ANSWER_COLOR = "#f2a900"
# The question, the blank line and the Ctrl-C warning, besides the options.
MENU_ROWS = 3
MIN_REPORT_ROWS = 6


class Unusable(Exception):
    """The menu could not be drawn, whatever the reason."""


class WarningNote(str):
    """A note that starts with a warning, the warning drawn in yellow."""

    def __new__(cls, warning, note=""):
        text = super().__new__(cls, f"{warning}\n{note}" if note else warning)
        text.warning = warning
        return text


def unusable_message(failure):
    from rich.text import Text

    return Text.assemble((f"The menu could not be drawn ({failure}).", "yellow"), " Type a number instead.")


def can_be_drawn():
    return importlib.util.find_spec("questionary") is not None and _is_a_terminal()


def _is_a_terminal():
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def styled(markup):
    """Returns rich markup as the (style, text) pieces a menu row is drawn from."""
    import io

    from prompt_toolkit.formatted_text import ANSI
    from rich.console import Console
    from rich.text import Text

    drawn = io.StringIO()
    Console(file=drawn, force_terminal=True, color_system="standard", highlight=False).print(
        Text.from_markup(markup), end="", soft_wrap=True
    )

    # The ANSI reader gives one piece per character.
    pieces = []
    for style, text in ANSI(drawn.getvalue()).__pt_formatted_text__():
        if pieces and pieces[-1][0] == style:
            pieces[-1] = (style, pieces[-1][1] + text)
        else:
            pieces.append((style, text))
    return pieces


def _style(for_note=False):
    from questionary import Style

    # Every row needs noinherit: questionary merges this onto its own defaults
    # instead of replacing them.
    return Style([
        ("qmark", "noinherit fg:ansicyan"),
        # The hint questionary writes itself stays plain; only a note is lighter.
        ("instruction", f"noinherit fg:{NOTE_COLOR}" if for_note else "noinherit"),
        ("answer", f"noinherit fg:{ANSWER_COLOR}"),
        ("pointer", "noinherit fg:ansicyan"),
        ("highlighted", "noinherit fg:ansicyan"),
        ("selected", "noinherit"),
        ("tick", "noinherit fg:ansiyellow"),
        ("warning", "noinherit fg:ansiyellow"),
        ("separator", f"noinherit fg:{SEPARATOR_COLOR}"),
    ])


BLANK_LINE = object()


def _choices(entries, checked=()):
    """Returns the entries as choices, with None a line of dashes and BLANK_LINE an empty one."""
    from questionary import Choice, Separator

    def one(entry):
        if entry is None:
            return Separator(SEPARATOR)
        if entry is BLANK_LINE:
            return Separator(" ")
        value, label = entry
        return Choice(label, value=value, checked=value in checked)

    return [one(entry) for entry in entries]


WARNING = "Press Ctrl-C again to stop the run."

_pressed_ctrl_c = False


def pressed_ctrl_c():
    return _pressed_ctrl_c


def press_ctrl_c():
    global _pressed_ctrl_c
    _pressed_ctrl_c = True


def forget_ctrl_c():
    global _pressed_ctrl_c
    _pressed_ctrl_c = False


def beside_the_question(note):
    """Returns a note as questionary draws it: its first line right after the question."""
    first, *rest = note.splitlines() or [""]
    return f" {first}" + "".join(f"\n{NOTE_INDENT}{line}" for line in rest)


def pick_one(question, entries, note=""):
    prompt = _select(question, entries, note)
    app = prompt.application
    if runs_on_its_own_screen(rows_of_options(_label_texts(entries))):
        prompt_toolkit_internals.make_full_screen(app)
    else:
        prompt_toolkit_internals.redraw_on_resize(app, _replay_own_screen)
    return _answer_to(prompt, warn_in_menu=True, blank_line=bool(question or note))


def runs_on_its_own_screen(option_rows):
    """Returns whether a menu with this many rows of options is drawn on a screen of its own, which a resize redraws whole."""
    return can_be_drawn() and not output.in_full_screen() and can_fill_the_screen(option_rows)


def _replay_own_screen():
    """Prints again what ran on the screen of its own, wrapped to the new width. Returns whether there was one."""
    if not output.in_full_screen():
        return False
    output.clear_and_replay()
    return True


def _label_texts(entries):
    """Returns the text each row of the menu shows, a line of dashes or a blank line included."""
    texts = []
    for entry in entries:
        if entry is None or entry is BLANK_LINE:
            texts.append("")
            continue
        label = entry[1]
        texts.append(label if isinstance(label, str) else "".join(text for _, text, *_ in label))
    return texts


def rows_of_options(labels):
    """Returns how many terminal rows the options take at the width of the terminal, a long one wrapped."""
    width = max(1, shutil.get_terminal_size().columns)
    return sum(_rows_of_option(label, width) for label in labels)


def _rows_of_option(label, width):
    laid_out = "".join(
        text for _, text, *_ in _wrapped_at_spaces([("", " " * LABEL_COLUMN + label), ("", "\n")], width, LABEL_COLUMN)
    )
    return sum(max(1, math.ceil(cell_len(line) / width)) for line in laid_out.rstrip("\n").split("\n"))


def _select(question, entries, note):
    import questionary

    prompt = questionary.select(
        question,
        choices=_choices(entries),
        pointer=POINTER,
        style=_style(for_note=bool(note)),
        # The note beside the question, and only until the menu is answered.
        instruction=beside_the_question(note) if note else " ",
        # Without a question there is nothing for the mark to introduce.
        qmark=QMARK if question else "",
    )
    _highlight_styled_rows(prompt)
    _wrap_long_rows(prompt, LABEL_COLUMN)
    if isinstance(note, WarningNote):
        _color_the_warning(prompt, note.warning)
    return prompt


def _color_the_warning(prompt, warning):
    """Draws the warning the note starts with in the warning style."""
    lead = beside_the_question(warning)

    def colored(tokens):
        shown = []
        for style, text, *rest in tokens:
            if style == "class:instruction" and text.startswith(lead):
                shown += [("class:warning", lead), (style, text[len(lead):])]
            else:
                shown.append((style, text, *rest))
        return shown

    prompt_toolkit_internals.recolor_question_line(prompt.application, colored)


def _highlight_styled_rows(prompt):
    """Makes the pointed row blue even when its label is styled pieces, which questionary leaves as they are."""
    control = _menu_window(prompt).content
    draw_rows = control._get_choice_tokens

    def draw_with_pointed_row_blue():
        tokens = []
        row = 0
        for style, text in draw_rows():
            if row == control.pointed_at and not style.startswith(("class:", "[")):
                style = f"class:highlighted {style}"
            tokens.append((style, text))
            row += text == "\n"
        return tokens

    control.text = draw_with_pointed_row_blue


def _menu_window(prompt):
    from questionary.prompts.common import InquirerControl

    return next(
        window for window in prompt.application.layout.find_all_windows()
        if isinstance(window.content, InquirerControl)
    )


def _wrap_long_rows(prompt, label_column):
    """Lets a row longer than the terminal continue on the next line, at a space, under its label."""
    output_of_the_menu = prompt.application.output
    prompt_toolkit_internals.wrap_rows(
        _menu_window(prompt),
        label_column,
        lambda tokens: _wrapped_at_spaces(tokens, output_of_the_menu.get_size().columns, label_column),
    )


def _per_row(tokens, transform):
    """Returns the tokens with every row, its line break included, replaced by what `transform` makes of it."""
    shown, row = [], []
    for token in tokens:
        row.append(token)
        if token[1] == "\n":
            shown += transform(row)
            row = []
    return shown + transform(row)


def _wrapped_at_spaces(tokens, width, indent):
    """Returns the tokens with every row wider than `width` continued on a new line at a space."""
    return _per_row(tokens, lambda row: _row_wrapped(row, width, indent))


def _row_wrapped(row, width, indent):
    """Returns the row with a line break before each word that would pass `width`."""
    return _joined(_laid_out(_words_of(row), width, indent))


def _words_of(row):
    """Returns the row's tokens cut into words, a word ending after its space."""
    words, word = [], []
    for style, text, *rest in row:
        if not text:
            word.append((style, "", *rest))
        for character in text:
            word.append((style, character, *rest))
            if character == " ":
                words.append(word)
                word = []
    return words + [word]


def _laid_out(words, width, indent):
    """Returns the words as tokens, a line break at `indent` where the next word would pass `width`."""
    wrapped, column = [], 0
    for word in words:
        text = "".join(token[1] for token in word).replace("\n", "")
        length = cell_len(text)
        spaced = cell_len(text.rstrip(" "))
        if column > indent and column + spaced > width:
            wrapped = _without_trailing_spaces(wrapped) + [("", "\n" + " " * indent)]
            column = indent
        wrapped += word
        column += length
    return wrapped


def _without_trailing_spaces(tokens):
    """Returns the tokens without the spaces at their end, which past the last column would wrap onto a row of their own."""
    end = len(tokens)
    while end and tokens[end - 1][1] == " ":
        end -= 1
    return tokens[:end]


def _joined(tokens):
    """Returns the tokens with neighbours of the same style made one, the line breaks left alone."""
    joined = []
    for token in tokens:
        last = joined[-1] if joined else None
        if last and last[0] == token[0] and last[2:] == token[2:] and "\n" not in last[1] + token[1]:
            joined[-1] = (last[0], last[1] + token[1], *last[2:])
        else:
            joined.append(token)
    return joined


class _InTheScreenAlreadyEntered:
    """An output that leaves entering and leaving the alternate screen to whoever entered it."""

    def __init__(self, output):
        self._output = output

    def __getattr__(self, name):
        return getattr(self._output, name)

    def enter_alternate_screen(self):
        pass

    def quit_alternate_screen(self):
        pass


def can_fill_the_screen(option_rows):
    """Returns whether the terminal is tall enough for a report above a menu with this many rows of options."""
    return shutil.get_terminal_size().lines >= option_rows + MENU_ROWS + MIN_REPORT_ROWS


def pick_one_below(print_report, question, entries, note=""):
    """Asks like pick_one, on a screen of its own with the scrolling report above the menu."""
    from prompt_toolkit.filters import to_filter
    from prompt_toolkit.key_binding import merge_key_bindings
    from prompt_toolkit.layout import HSplit, Layout, ScrollablePane, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl

    from update_my_mac.view import scrolling_report

    prompt = _select(question, entries, note)
    _ask_twice_before_aborting(prompt, warn_in_menu=True, blank_line=bool(question or note))

    app = prompt.application
    report = scrolling_report.ScrollingReport(print_report)
    menu = _menu_window(prompt)
    # Not keeping the menu in view, or the top of a long report could never be scrolled to.
    pane = ScrollablePane(
        HSplit([Window(report, dont_extend_height=True), Window(height=1), app.layout.container, Window(height=1)]),
        keep_cursor_visible=False,
        keep_focused_window_visible=False,
        # A scrollbar takes a column the rows were wrapped and counted for.
        show_scrollbar=False,
        display_arrows=False,
    )
    selection = scrolling_report.Selection()
    scrolling = scrolling_report.Scrolling(pane, report, selection)

    if output.in_full_screen():
        app.output = app.renderer.output = _InTheScreenAlreadyEntered(app.output)
    prompt_toolkit_internals.make_full_screen(app)
    app.mouse_support = app.renderer.mouse_support = to_filter(True)
    app.layout = Layout(
        HSplit([pane, Window(FormattedTextControl(scrolling.status_line), height=1, dont_extend_height=True)]),
        focused_element=menu,
    )
    for window in app.layout.find_all_windows():
        if isinstance(window.content, (FormattedTextControl, BufferControl, scrolling_report.ScrollingReport)):
            # The question is drawn by the window as a prefix of its line, which has no mouse position.
            prefix, window.get_line_prefix = window.get_line_prefix, None
            window.content = scrolling_report.Selectable(window.content, selection, prefix)
    app.before_render += selection.forget_what_was_drawn
    app.key_bindings = merge_key_bindings([app.key_bindings, scrolling.key_bindings(app.key_bindings)])
    with scrolling_report.reporting_keys_with_modifiers(app.output):
        return _run(prompt)


def yes_or_no(question, default=True):
    """Asks with Yes and No side by side, picked with the left and right arrows."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import merge_styles
    from questionary import Question
    from questionary.constants import DEFAULT_STYLE

    state = {"yes": default, "answered": False}

    def line():
        asked = [("class:qmark", QMARK), ("class:question", f" {question} ")]
        if state["answered"]:
            return asked + [("class:answer", "Yes" if state["yes"] else "No")]
        return asked + [
            ("class:highlighted" if state["yes"] else "", "Yes"),
            ("", " / "),
            ("" if state["yes"] else "class:highlighted", "No"),
        ]

    bindings = KeyBindings()

    @bindings.add("left")
    @bindings.add("right")
    @bindings.add("tab")
    def _(event):
        state["yes"] = not state["yes"]

    @bindings.add("y")
    def _(event):
        state["yes"] = True

    @bindings.add("n")
    def _(event):
        state["yes"] = False

    @bindings.add("enter")
    def _(event):
        state["answered"] = True
        event.app.exit(result=state["yes"])

    app = Application(
        layout=Layout(Window(FormattedTextControl(line, show_cursor=False), height=1)),
        key_bindings=bindings,
        style=merge_styles([DEFAULT_STYLE, _style()]),
    )
    return _answer_to(Question(app))


def pick_several(question, entries, ends_menu=(), confirm=None, checked=(), start_at=None):
    """Returns the values that are ticked, or just the one from `ends_menu` Enter was pressed on.

    The rows named in `checked` start ticked, and the pointer starts on `start_at`.
    """
    import questionary
    from questionary.prompts import common

    common.INDICATOR_SELECTED, common.INDICATOR_UNSELECTED = TICKED, UNTICKED
    prompt = questionary.checkbox(
        question,
        choices=_choices(entries, checked),
        pointer=POINTER,
        style=_style(),
        qmark=QMARK,
        instruction="(Use arrow keys to move, <space> to select)",
        initial_choice=start_at,
    )
    _shape_checkbox(prompt, ends_menu, confirm)
    _wrap_long_rows(prompt, CHECKBOX_LABEL_COLUMN)
    return _answer_to(prompt, warn_in_menu=True, blank_line=True)


def _answer_to(prompt, warn_in_menu=False, blank_line=False):
    _ask_twice_before_aborting(prompt, warn_in_menu, blank_line)
    return _run(prompt)


def _run(prompt):
    # A Ctrl-C is a BaseException, so it passes this by and ends the run.
    try:
        return prompt.unsafe_ask()
    except Exception as failure:
        raise Unusable(failure) from failure


def _ask_twice_before_aborting(prompt, warn_in_menu=False, blank_line=False):
    """Makes a Ctrl-C take the prompt off the screen, and in a menu only the second one end it.

    In a menu the first one warns, in a row under the options. A prompt without
    options ends at once, and whoever asked prints the warning.
    """
    from prompt_toolkit.filters import Always, Condition, IsDone
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.layout import ConditionalContainer, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    app = prompt.application
    parts = app.layout.container.children if warn_in_menu else None
    if parts is not None:
        # The options would stretch over the free space below them, and a row
        # after them would end up at the bottom of the screen.
        _menu_window(prompt).dont_extend_height = Always()

        if blank_line:
            parts.insert(1, ConditionalContainer(
                Window(FormattedTextControl(""), height=1, dont_extend_height=True),
                filter=~IsDone(),
            ))
        parts.append(ConditionalContainer(
            Window(
                FormattedTextControl([("fg:ansiyellow", WARNING)]),
                height=1,
                dont_extend_height=True,
            ),
            filter=Condition(pressed_ctrl_c) & ~IsDone(),
        ))

    # Any other key takes the warning back. The Ctrl-C that raised it is also
    # followed by this event, and must not be the one to take it back.
    just_pressed = []

    def forget_after_another_key(_key_processor):
        if just_pressed:
            just_pressed.clear()
        elif pressed_ctrl_c():
            forget_ctrl_c()
            app.invalidate()

    if parts is not None:
        app.key_processor.after_key_press += forget_after_another_key

    bindings = KeyBindings()

    @bindings.add(Keys.ControlQ, eager=True)
    @bindings.add(Keys.ControlC, eager=True)
    def _(event):
        just_pressed.append(True)
        if parts is not None and not pressed_ctrl_c():
            press_ctrl_c()
            event.app.invalidate()
            return
        event.app.erase_when_done = True
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    # The last binding for a key wins, so this one replaces questionary's own.
    app.key_bindings = merge_key_bindings([b for b in (app.key_bindings, bindings) if b])


def _shape_checkbox(prompt, ends_menu, confirm):
    """Makes the rows that act instead of tick work like buttons.

    They are drawn without a box, space leaves them alone, and Enter on one of
    `ends_menu` answers with that row alone. Enter on `confirm`, like Enter on
    any other row, answers with what is ticked. The keys <a> and <i> do nothing.
    """
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    from prompt_toolkit.keys import Keys
    from questionary import Separator
    from questionary.prompts import common

    app = prompt.application
    rows = _menu_window(prompt).content
    buttons = tuple(value for value in (*ends_menu, confirm) if value is not None)
    labels = {
        row.title for row in rows.choices
        if not isinstance(row, Separator) and row.value in buttons
    }
    boxes = (common.INDICATOR_SELECTED + " ", common.INDICATOR_UNSELECTED + " ")

    drawn = rows.text

    def tokens():
        return _per_row(
            drawn(), lambda row: _yellow_tick(_cyan_only_under_the_pointer(_without_box(row, labels, boxes)))
        )

    rows.text = tokens

    bindings = KeyBindings()

    @bindings.add("a", eager=True)
    @bindings.add("i", eager=True)
    def _(event):
        """Neither toggling every row nor inverting the picks is offered."""

    @bindings.add(" ", eager=True)
    def _(event):
        pointed = rows.get_pointed_at().value
        if pointed in buttons:
            return
        if pointed in rows.selected_options:
            rows.selected_options.remove(pointed)
        else:
            rows.selected_options.append(pointed)

    @bindings.add(Keys.ControlM, eager=True)
    def _(event):
        pointed = rows.get_pointed_at().value
        if pointed in ends_menu:
            rows.selected_options = [pointed]
        rows.is_answered = True
        event.app.exit(result=[row.value for row in rows.get_selected_values()])

    app.key_bindings = merge_key_bindings([app.key_bindings, bindings])


def _cyan_only_under_the_pointer(row):
    """Returns the row with everything after the pointer highlighted, or a ticked row plain.

    questionary paints a ticked row cyan wherever the pointer is, which hides
    where the pointer is.
    """
    if not any(token[0] == "class:pointer" for token in row):
        return [("class:text", token[1]) if token[0] == "class:selected" else token for token in row]
    marked = ("class:selected", "class:text", "class:highlighted")
    return [("class:highlighted", token[1]) if token[0] in marked else token for token in row]


def _yellow_tick(row):
    """Returns the row with the x of a ticked box in its own style."""
    shown = []
    for token in row:
        if token[1] == TICKED + " ":
            left, mark, right = TICKED
            shown += [(token[0], left), ("class:tick", mark), (token[0], right + " ")]
        else:
            shown.append(token)
    return shown


def _without_box(row, labels, boxes):
    if any(token[1] in labels for token in row):
        return [token for token in row if token[1] not in boxes]
    return row
