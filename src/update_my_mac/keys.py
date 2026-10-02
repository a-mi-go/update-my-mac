"""Answering a menu with the arrow keys. Without a terminal, the numbered
menu in prompting.py is used instead.
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
    if importlib.util.find_spec("questionary") is None:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def _style():
    from questionary import Style

    # Every row needs noinherit: questionary merges this onto its own defaults
    # instead of replacing them.
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
    """A None entry becomes a line the cursor skips."""
    from questionary import Choice, Separator

    return [
        Separator(SEPARATOR) if entry is None else Choice(entry[1], value=entry[0])
        for entry in entries
    ]


def _answer_to(prompt):
    # A Ctrl-C is a BaseException, so it passes this by and ends the run.
    try:
        return prompt.unsafe_ask()
    except Exception as failure:
        raise Unusable(failure) from failure


def pick_one(question, entries):
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
    import questionary

    return _answer_to(questionary.confirm(
        question, default=default, style=_style(), qmark=QMARK, auto_enter=False
    ))


def pick_several(question, entries):
    import questionary

    return _answer_to(questionary.checkbox(
        question,
        choices=_choices(entries),
        pointer=POINTER,
        style=_style(),
        qmark=QMARK,
    ))
