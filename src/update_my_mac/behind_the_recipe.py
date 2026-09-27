"""Apps that are older than the Homebrew recipe for them.

Homebrew compares the version it recorded at install time, and for a cask
marked `auto_updates` not even that, so it never notices.
"""

from dataclasses import dataclass

from update_my_mac import versions


@dataclass
class Behind:
    app: object
    cask: object

    def version_change(self):
        return f"{self.app.version} → {self.cask.version}"

    def describe(self):
        return f"{self.app.name}  {self.version_change()}"


def is_behind(app_version, cask_version):
    """Whether the recipe knows a newer version than the app on disk."""
    return versions.is_newer(cask_version, than=app_version)


def find(apps, casks):
    found = []
    for app in apps:
        cask = casks.for_app(app.path)
        if cask and is_behind(app.version, cask.version):
            found.append(Behind(app, cask))
    return found
