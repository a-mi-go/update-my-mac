"""Homebrew, which answers differently from the other three."""

import dataclasses
import re
import time
from pathlib import Path
from types import MappingProxyType

from update_my_mac.managers.homebrew import behind_the_recipe
from update_my_mac.managers.homebrew import brew
from update_my_mac.managers.homebrew import casks
from update_my_mac.managers.manager import (
    ManagerUpdate,
    PackageManager,
    package_name,
    nonblank_lines,
)
from update_my_mac.system import shell

INDEX_STALE_AFTER_SECONDS = 24 * 60 * 60
# "cursor  3.25.6,f0df77 -> 3.27.14,69b724  (190 MB)", the name and the size optional.
VERSION_CHANGE = re.compile(
    rb"^(?P<name> *(?:[^\s>]+ +)?)(?P<old>[^\s,]+)(?:,\S*)? *-> (?P<new>[^\s,]+)(?:,\S*)?(?P<size> +\(.*\))?\s*$"
)
# "✔︎ Cask cursor (3.27.22,b1aa50cb6db8)  Verified", as the downloads report themselves.
CASK_DOWNLOAD = re.compile(rb"(Cask \S+ \([^\s,()]+),[^\s()]*\)")


class Homebrew(PackageManager):
    key = "brew"
    label = "Homebrew"
    command = "brew"
    outdated_args = ("outdated", "--verbose")
    upgrade_args = ("upgrade",)
    extra_env = MappingProxyType({
        # A scheduled run should report against what Homebrew already knows
        # rather than pulling a new index first.
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        # Ask mode prints a plan table wider than a terminal, with download
        # sizes for formulae only, and asks before adding dependencies.
        "HOMEBREW_NO_ASK": "1",
        # A running app stays open, and the run offers to restart it afterwards.
        "HOMEBREW_NO_UPGRADE_QUIT_CASKS": "1",
    })
    self_upgrade_args = ("update",)
    cleanup_args = ("cleanup",)

    def __init__(self):
        self._greedy = None

    def outdated(self):
        """Returns Homebrew's outdated list, with the apps only a greedy upgrade reaches added."""
        report = super().outdated()
        self._greedy = []
        if report is None or report.error_message:
            return report
        named = {package_name(line) for line in report.outdated_packages}
        self._greedy = apps_only_a_greedy_upgrade_reaches(named)
        lines = [f"{item.cask.token}  {item.version_change()}" for item in self._greedy]
        return dataclasses.replace(report, outdated_packages=[*report.outdated_packages, *lines])

    def upgrade(self, status=None):
        if self._greedy is None:
            self.outdated()
        exit_code = super().upgrade(status)
        if not self._greedy:
            return exit_code
        tokens = [item.cask.token for item in self._greedy]
        greedy = self._stream(("upgrade", "--cask", "--greedy", *tokens), status)
        return exit_code or greedy

    def parse_outdated(self, stdout):
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

    def ignored_sources(self, result):
        """Returns the taps Homebrew left out of its answer without saying so."""
        if "not trusted" not in result.stderr:
            return []
        return brew.untrusted_taps()

    def shorten_output(self, data):
        """Returns the output with the build dropped from each version Homebrew writes for an upgrade."""
        lines = CASK_DOWNLOAD.sub(rb"\1)", data).split(b"\n")
        # The last piece may be the start of a line the next read finishes.
        finished = [(line, _version_change(line)) for line in lines[:-1]]
        if not any(b"," in line for line, change in finished if change):
            return b"\n".join(lines)
        width = max(len(change["old"]) for _, change in finished if change)
        shown = [_without_builds(line, change, width) if change else line for line, change in finished]
        return b"\n".join(shown + lines[-1:])

    def check_self(self):
        """Returns whether Homebrew's index is old enough to be worth refreshing."""
        executable = shell.find_executable(self.command)
        if executable is None:
            return None

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
            return ManagerUpdate(self.key, self.label, "index has never been fetched")

        if age < INDEX_STALE_AFTER_SECONDS:
            return None
        days = int(age // INDEX_STALE_AFTER_SECONDS)
        return ManagerUpdate(
            self.key, self.label, f"index is {days} day{'s' if days != 1 else ''} old"
        )


def _version_change(line):
    return VERSION_CHANGE.match(line.removesuffix(b"\r"))


def _without_builds(line, change, width):
    """Returns the line again with the builds gone and the arrows lined up at `width`."""
    size = b"  " + change["size"].strip() if change["size"] else b""
    ending = b"\r" if line.endswith(b"\r") else b""
    return change["name"] + change["old"].ljust(width) + b" -> " + change["new"] + size + ending


def apps_only_a_greedy_upgrade_reaches(already_reported):
    """Returns the apps behind their recipe that only `brew upgrade --greedy` brings level."""
    behind = behind_the_recipe.find_installed(casks.load(), already_reported)
    return [item for item in behind if item.needs_a_greedy_upgrade]
