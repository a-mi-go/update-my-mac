"""What every manager has in common: the shape of one, and of its answers."""

from abc import ABC
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from update_my_mac.system import shell


class CheckFailed(Exception):
    """The manager ran but its answer says something went wrong."""


@dataclass
class ManagerReport:
    manager: str
    label: str
    outdated_packages: list
    error_message: str = ""
    ignored_taps: list = field(default_factory=list)


@dataclass
class ManagerUpdate:
    key: str
    label: str
    description: str = ""
    error_message: str = ""


class PackageManager(ABC):
    """Base abstract class that provides a common interface for all package managers."""

    key: str
    label: str
    command: str
    outdated_args: tuple

    upgrade_args = ()
    success_exit_codes = (0,)
    extra_env = MappingProxyType({})
    counted_as = "packages"
    self_check_args = ()
    self_package = ""
    self_upgrade_args = ()
    cleanup_args = ()
    asks_for_password = False
    failure_hint = ""

    def parse_outdated(self, stdout):
        return nonblank_lines(stdout)

    def ignored_sources(self, result):
        """Returns what this manager left out of its answer without saying so."""
        return []

    def environment(self):
        return dict(shell.current_environment(), **self.extra_env) if self.extra_env else None

    def outdated(self):
        """Returns what this manager says is outdated, or None when it is absent."""
        executable = shell.find_executable(self.command)
        if executable is None:
            return None

        result = shell.run_command(
            [executable, *self.outdated_args], self.success_exit_codes, self.environment()
        )
        if not result.success:
            return ManagerReport(
                self.key, self.label, [], result.stderr or result.stdout
            )

        # A tolerated non-zero exit with no output is a failure, not a package list.
        if result.exit_code != 0 and not result.stdout:
            message = result.stderr or f"exited {result.exit_code} without output"
            return ManagerReport(self.key, self.label, [], message)

        try:
            packages = self.parse_outdated(result.stdout)
        except CheckFailed as failure:
            return ManagerReport(self.key, self.label, [], str(failure))

        return ManagerReport(self.key, self.label, packages,
                             ignored_taps=self.ignored_sources(result))

    def check_self(self):
        """Returns a newer version of this manager, or None when there is none."""
        if not self.self_upgrade_args:
            return None

        executable = shell.find_executable(self.command)
        if executable is None:
            return None
        if not self.self_check_args:
            return None

        result = shell.run_command(
            [executable, *self.self_check_args], self.success_exit_codes, self.environment()
        )
        if not result.success:
            return ManagerUpdate(
                self.key, self.label, error_message=result.stderr or result.stdout
            )

        try:
            described = describe_own_version(result.stdout, self.self_package)
        except CheckFailed as failure:
            return ManagerUpdate(self.key, self.label, error_message=str(failure))
        return ManagerUpdate(self.key, self.label, described) if described else None

    def upgrade(self, status=None):
        """Upgrades the packages with the terminal attached. Returns the exit code or None."""
        return self._stream(self.upgrade_args, status)

    def upgrade_self(self, status=None):
        """Updates this manager with the terminal attached. Returns the exit code or None."""
        return self._stream(self.self_upgrade_args, status)

    def cleanup(self, status=None):
        """Clears out what this manager no longer needs. Returns the exit code or None."""
        return self._stream(self.cleanup_args, status)

    def _stream(self, args, status):
        if not args:
            return None

        executable = shell.find_executable(self.command)
        if executable is None:
            return None
        # sudo asks on the real terminal, not through the pty, so a status
        # running over it would hide the question.
        if self.asks_for_password:
            status = None
        return shell.stream_command([executable, *args], self.environment(), silent_status=status)


def nonblank_lines(output):
    return [line for line in output.splitlines() if line.strip()]


def parse_json_packages(stdout):
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


def describe_own_version(stdout, package):
    """Returns one named package's line from `outdated --json`."""
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


def _describe_error(error):
    if not isinstance(error, dict):
        return str(error)
    described = ": ".join(part for part in (error.get("code"), error.get("summary")) if part)
    return described or str(error)
