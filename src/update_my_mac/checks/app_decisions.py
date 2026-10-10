"""What the user decided about an app, kept between runs.

Only one decision exists so far: leave this app alone. Adopting an app into
Homebrew Cask or watching its update feed will be recorded here too.
"""

import json
import os
import time
from pathlib import Path

FORMAT_VERSION = 1
IGNORE = "ignore"


def state_path(env):
    base = env.get("XDG_STATE_HOME") or os.path.join(env.get("HOME", ""), ".local", "state")
    return Path(base) / "update-my-mac" / "apps.json"


class AppDecisions:
    """The decisions file, read once and written when something changes."""

    def __init__(self, path):
        self.path = Path(path)
        self.apps = self._read()

    def _read(self):
        try:
            stored = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(stored, dict):
            return {}
        if stored.get("version") != FORMAT_VERSION:
            # A file from a version that doesn't exist yet: better to ask again
            # than to act on something written for other rules.
            return {}
        apps = stored.get("apps")
        return apps if isinstance(apps, dict) else {}

    def is_ignored(self, name):
        return self.apps.get(name, {}).get("decision") == IGNORE

    def ignored_names(self):
        return sorted(name for name in self.apps if self.is_ignored(name))

    def ignore(self, name, version, now=None):
        self.apps[name] = {
            "decision": IGNORE,
            "version": version,
            "decided": time.strftime("%Y-%m-%d", time.localtime(now)),
        }

    def forget(self, name):
        self.apps.pop(name, None)

    def save(self):
        """Writes the decisions and returns True if it worked."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Written beside the file and moved into place, so an interrupted
            # run can't leave half a file behind.
            temporary = self.path.with_name(self.path.name + ".new")
            temporary.write_text(
                json.dumps({"version": FORMAT_VERSION, "apps": self.apps}, indent=2, sort_keys=True)
                + "\n"
            )
            temporary.replace(self.path)
        except OSError:
            return False
        return True


def load(env=None):
    return AppDecisions(state_path(os.environ if env is None else env))
