"""Handing an app you installed yourself over to Homebrew.

Homebrew can register an app that is already in place instead of downloading
it again. What it does not do is look inside: it writes down the version from
its own recipe and says the install succeeded, even when the app on disk is an
older one. The result is worse than doing nothing, because from then on
Homebrew reports the app as current and nobody ever calls it outdated again.

So the version is compared before, and checked again afterwards.
"""

from update_my_mac import installed_apps, package_managers


def same_version(app_version, cask_version):
    """Whether Homebrew would see the installed app as the one in its recipe.

    A recipe often carries a build number after a comma, such as
    "4.92.0,240144", where the app itself reports only "4.92.0".
    """
    return app_version.strip() == cask_version.split(",")[0].strip()


def hand_to_homebrew(app, cask, shell):
    """Returns whether the app is now properly looked after, and why."""
    if cask is None:
        return False, "Homebrew has no recipe for this app."
    if shell.find_executable("brew") is None:
        return False, "Homebrew is not installed."

    # Trying anyway would download the whole thing and then refuse.
    if not same_version(app.version, cask.version):
        return False, (
            f"Homebrew has {cask.token} {cask.version} and yours is {app.version}. "
            f"It can only take over a version it already knows, so install over it "
            f"with: brew install --cask {cask.token}"
        )

    exit_code = package_managers.adopt_cask(cask.token, shell)
    if exit_code != 0:
        return False, f"Homebrew could not take it over, {cask.token} exited with {exit_code}."

    recorded = package_managers.recorded_cask_version(cask.token, shell)
    on_disk = installed_apps.read_version(app.path)
    if recorded and not same_version(on_disk, recorded):
        return False, (
            f"Homebrew wrote down {cask.token} {recorded}, but the app is still {on_disk}. "
            f"It would report the app as current from now on, so put it right with: "
            f"brew reinstall --cask {cask.token}"
        )

    return True, f"Homebrew looks after it now, as {cask.token}."
