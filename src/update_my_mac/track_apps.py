"""Going through the apps no package manager tracks, and revisiting that later.

Leaving an app alone is the only decision on offer so far; the menu can also
show where an app came from, which is not a decision but the thing you need
when you have to fetch the update yourself. Handing an app to Homebrew, or
watching its update feed, comes later and will appear in the same menu.
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


def _show_website(website, console_print, open_url):
    if not website:
        console_print("  [dim]Nothing on this Mac says where that app came from.[/]")
        return

    console_print(f"  {escape(website)}")
    if open_url is not None and not open_url(website):
        console_print("  [yellow]Could not open that in a browser.[/]")


def run_untracked_menu(
    apps,
    decisions,
    ask=input,
    out=None,
    interactive=True,
    find_website=None,
    open_url=None,
):
    """Offer a decision about each untracked app. Returns how many were ignored.

    `find_website` is asked where an app came from. It is a function rather
    than a ready answer so that nothing is looked up before someone is
    actually standing in front of the menu.
    """
    console_print = _printer(out)
    waiting = [app for app in apps if not decisions.is_ignored(app.name)]
    if not waiting or not interactive:
        return 0

    console_print()
    console_print(f"Going through {len(waiting)} untracked apps.")

    ignored = 0
    try:
        for app in waiting:
            console_print()
            console_print(f"[bold]{escape(app.name)}[/] {escape(app.version)}")
            console_print("  [bold cyan]1)[/] leave it alone, and stop listing it")
            console_print("  [bold cyan]2)[/] keep listing it")
            console_print("  [bold cyan]3)[/] show me where it came from")
            console_print("  [bold cyan]4)[/] stop going through them")

            while True:
                choice = _answer(ask, "> ")
                if choice != "3":
                    break
                # Showing where it came from decides nothing, so the same app
                # is asked about again afterwards.
                _show_website(find_website(app) if find_website else "", console_print, open_url)

            if choice == "1":
                decisions.ignore(app.name, app.version)
                ignored += 1
            elif choice == "4":
                break
    except Stopped:
        console_print()

    if ignored and not decisions.save():
        _say_it_was_not_written(decisions, console_print)
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

    if answer in ("0", ""):
        return 0
    if not answer.isdigit() or not 1 <= int(answer) <= len(names):
        console_print(f"[yellow]Answer a number from 1 to {len(names)}, or 0 for none.[/]")
        return 0

    name = names[int(answer) - 1]
    decisions.forget(name)
    if not decisions.save():
        _say_it_was_not_written(decisions, console_print)
        return 0
    console_print(f"[bold]{escape(name)}[/] will be listed again.")
    return 1


def _say_it_was_not_written(decisions, console_print):
    console_print(
        f"[yellow]Could not write {escape(str(decisions.path))}, "
        f"so this won't be remembered.[/]"
    )
