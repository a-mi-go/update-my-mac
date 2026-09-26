"""Apps that are older than the Homebrew recipe for them.

Homebrew compares the version it recorded at install time, and for a cask
marked `auto_updates` not even that, so it never notices.
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
    """Whether the recipe knows a newer version than the app on disk."""
    if not app_version or app_version == "?" or not cask_version:
        return False
    # A recipe writes "4.92.0,240144" where the app reports only "4.92.0".
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
