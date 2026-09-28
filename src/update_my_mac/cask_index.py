"""Find out whether Homebrew has a cask for an app you installed yourself."""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

SOURCE = "https://formulae.brew.sh/api/cask.json"
STALE_AFTER_SECONDS = 24 * 60 * 60
TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Cask:
    token: str
    homepage: str
    version: str


def cache_path(env):
    base = env.get("XDG_CACHE_HOME") or os.path.join(env.get("HOME", ""), ".cache")
    return Path(base) / "update-my-mac" / "casks.json"


def app_names_in(cask):
    """The file names of the applications this cask installs.

    A cask lists what it puts on disk, and an application shows up there as
    "Something.app". Most casks install exactly one, some install none because
    they ship a command or an installer package instead.
    """
    found = []
    for artifact in cask.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        apps = artifact.get("app")
        if isinstance(apps, str):
            apps = [apps]
        for app in apps or []:
            if isinstance(app, str) and app.endswith(".app"):
                found.append(os.path.basename(app))
    return found


def reduce_to_apps(casks):
    """Boil the published list of casks down to a lookup table.

    Homebrew publishes every cask it has, which is about ten megabytes of
    release notes, checksums and dependency lists. We need three fields out of
    that, so we throw the rest away before writing anything to disk.
    """
    by_app = {}
    for cask in casks:
        token = cask.get("token")
        if not token:
            continue
        entry = {
            "token": token,
            "homepage": cask.get("homepage") or "",
            "version": cask.get("version") or "",
        }
        for name in app_names_in(cask):
            by_app.setdefault(name, entry)
    return by_app


def download(source=SOURCE):
    with urllib.request.urlopen(source, timeout=TIMEOUT_SECONDS) as answer:
        return reduce_to_apps(json.load(answer))


def read_cache(path):
    """What we stored last time, and how many seconds ago.

    A missing or damaged file counts as nothing stored, so a bad cache can
    never be worse than an empty one.
    """
    try:
        stored = json.loads(path.read_text())
        age = time.time() - path.stat().st_mtime
    except (OSError, ValueError):
        return None, 0
    return (stored, age) if isinstance(stored, dict) else (None, 0)


def write_cache(path, by_app):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".new")
        temporary.write_text(json.dumps(by_app, sort_keys=True))
        temporary.replace(path)
    except OSError:
        # Not being able to save the table only means the next run has to
        # fetch it again. That is not worth interrupting anything over.
        pass


class CaskIndex:
    def __init__(self, by_app):
        self.by_app = by_app

    def for_app(self, app_path):
        """The cask that installs this app, or None if Homebrew has none.

        Matched on the exact file name. Matching without regard to case would
        find one more app on this Mac and get it wrong: the orca cask installs
        plotly's orca, while the Orca in /Applications is a different program
        that happens to share the name. A file name is a weak identifier and
        nothing in the published cask list is a stronger one.
        """
        found = self.by_app.get(Path(app_path).name)
        if not isinstance(found, dict):
            return None
        return Cask(found.get("token", ""), found.get("homepage", ""), found.get("version", ""))

    def __len__(self):
        return len(self.by_app)


def load(env=None, fetch=download):
    """The lookup table, from disk while it is recent, otherwise from Homebrew.

    If fetching fails, usually because there is no network, we fall back to
    whatever is on disk even when it is old. An out of date answer about which
    cask installs an app is still far better than no answer, because that part
    of a cask hardly ever changes.
    """
    path = cache_path(os.environ if env is None else env)
    stored, age = read_cache(path)
    if stored is not None and age < STALE_AFTER_SECONDS:
        return CaskIndex(stored)

    try:
        fetched = fetch()
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return CaskIndex(stored or {})

    write_cache(path, fetched)
    return CaskIndex(fetched)
