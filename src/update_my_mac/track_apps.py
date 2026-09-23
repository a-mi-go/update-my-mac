"""Going through the apps no package manager tracks, and revisiting that later.

Deciding to leave an app alone is the only decision on offer so far. Adopting
one into Homebrew Cask, or watching its update feed, comes later; the menu is
where those will appear.
"""

from rich.console import Console
from rich.markup import escape


def _printer(out):
    """The given print function, or one onto a fresh console."""
    return out or Console(highlight=False, soft_wrap=True).print


class Stopped(Exception):
    """Ctrl-C, or no more input to answer with."""


def _answer(ask, question):
    try:
        return ask(question).strip()
    except (EOFError, KeyboardInterrupt):
        raise Stopped


def run_untracked_menu(apps, decisions, ask=input, out=None, interactive=True):
    """Offer to leave each untracked app alone. Returns how many were ignored."""
    console_print = _printer(out)
    waiting = [app for app in apps if not decisions.is_ignored(app.name)]
    if not waiting or not interactive:
        return 0

    console_print()
    console_print(f"{len(waiting)} of these are not tracked by any package manager.")

    ignored = 0
    try:
        if _answer(ask, "Go through them now? [y/N] ").lower() not in ("y", "yes"):
            return 0

        for app in waiting:
            console_print()
            console_print(f"[bold]{escape(app.name)}[/] {escape(app.version)}")
            console_print("  [bold cyan]1)[/] leave it alone, and stop listing it")
            console_print("  [bold cyan]2)[/] keep listing it")
            console_print("  [bold cyan]3)[/] stop going through them")
            choice = _answer(ask, "> ")

            if choice == "1":
                decisions.ignore(app.name, app.version)
                ignored += 1
            elif choice == "3":
                break
    except Stopped:
        console_print()

    if ignored:
        decisions.save()
    return ignored


def run_revisit_menu(decisions, ask=input, out=None, interactive=True):
    """Bring an app back into the list. Returns how many came back."""
    console_print = _printer(out)
    names = decisions.ignored_names()

    if not names:
        console_print("No apps are being left alone.")
        return 0
    if not interactive:
        console_print("Apps being left alone:")
        for name in names:
            console_print(f"  {escape(name)}")
        return 0

    console_print("Apps being left alone:")
    for number, name in enumerate(names, start=1):
        console_print(f"  [bold cyan]{number})[/] {escape(name)}")
    console_print("  [bold cyan]0)[/] none of them")

    try:
        answer = _answer(ask, "List one of them again? ")
    except Stopped:
        return 0
    if not answer.isdigit() or not 1 <= int(answer) <= len(names):
        return 0

    name = names[int(answer) - 1]
    decisions.forget(name)
    decisions.save()
    console_print(f"[bold]{escape(name)}[/] will be listed again.")
    return 1
