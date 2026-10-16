"""Doubles for a run that changes something: a shell, a console, an answer."""

import os
from contextlib import contextmanager

from rich.console import Console

from update_my_mac.managers import ManagerUpdate
from update_my_mac.system import shell
from update_my_mac.system.shell import CommandResult
from update_my_mac.view import output
from update_my_mac.view import prompting


MANAGER_UPDATES = [
    ManagerUpdate("brew", "Homebrew", "index is 3 days old"),
    ManagerUpdate("npm", "npm (global)", "npm  12.0.2 → 12.1.0"),
]

class RecordingShell:
    """Records upgrades, and answers the check that follows them.

    `still_outdated` is what each manager reports when asked again after the
    upgrade, keyed by command name. Empty means it has nothing left.
    """

    def __init__(self, exit_code=0, still_outdated=None):
        self.streamed = []
        self.exit_code = exit_code
        self.still_outdated = still_outdated or {}

    def find_executable(self, command):
        return f"/fake/{command}"

    def stream_command(self, args, env=None, silent_status=None):
        self.streamed.append(args)
        return self.exit_code

    def run_command(self, args, success_exit_codes=(0,), env=None):
        command = args[0].rsplit("/", 1)[-1]
        return CommandResult(True, self.still_outdated.get(command, ""), "")

def answers(*replies):
    replies = list(replies)
    return lambda _prompt: replies.pop(0)

@contextmanager
def printing_to(console):
    """Points the run's shared console at this one until the block ends."""
    saved, output.console = output.console, console
    try:
        yield console
    finally:
        output.console = saved


SHELL_FUNCTIONS = (
    "find_executable", "run_command", "stream_command", "open_in_browser",
    "ask_application_to_quit", "open_application", "is_running",
)


def use_shell(fake):
    """Answers every command the run gives with this fake shell. Returns the fake."""
    for name in SHELL_FUNCTIONS:
        if hasattr(fake, name):
            setattr(shell, name, getattr(fake, name))
    return fake


_swapped = []


def swap(owner, name, value):
    """Replaces owner.name for the rest of the test; undone after it."""
    _swapped.append((owner, name, getattr(owner, name)))
    setattr(owner, name, value)


def undo_swaps():
    while _swapped:
        owner, name, value = _swapped.pop()
        setattr(owner, name, value)


def use_environment(env):
    """Makes this the environment the run reads, the same dict, until the test ends."""
    swap(os, "environ", env)


def answer_with(ask):
    """Answers every typed question the run asks with this function."""
    prompting.read_answer = ask


def printed_by(action, console=None):
    console = console or Console(width=100, no_color=True)
    with printing_to(console), console.capture() as captured:
        action()
    return captured.get()

def raising(exception):
    def ask(_prompt):
        raise exception

    return ask
