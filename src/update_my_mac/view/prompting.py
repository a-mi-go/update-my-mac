"""Asking a question at the terminal, for the walk-throughs that do that."""

import re
import signal
from contextlib import contextmanager

from rich.markup import escape
from rich.rule import Rule
from rich.text import Text

from update_my_mac.view import arrow_menu, output

# Leads an answer that leaves the menu without doing anything.
WAY_OUT = "↩ "
WAYS_OUT = (WAY_OUT, "↳ ", "⏭ ")

# How far one step of the conversation sits inside the one that opened it.
STEP = "  "

# The line that sets a menu apart, capped so it reads as a divider rather than
# as the edge of the terminal.
SEPARATOR_WIDTH = 84
SEPARATOR_CHARACTER = "─"

# Leads an option that has no symbol of its own, so all texts start in line.
BULLET = "• "
STARTS_WITH_SYMBOL = re.compile(r"[^\w\s(\[\"'] ")


class Stopped(Exception):
    """No more input to answer with."""


class Markup(str):
    """A menu label that carries rich markup, drawn styled instead of escaped."""


def label_with_note(label, note):
    """Returns the menu label with the note after it in grey, or just the label without a note."""
    if not note:
        return label
    return Markup(f"{escape(label)} [{arrow_menu.NOTE_COLOR}]({escape(note)})[/]")


class Step:
    """One level of the conversation, and the only way to reach the next."""

    def __init__(self, depth=0):
        self.depth = depth
        self.margin = STEP * depth
        self._set_next_menu_apart = False

    def inside(self):
        return Step(self.depth + 1)

    def print_indented(self, *pieces, style=None):
        """Prints one line at this step's indent.

        Each piece is plain text, a (text, style) pair, or a rich Text.
        """
        print_unwrapped(Text.assemble(self.margin, Text.assemble(*pieces, style=style or "")))

    def print_empty_line(self):
        # Not indented, which would leave trailing spaces.
        print_unwrapped("")

    def read(self, question):
        try:
            return read_answer(f"{self.margin}{question}").strip()
        except EOFError:
            raise Stopped

    def choose(self, options, question="", note="", above=None):
        """Returns the key that was picked; `above` prints the report the menu belongs under."""
        if not options:
            # Asking would loop forever, because no answer could be right.
            raise ValueError("a menu has to offer something")
        self._set_apart_if_asked(options)
        while True:
            try:
                chosen = self._ask_by_arrows_or_typed_number(options, question, note, above)
            except KeyboardInterrupt:
                interrupted(self.print_indented)
                continue
            except Stopped:
                answered()
                raise
            answered()
            return chosen

    def yes_or_no(self, question, default=True):
        """Returns True for yes. Asked with the arrow keys, or by number without them."""
        while True:
            try:
                answer = self._yes_or_no_by_arrows_or_typed_number(question, default)
            except KeyboardInterrupt:
                interrupted(self.print_indented)
                continue
            except Stopped:
                answered()
                raise
            answered()
            self._remember_answer(question, "Yes" if answer else "No")
            return answer

    def _remember_answer(self, question, shown):
        # The menu drew this line itself, which is not on any console to be kept.
        output.remember(lambda console: console.print(Text.assemble(
            (arrow_menu.QMARK, "cyan"), " ", (f"{question} ", "bold"), (shown, arrow_menu.ANSWER_COLOR),
        )))

    def _yes_or_no_by_arrows_or_typed_number(self, question, default):
        if arrow_menu.can_be_drawn():
            try:
                return bool(arrow_menu.yes_or_no(question, default))
            except arrow_menu.Unusable as failure:
                self.print_indented(arrow_menu.unusable_message(failure))
        return self._ask_by_typed_number([(True, "yes"), (False, "no")], question, "")

    def _ask_by_arrows_or_typed_number(self, options, question, note, above):
        if above is not None and not self._can_show_below(options):
            self._print_above(above)
            above = None
        if arrow_menu.can_be_drawn():
            try:
                return self._choose_with_arrows(options, question, note, above)
            except arrow_menu.Unusable as failure:
                self.print_indented(arrow_menu.unusable_message(failure))
        if above is not None:
            self._print_above(above)
        return self._ask_by_typed_number(options, question, note)

    def _can_show_below(self, options):
        return arrow_menu.can_be_drawn() and arrow_menu.can_fill_the_screen(len(options))

    def _print_above(self, above):
        if output.is_already_printed(above):
            return
        output.print_above(above)
        self.print_empty_line()

    def _ask_by_typed_number(self, options, question, note):
        # An empty question still takes its line, as it does with the arrow keys.
        first, *rest = note.splitlines() or [""]
        if first:
            self.print_indented((question, "bold"), "  ", (first, arrow_menu.NOTE_COLOR))
        elif question:
            self.print_indented(question, style="bold")
        else:
            self.print_empty_line()
        for line in rest:
            self.inside().print_indented(line, style=arrow_menu.NOTE_COLOR)
        if question or note:
            self.print_empty_line()
        self._print_numbered(options)
        while True:
            # Asked again rather than guessed at, because guessing wrong here
            # acts on an app the person did not mean.
            given = self.read("> ")
            if given.isdigit() and 1 <= int(given) <= len(options):
                return options[int(given) - 1][0]
            self.print_indented("Didn't catch that.", style="yellow")

    def _choose_with_arrows(self, options, question, note, above=None):
        entries = [
            (key, arrow_menu.styled(_bulleted(label)) if isinstance(label, Markup) else _bulleted(label))
            for key, label in options
        ]
        # A line the cursor skips sets the way out apart.
        way_out = next(
            (at for at, (_, label) in enumerate(options)
             if _plain(label).startswith(WAYS_OUT)),
            None,
        )
        if way_out is not None:
            entries.insert(way_out, None)

        if above is None:
            picked = arrow_menu.pick_one(question, entries, note)
        else:
            picked = arrow_menu.pick_one_below(above, question, entries, note)
        if picked is None:
            # questionary gives None when the menu was aborted.
            raise Stopped
        if above is not None:
            # The screen the menu was on is gone, with the report.
            self._print_above(above)
        return picked

    def _print_numbered(self, options):
        listed_items = self.inside()
        for at, (_, label) in enumerate(options):
            label = _bulleted(label)
            shown = Text.from_markup(label) if isinstance(label, Markup) else label
            listed_items.print_indented((f"{at + 1})", "cyan"), " ", shown)

    def print_separator(self):
        print_separator()

    def begin_menu(self):
        """Has the next menu set apart from what is above it, unless it comes up on a screen that leaves nothing behind."""
        self._set_next_menu_apart = True

    def _set_apart_if_asked(self, options):
        if not self._set_next_menu_apart:
            return
        self._set_next_menu_apart = False
        if not arrow_menu.runs_on_its_own_screen(len(options)):
            self.print_empty_line()
            self.print_separator()


def print_unwrapped(renderable, **options):
    """Prints to the shared console without letting it re-wrap long lines."""
    if isinstance(renderable, str):
        renderable = Text(renderable)
    output.console.print(renderable, soft_wrap=True, **options)


def print_separator():
    """Draws the line that sets a new menu apart from what came before."""
    print_unwrapped(
        Rule(characters=SEPARATOR_CHARACTER, style=arrow_menu.SEPARATOR_COLOR), width=SEPARATOR_WIDTH
    )


def interrupted(print_line):
    if arrow_menu.pressed_ctrl_c():
        raise KeyboardInterrupt
    arrow_menu.press_ctrl_c()
    print_line(arrow_menu.WARNING, style="yellow")


def answered():
    arrow_menu.forget_ctrl_c()


@contextmanager
def warning_before_stopping():
    """Makes the first Ctrl-C only warn while the block runs, as it does in a menu."""
    previous = signal.signal(signal.SIGINT, lambda *_: interrupted(print_unwrapped))
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
        answered()


def read_answer(prompt):
    return input(prompt)


def _bulleted(label):
    if STARTS_WITH_SYMBOL.match(_plain(label)):
        return label
    return Markup(BULLET + label) if isinstance(label, Markup) else BULLET + label


def _plain(label):
    """Returns the text a label shows, without its markup if it carries any."""
    return _without_markup(label) if isinstance(label, Markup) else label


def _without_markup(text):
    return Text.from_markup(text).plain if text else ""
