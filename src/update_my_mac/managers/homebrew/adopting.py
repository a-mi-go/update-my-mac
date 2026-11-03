"""Handing an app you installed yourself over to Homebrew.

Homebrew can register an app that is already in place instead of downloading
it again. What it does not do is look inside: it writes down the version from
its own recipe and says the install succeeded, even when the app on disk is an
older one. The result is worse than doing nothing, because from then on
Homebrew reports the app as current and nobody ever calls it outdated again.

So the version is compared before, and checked again afterwards.
"""

from typing import NamedTuple

from update_my_mac.checks import installed_apps, versions
from update_my_mac.managers.homebrew import brew
from update_my_mac.system import shell
from update_my_mac.system.shell import describe_exit

SAME, NEWER, OLDER, UNCLEAR = "same", "newer", "older", "unclear"

MAY_BE_A_DOWNGRADE = "the versions can't be compared, this may be a downgrade"


class HomebrewTakeover(NamedTuple):
    """What Homebrew's takeover of an app offers, and what it replaces."""

    offer: str
    detail: str


NO_TAKEOVER = HomebrewTakeover("", "")


def compare_to_app(app, cask):
    """Returns how the recipe's version stands to the installed one."""
    if not has_a_recipe(cask):
        return ""
    if versions.any_version_matches(app.versions_named(), cask.version):
        return SAME
    if not versions.comparable(app.version, cask.version):
        return UNCLEAR
    return NEWER if versions.is_newer(cask.version, than=app.version) else OLDER


def can_adopt(app, cask):
    """Returns whether Homebrew can register the app that is already there, as it is."""
    return has_a_recipe(cask) and not cask.installs_a_package and compare_to_app(app, cask) == SAME


def would_downgrade(app, cask):
    """Returns whether taking the app over would put an older version in its place."""
    return compare_to_app(app, cask) == OLDER


def has_a_recipe(cask):
    """Returns whether Homebrew has a recipe to take the app over with."""
    return cask is not None


def can_join_the_bulk_takeover(app, cask):
    """Returns whether Homebrew can take the app over without asking about it alone: no downgrade, no installer."""
    return has_a_recipe(cask) and not would_downgrade(app, cask) and not cask.installs_a_package


def homebrew_takeover_of(app, cask):
    """Returns the takeover to offer, which is NO_TAKEOVER without a recipe."""
    if not has_a_recipe(cask):
        return NO_TAKEOVER
    standing = compare_to_app(app, cask)
    downgrade_warning = _downgrade_warning(app, cask, standing)
    if cask.installs_a_package:
        return HomebrewTakeover("reinstall with Homebrew's installer", downgrade_warning or f"{cask.token} {_shown(cask.version)}")
    if downgrade_warning:
        return HomebrewTakeover("let Homebrew take over", downgrade_warning)
    if standing == SAME:
        return HomebrewTakeover("add to Homebrew", f"{cask.token} {_shown(cask.version)}")
    if standing == NEWER:
        return HomebrewTakeover(f"update to {cask.token} {_shown(cask.version)} and let Homebrew take over", "")
    return NO_TAKEOVER


def _downgrade_warning(app, cask, standing):
    """Returns the warning that the recipe's version is or may be older, or "" when it is not."""
    if standing == OLDER:
        return f"downgrade {_shown(app.version)} → {_shown(cask.version)}"
    if standing == UNCLEAR:
        return f"replace {_shown(app.version)} with {_shown(cask.version)}, {MAY_BE_A_DOWNGRADE}"
    return ""


def homebrew_note(app, cask):
    """Returns where Homebrew stands with this app, or nothing when it matches or leads."""
    standing = compare_to_app(app, cask)
    if not standing:
        return "Homebrew has no recipe for this app."
    if cask.installs_a_package:
        return (
            f"Homebrew knows it as {cask.token} {_shown(cask.version)}, but would have to reinstall it to take over. "
            f"App settings should stay untouched."
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


def take_over_with_homebrew(app, cask, status=None):
    """Has Homebrew take the app over. Returns whether it is now looked after, and why."""
    if not has_a_recipe(cask):
        return False, "Homebrew has no recipe for this app."
    if shell.find_executable("brew") is None:
        return False, "Homebrew is not installed."

    if can_adopt(app, cask):
        exit_code = brew.adopt_cask(cask.token, status)
    else:
        # --adopt takes nothing but an identical app bundle.
        exit_code = brew.install_cask_over(cask.token, status)
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
