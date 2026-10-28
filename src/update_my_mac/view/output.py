"""The console a run prints to, shared so nothing has to hand one around."""

import codecs
import re
import sys
from contextlib import contextmanager

from rich.console import Console
from rich.control import Control
from rich.text import Text

from update_my_mac.system import shell

_NOT_A_COLOUR = re.compile(r"\x1b\](?:[^\x07\x1b]*)(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[ -/]*[@-ln-~]")


class RecordingConsole(Console):
    """A console that keeps what is printed to it while the run is on a screen of its own."""

    def print(self, *objects, **options):
        super().print(*objects, **options)
        # The spinner prints control codes to move itself, which are not output.
        if not any(isinstance(each, Control) for each in objects):
            remember(lambda console: console.print(*objects, **options))


console = RecordingConsole(highlight=False)

# Below this a screen of its own has no room for a report above a menu.
MIN_FULL_SCREEN_ROWS = 20
# A program that ended without switching these off leaves the terminal's selection blocked for the next one.
MOUSE_REPORTING_OFF = "\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l"

_in_full_screen = False
_remembered = []
_remembering = False
_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
_unfinished_line = ""


def remember(print_again):
    """Keeps something printed on the screen of its own, as the function that prints it again."""
    if _remembering:
        _remembered.append(print_again)


def replay(console):
    for print_again in _remembered:
        print_again(console)


def remember_command_output(data):
    """Keeps what a command wrote a line at a time, and what is left when it ends (None)."""
    global _unfinished_line
    if not _remembering:
        return
    text = _unfinished_line + (_decoder.decode(data) if data is not None else _decoder.decode(b"", final=True))
    *lines, _unfinished_line = text.split("\n")
    if data is None and _unfinished_line:
        lines.append(_unfinished_line)
    if data is None:
        _unfinished_line = ""
    for line in lines:
        # A progress bar redraws its line, and a pty ends every line with a carriage return.
        shown = _NOT_A_COLOUR.sub("", line.rstrip("\r").split("\r")[-1])
        remember(lambda console, shown=shown: console.print(Text.from_ansi(shown)))


def print_above(above):
    """Leaves the screen of its own and prints what ran on it, then what `above` prints."""
    leave_full_screen()
    replay(console)
    above(console)


def in_full_screen():
    return _in_full_screen


@contextmanager
def full_screen():
    """Runs on a screen of its own, where the terminal can have one, until it is left."""
    global _in_full_screen, _remembering
    if console.is_terminal:
        console.file.write(MOUSE_REPORTING_OFF)
        console.file.flush()
    if console.is_terminal and sys.stdin.isatty() and console.height >= MIN_FULL_SCREEN_ROWS:
        console.set_alt_screen(True)
        _in_full_screen = True
        _remembered.clear()
        _remembering = True
        shell.listen_to_command_output(remember_command_output)
    try:
        yield
    finally:
        if _in_full_screen:
            leave_full_screen()
            replay(console)


def leave_full_screen():
    """Goes back to the screen the run started on. Does nothing when it is already there."""
    global _in_full_screen, _remembering
    if _in_full_screen:
        console.set_alt_screen(False)
        _in_full_screen = False
        _remembering = False
        shell.listen_to_command_output(None)


def print_plain(*pieces, style=None):
    """Prints one line of plain text pieces or (text, style) pairs, none read as markup."""
    console.print(Text.assemble(*pieces, style=style or ""))
