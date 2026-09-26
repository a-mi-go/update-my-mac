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
    """Run a command, keeping its two output streams apart.

    They stay separate because stdout is what gets parsed: warnings and
    diagnostics on stderr must never be read as package rows.

    success_exit_codes exists because several package managers report
    "something is outdated" with a non-zero exit: npm and pnpm both exit 1 when
    they find updates, which is exactly the case we care about.
    """
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
    """Run a command with the terminal attached, returning its exit code.

    Upgrades are not captured: brew and mas may ask for a password, and a
    prompt needs the real terminal to be readable. It also means a long
    download shows progress as it happens.
    """
    try:
        return subprocess.run(args, env=env).returncode
    except (OSError, subprocess.SubprocessError):
        return -1


def open_in_browser(url):
    """Hand a web address to whatever the Mac opens web addresses with.

    Only https, so that a bad entry somewhere upstream cannot turn this into
    opening a file or running something. Returns whether it worked.
    """
    if not url.startswith("https://"):
        return False

    executable = find_executable("open")
    if executable is None:
        return False
    return run_command([executable, url]).success


def ask_application_to_quit(bundle_id):
    """Ask an app to quit the way the Quit menu item does.

    Never a kill: an app with unsaved work must get its chance to say so, and
    whether to lose that work is not this tool's decision.
    """
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
