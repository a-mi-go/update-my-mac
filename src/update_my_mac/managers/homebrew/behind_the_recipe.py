"""Apps Homebrew installed that are older than its recipe for them.

Homebrew compares the version it recorded at install time, and for a cask
marked `auto_updates` not even that, so it never notices.

Only apps it actually installed belong here, and only the ones it is not
already calling outdated. One it never installed is somebody else's app that
happens to have a recipe, and the way to bring that one in is the handover,
not an upgrade.
"""

from dataclasses import dataclass, field, replace

from update_my_mac.checks import app_updaters
from update_my_mac.checks import versions


@dataclass
class Behind:
    app: object
    cask: object
    # What Homebrew wrote down when it installed the cask, which is not
    # necessarily what it put on disk.
    recorded: str = ""
    updater: object = field(default_factory=app_updaters.UpdaterStatus)

    def version_change(self):
        return (f"{versions.without_build(self.app.version)} → "
                f"{versions.without_build(self.cask.version)}")

    def describe(self):
        return f"{self.app.name}  {self.version_change()}"

    @property
    def false_version_recorded(self):
        """Returns whether Homebrew's note matches the recipe while the app is older."""
        return versions.same_release(self.recorded, self.cask.version)


def is_behind(app_version, cask_version):
    """Returns whether the recipe knows a newer version than the app on disk."""
    return versions.is_newer(cask_version, than=app_version)


def find(apps, casks, recorded=None, already_reported=(), would_install=None):
    """Returns apps behind the version Homebrew would install, where Homebrew itself says nothing about it."""
    recorded = recorded or {}
    would_install = would_install or {}
    found = []
    for app in apps:
        cask = casks.for_app(app.path)
        if not cask or not recorded.get(cask.token) or cask.token in already_reported:
            continue
        if would_install.get(cask.token):
            cask = replace(cask, version=would_install[cask.token])
        if versions.any_version_matches(app.versions_named(), cask.version):
            continue
        if is_behind(app.version, cask.version):
            found.append(
                Behind(app, cask, recorded[cask.token], app_updaters.detect(app.path))
            )
    return found

