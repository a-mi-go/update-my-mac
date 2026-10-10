"""Doubles for a run that changes something: a shell, a console, an answer."""

from rich.console import Console

from update_my_mac.managers import ManagerUpdate
from update_my_mac.system.shell import CommandResult


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

    def stream_command(self, args, env=None):
        self.streamed.append(args)
        return self.exit_code

    def run_command(self, args, success_exit_codes=(0,), env=None):
        command = args[0].rsplit("/", 1)[-1]
        return CommandResult(True, self.still_outdated.get(command, ""), "")

def answers(*replies):
    replies = list(replies)
    return lambda _prompt: replies.pop(0)

def printed_by(action):
    console = Console(width=100, no_color=True)
    with console.capture() as captured:
        action(console)
    return captured.get()

def quiet_console():
    return Console(file=open("/dev/null", "w"), width=200)

def raising(exception):
    def ask(_prompt):
        raise exception

    return ask
