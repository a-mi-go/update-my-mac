"""What each package manager is called, how to ask it what's outdated, and how
to read the answer. Adding a manager means adding an entry here.
"""

import json
import os
import re

from update_my_mac.managers.homebrew import brew
from update_my_mac.managers.manager import (
    CheckFailed,
    ManagerReport,
    ManagerUpdate,
    PackageManager,
    _describe_error,
    _parse_json_packages,
    nonblank_lines,
)


def parse_mas_outdated(stdout):
    """Reads `mas outdated`, which writes "497799835  Xcode  (14.0 -> 14.1)"."""
    apps = []
    for line in nonblank_lines(stdout):
        match = re.match(r"\d+\s+(.+?)\s+\((.+?)\s*->\s*(.+?)\)", line.strip())
        if match:
            name, current, latest = match.groups()
            apps.append(f"{name}  {current} → {latest}")
        else:
            apps.append(line.strip())
    return apps


def parse_npm_outdated(stdout):
    """Returns what `npm outdated -g --json` names, or an error when it carries one."""
    return _parse_json_packages(stdout)


def parse_pnpm_outdated(stdout):
    return _parse_json_packages(stdout)


MANAGERS = (
    PackageManager(
        "mas",
        "Mac App Store",
        "mas",
        ("outdated",),
        ("upgrade",),
        parse_output=parse_mas_outdated,
        counted_as="apps",
    ),
    PackageManager(
        "brew",
        "Homebrew",
        "brew",
        ("outdated", "--verbose"),
        ("upgrade",),
        parse_output=brew.parse_outdated,
        # A scheduled run should report against what Homebrew already knows
        # rather than pulling a new index first.
        extra_env={"HOMEBREW_NO_AUTO_UPDATE": "1"},
        self_check=lambda manager, shell: brew.check_index(manager, shell),
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
    """Asks one manager what's outdated. Returns None when it isn't installed."""
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

    # Homebrew says on stderr when it is ignoring a tap, and an ignored tap is
    # left out of the answer silently. Without this the report looks complete.
    ignored = brew.untrusted_taps(shell) if "not trusted" in result.stderr else []
    return ManagerReport(manager.key, manager.label, packages, ignored_taps=ignored)


def check_what_is_outdated(shell, managers=MANAGERS):
    reports = (check_for_outdated(manager, shell) for manager in managers)
    return [report for report in reports if report is not None]


def check_self(manager, shell):
    """Returns a newer version of the manager itself, or None when there is none."""
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
    """Reads one named package out of `outdated --json`."""
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


def installed(shell, managers=MANAGERS):
    return [m for m in managers if shell.find_executable(m.command) is not None]


def check_themselves(shell, managers=MANAGERS):
    updates = (check_self(manager, shell) for manager in managers)
    return [update for update in updates if update is not None]


def still_behind(behind, updated):
    """Returns the managers that did not update, counting an unanswered check."""
    return [one for one in behind if one.error_message or one.key not in updated]


def upgrade_self(manager, shell):
    """Updates the manager itself, with the terminal attached. Returns the exit code."""
    if not manager.self_upgrade_args:
        return -1

    executable = shell.find_executable(manager.command)
    if executable is None:
        return -1

    env = dict(os.environ, **manager.extra_env) if manager.extra_env else None
    return shell.stream_command([executable, *manager.self_upgrade_args], env)


def upgrade(manager, shell):
    """Runs a manager's upgrade command with the terminal attached."""
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
