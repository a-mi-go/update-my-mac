"""Apps that are still running the version they were started with.

An upgrade replaces the bundle, but a running process keeps the old code in
memory and goes on offering an update that is already installed.
"""

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from update_my_mac.checks import installed_apps
from update_my_mac.shell_configs import parse_elapsed

# A bundle written at about the moment the app started is the app being
# launched, not an upgrade underneath it.
TOLERANCE_SECONDS = 60


@dataclass
class StillRunningOld:
    name: str
    bundle: Path
    pid: int
    running_since: float
    written: float
    # The version waiting on disk. What the running process holds is gone
    # from everywhere but its own memory, so nothing can report that one.
    version: str = ""

    def comment(self):
        started = time.strftime("%d %b %H:%M", time.localtime(self.running_since))
        replaced = time.strftime("%d %b %H:%M", time.localtime(self.written))
        return f"running since {started}, replaced {replaced}"

    def describe(self):
        known = self.version and self.version != installed_apps.UNKNOWN_VERSION
        named = f"{self.name}  {self.version}" if known else self.name
        return f"{named}:  {self.comment()}"


def _processes(shell):
    """Every running process as (pid, seconds running, executable path).

    `etime` rather than a start date, which ps writes in the machine's own
    language.
    """
    executable = shell.find_executable("ps")
    if executable is None:
        return []

    result = shell.run_command([executable, "-eo", "pid=,etime=,comm="], (0,))
    if not result.success:
        return []

    found = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, elapsed, command = parts
        seconds = parse_elapsed(elapsed)
        if pid.isdigit() and seconds is not None:
            found.append((int(pid), seconds, command))
    return found


def _bundle_of(command):
    """The .app a running executable belongs to, if it belongs to one."""
    match = re.match(r"(.*?\.app)/Contents/MacOS/", command)
    return Path(match.group(1)) if match else None


def _our_own_ancestors(shell):
    """The app this tool is running inside, which must not be restarted."""
    executable = shell.find_executable("ps")
    if executable is None:
        return set()

    ours = set()
    pid = os.getpid()
    for _ in range(8):
        result = shell.run_command([executable, "-o", "ppid=,comm=", "-p", str(pid)], (0,))
        if not result.success or not result.stdout.strip():
            break
        parent, _, command = result.stdout.strip().partition(" ")
        bundle = _bundle_of(command.strip())
        if bundle:
            ours.add(bundle)
        if not parent.isdigit() or int(parent) <= 1:
            break
        pid = int(parent)
    return ours


def find(shell, env=None):
    """Running apps whose bundle was replaced after they were started."""
    env = os.environ if env is None else env
    directories = {path.resolve() for path in installed_apps.app_directories(env)}
    ours = _our_own_ancestors(shell)
    now = time.time()

    found = {}
    for pid, seconds, command in _processes(shell):
        bundle = _bundle_of(command)
        if bundle is None or bundle in ours or bundle.parent not in directories:
            continue
        try:
            written = bundle.stat().st_mtime
        except OSError:
            continue

        running_since = now - seconds
        if written > running_since + TOLERANCE_SECONDS:
            found.setdefault(
                bundle,
                StillRunningOld(
                    bundle.stem, bundle, pid, running_since, written,
                    installed_apps.read_version(bundle),
                ),
            )
    return sorted(found.values(), key=lambda app: app.name)
