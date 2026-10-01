"""Commands that more than one package manager has installed.

Each manager is right about its own copy and reports nothing outdated, while
PATH decides which one you actually run.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Copy:
    manager: str
    path: Path
    package: str
    remove_with: tuple = ()
    version: str = ""

    def describe(self):
        named = f"{self.manager}, {self.package or self.path}"
        return f"{named} {self.version}" if self.version else named


@dataclass
class Duplicate:
    command: str
    copies: list

    @property
    def winner(self):
        return self.copies[0]

    @property
    def shadowed(self):
        return self.copies[1:]


def _asked(shell, command, args):
    executable = shell.find_executable(command)
    if executable is None:
        return ""
    result = shell.run_command([executable, *args], (0,))
    return result.stdout.strip() if result.success else ""


def bin_directories(shell):
    """Where each manager puts the commands it installs."""
    found = {}

    prefix = _asked(shell, "brew", ["--prefix"])
    if prefix:
        found["Homebrew"] = Path(prefix) / "bin"

    prefix = _asked(shell, "npm", ["prefix", "-g"])
    if prefix:
        found["npm (global)"] = Path(prefix) / "bin"

    directory = _asked(shell, "pnpm", ["bin", "-g"])
    if directory:
        found["pnpm (global)"] = Path(directory)

    return found


def package_behind(path):
    """The package a command belongs to, its version, and how to get rid of it.

    Read off the symlink, which points into wherever the manager keeps it.
    """
    try:
        real = Path(os.path.realpath(path))
    except OSError:
        return "", "", ()
    parts = real.parts

    for keep in ("Caskroom", "Cellar"):
        if keep in parts:
            at = parts.index(keep) + 1
            name = parts[at]
            # Homebrew keeps each version in a directory of its own.
            version = parts[at + 1] if len(parts) > at + 1 else ""
            if keep == "Caskroom":
                return name, version, ("brew", "uninstall", "--cask", name)
            return name, version, ("brew", "uninstall", name)

    if "node_modules" in parts:
        at = parts.index("node_modules") + 1
        name = parts[at]
        # A scoped package is two path segments, @scope/name.
        if name.startswith("@") and len(parts) > at + 1:
            at += 1
            name = f"{name}/{parts[at]}"
        installed = Path(*parts[: at + 1])
        version = _version_in(installed / "package.json")
        remover = "pnpm" if ".pnpm" in parts or "pnpm" in parts else "npm"
        if remover == "pnpm":
            return name, version, ("pnpm", "remove", "-g", name)
        return name, version, ("npm", "uninstall", "-g", name)

    return "", "", ()


def _version_in(manifest):
    """The version a node package writes down about itself."""
    try:
        return str(json.loads(manifest.read_text()).get("version", ""))
    except (OSError, ValueError):
        return ""


def _in_path_order(directories, env):
    """The manager directories, in the order PATH would search them."""
    searched = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    places = {Path(entry): position for position, entry in enumerate(searched)}
    never_on_path = len(searched)
    return sorted(directories.items(), key=lambda pair: places.get(pair[1], never_on_path))


def find(shell, env=None):
    """Commands that exist in more than one manager's directory."""
    env = os.environ if env is None else env
    ordered = _in_path_order(bin_directories(shell), env)

    seen = {}
    for manager, directory in ordered:
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            package, version, remove_with = package_behind(entry)
            seen.setdefault(entry.name, []).append(
                Copy(manager, entry, package, remove_with, version)
            )

    return [
        Duplicate(command, copies)
        for command, copies in sorted(seen.items())
        if len(copies) > 1
    ]
