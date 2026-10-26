"""Scrolling and selecting on the screen that has the report above the menu."""

import io
import time
from contextlib import contextmanager

from prompt_toolkit.application import get_app
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.input.vt100_parser import _IS_PREFIX_OF_LONGER_MATCH_CACHE
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.mouse_events import MouseEventType
from rich.console import Console

from update_my_mac.system import shell
from update_my_mac.view import arrow_menu
from update_my_mac.view import output

WHEEL_ROWS = 3
DOUBLE_CLICK_SECONDS = 0.4
AFTER_THE_LAST_COLUMN = 10_000
# More rows than any screen has, which a pane clamps to its last.
TO_THE_END = 1_000_000
ROWS_BESIDE_THE_PANE = 1

PUSH_KITTY_DISAMBIGUATE = "\x1b[>1u"
POP_KITTY_FLAGS = "\x1b[<u"
# What the terminal writes then for the menu's keys, and for Cmd-C, which is read as F24.
KEYS_WITH_MODIFIERS = {
    "\x1b[99;9u": Keys.F24,
    "\x1b[99;5u": Keys.ControlC,
    "\x1b[113;5u": Keys.ControlQ,
    "\x1b[110;5u": Keys.ControlN,
    "\x1b[112;5u": Keys.ControlP,
    "\x1b[100;5u": Keys.ControlD,
    "\x1b[27u": Keys.Escape,
}


class ScrollingReport(UIControl):
    """The earlier output, then the report, printed at the width it is given."""

    def __init__(self, print_report):
        self._print_report = print_report
        self._lines = []
        self._width = None
        self.show_line = lambda line: None
        self.report_starts_at = 0

    def _printed(self, print_to, width):
        drawn = io.StringIO()
        print_to(Console(
            file=drawn, width=width, force_terminal=True, color_system="standard", highlight=False
        ))
        lines = list(split_lines(ANSI(drawn.getvalue()).__pt_formatted_text__()))
        # The newline that ends the last line is not another line.
        if lines and not any(text for _, text, *_ in lines[-1]):
            lines.pop()
        return lines

    def _lines_at(self, width):
        if width != self._width:
            earlier = self._printed(output.replay, width)
            first_time = self._width is None
            self._lines = earlier + self._printed(self._print_report, width)
            self._width = width
            self.report_starts_at = len(earlier)
            if first_time:
                self.show_line(self.report_starts_at)
        return self._lines

    def preferred_height(self, width, max_available_height, wrap_lines, get_line_prefix):
        return len(self._lines_at(width))

    def create_content(self, width, height):
        lines = self._lines_at(width)
        return UIContent(lambda at: lines[at], line_count=len(lines), show_cursor=False)


class Selection:
    """What is selected over the controls of a screen, as (control, line, character) positions."""

    def __init__(self):
        self._controls = []
        self._drawn = {}
        self._widths = {}
        self._anchor = self._focus = None
        self._dragging = False
        self._clicks, self._last_click = 0, None
        self.notice = ""
        self.scroll_by = lambda rows: None

    def add(self, control):
        self._controls.append(control)
        return len(self._controls) - 1

    def draw(self, control, content, width):
        # A position is a character of a line, which another width draws somewhere else.
        if self._widths.get(control, width) != width:
            self._anchor = self._focus = None
        self._widths[control] = width
        self._drawn[control] = content

    def forget_what_was_drawn(self, _app=None):
        self._drawn.clear()

    def _text(self, control, line):
        return "".join(text for _, text, *_ in self._drawn[control].get_line(line))

    def _span(self, control, line):
        """Returns the first and last character selected on a line, or None when none is."""
        if self._anchor is None or self._anchor == self._focus and self._clicks < 2:
            return None
        first, last = sorted((self._anchor, self._focus))
        here = (control, line)
        if not first[:2] <= here <= last[:2]:
            return None
        return (first[2] if here == first[:2] else 0, last[2] if here == last[:2] else AFTER_THE_LAST_COLUMN)

    def styled(self, control, line, fragments):
        span = self._span(control, line)
        if span is None:
            return fragments
        styled = []
        for at, (style, character) in enumerate(
            (style, character) for style, text, *_ in fragments for character in text
        ):
            if span[0] <= at <= span[1]:
                style = f"{style} reverse"
            if styled and styled[-1][0] == style:
                styled[-1] = (style, styled[-1][1] + character)
            else:
                styled.append((style, character))
        return styled

    def handle(self, control, mouse_event, line_count):
        """Reads a mouse event over a control. Returns NotImplemented for what is not for the selection."""
        kind, position = mouse_event.event_type, mouse_event.position
        at = (control, max(0, min(position.y, line_count - 1)), position.x)
        if kind == MouseEventType.SCROLL_UP:
            self.scroll_by(-WHEEL_ROWS)
        elif kind == MouseEventType.SCROLL_DOWN:
            self.scroll_by(WHEEL_ROWS)
        elif kind == MouseEventType.MOUSE_DOWN:
            self._press(at)
        elif kind == MouseEventType.MOUSE_MOVE and self._dragging:
            self._focus = at
            get_app().invalidate()
        elif kind == MouseEventType.MOUSE_UP and self._dragging:
            self._release()
        else:
            return NotImplemented
        return None

    def _press(self, at):
        now = time.monotonic()
        again = self._last_click is not None and (
            now - self._last_click[0] < DOUBLE_CLICK_SECONDS and self._last_click[1:] == at
        )
        self._clicks = self._clicks + 1 if again else 1
        self._last_click = (now, *at)
        self._dragging = True
        self.notice = ""
        self._anchor = self._focus = at
        if self._clicks == 2:
            self._anchor, self._focus = self._word_at(*at)
        elif self._clicks >= 3:
            self._anchor, self._focus = (at[0], at[1], 0), (at[0], at[1], AFTER_THE_LAST_COLUMN)
        get_app().invalidate()

    def _word_at(self, control, line, column):
        text = self._text(control, line)
        if not 0 <= column < len(text) or text[column].isspace():
            return (control, line, column), (control, line, column)
        first = last = column
        while first > 0 and not text[first - 1].isspace():
            first -= 1
        while last < len(text) - 1 and not text[last + 1].isspace():
            last += 1
        return (control, line, first), (control, line, last)

    def _release(self):
        self._dragging = False
        if self._anchor == self._focus and self._clicks < 2:
            self._anchor = self._focus = None
            return
        self.copy_selection()

    def copy_selection(self):
        if self._anchor is None or self._anchor == self._focus and self._clicks < 2:
            self.notice = "nothing is selected"
            get_app().invalidate()
            return
        text = self._selected_text()
        copied = shell.copy_to_clipboard(text)
        self.notice = (
            f"copied {len(text)} characters, they are on the clipboard already"
            if copied else "could not copy the selection"
        )
        get_app().invalidate()

    def _selected_text(self):
        first, last = sorted((self._anchor, self._focus))
        lines = []
        for control in range(first[0], last[0] + 1):
            if control not in self._drawn:
                continue
            start = first[1] if control == first[0] else 0
            end = last[1] if control == last[0] else self._drawn[control].line_count - 1
            for line in range(start, end + 1):
                from_character, to_character = self._span(control, line)
                lines.append(self._text(control, line)[from_character : to_character + 1].rstrip())
        return "\n".join(lines)


class Selectable(UIControl):
    """A control of the screen that shows what is selected over it, and reads the mouse for the selection."""

    def __init__(self, control, selection, line_prefix=None):
        self._control = control
        self._selection = selection
        self._line_prefix = line_prefix
        self._number = selection.add(self)
        self._line_count = 0

    def reset(self):
        self._control.reset()

    def preferred_width(self, max_available_width):
        return self._control.preferred_width(max_available_width)

    def preferred_height(self, width, max_available_height, wrap_lines, get_line_prefix):
        return self._control.preferred_height(width, max_available_height, wrap_lines, get_line_prefix)

    def is_focusable(self):
        return self._control.is_focusable()

    def create_content(self, width, height):
        content = self._control.create_content(width, height)
        whole = UIContent(self._with_prefix(content), line_count=content.line_count)
        self._selection.draw(self._number, whole, width)
        self._line_count = content.line_count
        return UIContent(
            lambda line: self._selection.styled(self._number, line, whole.get_line(line)),
            line_count=content.line_count,
            cursor_position=content.cursor_position,
            menu_position=content.menu_position,
            show_cursor=content.show_cursor,
        )

    def _with_prefix(self, content):
        if self._line_prefix is None:
            return content.get_line
        return lambda line: [*self._line_prefix(line, 0), *content.get_line(line)]

    def mouse_handler(self, mouse_event):
        result = self._selection.handle(self._number, mouse_event, self._line_count)
        return self._control.mouse_handler(mouse_event) if result is NotImplemented else result

    def move_cursor_down(self):
        self._control.move_cursor_down()

    def move_cursor_up(self):
        self._control.move_cursor_up()

    def get_key_bindings(self):
        return self._control.get_key_bindings()

    def get_invalidate_events(self):
        return self._control.get_invalidate_events()


class Scrolling:
    """Scrolls a pane by lines and pages, and takes it to the menu when the menu's own keys are used."""

    def __init__(self, pane, report, selection):
        self._pane = pane
        self._report = report
        self._selection = selection
        selection.scroll_by = self.by
        report.show_line = self._show_line

    def _show_line(self, line):
        self._pane.vertical_scroll = line

    def by(self, rows):
        self._selection.notice = ""
        self._pane.vertical_scroll = max(0, self._pane.vertical_scroll + rows)
        get_app().invalidate()

    def _page(self):
        return max(1, get_app().output.get_size().rows - ROWS_BESIDE_THE_PANE - 1)

    def status_line(self):
        keys = "Up/Down choose  ·  Page Up/Down, Home/End, wheel scroll  ·  drag or Cmd-C copies"
        before = "Scroll up for what ran before  ·  " if self._report.report_starts_at else ""
        return [(f"fg:{arrow_menu.NOTE_COLOUR}", f" {self._selection.notice or before + keys}")]

    def key_bindings(self, menu_bindings):
        bindings = KeyBindings()
        bindings.add("pageup")(lambda event: self.by(-self._page()))
        bindings.add("pagedown")(lambda event: self.by(self._page()))
        bindings.add("home")(lambda event: self.by(-TO_THE_END))
        bindings.add("end")(lambda event: self.by(TO_THE_END))
        bindings.add(Keys.F24)(lambda event: self._selection.copy_selection())
        for key in (Keys.Up, Keys.Down, Keys.ControlC):
            bindings.add(key, eager=True)(self._moving_the_menu(menu_bindings, key))
        return bindings

    def _moving_the_menu(self, menu_bindings, key):
        move = menu_bindings.get_bindings_for_keys((key,))[-1].handler

        def move_and_show(event):
            move(event)
            self.by(TO_THE_END)

        return move_and_show


@contextmanager
def reporting_keys_with_modifiers(output):
    """Has the terminal tell which modifier went with a key, so Cmd-C reaches the run instead of the terminal."""
    ANSI_SEQUENCES.update(KEYS_WITH_MODIFIERS)
    _IS_PREFIX_OF_LONGER_MATCH_CACHE.clear()
    output.write_raw(PUSH_KITTY_DISAMBIGUATE)
    output.flush()
    try:
        yield
    finally:
        output.write_raw(POP_KITTY_FLAGS)
        output.flush()
