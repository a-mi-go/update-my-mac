"""The commands that put right what Homebrew cannot or will not update by itself.

A cask marked `auto_updates` is never called outdated, and one Homebrew wrote
the wrong version down for is not even picked up by a greedy upgrade. Either
way the app sits there, older than the recipe, and nothing says so. Next to
those: packages Homebrew flagged, and downloads an upgrade left attached.
"""

import re

from pathlib import Path
from update_my_mac.checks import app_updaters
from update_my_mac.checks import installed_apps
from update_my_mac.controller.resolve_by_command import Fix, Option
from update_my_mac.managers.homebrew import flagged
from update_my_mac.view.sections import STILL_ATTACHED, doubt_about, download_name

FALSE_RECORD_NOTE = (
    "Homebrew wrote down a version it never installed, so no upgrade will touch this one."
)

REINSTALL = ("brew", "reinstall", "--cask")
UPGRADE = ("brew", "upgrade", "--cask", "--greedy")

CASK_TOKEN = re.compile(r"[a-z0-9][a-z0-9@._+-]*")


def command_for(item):
    """Returns the one command that puts a single app right."""
    return (REINSTALL if item.false_version_recorded else UPGRADE) + (item.cask.token,)


def fix_for_image(image):
    return Fix(
        download_name(image), STILL_ATTACHED,
        Option("", ("hdiutil", "detach", "-force", image.device), "detached"),
    )


def fix_for_flagged(item):
    """Returns the fix for a package Homebrew flagged, or None where no command puts it right."""
    label = f"{item.name}  {item.installed} → {item.available}" if item.available else item.name
    if item.kind == flagged.DIFFERS:
        return Fix(
            label, doubt_about(item),
            Option("", ("brew", "reinstall", item.name), "reinstalled"),
            (Option("", ("brew", "uninstall", item.name), "uninstalled"),),
        )
    if item.kind == flagged.DISABLED:
        cask = ("--cask",) if item.is_cask else ()
        return Fix(
            label, doubt_about(item),
            Option("", ("brew", "uninstall", *cask, item.name), "uninstalled"),
        )
    return None


def fix_for_behind(item, caskroom=None):
    """Returns the fix for one app, with the other ways out Homebrew leaves open."""
    others = []
    if item.updater.kind != app_updaters.NONE:
        others.append(Option(
            f"open {item.app.display_name} and update it manually",
            ("open", "-a", str(item.app.path)), "opened", settles=False,
        ))
    record = _caskroom_record(item.cask.token, caskroom)
    if record:
        # Homebrew has no command for letting go of an app and keeping it, so
        # its record of the cask is what goes.
        others.append(Option(
            "stop Homebrew tracking it, keep the app", ("rm", "-r", str(record)),
            "no longer tracked by Homebrew",
        ))
    others.append(Option("", ("brew", "uninstall", "--cask", item.cask.token), "uninstalled"))
    return Fix(
        f"{item.app.display_name} {item.version_change()}",
        FALSE_RECORD_NOTE if item.false_version_recorded else "",
        Option("", command_for(item), "reinstalled" if item.false_version_recorded else "updated"),
        tuple(others),
        _confirm(item),
    )


def _caskroom_record(token, caskroom):
    """Returns Homebrew's folder for the cask, or None unless it is safe to remove."""
    if not caskroom or not CASK_TOKEN.fullmatch(token):
        return None
    record = Path(caskroom) / token
    return record if record.parent == Path(caskroom) and record.is_dir() else None


def _confirm(item):
    """Returns a check that the app on disk really changed after a reinstall or upgrade."""
    def confirm(command):
        if command[1] not in ("reinstall", "upgrade"):
            return True, None
        name, was = item.app.display_name, item.app.version
        now = installed_apps.read_version(item.app.path)
        if now not in ("", installed_apps.UNKNOWN_VERSION, was):
            return True, (f"{name}: updated {was} → {now}", "green")
        return False, (f"{name}: the command finished, but the app is still {was}", "yellow")

    return confirm
