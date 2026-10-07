"""Apps in /Applications, and which of them no package manager knows about."""

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from update_my_mac.checks import app_updaters
from update_my_mac.checks import versions

APP_DIRECTORIES = ("/Applications", "~/Applications")

# Set UPDATE_MY_MAC_APP_DIRS to look elsewhere, colon-separated. It replaces the
# list above rather than adding to it.
DIRECTORY_OVERRIDE = "UPDATE_MY_MAC_APP_DIRS"


@dataclass
class InstalledApp:
    name: str
    version: str
    path: Path
    updater: app_updaters.UpdaterStatus = field(default_factory=app_updaters.UpdaterStatus)
    bundle_id: str = ""
    # Sometimes the only version a Homebrew recipe matches.
    build: str = ""

    def describe(self):
        return f"{self.name}  {self.version}"

    def versions_named(self):
        """Returns every version the app gives for itself, most readable first."""
        return [self.version, self.build]


def app_directories(env):
    configured = env.get(DIRECTORY_OVERRIDE)
    if configured is None:
        directories = APP_DIRECTORIES
    else:
        directories = tuple(entry for entry in configured.split(os.pathsep) if entry)

    home = env.get("HOME", "")
    found = []
    for directory in directories:
        if directory.startswith("~"):
            # Without HOME this would turn into a second /Applications, which
            # is exactly the environment a launchd job starts in.
            if not home:
                continue
            directory = home + directory[1:]
        found.append(Path(directory))
    return found


# What an app that says nothing about its version is listed as.
UNKNOWN_VERSION = versions.UNKNOWN


def read_build(info):
    """Returns the build the app came from."""
    return info.get("CFBundleVersion") or ""


def read_version(app_path, info=None):
    """Returns the version a person would recognise, from the app's own Info.plist."""
    info = app_updaters.read_bundle_info(app_path) if info is None else info
    return (
        info.get("CFBundleShortVersionString")
        or info.get("CFBundleVersion")
        or UNKNOWN_VERSION
    )


def belongs_to_macos(app_path):
    """Returns whether macOS ships this app, read from the restricted flag."""
    try:
        return bool(app_path.stat().st_flags & stat.SF_RESTRICTED)
    except (OSError, AttributeError):
        return False


def comes_from_the_app_store(app_path):
    # mas covers these, and an App Store app always carries its receipt.
    return (app_path / "Contents" / "_MASReceipt").exists()


def apps_installed_by_homebrew(shell):
    """Returns app file names Homebrew installed, empty when brew isn't there."""
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
    """Returns the app file names an artifact mentions, however it phrases them."""
    found = []
    for app in _as_path_list(artifact.get("app")):
        if isinstance(app, str):
            found.append(os.path.basename(app))

    for removal in _as_path_list(artifact.get("uninstall")) + _as_path_list(artifact.get("zap")):
        if not isinstance(removal, dict):
            continue
        for path in _as_path_list(removal.get("delete")) + _as_path_list(removal.get("trash")):
            if isinstance(path, str) and path.endswith(".app"):
                found.append(os.path.basename(path))
    return found


def _as_path_list(value):
    """Returns the paths an artifact names, written as a string or as a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def find_all(env=None):
    """Returns every app in the usual places that is somebody's to update."""
    env = os.environ if env is None else env

    found = []
    visited = set()
    for directory in app_directories(env):
        resolved = directory.resolve()
        if resolved in visited or not resolved.is_dir():
            continue
        visited.add(resolved)
        for app_path in sorted(resolved.glob("*.app")):
            if comes_from_the_app_store(app_path) or belongs_to_macos(app_path):
                continue
            info = app_updaters.read_bundle_info(app_path)
            found.append(
                InstalledApp(
                    app_path.stem,
                    read_version(app_path, info),
                    app_path,
                    bundle_id=info.get("CFBundleIdentifier", ""),
                    build=read_build(info),
                )
            )
    return found


def find_untracked(shell, env=None):
    """Returns apps in the usual places that neither mas nor Homebrew accounts for."""
    env = os.environ if env is None else env
    from_homebrew = apps_installed_by_homebrew(shell)

    found = []
    visited = set()
    for directory in app_directories(env):
        resolved = directory.resolve()
        if resolved in visited or not resolved.is_dir():
            continue
        visited.add(resolved)
        for app_path in sorted(resolved.glob("*.app")):
            if (
                app_path.name in from_homebrew
                or comes_from_the_app_store(app_path)
                or belongs_to_macos(app_path)
            ):
                continue
            # One read of Info.plist answers both the version and the updater.
            info = app_updaters.read_bundle_info(app_path)
            found.append(
                InstalledApp(
                    app_path.stem,
                    read_version(app_path, info),
                    app_path,
                    app_updaters.detect(app_path, shell, info),
                    info.get("CFBundleIdentifier", ""),
                    read_build(info),
                )
            )
    return without_shortcuts(found)


def without_shortcuts(apps):
    """Returns the apps, minus the launchers other apps put beside themselves."""
    owners = {app.bundle_id for app in apps if app.bundle_id}
    return [app for app in apps if not made_by_another_app(app, owners)]


def made_by_another_app(app, owners):
    return any(
        app.bundle_id.startswith(f"{owner}.") for owner in owners if owner != app.bundle_id
    )


def owned_by_someone_else(env=None):
    """Returns apps in the usual places that belong to another user."""
    env = os.environ if env is None else env
    mine = os.getuid()

    found = []
    visited = set()
    for directory in app_directories(env):
        resolved = directory.resolve()
        if resolved in visited or not resolved.is_dir():
            continue
        visited.add(resolved)
        for app_path in sorted(resolved.glob("*.app")):
            try:
                owner = app_path.stat().st_uid
            except OSError:
                continue
            # Root owns every App Store app, and those are not Homebrew's.
            if owner not in (mine, 0):
                found.append(app_path)
    return found
