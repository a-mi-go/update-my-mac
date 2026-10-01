"""Answering a menu with the arrow keys, where the terminal allows it.

Typing a number always works and is what a pipe, a scheduled run and every
test uses. Where someone is sitting in front of a terminal, moving a cursor
is less work, and the list erases itself afterwards so the transcript keeps
the answer rather than every option that was not chosen.
"""

import importlib.util
import sys

POINTER = "❯"
QMARK = "፧፧፧"


class Unusable(Exception):
    """The menu could not be drawn, whatever the reason."""


def did_not_work(failure):
    return f"[yellow]The arrow keys did not work here ({failure}).[/]"


def available():
    """Whether the keys can be read at all.

    It needs a terminal at both ends, and the library that reads them. An
    installation without it types numbers instead: that path is the one
    everything else uses anyway.
    """
    if importlib.util.find_spec("questionary") is None:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _style():
    """Cyan for what the cursor is on, plain for everything else.

    Merged onto questionary's own style rather than replacing it, so what it
    puts there has to be turned off by name: noinherit clears what came
    before. Its question is already bold and white, which is what a question
    should look like, so that one is left alone.
    """
    from questionary import Style

    return Style([
        ("qmark", "noinherit fg:cyan"),
        ("instruction", "noinherit"),
        ("answer", "noinherit"),
        ("pointer", "noinherit fg:cyan bold"),
        ("highlighted", "noinherit fg:cyan bold"),
        ("selected", "noinherit fg:cyan"),
        ("separator", "noinherit fg:#666666"),
    ])


def _choices(entries):
    """The entries as choices. A None entry is a line the cursor skips.

    Each choice carries the answer it stands for, so nothing has to be
    counted back around the line.
    """
    from questionary import Choice, Separator

    return [
        Separator(SEPARATOR) if entry is None else Choice(entry[1], value=entry[0])
        for entry in entries
    ]


SEPARATOR = "─" * 24


def _answer_to(prompt):
    """Ask the prompt, leaving a Ctrl-C to the run and the rest to the caller.

    Ctrl-C is re-raised rather than handled, because questionary would print
    its own message and hand back None as though nothing had been chosen.
    """
    try:
        return prompt.unsafe_ask()
    except KeyboardInterrupt:
        raise
    except Exception as failure:
        raise Unusable(failure) from failure


def pick_one(question, entries):
    """The answer that was chosen, or None when the person backed out."""
    import questionary

    return _answer_to(questionary.select(
        question,
        choices=_choices(entries),
        pointer=POINTER,
        style=_style(),
        instruction=" ",
        qmark=QMARK,
    ))


def confirm(question, default=False):
    """Yes or no, or None when the person backed out."""
    import questionary

    return _answer_to(questionary.confirm(
        question, default=default, style=_style(), qmark=QMARK, auto_enter=False
    ))


def pick_several(question, entries):
    """The answers that were chosen, or None when the person backed out."""
    import questionary

    return _answer_to(questionary.checkbox(
        question,
        choices=_choices(entries),
        pointer=POINTER,
        style=_style(),
        qmark=QMARK,
    ))
