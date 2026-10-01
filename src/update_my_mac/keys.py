"""Answering a menu with the arrow keys, where the terminal allows it.

Typing a number always works and is what a pipe, a scheduled run and every
test uses.
"""

import importlib.util
import sys

POINTER = "❯"
QMARK = "፧፧፧"
SEPARATOR = "─" * 24


class Unusable(Exception):
    """The menu could not be drawn, whatever the reason."""


def unusable_message(failure):
    return f"[yellow]The menu could not be drawn ({failure}).[/] Type a number instead."


def available():
    """A terminal at both ends, and the library that reads the keys."""
    if importlib.util.find_spec("questionary") is None:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _style():
    """Cyan for what the cursor is on, plain for everything else.

    Every row starts with noinherit because questionary merges this style onto
    its own defaults instead of replacing them.
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
    """The entries as choices. A None entry is a line the cursor skips."""
    from questionary import Choice, Separator

    return [
        Separator(SEPARATOR) if entry is None else Choice(entry[1], value=entry[0])
        for entry in entries
    ]


def _answer_to(prompt):
    """The answer, or Unusable when questionary could not ask at all.

    A Ctrl-C is a BaseException, so it passes this by and ends the run.
    """
    try:
        return prompt.unsafe_ask()
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
