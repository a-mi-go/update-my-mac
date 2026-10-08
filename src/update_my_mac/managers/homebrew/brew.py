"""What Homebrew reports, and the commands that drive it."""

import json
import os
import re
import time
from pathlib import Path

from update_my_mac.managers.manager import (
    ManagerUpdate,
    STALE_AFTER_SECONDS,
    nonblank_lines,
)


def parse_outdated(stdout):
    """Returns what `brew outdated --verbose` names, formulae and casks alike."""
    packages = []
    for line in nonblank_lines(stdout):
        match = re.match(r"(\S+) \((.+?)\) (?:<|!=) (\S+)", line.strip())
        if match:
            name, current, latest = match.groups()
            packages.append(f"{name}  {current} → {latest}")
        else:
            packages.append(line.strip())
    return packages

def check_index(manager, shell):
    """Returns whether Homebrew's index is old enough to be worth refreshing."""
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

def untrusted_taps(shell):
    """Returns the taps Homebrew will not read from until they are trusted."""
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

def recorded_cask_versions(shell):
    """Returns what Homebrew wrote down for every cask it installed, in one question."""
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
    """Returns the version Homebrew wrote down for a cask."""
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

def adopt_cask(token, shell):
    """Hands an app that is already installed over to Homebrew, index first."""
    executable = shell.find_executable("brew")
    if executable is None:
        return -1
    return shell.stream_command([executable, "install", "--cask", token, "--adopt"])

def install_cask_over(token, shell):
    """Downloads the cask's version and puts it over the app already in place."""
    executable = shell.find_executable("brew")
    if executable is None:
        return -1
    return shell.stream_command([executable, "install", "--cask", token, "--force"])
