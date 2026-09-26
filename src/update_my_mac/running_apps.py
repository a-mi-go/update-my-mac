"""Apps that are still running the version they were started with.

An upgrade replaces the bundle on disk, but a process that was already running
keeps the old code in memory. Nothing on disk says anything is wrong, so every
check here reports the app as current while the app itself goes on offering
its own update, because it compares the version it was started with.

That is how Markdown Preview offered 0.0.62 while 0.0.62 was already installed:
the process had been running since three days before the upgrade.
"""

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from update_my_mac import installed_apps
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

    def comment(self):
        started = time.strftime("%d %b %H:%M", time.localtime(self.running_since))
        replaced = time.strftime("%d %b %H:%M", time.localtime(self.written))
        return f"running since {started}, replaced {replaced}"

    def describe(self):
        return f"{self.name}:  {self.comment()}"


def _processes(shell):
    """Every running process as (pid, seconds running, executable path).

    `etime` rather than a start date, because ps writes dates in the machine's
    own language and there is nothing to parse reliably in that.
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
                bundle, StillRunningOld(bundle.stem, bundle, pid, running_since, written)
            )
    return sorted(found.values(), key=lambda app: app.name)
