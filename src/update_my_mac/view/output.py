"""The console a run prints to, shared so nothing has to hand one around."""

from contextlib import contextmanager

from rich.console import Console
from rich.control import Control
from rich.text import Text

console = Console(highlight=False)

# What prints the screen again when the window is resized. Set only while the
# screen shows nothing but what it prints, or the clearing would take more away.
_draw_again = None


def redraws_on_resize():
    return _draw_again is not None


@contextmanager
def redrawn_on_resize(draw):
    """Lets a menu asked inside clear the screen and call draw when the window is resized."""
    global _draw_again
    _draw_again = draw
    try:
        yield
    finally:
        _draw_again = None


def stop_redrawing_on_resize():
    global _draw_again
    _draw_again = None


def redraw():
    """Clears the screen and prints it again, now in the width the window has."""
    console.control(Control.clear(), Control.home())
    _draw_again()


def print_plain(*pieces, style=None):
    """Prints one line of plain text pieces or (text, style) pairs, none read as markup."""
    console.print(Text.assemble(*pieces, style=style or ""))
