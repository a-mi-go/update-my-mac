"""The one place that runs external commands."""

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class CommandResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int = 0


def find_executable(command):
    return shutil.which(command)


def run_command(args, success_exit_codes=(0,), env=None, timeout=120):
    """Runs a command and returns its output, keeping the two streams apart."""
    # success_exit_codes is for managers like npm, which exits 1 when it finds
    # updates.
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(False, "", str(exc), -1)

    return CommandResult(
        proc.returncode in success_exit_codes,
        proc.stdout.strip(),
        proc.stderr.strip(),
        proc.returncode,
    )


def stream_command(args, env=None):
    """Runs a command with the terminal attached. Returns its exit code."""
    # Not captured: a password prompt needs the real terminal.
    try:
        return subprocess.run(args, env=env).returncode
    except (OSError, subprocess.SubprocessError):
        return -1


def open_in_browser(url):
    """Opens an https address. Returns whether it worked."""
    if not url.startswith("https://"):
        return False

    executable = find_executable("open")
    if executable is None:
        return False
    return run_command([executable, url]).success


def ask_application_to_quit(bundle_id):
    """Asks an app to quit the way the Quit menu item does."""
    executable = find_executable("osascript")
    if executable is None:
        return False
    return run_command(
        [executable, "-e", f'tell application id "{bundle_id}" to quit']
    ).success


def open_application(path):
    executable = find_executable("open")
    if executable is None:
        return False
    return run_command([executable, "-a", str(path)]).success


def is_running(pid):
    executable = find_executable("ps")
    if executable is None:
        return False
    return run_command([executable, "-p", str(pid)], (0, 1)).exit_code == 0
