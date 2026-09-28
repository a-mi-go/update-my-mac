"""Apps Homebrew installed that are older than its recipe for them.

Homebrew compares the version it recorded at install time, and for a cask
marked `auto_updates` not even that, so it never notices.

Only apps it actually installed belong here, and only the ones it is not
already calling outdated. One it never installed is somebody else's app that
happens to have a recipe, and the way to bring that one in is the handover,
not an upgrade.
"""

from dataclasses import dataclass

from update_my_mac import versions


@dataclass
class Behind:
    app: object
    cask: object
    # What Homebrew wrote down when it installed the cask, which is not
    # necessarily what it put on disk.
    recorded: str = ""

    def version_change(self):
        return f"{self.app.version} → {self.cask.version}"

    def describe(self):
        return f"{self.app.name}  {self.version_change()}"

    @property
    def wrongly_recorded(self):
        """Homebrew believes it has this version, so no upgrade will touch it.

        What it wrote down at install time matches the recipe while the app on
        disk is older. `brew outdated` stays silent about it, and so does
        --greedy, because Homebrew compares its own note, never the bundle.
        """
        return versions.same(self.recorded, self.cask.version)


def is_behind(app_version, cask_version):
    """Whether the recipe knows a newer version than the app on disk."""
    return versions.is_newer(cask_version, than=app_version)


def to_reinstall(behind):
    """The casks Homebrew has a wrong version written down for."""
    return [item.cask.token for item in behind if item.wrongly_recorded]


def to_upgrade(behind):
    """The casks a greedy upgrade would actually pick up."""
    return [item.cask.token for item in behind if not item.wrongly_recorded]


def find(apps, casks, recorded=None, already_reported=()):
    """Apps behind their recipe that Homebrew is saying nothing about.

    `already_reported` is what `brew outdated` named. Listing one of those
    here as well would say the same thing twice, in two places, with two
    different names for the same app.
    """
    recorded = recorded or {}
    found = []
    for app in apps:
        cask = casks.for_app(app.path)
        if not cask or not recorded.get(cask.token) or cask.token in already_reported:
            continue
        if is_behind(app.version, cask.version):
            found.append(Behind(app, cask, recorded[cask.token]))
    return found
