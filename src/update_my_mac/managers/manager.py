"""What every manager has in common: the shape of one, and of its answers."""

import json
from dataclasses import dataclass, field


class CheckFailed(Exception):
    """The manager ran but its answer says something went wrong."""


def nonblank_lines(output):
    return [line for line in output.splitlines() if line.strip()]


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


@dataclass
class ManagerReport:
    manager: str
    label: str
    outdated_packages: list
    error_message: str = ""
    # Taps Homebrew is leaving out of the answer it just gave.
    ignored_taps: list = field(default_factory=list)


@dataclass
class ManagerUpdate:
    key: str
    label: str
    description: str = ""
    error_message: str = ""


STALE_AFTER_SECONDS = 24 * 60 * 60


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
