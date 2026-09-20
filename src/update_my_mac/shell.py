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
