"""Handing an app you installed yourself over to Homebrew.

Homebrew can register an app that is already in place instead of downloading
it again. What it does not do is look inside: it writes down the version from
its own recipe and says the install succeeded, even when the app on disk is an
older one. The result is worse than doing nothing, because from then on
Homebrew reports the app as current and nobody ever calls it outdated again.

So the version is compared before, and checked again afterwards.
"""

from update_my_mac.checks import installed_apps
from update_my_mac.managers.homebrew import brew
from update_my_mac.system.shell import describe_exit
from update_my_mac.checks import versions
from update_my_mac.system import shell


SAME, NEWER, OLDER, UNCLEAR = "same", "newer", "older", "unclear"


def compare_to_app(app, cask):
    """Returns how the recipe's version stands to the installed one."""
    if cask is None:
        return ""
    if versions.any_version_matches(app.versions_named(), cask.version):
        return SAME
    if not versions.comparable(app.version, cask.version):
        return UNCLEAR
    return NEWER if versions.is_newer(cask.version, than=app.version) else OLDER


def can_adopt(app, cask):
    """Returns whether Homebrew can register the app that is already there, as it is."""
    return compare_to_app(app, cask) == SAME


def would_downgrade(app, cask):
    """Returns whether taking the app over would put an older version in its place."""
    return compare_to_app(app, cask) == OLDER


def can_take_over(app, cask):
    """Returns whether the handover can be offered, which rules out installer casks."""
    return cask is not None and not cask.installs_a_package


def handover_label(app, cask):
    """Returns the menu wording for what the handover would do to this app."""
    if not can_take_over(app, cask):
        return ""
    standing = compare_to_app(app, cask)
    if standing == SAME:
        return f"add to Homebrew ({cask.token} {_shown(cask.version)})"
    if standing == NEWER:
        return f"update to {cask.token} {_shown(cask.version)} and let Homebrew take over"
    # What it costs goes in brackets after the offer, because the cost is what
    # makes this a different answer from the one above it.
    if standing == OLDER:
        return (
            f"let Homebrew take over (downgrade {_shown(app.version)} → {_shown(cask.version)})"
        )
    if standing == UNCLEAR:
        return (
            f"let Homebrew take over (replace {_shown(app.version)} with {_shown(cask.version)}, "
            f"no telling which is newer)"
        )
    return ""


def homebrew_note(app, cask):
    """Returns where Homebrew stands with this app, or nothing when it matches or leads."""
    standing = compare_to_app(app, cask)
    if not standing:
        return "Homebrew has no recipe for this app."
    if cask.installs_a_package:
        return (
            f"Homebrew knows it as {cask.token} {_shown(cask.version)}, but installs it from a "
            f"package, which it cannot take an app over from."
        )
    if standing == OLDER:
        return (
            f"Homebrew's recipe {cask.token} is still {_shown(cask.version)}, older than the "
            f"{_shown(app.version)} you have, so handing the app over would put that older "
            f"build back in its place."
        )
    if standing == UNCLEAR:
        return (
            f"Homebrew's recipe {cask.token} says {_shown(cask.version)}, which is not counted "
            f"the way your {_shown(app.version)} is, so neither one is clearly the newer."
        )
    return ""


def hand_to_homebrew(app, cask):
    """Hands the app over. Returns whether it is now looked after, and why."""
    if cask is None:
        return False, "Homebrew has no recipe for this app."
    if cask.installs_a_package:
        return False, f"{cask.token} installs a package, so there is no app to take over."
    if shell.find_executable("brew") is None:
        return False, "Homebrew is not installed."

    if can_adopt(app, cask):
        exit_code = brew.adopt_cask(cask.token)
    else:
        # Any other version, ahead or behind, has to be downloaded and put in
        # place, because --adopt takes nothing but an identical copy.
        exit_code = brew.install_cask_over(cask.token)
    if exit_code != 0:
        how = describe_exit(exit_code)
        return False, f"Homebrew could not take it over, {cask.token} {how}."

    recorded = brew.recorded_cask_version(cask.token)
    on_disk = installed_apps.read_version(app.path)
    if recorded and not versions.same_release(on_disk, recorded):
        return False, (
            f"Homebrew wrote down {cask.token} {recorded}, but the app is still {on_disk}. "
            f"It would report the app as current from now on, so put it right with: "
            f"brew reinstall --cask {cask.token}"
        )

    return True, f"Homebrew looks after it now, as {cask.token}."


def _shown(version):
    """Returns a version as a person should read it, without the build."""
    return versions.without_build(version)
