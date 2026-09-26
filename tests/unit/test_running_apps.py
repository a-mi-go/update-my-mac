"""Apps still running the version they were started with."""

import os
import time

from update_my_mac import running_apps
from update_my_mac.shell import CommandResult


def bundle(directory, name, written_ago_seconds):
    app = directory / f"{name}.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    when = time.time() - written_ago_seconds
    os.utime(app, (when, when))
    return app


class PsShell:
    """Answers the two questions asked of ps, and nothing else.

    `listing` is (pid, etime, command) per process, `parents` maps a pid to
    the line ps would print for `-p`.
    """

    def __init__(self, listing, parents=None, has_ps=True):
        self.listing = listing
        self.parents = parents or {}
        self.has_ps = has_ps

    def find_executable(self, command):
        return "/bin/ps" if self.has_ps and command == "ps" else None

    def run_command(self, args, success_exit_codes=(0,), env=None):
        if "-p" in args:
            pid = args[args.index("-p") + 1]
            return CommandResult(True, self.parents.get(pid, ""), "")
        lines = "\n".join(f"{pid} {etime} {command}" for pid, etime, command in self.listing)
        return CommandResult(True, lines, "")


def running(app, etime, pid=100):
    return (str(pid), etime, f"{app}/Contents/MacOS/{app.stem}")


def test_an_app_replaced_after_it_started_is_found(tmp_path):
    app = bundle(tmp_path, "Markdown Preview", written_ago_seconds=60)
    shell = PsShell([running(app, "02:00:00")])

    found = running_apps.find(shell, {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)})
    assert [item.name for item in found] == ["Markdown Preview"]


def test_an_app_started_after_it_was_replaced_is_current(tmp_path):
    app = bundle(tmp_path, "Current", written_ago_seconds=7200)
    shell = PsShell([running(app, "10:00")])

    assert running_apps.find(shell, {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)}) == []


def test_a_bundle_written_as_the_app_launched_is_not_a_find(tmp_path):
    # Launching writes the bundle's own timestamps, which looked like an
    # upgrade and reported iTerm on every run.
    app = bundle(tmp_path, "JustLaunched", written_ago_seconds=30)
    shell = PsShell([running(app, "00:30")])

    assert running_apps.find(shell, {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)}) == []


def test_the_app_this_tool_runs_inside_is_left_alone(tmp_path):
    app = bundle(tmp_path, "Terminal", written_ago_seconds=60)
    ours = f"{app}/Contents/MacOS/Terminal"
    shell = PsShell(
        [running(app, "02:00:00")],
        parents={str(os.getpid()): f"1 {ours}"},
    )

    assert running_apps.find(shell, {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)}) == []


def test_a_process_that_is_not_an_app_is_ignored(tmp_path):
    bundle(tmp_path, "Whatever", written_ago_seconds=60)
    shell = PsShell([("200", "02:00:00", "/usr/sbin/cfprefsd")])

    assert running_apps.find(shell, {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)}) == []


def test_an_app_somewhere_else_is_not_our_business(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    app = bundle(elsewhere, "Stray", written_ago_seconds=60)
    shell = PsShell([running(app, "02:00:00")])

    assert running_apps.find(shell, {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)}) == []


def test_each_app_is_named_once_however_many_processes_it_has(tmp_path):
    app = bundle(tmp_path, "Chatty", written_ago_seconds=60)
    shell = PsShell([running(app, "02:00:00", 1), running(app, "02:00:00", 2)])

    assert len(running_apps.find(shell, {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)})) == 1


def test_without_ps_nothing_is_claimed(tmp_path):
    assert running_apps.find(PsShell([], has_ps=False), {"UPDATE_MY_MAC_APP_DIRS": str(tmp_path)}) == []
