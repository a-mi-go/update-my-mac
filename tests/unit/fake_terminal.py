"""A terminal that answers from a script and keeps what was printed."""

from rich.rule import Rule
from rich.text import Text

from update_my_mac.prompting import Step

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
        return Step(self.out, self.ask)

    def ask(self, prompt):
        self.lines.append(prompt)
        if not self.answers and self.then is not None:
            raise self.then
        return self.answers.pop(0)

    def out(self, *parts, **options):
        # A rule is a line of its own character, as wide as it was asked for,
        # the way the console draws it.
        drawn = [
            part.characters * options.get("width", WIDTH) if isinstance(part, Rule) else str(part)
            for part in parts
        ]
        # What a person would read, without the colour markup. Parsing it also
        # catches a line whose markup rich cannot render.
        self.lines.append(Text.from_markup(" ".join(drawn)).plain)

    @property
    def text(self):
        return "\n".join(self.lines)
