"""Choosing which copy of a doubly installed command to drop."""

from pathlib import Path

import pytest
from rich.text import Text

from update_my_mac.controller import resolve_duplicates
from update_my_mac.checks.duplicate_installations import Copy, Duplicate
from fake_terminal import Terminal


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


# The menu asks once what to do with all of them; picking a copy happens in
# the walk-through behind DECIDE.
DROP_SHADOWED, DECIDE = "1", "2"
DROP_HOMEBREW, DROP_NPM, LEAVE_BOTH, CANCEL = "1", "2", "3", "4"


class Remover:
    def __init__(self, exit_code=0):
        self.removed = []
        self.exit_code = exit_code

    def __call__(self, copy):
        self.removed.append(copy.package)
        return self.exit_code


def test_which_one_runs_and_which_one_never_does_is_spelled_out():
    terminal = Terminal(DECIDE, LEAVE_BOTH)
    resolve_duplicates.ask_what_to_do([doubled()], Remover(), terminal.step)

    assert "runs now:   Homebrew, codex" in terminal.text
    assert "never used: npm (global), @openai/codex" in terminal.text


def test_the_shadowed_copy_can_be_dropped():
    remover = Remover()
    terminal = Terminal(DECIDE, DROP_NPM)

    removed = resolve_duplicates.ask_what_to_do(
        [doubled()], remover, terminal.step
    )
    assert removed == 1
    assert remover.removed == ["@openai/codex"]


def test_the_one_that_runs_can_be_dropped_instead():
    remover = Remover()
    terminal = Terminal(DECIDE, DROP_HOMEBREW)

    resolve_duplicates.ask_what_to_do([doubled()], remover, terminal.step)
    assert remover.removed == ["codex"]


def test_leaving_both_removes_nothing():
    remover = Remover()
    terminal = Terminal(DECIDE, LEAVE_BOTH)

    assert resolve_duplicates.ask_what_to_do(
        [doubled()], remover, terminal.step
    ) == 0
    assert remover.removed == []


def test_stopping_partway_leaves_the_rest_alone():
    remover = Remover()
    terminal = Terminal(DECIDE, CANCEL)

    resolve_duplicates.ask_what_to_do(
        [doubled(), doubled()], remover, terminal.step
    )
    assert remover.removed == []


def test_a_removal_that_failed_is_not_counted():
    terminal = Terminal(DECIDE, DROP_NPM)

    removed = resolve_duplicates.ask_what_to_do(
        [doubled()], Remover(exit_code=1), terminal.step
    )
    assert removed == 0
    assert "exited with 1" in terminal.text


def test_a_copy_of_unknown_origin_is_not_guessed_at():
    unknown = Duplicate("thing", [
        Copy("Homebrew", Path("/a"), "", ()),
        Copy("npm (global)", Path("/b"), "", ()),
    ])
    remover = Remover()
    terminal = Terminal(DECIDE, DROP_HOMEBREW)

    resolve_duplicates.ask_what_to_do([unknown], remover, terminal.step)
    assert remover.removed == []
    assert "Nothing here says how that one was installed" in terminal.text


def test_no_terminal_means_nothing_is_asked():
    terminal = Terminal()

    assert resolve_duplicates.ask_what_to_do(
        [doubled()], Remover(), terminal.step, interactive=False
    ) == 0
    assert terminal.text == ""


def test_ctrl_c_is_left_to_end_the_run():
    terminal = Terminal(then=KeyboardInterrupt)

    with pytest.raises(KeyboardInterrupt):
        resolve_duplicates.ask_what_to_do([doubled()], Remover(), terminal.step)


def test_every_copy_that_never_runs_can_go_in_one_step():
    remover = Remover()
    terminal = Terminal(DROP_SHADOWED)

    removed = resolve_duplicates.ask_what_to_do(
        [doubled(), doubled()], remover, terminal.step
    )

    assert removed == 2
    # The copy PATH reaches is the one left standing.
    assert remover.removed == ["@openai/codex", "@openai/codex"]


def test_doing_nothing_asks_about_no_command_at_all():
    remover = Remover()
    terminal = Terminal("3")

    assert resolve_duplicates.ask_what_to_do(
        [doubled()], remover, terminal.step
    ) == 0
    assert "runs now" not in terminal.text


def test_ctrl_c_during_a_removal_ends_the_run():
    class Interrupting(Remover):
        def __call__(self, copy):
            super().__call__(copy)
            raise KeyboardInterrupt

    terminal = Terminal(DROP_SHADOWED)

    with pytest.raises(KeyboardInterrupt):
        resolve_duplicates.ask_what_to_do([doubled()], Interrupting(), terminal.step)
