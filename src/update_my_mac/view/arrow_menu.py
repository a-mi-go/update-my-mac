"""The menu answered with the arrow keys. Where it cannot be drawn, prompting.py
prints numbered options and reads a typed number instead.
"""

import importlib.util
import sys

from update_my_mac.view import output

POINTER = "❯"
QMARK = "፧፧"
SEPARATOR = "─" * 24
SEPARATOR_COLOUR = "#666666"
# The note under a question, lighter than the separator and darker than the text.
NOTE_COLOUR = "#999999"
# Where the labels start, so the note lines up with the rows below it.
NOTE_INDENT = "   "


# How long the window has to keep its width before the screen is drawn again:
# dragging an edge resizes it at every step, and only the last one counts.
RESIZE_SETTLE = 0.3


class Unusable(Exception):
    """The menu could not be drawn, whatever the reason."""


class Resized(Exception):
    """The window got another width while the menu was asking."""


def unusable_message(failure):
    from rich.text import Text

    return Text.assemble((f"The menu could not be drawn ({failure}).", "yellow"), " Type a number instead.")


def can_be_drawn():
    if importlib.util.find_spec("questionary") is None:
        return False
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
        ("instruction", f"noinherit fg:{NOTE_COLOUR}" if for_note else "noinherit"),
        ("answer", "noinherit fg:#f2a900"), # d48d37
        ("pointer", "noinherit fg:ansicyan"),
        ("highlighted", "noinherit fg:ansicyan"),
        ("selected", "noinherit"),
        ("separator", f"noinherit fg:{SEPARATOR_COLOUR}"),
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
    import questionary

    return _answer_to(questionary.select(
        question,
        choices=_choices(entries),
        pointer=POINTER,
        style=_style(for_note=bool(note)),
        # The note beside the question, and only until the menu is answered.
        instruction=beside_the_question(note) if note else " ",
        # Without a question there is nothing for the mark to introduce.
        qmark=QMARK if question else "",
    ), warn_in_menu=True, blank_line=bool(question or note))


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

    common.INDICATOR_SELECTED, common.INDICATOR_UNSELECTED = "[X]", "[ ]"
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
    return _answer_to(prompt, warn_in_menu=True, blank_line=True)


def _answer_to(prompt, warn_in_menu=False, blank_line=False):
    _ask_twice_before_aborting(prompt, warn_in_menu, blank_line)
    if output.redraws_on_resize():
        _end_when_resized(prompt.application)
    # A Ctrl-C is a BaseException, so it passes this by and ends the run.
    try:
        return prompt.unsafe_ask()
    except Resized:
        raise
    except Exception as failure:
        raise Unusable(failure) from failure


def _end_when_resized(app):
    """Ends the prompt with Resized once the window's width has stopped changing."""
    width = app.output.get_size().columns
    waiting = []

    def end():
        if not app.is_done:
            app.exit(exception=Resized())

    def look_at_the_width(_app):
        for timer in waiting:
            timer.cancel()
        waiting.clear()
        if app.output.get_size().columns != width:
            waiting.append(app.loop.call_later(RESIZE_SETTLE, end))

    app.before_render += look_at_the_width


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
    from questionary.prompts.common import InquirerControl

    app = prompt.application
    parts = app.layout.container.children if warn_in_menu else None
    if parts is not None:
        # The options would stretch over the free space below them, and a row
        # after them would end up at the bottom of the screen.
        for window in app.layout.find_all_windows():
            if isinstance(window.content, InquirerControl):
                window.dont_extend_height = Always()

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
    from questionary.prompts.common import InquirerControl

    app = prompt.application
    rows = next(c for c in app.layout.find_all_controls() if isinstance(c, InquirerControl))
    buttons = tuple(value for value in (*ends_menu, confirm) if value is not None)
    labels = {
        row.title for row in rows.choices
        if not isinstance(row, Separator) and row.value in buttons
    }
    boxes = (common.INDICATOR_SELECTED + " ", common.INDICATOR_UNSELECTED + " ")

    drawn = rows.text

    def tokens():
        shown, row = [], []
        for token in drawn():
            row.append(token)
            if token[1] == "\n":
                shown += _cyan_only_under_the_pointer(_without_box(row, labels, boxes))
                row = []
        return shown + _cyan_only_under_the_pointer(_without_box(row, labels, boxes))

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


def _without_box(row, labels, boxes):
    if any(token[1] in labels for token in row):
        return [token for token in row if token[1] not in boxes]
    return row
