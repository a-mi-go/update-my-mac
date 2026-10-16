"""A terminal that answers from a script and keeps what was printed."""

from rich.rule import Rule
from rich.text import Text

from update_my_mac.view import prompting

WIDTH = 60


class Terminal:
    def __init__(self, *answers, then=None):
        self.answers = list(answers)
        # What happens once the script runs out: a real terminal can reach the
        # end of its input, or the person can press Ctrl-C.
        self.then = then
        self.lines = []

    @property
    def step(self):
        """The outermost level of a conversation held with this terminal."""
        prompting.print_unwrapped = self.out
        prompting.read_answer = self.ask
        return prompting.Step()

    def answering(self, ask):
        """A step that prints here but takes its answers from `ask`."""
        step = self.step
        prompting.read_answer = ask
        return step

    def with_arrows(self):
        """A step that offers the arrow-key menu, printing here."""
        step = self.step
        prompting.arrow_menu.can_be_drawn = lambda: True
        return step

    def ask(self, prompt):
        self.lines.append(prompt)
        if not self.answers and self.then is not None:
            raise self.then
        return self.answers.pop(0)

    def out(self, renderable="", **options):
        # A rule is a line of its own character, as wide as it was asked for,
        # the way the console draws it.
        if isinstance(renderable, Rule):
            self.lines.append(renderable.characters * options.get("width", WIDTH))
        else:
            # The setup command still prints markup strings; a menu prints Text.
            text = renderable if isinstance(renderable, Text) else Text.from_markup(str(renderable))
            self.lines.append(text.plain)

    @property
    def text(self):
        return "\n".join(self.lines)
