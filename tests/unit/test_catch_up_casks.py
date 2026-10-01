"""Updating the apps Homebrew installed but stopped reporting."""

from pathlib import Path

import pytest

from update_my_mac import behind_the_recipe, catch_up_casks
from update_my_mac.cask_index import Cask
from update_my_mac.installed_apps import InstalledApp

from fake_terminal import Terminal

# 1) the command, 2) leave it for now, 3) cancel
CATCH_UP, LATER, CANCEL = "1", "2", "3"
ALL, DECIDE, NOTHING = "1", "2", "3"


def item(name="BetterDisplay", app_version="5.0.5", cask_version="5.0.6", recorded="5.0.6"):
    app = InstalledApp(name, app_version, Path(f"/Applications/{name}.app"))
    return behind_the_recipe.Behind(
        app, Cask(name.lower(), "https://x.test/", cask_version), recorded
    )


class Brew:
    def __init__(self, exit_code=0):
        self.ran = []
        self.exit_code = exit_code

    def __call__(self, command):
        self.ran.append(command)
        return self.exit_code


def test_nothing_behind_means_nothing_is_asked():
    terminal = Terminal()

    assert catch_up_casks.run_catch_up_menu([], Brew(), terminal.step) == 0
    assert terminal.text == ""


def test_a_false_version_recorded_version_is_reinstalled():
    brew = Brew()
    terminal = Terminal(DECIDE, CATCH_UP, then=EOFError)

    done = catch_up_casks.run_catch_up_menu([item()], brew, terminal.step)

    assert done == 1
    assert brew.ran == [("reinstall", "--cask", "betterdisplay")]
    assert "wrote down a version it never installed" in terminal.text


def test_a_cask_homebrew_knows_is_old_is_upgraded_greedily():
    brew = Brew()
    terminal = Terminal(DECIDE, CATCH_UP, then=EOFError)

    catch_up_casks.run_catch_up_menu([item(recorded="5.0.5")], brew, terminal.step)

    assert brew.ran == [("upgrade", "--cask", "--greedy", "betterdisplay")]


def test_all_of_them_go_in_two_commands_not_one_each():
    brew = Brew()
    terminal = Terminal(ALL)

    done = catch_up_casks.run_catch_up_menu(
        [item("BetterDisplay"), item("Opera"), item("ChatGPT", recorded="1.0")],
        brew,
        terminal.step,
    )

    assert brew.ran == [
        ("reinstall", "--cask", "betterdisplay", "opera"),
        ("upgrade", "--cask", "--greedy", "chatgpt"),
    ]
    assert done == 3


def test_a_command_that_failed_is_not_counted():
    terminal = Terminal(DECIDE, CATCH_UP, then=EOFError)

    done = catch_up_casks.run_catch_up_menu([item()], Brew(exit_code=1), terminal.step)

    assert done == 0
    assert "exited with 1" in terminal.text


def test_leaving_one_alone_runs_nothing():
    brew = Brew()
    terminal = Terminal(DECIDE, LATER, then=EOFError)

    assert catch_up_casks.run_catch_up_menu([item()], brew, terminal.step) == 0
    assert brew.ran == []


def test_cancelling_stops_the_rest():
    brew = Brew()
    terminal = Terminal(DECIDE, CANCEL)

    catch_up_casks.run_catch_up_menu([item("BetterDisplay"), item("Opera")], brew, terminal.step)

    assert brew.ran == []


def test_doing_nothing_asks_about_no_app_at_all():
    terminal = Terminal(NOTHING)

    catch_up_casks.run_catch_up_menu([item()], Brew(), terminal.step)

    assert "BetterDisplay  5.0.5" not in terminal.text


def test_without_a_terminal_nothing_is_asked():
    terminal = Terminal()

    catch_up_casks.run_catch_up_menu([item()], Brew(), terminal.step, interactive=False)

    assert terminal.text == ""


def test_ctrl_c_is_left_to_end_the_run():
    terminal = Terminal(then=KeyboardInterrupt)

    with pytest.raises(KeyboardInterrupt):
        catch_up_casks.run_catch_up_menu([item()], Brew(), terminal.step)


def test_ctrl_c_during_a_command_ends_the_run():
    ran = []

    def brew(command):
        ran.append(command[0])
        raise KeyboardInterrupt

    terminal = Terminal(ALL)

    with pytest.raises(KeyboardInterrupt):
        catch_up_casks.run_catch_up_menu([item("BetterDisplay")], brew, terminal.step)
    assert ran == ["reinstall"]
