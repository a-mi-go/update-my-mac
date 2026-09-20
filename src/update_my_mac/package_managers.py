"""What each package manager is called, how to ask it what's outdated, and how
to read the answer. Adding a manager means adding an entry here.
"""

import json
import os
from dataclasses import dataclass, field


class CheckFailed(Exception):
    """The manager ran but its answer says something went wrong."""


@dataclass
class ManagerReport:
    manager: str
    label: str
    outdated_packages: list
    error_message: str = ""


def nonblank_lines(output):
    return [line for line in output.splitlines() if line.strip()]


def parse_npm_outdated(stdout):
    """Read `npm outdated -g --json`.

    npm exits 1 both when it finds updates and when it fails, so the exit code
    alone cannot tell those apart. The JSON can: a failure carries an "error"
    key instead of packages.
    """
    return _parse_json_packages(stdout)


def parse_pnpm_outdated(stdout):
    return _parse_json_packages(stdout)


def _describe_error(error):
    if not isinstance(error, dict):
        return str(error)
    # The code alone is cryptic and the summary alone loses the category.
    described = " — ".join(part for part in (error.get("code"), error.get("summary")) if part)
    return described or str(error)


def _parse_json_packages(stdout):
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
    except ValueError:
        raise CheckFailed(f"unreadable JSON: {stdout[:200]}")

    if not isinstance(data, dict):
        raise CheckFailed(f"unexpected JSON: {stdout[:200]}")

    if "error" in data:
        raise CheckFailed(_describe_error(data["error"]))

    packages = []
    for name, info in sorted(data.items()):
        current = info.get("current", "?") if isinstance(info, dict) else "?"
        latest = info.get("latest", "?") if isinstance(info, dict) else "?"
        packages.append(f"{name}  {current} → {latest}")
    return packages


@dataclass(frozen=True)
class PackageManager:
    key: str
    label: str
    command: str
    outdated_args: tuple
    upgrade_args: tuple = ()
    parse_output: object = nonblank_lines
    success_exit_codes: tuple = (0,)
    extra_env: dict = field(default_factory=dict)


MANAGERS = (
    PackageManager("mas", "Mac App Store", "mas", ("outdated",), ("upgrade",)),
    PackageManager(
        "brew",
        "Homebrew",
        "brew",
        ("outdated",),
        ("upgrade",),
        # A scheduled run should report against what Homebrew already knows
        # rather than pulling a new index first.
        extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1"},
    ),
    PackageManager(
        "npm",
        "npm (global)",
        "npm",
        ("outdated", "-g", "--json"),
        ("update", "-g"),
        parse_npm_outdated,
        (0, 1),
    ),
    PackageManager(
        "pnpm",
        "pnpm (global)",
        "pnpm",
        ("outdated", "-g", "--json"),
        ("update", "-g"),
        parse_pnpm_outdated,
        (0, 1),
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
        return ManagerReport(
            manager.key, manager.label, [], result.stderr or result.stdout
        )

    # A tolerated non-zero exit means "updates found", and that answer has to
    # look like one. Silence plus an exit code is a failure the tool didn't
    # bother to phrase as JSON.
    if result.exit_code != 0 and not result.stdout:
        message = result.stderr or f"exited {result.exit_code} without output"
        return ManagerReport(manager.key, manager.label, [], message)

    try:
        packages = manager.parse_output(result.stdout)
    except CheckFailed as failure:
        return ManagerReport(manager.key, manager.label, [], str(failure))
    return ManagerReport(manager.key, manager.label, packages)


def check_installed(shell, managers=MANAGERS):
    reports = (check_for_outdated(manager, shell) for manager in managers)
    return [report for report in reports if report is not None]


def upgrade(manager, shell):
    """Run a manager's upgrade command with the terminal attached."""
    executable = shell.find_executable(manager.command)
    if executable is None:
        return -1

    env = dict(os.environ, **manager.extra_env) if manager.extra_env else None
    return shell.stream_command([executable, *manager.upgrade_args], env)


def by_key(key, managers=MANAGERS):
    return next(manager for manager in managers if manager.key == key)
