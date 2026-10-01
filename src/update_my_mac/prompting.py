"""Asking a question at the terminal, for the walk-throughs that do that."""

from rich.console import Console
from rich.markup import escape
from rich.rule import Rule
from rich.text import Text

from update_my_mac import keys

# Marked rather than set below a line, because a separator is a row of its own
# and a row can be landed on. An arrow rather than a cross: the last answer is
# often "not now" rather than a refusal.
WAY_OUT = "↩ "

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


def _with_way_out_mark(label, at, total):
    """The label, marked when it is the last one in a menu."""
    return f"{WAY_OUT}{label}" if at == total - 1 else label


def _without_markup(text):
    return Text.from_markup(text).plain if text else ""


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

    def __init__(self, out=None, ask=input, depth=0, with_keys=None):
        self.out = printer(out)
        self.ask = ask
        self.depth = depth
        self.margin = STEP * depth
        # None means "decide from the terminal", which is False in every test.
        self.with_keys = keys.available() if with_keys is None else with_keys

    def inside(self):
        """The step one level in, for whatever this one opens."""
        return Step(self.out, self.ask, self.depth + 1, self.with_keys)

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
        if self.with_keys:
            try:
                chosen = self._choose_with_keys(options, question)
                answered()
                return chosen
            except keys.Unusable as failure:
                self.say(keys.did_not_work(failure))

        if question:
            self.say(question)
        self._print_numbered(options)
        while True:
            # Asked again rather than guessed at, because guessing wrong here
            # acts on an app the person did not mean.
            given = self.read("> ")
            if given.isdigit() and 1 <= int(given) <= len(options):
                answered()
                return options[int(given) - 1][0]
            self.say("[yellow]Didn't catch that.[/]")

    def _choose_with_keys(self, options, question):
        """Move a cursor instead of typing a number.

        A line the cursor skips sets the way out apart, which is what the
        numbered menu uses a mark for.
        """
        entries = list(options)
        entries.insert(len(entries) - 1, None)

        picked = keys.pick_one(_without_markup(question), entries)
        if picked is None:
            # No answer at all, whatever the menu's reason for giving none.
            raise Stopped
        return picked

    def _print_numbered(self, options):
        listed = self.inside()
        for at, (_, label) in enumerate(options):
            marked = escape(_with_way_out_mark(label, at, len(options)))
            listed.say(f"[bold cyan]{at + 1})[/] {marked}")

    def close_section(self):
        self.out(Rule(characters="-", style="white"), width=CLOSING_WIDTH)
