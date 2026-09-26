"""Apps that are older than the Homebrew recipe for them.

Homebrew only compares the version it wrote down at install time against the
recipe, and for a cask marked `auto_updates` it does not even do that, on the
assumption that the app looks after itself. When the app then stops looking
after itself, nobody notices: Homebrew reports nothing, the app reports
nothing, and the version on disk quietly falls behind.

Reading the version out of the app bundle and comparing it against the recipe
is the only way to see it. On the machine this was written on that found
nineteen apps, and `brew outdated` reported none of them.
"""

import re
from dataclasses import dataclass


@dataclass
class Behind:
    app: object
    cask: object

    def version_change(self):
        return f"{self.app.version} → {self.cask.version}"

    def describe(self):
        return f"{self.app.name}  {self.version_change()}"


def _numbers_in(version):
    return [int(part) for part in re.findall(r"\d+", version)]


def is_behind(app_version, cask_version):
    """Whether the recipe knows a newer version than the app on disk.

    A recipe often carries a build number after a comma, and a version that
    only differs there is the same version.
    """
    if not app_version or app_version == "?" or not cask_version:
        return False
    if app_version.strip() == cask_version.split(",")[0].strip():
        return False
    return _numbers_in(app_version) < _numbers_in(cask_version)


def find(apps, casks):
    found = []
    for app in apps:
        cask = casks.for_app(app.path)
        if cask and is_behind(app.version, cask.version):
            found.append(Behind(app, cask))
    return found
