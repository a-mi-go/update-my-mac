"""Asking a question at the terminal, for the walk-throughs that do that."""

from rich.console import Console


class Stopped(Exception):
    """Ctrl-C, or no more input to answer with."""


def printer(out):
    """The given print function, or one onto a fresh console."""
    return out or Console(highlight=False, soft_wrap=True).print


def answer(ask, question):
    try:
        return ask(question).strip()
    except (EOFError, KeyboardInterrupt):
        raise Stopped
