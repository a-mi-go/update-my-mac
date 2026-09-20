"""What each package manager is called, how to ask it what's outdated, and how
to read the answer. Adding a manager means adding an entry here.
"""

import os
from dataclasses import dataclass, field


@dataclass
class ManagerReport:
    manager: str
    label: str
    outdated_packages: list
    error_message: str = ""


def nonblank_lines(output):
    return [line for line in output.splitlines() if line.strip()]


def parse_npm_outdated(output):
    # npm prints a table with a "Package Current Wanted Latest" header.
    lines = nonblank_lines(output)
    if lines and lines[0].split()[:2] == ["Package", "Current"]:
        lines = lines[1:]
    return lines


def parse_pnpm_outdated(output):
    if "Everything up-to-date" in output:
        return []
    # pnpm draws a box: drop the rules, then the header row they framed.
    rows = [
        line.strip("│ ")
        for line in nonblank_lines(output)
        if line.strip("│├─┤┬┴┼└┘┌┐ ")
    ]
    if rows and rows[0].startswith("Package"):
        rows = rows[1:]
    return rows


@dataclass(frozen=True)
class PackageManager:
    key: str
    label: str
    command: str
    outdated_args: tuple
    parse_output: object = nonblank_lines
    success_exit_codes: tuple = (0,)
    extra_env: dict = field(default_factory=dict)


MANAGERS = (
    PackageManager("mas", "Mac App Store", "mas", ("outdated",)),
    PackageManager(
        "brew",
        "Homebrew",
        "brew",
        ("outdated",),
        # A scheduled run should report against what Homebrew already knows
        # rather than pulling a new index first.
        extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1"},
    ),
    PackageManager(
        "npm", "npm (global)", "npm", ("outdated", "-g"), parse_npm_outdated, (0, 1)
    ),
    PackageManager(
        "pnpm", "pnpm (global)", "pnpm", ("outdated", "-g"), parse_pnpm_outdated, (0, 1)
    ),
)


def check_for_outdated(manager, shell):
    """Ask one manager what's outdated. Returns None when it isn't installed."""
    executable = shell.find_executable(manager.command)
    if executable is None:
        return None

    env = dict(os.environ, **manager.extra_env) if manager.extra_env else None
    result = shell.run_command(
        [executable, *manager.outdated_args], manager.success_exit_codes, env
    )
    if not result.success:
        return ManagerReport(manager.key, manager.label, [], result.output)
    return ManagerReport(
        manager.key, manager.label, manager.parse_output(result.output)
    )


def check_installed(shell, managers=MANAGERS):
    reports = (check_for_outdated(manager, shell) for manager in managers)
    return [report for report in reports if report is not None]
