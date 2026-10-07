"""What each package manager is called, how to ask it what's outdated, and how
to read the answer. Adding a manager means adding an entry here.
"""

import json
import os
import re
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
    # Taps Homebrew is leaving out of the answer it just gave.
    ignored_taps: list = field(default_factory=list)


def nonblank_lines(output):
    return [line for line in output.splitlines() if line.strip()]


def parse_brew_outdated(stdout):
    """Read `brew outdated --verbose`.

    Without --verbose Homebrew prints bare names as soon as its output is not
    a terminal, and ours never is. It writes "name (1.2.3) < 1.2.4" for a
    formula and "!=" for a cask, where the versions merely differ.
    """
    packages = []
    for line in nonblank_lines(stdout):
        match = re.match(r"(\S+) \((.+?)\) (?:<|!=) (\S+)", line.strip())
        if match:
            name, current, latest = match.groups()
            packages.append(f"{name}  {current} → {latest}")
        else:
            packages.append(line.strip())
    return packages


def parse_mas_outdated(stdout):
    """Read `mas outdated`, which writes "497799835  Xcode  (14.0 -> 14.1)"."""
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
    """Read `npm outdated -g --json`.

    npm exits 1 both when it finds updates and when it fails; only the JSON
    tells them apart, by carrying an "error" key.
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
        parse_output=parse_mas_outdated,
        counted_as="apps",
    ),
    PackageManager(
        "brew",
        "Homebrew",
        "brew",
        ("outdated", "--verbose"),
        ("upgrade",),
        parse_output=parse_brew_outdated,
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

    # Homebrew says on stderr when it is ignoring a tap, and an ignored tap is
    # left out of the answer silently. Without this the report looks complete.
    ignored = untrusted_taps(shell) if "not trusted" in result.stderr else []
    return ManagerReport(manager.key, manager.label, packages, ignored_taps=ignored)


def untrusted_taps(shell):
    """The taps Homebrew will not read from until they are trusted."""
    executable = shell.find_executable("brew")
    if executable is None:
        return []

    result = shell.run_command([executable, "tap-info", "--json", "--installed"], (0,))
    if not result.success:
        return []

    try:
        taps = json.loads(result.stdout)
    except ValueError:
        return []
    return [
        tap["name"]
        for tap in taps
        if isinstance(tap, dict) and tap.get("trusted") is False and tap.get("name")
    ]


def check_what_is_outdated(shell, managers=MANAGERS):
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
    """Whether Homebrew's index is old enough to be worth refreshing.

    Homebrew cannot say whether it is behind without fetching, so the age of
    the index it answers from has to stand in.
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

    api = cache / "api"
    if not api.is_dir():
        # A Homebrew that fetches formulae over git rather than the API keeps
        # no such directory, and then its age says nothing.
        return None

    try:
        age = time.time() - (api / "formula_names.txt").stat().st_mtime
    except OSError:
        return ManagerUpdate(manager.key, manager.label, "index has never been fetched")

    if age < STALE_AFTER_SECONDS:
        return None
    days = int(age // STALE_AFTER_SECONDS)
    return ManagerUpdate(
        manager.key, manager.label, f"index is {days} day{'s' if days != 1 else ''} old"
    )


def check_self(manager, shell):
    """A newer version of the manager itself, or None when there is none."""
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
    """Read one named package out of `outdated --json`."""
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
    """One whose check could not run stays, because nobody answered that question."""
    return [one for one in behind if one.error_message or one.key not in updated]


def adopt_cask(token, shell):
    """Hand an app that is already installed over to Homebrew.

    Adoption needs a current index to match against, so unlike the checks
    this one lets Homebrew update itself first.
    """
    executable = shell.find_executable("brew")
    if executable is None:
        return -1
    return shell.stream_command([executable, "install", "--cask", token, "--adopt"])


def install_cask_over(token, shell):
    """Download the cask's version and put it over the app already in place.

    --force rather than --adopt, which Homebrew refuses for anything but an
    identical copy, and the two flags cannot be combined.
    """
    executable = shell.find_executable("brew")
    if executable is None:
        return -1
    return shell.stream_command([executable, "install", "--cask", token, "--force"])


def recorded_cask_versions(shell):
    """What Homebrew has written down for every cask it installed.

    One question rather than one per app, and the answer is what Homebrew
    believes rather than what is on disk.
    """
    executable = shell.find_executable("brew")
    if executable is None:
        return {}

    env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1")
    result = shell.run_command([executable, "list", "--cask", "--versions"], (0,), env)
    if not result.success:
        return {}

    recorded = {}
    for line in nonblank_lines(result.stdout):
        parts = line.split()
        if len(parts) >= 2:
            recorded[parts[0]] = parts[-1]
    return recorded


def recorded_cask_version(token, shell):
    """The version Homebrew wrote down for a cask, which it takes on trust."""
    executable = shell.find_executable("brew")
    if executable is None:
        return ""

    env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1")
    result = shell.run_command([executable, "list", "--cask", "--versions", token], (0,), env)
    if not result.success:
        return ""

    # "betterdisplay 5.0.6", or nothing at all when it isn't installed.
    parts = result.stdout.split()
    return parts[-1] if len(parts) >= 2 else ""


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
