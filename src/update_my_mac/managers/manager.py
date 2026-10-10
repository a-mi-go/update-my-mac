"""What every manager has in common: the shape of one, and of its answers."""

import json
import os
from dataclasses import dataclass, field
from types import MappingProxyType


class CheckFailed(Exception):
    """The manager ran but its answer says something went wrong."""


def nonblank_lines(output):
    return [line for line in output.splitlines() if line.strip()]


def _describe_error(error):
    if not isinstance(error, dict):
        return str(error)
    described = ": ".join(part for part in (error.get("code"), error.get("summary")) if part)
    return described or str(error)


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


class PackageManager:
    """One package manager: what it is called, and how to ask it anything."""

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

    def parse_outdated(self, stdout):
        return nonblank_lines(stdout)

    def ignored_sources(self, shell, result):
        """Returns what this manager left out of its answer without saying so."""
        return []

    def _env(self):
        return dict(os.environ, **self.extra_env) if self.extra_env else None

    def outdated(self, shell):
        """Returns what this manager says is outdated, or None when it is absent."""
        executable = shell.find_executable(self.command)
        if executable is None:
            return None

        result = shell.run_command(
            [executable, *self.outdated_args], self.success_exit_codes, self._env()
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
                             ignored_taps=self.ignored_sources(shell, result))

    def check_self(self, shell):
        """Returns a newer version of this manager, or None when there is none."""
        if not self.self_upgrade_args:
            return None

        executable = shell.find_executable(self.command)
        if executable is None:
            return None
        if not self.self_check_args:
            return None

        result = shell.run_command(
            [executable, *self.self_check_args], self.success_exit_codes, self._env()
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

    def upgrade(self, shell):
        """Upgrades the packages with the terminal attached. Returns the exit code or None."""
        return self._stream(shell, self.upgrade_args)

    def upgrade_self(self, shell):
        """Updates this manager with the terminal attached. Returns the exit code or None."""
        return self._stream(shell, self.self_upgrade_args)

    def _stream(self, shell, args):
        if not args:
            return None

        executable = shell.find_executable(self.command)
        if executable is None:
            return None
        return shell.stream_command([executable, *args], self._env())
