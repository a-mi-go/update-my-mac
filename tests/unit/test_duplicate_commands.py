"""Finding a command that two managers have each installed."""

import os

from update_my_mac import duplicate_commands
from update_my_mac.shell import CommandResult


def make_brew(root, cask, command):
    """A Homebrew prefix: bin/<command> pointing into the Caskroom."""
    real = root / "Caskroom" / cask / "1.0" / "bin" / command
    real.parent.mkdir(parents=True)
    real.write_text("#!/bin/sh\n")
    link = root / "bin" / command
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(real)
    return root


def make_npm(root, package, command):
    """An npm prefix: bin/<command> pointing into lib/node_modules."""
    parts = package.split("/")
    real = root.joinpath("lib", "node_modules", *parts, "bin", f"{command}.js")
    real.parent.mkdir(parents=True)
    real.write_text("#!/usr/bin/env node\n")
    link = root / "bin" / command
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(real)
    return root


class ManagerShell:
    """Answers the three questions about where managers put their commands."""

    def __init__(self, brew=None, npm=None, pnpm=None):
        self.answers = {"brew": brew, "npm": npm, "pnpm": pnpm}

    def find_executable(self, command):
        return f"/fake/{command}" if self.answers.get(command) else None

    def run_command(self, args, success_exit_codes=(0,), env=None):
        command = args[0].rsplit("/", 1)[-1]
        return CommandResult(True, str(self.answers[command]), "")


def path_of(*directories):
    return {"PATH": os.pathsep.join(str(d / "bin") for d in directories)}


def test_a_command_only_one_manager_has_is_not_reported(tmp_path):
    brew = make_brew(tmp_path / "brew", "ripgrep", "rg")
    shell = ManagerShell(brew=brew)

    assert duplicate_commands.find(shell, path_of(brew)) == []


def test_the_same_command_from_two_managers_is_found(tmp_path):
    brew = make_brew(tmp_path / "brew", "codex", "codex")
    npm = make_npm(tmp_path / "npm", "@openai/codex", "codex")
    shell = ManagerShell(brew=brew, npm=npm)

    found = duplicate_commands.find(shell, path_of(brew, npm))
    assert [d.command for d in found] == ["codex"]
    assert found[0].winner.manager == "Homebrew"
    assert [c.manager for c in found[0].shadowed] == ["npm (global)"]


def test_path_order_decides_which_one_runs(tmp_path):
    brew = make_brew(tmp_path / "brew", "codex", "codex")
    npm = make_npm(tmp_path / "npm", "@openai/codex", "codex")
    shell = ManagerShell(brew=brew, npm=npm)

    # Same two copies, npm's directory searched first.
    found = duplicate_commands.find(shell, path_of(npm, brew))
    assert found[0].winner.manager == "npm (global)"


def test_a_directory_path_never_mentions_cannot_win(tmp_path):
    brew = make_brew(tmp_path / "brew", "codex", "codex")
    npm = make_npm(tmp_path / "npm", "@openai/codex", "codex")
    shell = ManagerShell(brew=brew, npm=npm)

    found = duplicate_commands.find(shell, path_of(npm))
    assert found[0].winner.manager == "npm (global)"


def test_the_package_and_the_way_to_remove_it_are_read_off_the_link(tmp_path):
    brew = make_brew(tmp_path / "brew", "codex", "codex")
    npm = make_npm(tmp_path / "npm", "@openai/codex", "codex")
    shell = ManagerShell(brew=brew, npm=npm)

    copies = duplicate_commands.find(shell, path_of(brew, npm))[0].copies
    assert copies[0].package == "codex"
    assert copies[0].remove_with == ("brew", "uninstall", "--cask", "codex")
    assert copies[1].package == "@openai/codex"
    assert copies[1].remove_with == ("npm", "uninstall", "-g", "@openai/codex")


def test_a_formula_is_removed_differently_from_a_cask(tmp_path):
    root = tmp_path / "brew"
    real = root / "Cellar" / "wget" / "1.25" / "bin" / "wget"
    real.parent.mkdir(parents=True)
    real.write_text("")
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "wget").symlink_to(real)

    package, remove_with = duplicate_commands.package_behind(root / "bin" / "wget")
    assert package == "wget"
    assert remove_with == ("brew", "uninstall", "wget")


def test_a_manager_that_is_not_installed_is_skipped(tmp_path):
    assert duplicate_commands.bin_directories(ManagerShell()) == {}


def test_a_directory_that_cannot_be_read_does_not_stop_the_run(tmp_path):
    brew = tmp_path / "gone"
    shell = ManagerShell(brew=brew)

    assert duplicate_commands.find(shell, {"PATH": ""}) == []
