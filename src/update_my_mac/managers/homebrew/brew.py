"""The commands only Homebrew has, and what it wrote down about its casks."""

import json
import os

from update_my_mac.managers.manager import nonblank_lines


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
