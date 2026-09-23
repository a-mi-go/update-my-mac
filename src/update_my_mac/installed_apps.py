"""Apps that no package manager knows about.

An app dragged out of a `.dmg` is in no manager's list, so nothing reports it
as outdated. Finding those is the first half of doing something about it.
"""

import json
import os
import plistlib
import stat
from dataclasses import dataclass
from pathlib import Path

APP_DIRECTORIES = ("/Applications", "~/Applications")

# Set UPDATE_MY_MAC_APP_DIRS to look elsewhere, colon-separated. It replaces the
# list above rather than adding to it.
DIRECTORY_OVERRIDE = "UPDATE_MY_MAC_APP_DIRS"


@dataclass
class InstalledApp:
    name: str
    version: str
    path: Path

    def describe(self):
        return f"{self.name}  {self.version}"


def app_directories(env):
    configured = env.get(DIRECTORY_OVERRIDE)
    if configured is None:
        directories = APP_DIRECTORIES
    else:
        directories = tuple(entry for entry in configured.split(os.pathsep) if entry)
    home = env.get("HOME", "")
    return [Path(directory.replace("~", home, 1)) for directory in directories]


def read_version(app_path):
    """The version a person would recognise, from the app's own Info.plist."""
    try:
        with open(app_path / "Contents" / "Info.plist", "rb") as plist:
            info = plistlib.load(plist)
    except (OSError, plistlib.InvalidFileException):
        return "?"
    return info.get("CFBundleShortVersionString") or info.get("CFBundleVersion") or "?"


def belongs_to_macos(app_path):
    """Apps shipped with the system, which softwareupdate looks after.

    They carry the restricted flag that keeps even root from changing them,
    which is a surer sign than the path: Safari sits in /Applications like
    anything else.
    """
    try:
        return bool(app_path.stat().st_flags & stat.SF_RESTRICTED)
    except (OSError, AttributeError):
        return False


def comes_from_the_app_store(app_path):
    # mas covers these, and an App Store app always carries its receipt.
    return (app_path / "Contents" / "_MASReceipt").exists()


def apps_installed_by_homebrew(shell):
    """App file names Homebrew installed, empty when brew isn't there."""
    executable = shell.find_executable("brew")
    if executable is None:
        return set()

    env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1")
    result = shell.run_command(
        [executable, "info", "--json=v2", "--installed", "--cask"], (0,), env
    )
    if not result.success:
        return set()

    try:
        casks = json.loads(result.stdout).get("casks", [])
    except ValueError:
        return set()

    names = set()
    for cask in casks:
        for artifact in cask.get("artifacts", []):
            if isinstance(artifact, dict):
                names.update(_app_names_in(artifact))
    return names


def _app_names_in(artifact):
    """App file names an artifact mentions, however it phrases it.

    A cask that ships an app says so with an `app` stanza. One that ships a
    `pkg` names the app only in what it would remove again, which is why zoom
    and Safari Technology Preview were counted as untracked.
    """
    found = []
    for app in _as_list(artifact.get("app")):
        if isinstance(app, str):
            found.append(os.path.basename(app))

    for removal in _as_list(artifact.get("uninstall")) + _as_list(artifact.get("zap")):
        if not isinstance(removal, dict):
            continue
        for path in _as_list(removal.get("delete")) + _as_list(removal.get("trash")):
            if isinstance(path, str) and path.endswith(".app"):
                found.append(os.path.basename(path))
    return found


def _as_list(value):
    """Casks write a single path as a string and several as a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def find_untracked(shell, env=None):
    """Apps in the usual places that neither mas nor Homebrew accounts for."""
    env = os.environ if env is None else env
    from_homebrew = apps_installed_by_homebrew(shell)

    found = []
    for directory in app_directories(env):
        if not directory.is_dir():
            continue
        for app_path in sorted(directory.glob("*.app")):
            if (
                app_path.name in from_homebrew
                or comes_from_the_app_store(app_path)
                or belongs_to_macos(app_path)
            ):
                continue
            found.append(
                InstalledApp(app_path.stem, read_version(app_path), app_path)
            )
    return found
