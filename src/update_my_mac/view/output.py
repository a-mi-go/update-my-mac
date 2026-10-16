"""The console a run prints to, shared so nothing has to hand one around."""

from rich.console import Console
from rich.text import Text

console = Console(highlight=False)


def print_plain(*pieces, style=None):
    """Prints one line of plain text pieces or (text, style) pairs, none read as markup."""
    console.print(Text.assemble(*pieces, style=style or ""))
