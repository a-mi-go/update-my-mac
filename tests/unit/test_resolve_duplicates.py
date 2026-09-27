"""Choosing which copy of a doubly installed command to drop."""

from pathlib import Path

from rich.text import Text

from update_my_mac import resolve_duplicates
from update_my_mac.duplicate_commands import Copy, Duplicate


class Terminal:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.lines = []

    def ask(self, prompt):
        self.lines.append(prompt)
        return self.answers.pop(0)

    def out(self, *parts, **_):
        self.lines.append(Text.from_markup(" ".join(str(part) for part in parts)).plain)

    @property
    def text(self):
        return "\n".join(self.lines)


def doubled():
    return Duplicate(
        "codex",
        [
            Copy("Homebrew", Path("/opt/homebrew/bin/codex"), "codex",
                 ("brew", "uninstall", "--cask", "codex")),
            Copy("npm (global)", Path("~/.npm-global/bin/codex"), "@openai/codex",
                 ("npm", "uninstall", "-g", "@openai/codex")),
        ],
    )


class Remover:
    def __init__(self, exit_code=0):
        self.removed = []
        self.exit_code = exit_code

    def __call__(self, copy):
        self.removed.append(copy.package)
        return self.exit_code


def test_which_one_runs_and_which_one_never_does_is_spelled_out():
    terminal = Terminal("3")
    resolve_duplicates.run_duplicate_menu([doubled()], Remover(), terminal.ask, terminal.out)

    assert "runs now:   Homebrew, codex" in terminal.text
    assert "never used: npm (global), @openai/codex" in terminal.text


def test_the_shadowed_copy_can_be_dropped():
    remover = Remover()
    terminal = Terminal("2")

    removed = resolve_duplicates.run_duplicate_menu(
        [doubled()], remover, terminal.ask, terminal.out
    )
    assert removed == 1
    assert remover.removed == ["@openai/codex"]


def test_the_one_that_runs_can_be_dropped_instead():
    remover = Remover()
    terminal = Terminal("1")

    resolve_duplicates.run_duplicate_menu([doubled()], remover, terminal.ask, terminal.out)
    assert remover.removed == ["codex"]


def test_leaving_both_removes_nothing():
    remover = Remover()
    terminal = Terminal("3")

    assert resolve_duplicates.run_duplicate_menu(
        [doubled()], remover, terminal.ask, terminal.out
    ) == 0
    assert remover.removed == []


def test_stopping_partway_leaves_the_rest_alone():
    remover = Remover()
    terminal = Terminal("4")

    resolve_duplicates.run_duplicate_menu(
        [doubled(), doubled()], remover, terminal.ask, terminal.out
    )
    assert remover.removed == []


def test_a_removal_that_failed_is_not_counted():
    terminal = Terminal("2")

    removed = resolve_duplicates.run_duplicate_menu(
        [doubled()], Remover(exit_code=1), terminal.ask, terminal.out
    )
    assert removed == 0
    assert "exited with 1" in terminal.text


def test_a_copy_of_unknown_origin_is_not_guessed_at():
    unknown = Duplicate("thing", [
        Copy("Homebrew", Path("/a"), "", ()),
        Copy("npm (global)", Path("/b"), "", ()),
    ])
    remover = Remover()
    terminal = Terminal("1")

    resolve_duplicates.run_duplicate_menu([unknown], remover, terminal.ask, terminal.out)
    assert remover.removed == []
    assert "Nothing here says how that one was installed" in terminal.text


def test_no_terminal_means_nothing_is_asked():
    terminal = Terminal()

    assert resolve_duplicates.run_duplicate_menu(
        [doubled()], Remover(), terminal.ask, terminal.out, interactive=False
    ) == 0
    assert terminal.text == ""


def test_ctrl_c_stops_without_crashing():
    def ask(_prompt):
        raise KeyboardInterrupt

    assert resolve_duplicates.run_duplicate_menu([doubled()], Remover(), ask, Terminal().out) == 0
