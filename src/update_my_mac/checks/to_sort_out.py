"""What the first menu offers to sort out, read the same way by the report and by the menu."""

import time
from dataclasses import dataclass

from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.checks import versions
from update_my_mac.managers.homebrew import adopting
from update_my_mac.managers.homebrew import flagged

# The flags a command can put right; Homebrew's other doubts are only worth knowing.
FIXABLE_FLAGS = (flagged.DIFFERS, flagged.DISABLED)
CANNOT_CHECK = "can't check for updates"


@dataclass(frozen=True)
class Concern:
    """Why an untracked app is on the list, what else is known, and whether it cannot wait."""

    reason: str
    detail: str = ""
    urgent: bool = False

    @property
    def note(self):
        return f"{self.reason}, {self.detail}" if self.detail else self.reason


def concern_about(app, findings):
    """Returns why this untracked app needs a decision, or None when nothing says it does."""
    updater = app.updater
    if updater.kind == app_updaters.HOST_APP or _in_the_homebrew_group(app, findings):
        return None

    answer = appcast.answer_for(app, findings.offered)
    history = updater.history_note() if updater.kind == app_updaters.SPARKLE else ""
    if answer.error:
        return Concern(answer.error, history, urgent=True)
    if updater.is_switched_off:
        return Concern("updater off", history)
    if appcast.offers_newer(app, answer):
        return Concern(f"{versions.without_build(answer.version)} is out")
    if answer.version:
        return None

    cask = cask_of(findings, app)
    standing = adopting.compare_to_app(app, cask)
    if standing == adopting.NEWER:
        return Concern(f"Homebrew has {versions.without_build(cask.version)}")
    if standing in (adopting.SAME, adopting.OLDER) or updater.looks_after_itself:
        return None
    changed = last_changed(app)
    since = f"unchanged since {time.strftime('%Y-%m', time.localtime(changed))}" if changed else ""
    return Concern(CANNOT_CHECK, since)


def _in_the_homebrew_group(app, findings):
    return any(item.app.path == app.path for item in findings.apps_behind)


def last_changed(app):
    """Returns when the app's bundle last changed, or None where that cannot be read."""
    try:
        # An update replaces the bundle, and with it this file.
        return (app.path / "Contents" / "Info.plist").stat().st_mtime
    except OSError:
        return None


def untracked_concerns(findings):
    """Returns (app, concern) for the untracked apps that need a decision, those that cannot wait first."""
    listed = [(app, concern_about(app, findings)) for app in findings.untracked]
    return sorted(
        ((app, concern) for app, concern in listed if concern),
        key=lambda pair: not pair[1].urgent,
    )


def untracked_to_sort_out(findings):
    return [app for app, _ in untracked_concerns(findings)]


def blocking_brew_upgrade(findings):
    """Returns what `brew upgrade` skips or gets wrong until it is fixed, worst first."""
    behind = [item for item in findings.apps_behind if not _by_macos(item)]
    recorded_at_a_false_version = [item for item in behind if item.false_version_recorded]
    held_at_another_version = _flagged_as(findings, flagged.DIFFERS)
    disabled = _flagged_as(findings, flagged.DISABLED)
    installer_still_mounted = findings.mounted
    replaced_outside_homebrew = [item for item in behind if not item.false_version_recorded]
    return [
        *recorded_at_a_false_version,
        *held_at_another_version,
        *disabled,
        *installer_still_mounted,
        *replaced_outside_homebrew,
    ]


def _flagged_as(findings, kind):
    return [item for item in findings.flagged if item.kind == kind]


def _by_macos(item):
    """Returns whether macOS keeps this app current, whatever a Homebrew recipe says."""
    return item.app.updater.kind == app_updaters.HOST_APP or item.app.bundle_id.startswith("com.apple.")


def only_worth_knowing(findings):
    """Returns the packages Homebrew has doubts about that no command puts right."""
    return [item for item in findings.flagged if item.kind not in FIXABLE_FLAGS]


def cask_of(findings, app):
    return findings.find_cask(app) if findings.find_cask else None
