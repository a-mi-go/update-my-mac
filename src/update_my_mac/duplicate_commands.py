"""Commands that more than one package manager has installed.

Two managers can each provide a command of the same name, and then PATH
decides which one you actually run. Both managers report themselves as up to
date, because each is right about its own copy, and the version you type is
whichever directory comes first. That is how a freshly updated tool can sit
unused while an older one answers.

The copies are found by looking in the directories the managers install into,
and the package to uninstall is read off the symlink each command points at.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Copy:
    manager: str
    path: Path
    package: str
    remove_with: tuple = ()

    def describe(self):
        return f"{self.manager}, {self.package or self.path}"


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
    """The package a command belongs to, and how to get rid of it.

    A command in a manager's bin directory is a symlink into wherever that
    manager keeps the package, and the path says both which package it is and
    what kind, which is what the uninstall command needs.
    """
    try:
        parts = Path(os.path.realpath(path)).parts
    except OSError:
        return "", ()

    if "Caskroom" in parts:
        name = parts[parts.index("Caskroom") + 1]
        return name, ("brew", "uninstall", "--cask", name)
    if "Cellar" in parts:
        name = parts[parts.index("Cellar") + 1]
        return name, ("brew", "uninstall", name)

    if "node_modules" in parts:
        at = parts.index("node_modules") + 1
        name = parts[at]
        # A scoped package is two path segments, @openai/codex.
        if name.startswith("@") and len(parts) > at + 1:
            name = f"{name}/{parts[at + 1]}"
        remover = "pnpm" if ".pnpm" in parts or "pnpm" in parts else "npm"
        if remover == "pnpm":
            return name, ("pnpm", "remove", "-g", name)
        return name, ("npm", "uninstall", "-g", name)

    return "", ()


def _in_path_order(directories, env):
    """The manager directories, in the order PATH would search them."""
    searched = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    places = {Path(entry): position for position, entry in enumerate(searched)}
    # A directory PATH never mentions cannot win, so it goes last.
    return sorted(directories.items(), key=lambda pair: places.get(pair[1], len(searched)))


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
            package, remove_with = package_behind(entry)
            seen.setdefault(entry.name, []).append(
                Copy(manager, entry, package, remove_with)
            )

    return [
        Duplicate(command, copies)
        for command, copies in sorted(seen.items())
        if len(copies) > 1
    ]
