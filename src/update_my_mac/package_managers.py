"""What each package manager is called, how to ask it what's outdated, and how
to read the answer. Adding a manager means adding an entry here.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


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
    described = ": ".join(part for part in (error.get("code"), error.get("summary")) if part)
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
    counted_as: str = "packages"
    # How the manager reports a newer version of itself, and how it installs it.
    # Either a command to run, or a function for a manager that has no such
    # command. Without one, the manager is never offered an update of itself.
    self_check_args: tuple = ()
    self_check: object = None
    self_package: str = ""
    self_upgrade_args: tuple = ()


MANAGERS = (
    PackageManager(
        "mas",
        "Mac App Store",
        "mas",
        ("outdated",),
        ("upgrade",),
        counted_as="apps",
    ),
    PackageManager(
        "brew",
        "Homebrew",
        "brew",
        ("outdated",),
        ("upgrade",),
        # A scheduled run should report against what Homebrew already knows
        # rather than pulling a new index first.
        extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1"},
        self_check=lambda manager, shell: check_homebrew_index(manager, shell),
        self_upgrade_args=("update",),
    ),
    PackageManager(
        "npm",
        "npm (global)",
        "npm",
        ("outdated", "-g", "--json"),
        ("update", "-g"),
        parse_npm_outdated,
        (0, 1),
        self_check_args=("outdated", "-g", "npm", "--json"),
        self_package="npm",
        self_upgrade_args=("install", "-g", "npm@latest"),
    ),
    PackageManager(
        "pnpm",
        "pnpm (global)",
        "pnpm",
        ("outdated", "-g", "--json"),
        ("update", "-g"),
        parse_pnpm_outdated,
        (0, 1),
        self_check_args=("outdated", "-g", "pnpm", "--json"),
        self_package="pnpm",
        self_upgrade_args=("self-update",),
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


@dataclass
class ManagerUpdate:
    key: str
    label: str
    description: str = ""
    error_message: str = ""


STALE_AFTER_SECONDS = 24 * 60 * 60


def check_homebrew_index(manager, shell):
    """Homebrew has no way to ask whether it is behind without fetching.

    What it does leave behind is the age of its index, and that is the thing
    `brew outdated` reads. An index older than a day is worth refreshing, which
    is also when Homebrew itself would auto-update.
    """
    executable = shell.find_executable(manager.command)
    result = shell.run_command([executable, "--cache"], (0,))
    if not result.success:
        return None

    told = result.stdout.strip()
    # An empty answer would become Path("."), which is a directory and would
    # then be read as a Homebrew cache.
    cache = Path(told)
    if not told or not cache.is_absolute() or not cache.is_dir():
        # Not a real Homebrew, or a layout we don't know. Saying nothing beats
        # offering an update we can't justify.
        return None

    marker = cache / "api" / "formula_names.txt"
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return ManagerUpdate(manager.key, manager.label, "index has never been fetched")

    if age < STALE_AFTER_SECONDS:
        return None
    days = int(age // STALE_AFTER_SECONDS)
    return ManagerUpdate(
        manager.key, manager.label, f"index is {days} day{'s' if days != 1 else ''} old"
    )


def check_self(manager, shell):
    """Whether the manager has a newer version of itself.

    None means there is nothing to offer: the manager isn't installed, can't
    update itself, or already is current.
    """
    if not manager.self_upgrade_args:
        return None

    executable = shell.find_executable(manager.command)
    if executable is None:
        return None

    if manager.self_check:
        return manager.self_check(manager, shell)
    if not manager.self_check_args:
        return None

    env = dict(os.environ, **manager.extra_env) if manager.extra_env else None
    result = shell.run_command(
        [executable, *manager.self_check_args], manager.success_exit_codes, env
    )
    if not result.success:
        return ManagerUpdate(
            manager.key, manager.label, error_message=result.stderr or result.stdout
        )

    try:
        described = describe_own_version(result.stdout, manager.self_package)
    except CheckFailed as failure:
        return ManagerUpdate(manager.key, manager.label, error_message=str(failure))
    return ManagerUpdate(manager.key, manager.label, described) if described else None


def describe_own_version(stdout, package):
    """Read one named package out of `outdated --json`.

    Asking about a single package is not the same as trusting the answer to
    hold only that package, so the name is looked up rather than assumed.
    """
    if not stdout.strip():
        return ""

    try:
        data = json.loads(stdout)
    except ValueError:
        raise CheckFailed(f"unreadable JSON: {stdout[:200]}")
    if not isinstance(data, dict):
        raise CheckFailed(f"unexpected JSON: {stdout[:200]}")
    if "error" in data:
        raise CheckFailed(_describe_error(data["error"]))

    found = data.get(package)
    if not isinstance(found, dict):
        return ""
    return f"{package}  {found.get('current', '?')} → {found.get('latest', '?')}"


def installed_managers(shell, managers=MANAGERS):
    return [m for m in managers if shell.find_executable(m.command) is not None]


def check_managers_themselves(shell, managers=MANAGERS):
    updates = (check_self(manager, shell) for manager in managers)
    return [update for update in updates if update is not None]


def upgrade_self(manager, shell):
    """Update the manager itself, with the terminal attached."""
    if not manager.self_upgrade_args:
        return -1

    executable = shell.find_executable(manager.command)
    if executable is None:
        return -1

    env = dict(os.environ, **manager.extra_env) if manager.extra_env else None
    return shell.stream_command([executable, *manager.self_upgrade_args], env)


def upgrade(manager, shell):
    """Run a manager's upgrade command with the terminal attached."""
    if not manager.upgrade_args:
        # Otherwise a registry entry that forgot them runs the bare command.
        return -1

    executable = shell.find_executable(manager.command)
    if executable is None:
        return -1

    env = dict(os.environ, **manager.extra_env) if manager.extra_env else None
    return shell.stream_command([executable, *manager.upgrade_args], env)


def by_key(key, managers=MANAGERS):
    return next(manager for manager in managers if manager.key == key)
