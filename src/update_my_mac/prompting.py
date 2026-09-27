"""Asking a question at the terminal, for the walk-throughs that do that."""

from rich.console import Console
from rich.markup import escape
from rich.rule import Rule

# The way out of a menu sits below a line, so it reads as a way out rather
# than as one more thing to do.
SEPARATOR = "-----"

# How far one step of the conversation sits inside the one that opened it.
STEP = "  "

# The line that closes a section. Capped rather than drawn edge to edge, so it
# reads as a divider between two parts of the run rather than as the edge of
# the terminal, and a narrow terminal still gets a whole line of its own.
CLOSING_WIDTH = 84


class Stopped(Exception):
    """Ctrl-C, or no more input to answer with."""


def printer(out):
    """The given print function, or one onto a fresh console."""
    return out or Console(highlight=False, soft_wrap=True).print


class Step:
    """One level of the conversation, and the only way to reach the next.

    A question and the answer to it stand in the same column, with the options
    between them one step further in. Where that column is, is nobody's
    business but the step's: a walk-through opened from here gets `inside()`
    and never learns how deep it ended up.
    """

    def __init__(self, out=None, ask=input, depth=0):
        self.out = printer(out)
        self.ask = ask
        self.depth = depth
        self.margin = STEP * depth

    def inside(self):
        """The step one level in, for whatever this one opens."""
        return Step(self.out, self.ask, self.depth + 1)

    def say(self, text=""):
        # A blank line is left as it is: indenting it would leave trailing spaces.
        self.out(f"{self.margin}{text}" if text else "")

    def read(self, question):
        try:
            return self.ask(f"{self.margin}{question}").strip()
        except (EOFError, KeyboardInterrupt):
            raise Stopped

    def choose(self, options):
        """Offer the (key, label) options and return the key that was picked."""
        if not options:
            # Asking would loop forever, because no answer could be right.
            raise ValueError("a menu has to offer something")
        self._list(options)
        while True:
            # Asked again rather than guessed at, because guessing wrong here
            # acts on an app the person did not mean.
            given = self.read("> ")
            if given.isdigit() and 1 <= int(given) <= len(options):
                return options[int(given) - 1][0]
            self.say("[yellow]Didn't catch that.[/]")

    def _list(self, options):
        listed = self.inside()
        for number, (_, label) in enumerate(options, start=1):
            if number == len(options):
                listed.say(f"[dim]{SEPARATOR}[/]")
            listed.say(f"[bold cyan]{number})[/] {escape(label)}")

    def close_section(self):
        self.out(Rule(characters="-", style="white"), width=CLOSING_WIDTH)
