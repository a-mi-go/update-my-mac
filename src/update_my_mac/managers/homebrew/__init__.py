"""Homebrew, which answers differently from the other three."""

import re
import time
from pathlib import Path
from types import MappingProxyType

from update_my_mac.managers.homebrew import brew
from update_my_mac.managers.manager import (
    ManagerUpdate,
    PackageManager,
    nonblank_lines,
)
from update_my_mac.system import shell

INDEX_STALE_AFTER_SECONDS = 24 * 60 * 60


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
