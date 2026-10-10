"""Asking a question at the terminal, for the walk-throughs that do that."""

from rich.console import Console
from rich.markup import escape
from rich.rule import Rule
from rich.text import Text

from update_my_mac.view import keys

# Marked rather than set below a line, because a separator is a row of its own
# and a cursor can land on it.
WAY_OUT = "↩ "

# How far one step of the conversation sits inside the one that opened it.
STEP = "  "

# The line that closes a section, capped so it reads as a divider rather than
# as the edge of the terminal.
CLOSING_WIDTH = 84


_pressed_ctrl_c = False


def interrupted(say):
    global _pressed_ctrl_c
    if _pressed_ctrl_c:
        raise KeyboardInterrupt
    _pressed_ctrl_c = True
    say("[yellow]Press Ctrl-C again to stop the run.[/]")


def answered():
    global _pressed_ctrl_c
    _pressed_ctrl_c = False


class Stopped(Exception):
    """No more input to answer with. Ctrl-C is the other one, and it ends the run."""


def _with_way_out_mark(label, at, total):
    return f"{WAY_OUT}{label}" if at == total - 1 else label


def _without_markup(text):
    return Text.from_markup(text).plain if text else ""


def printer(out):
    return out or Console(highlight=False, soft_wrap=True).print


class Step:
    """One level of the conversation, and the only way to reach the next."""

    def __init__(self, out=None, ask=input, depth=0, with_keys=None):
        self.out = printer(out)
        self.ask = ask
        self.depth = depth
        self.margin = STEP * depth
        self.with_keys = keys.available() if with_keys is None else with_keys

    def inside(self):
        return Step(self.out, self.ask, self.depth + 1, self.with_keys)

    def say(self, text=""):
        # A blank line is left as it is: indenting it would leave trailing spaces.
        self.out(f"{self.margin}{text}" if text else "")

    def read(self, question):
        try:
            return self.ask(f"{self.margin}{question}").strip()
        except EOFError:
            raise Stopped

    def choose(self, options, question=""):
        """Returns the key that was picked, after drawing the question and the options."""
        if not options:
            # Asking would loop forever, because no answer could be right.
            raise ValueError("a menu has to offer something")
        while True:
            try:
                chosen = self._ask_by_keys_or_number(options, question)
            except KeyboardInterrupt:
                interrupted(self.say)
                continue
            except Stopped:
                answered()
                raise
            answered()
            return chosen

    def _ask_by_keys_or_number(self, options, question):
        if self.with_keys:
            try:
                return self._choose_with_keys(options, question)
            except keys.Unusable as failure:
                self.say(keys.unusable_message(failure))

        if question:
            self.say(question)
        self._print_numbered(options)
        while True:
            # Asked again rather than guessed at, because guessing wrong here
            # acts on an app the person did not mean.
            given = self.read("> ")
            if given.isdigit() and 1 <= int(given) <= len(options):
                return options[int(given) - 1][0]
            self.say("[yellow]Didn't catch that.[/]")

    def _choose_with_keys(self, options, question):
        entries = list(options)
        # A line the cursor skips sets the way out apart.
        entries.insert(len(entries) - 1, None)

        picked = keys.pick_one(_without_markup(question), entries)
        if picked is None:
            # questionary gives None when the menu was aborted.
            raise Stopped
        return picked

    def _print_numbered(self, options):
        listed = self.inside()
        for at, (_, label) in enumerate(options):
            marked = escape(_with_way_out_mark(label, at, len(options)))
            listed.say(f"[bold cyan]{at + 1})[/] {marked}")

    def close_section(self):
        self.out(Rule(characters="-", style="white"), width=CLOSING_WIDTH)
