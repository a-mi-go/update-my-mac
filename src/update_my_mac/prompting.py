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


# Once is a warning, twice in a row ends the run. An answer in between clears
# it, because one press is easy to hit by accident.
_warned = False


def interrupted(say):
    """What to do about a Ctrl-C. Raises it again when it is the second one."""
    global _warned
    if _warned:
        raise KeyboardInterrupt
    _warned = True
    say("[yellow]Press Ctrl-C again to stop the run.[/]")


def answered():
    """A question that came back clears the warning."""
    global _warned
    _warned = False


class Stopped(Exception):
    """No more input to answer with, which ends the step but not the run.

    Ctrl-C is a different thing and is not caught anywhere below the top: it
    ends the run wherever it arrives.
    """


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
        except EOFError:
            # No more input to answer with, which stops this step. Ctrl-C is
            # not caught here: it ends the run.
            raise Stopped

    def choose(self, options, question=""):
        """Offer the (key, label) options and return the key that was picked.

        The question is asked by whatever draws the menu, so that the one
        that erases itself afterwards takes the question with it.
        """
        if not options:
            # Asking would loop forever, because no answer could be right.
            raise ValueError("a menu has to offer something")
        while True:
            try:
                return self._ask(options, question)
            except KeyboardInterrupt:
                interrupted(self.say)

    def _ask(self, options, question):
        if question:
            self.say(question)
        self._list(options)
        while True:
            # Asked again rather than guessed at, because guessing wrong here
            # acts on an app the person did not mean.
            given = self.read("> ")
            if given.isdigit() and 1 <= int(given) <= len(options):
                answered()
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
