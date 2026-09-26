"""Sequencing the steps of a run, independent of how the flags were parsed."""

from update_my_mac import (
    app_decisions,
    apply_updates,
    cask_index,
    installed_apps,
    package_managers,
    report,
    shell,
    track_apps,
)


def _exit_code(reports, manager_updates=()):
    # Outdated packages are the normal case, so only a check that could not run
    # is worth a non-zero exit. A scheduled caller needs to tell those apart,
    # and a manager that could not answer about itself is such a check.
    failed = [thing for thing in list(reports) + list(manager_updates) if thing.error_message]
    return 1 if failed else 0


def _website_and_cask():
    """One lookup of Homebrew's casks, shared by the two things that need it."""
    casks = None

    def cask_for(app):
        nonlocal casks
        if casks is None:
            casks = cask_index.load()
        return casks.for_app(app.path)

    return cask_for


def _same_version(app_version, cask_version):
    """Whether Homebrew would see the installed app as the one in its recipe.

    A cask often carries a build number after a comma, such as "4.92.0,240144",
    while the app reports only the part in front of it.
    """
    return app_version.strip() == cask_version.split(",")[0].strip()


def _adopt_into_homebrew(cask_for):
    """Hand an app to Homebrew. Returns whether it is dealt with, and why."""

    def adopt(app):
        cask = cask_for(app)
        if cask is None:
            return False, "Homebrew has no recipe for this app."
        if shell.find_executable("brew") is None:
            return False, "Homebrew is not installed."

        # Adoption only works on an app that already matches the recipe. Trying
        # anyway would download the whole thing first and then refuse.
        if not _same_version(app.version, cask.version):
            return False, (
                f"Homebrew has {cask.token} {cask.version} and yours is {app.version}. "
                f"It can only take over a version it already knows, so install over it "
                f"with: brew install --cask {cask.token}"
            )

        exit_code = package_managers.adopt_cask(cask.token, shell)
        if exit_code != 0:
            return False, f"Homebrew could not take it over, {cask.token} exited with {exit_code}."
        return True, f"Homebrew looks after it now, as {cask.token}."

    return adopt


def _app_walkthrough(decisions):
    cask_for = _website_and_cask()

    def find_website(app):
        cask = cask_for(app)
        return cask.homepage if cask else ""

    def go_through_apps(apps, ask, out):
        return track_apps.run_untracked_menu(
            apps,
            decisions,
            ask,
            out,
            find_website=find_website,
            open_url=shell.open_in_browser,
            adopt=_adopt_into_homebrew(cask_for),
        )

    return go_through_apps


def _untracked_apps(decisions):
    """Untracked apps, minus the ones the user asked not to see again."""
    found = installed_apps.find_untracked(shell)
    listed = [app for app in found if not decisions.is_ignored(app.name)]
    return listed, len(found) - len(listed)


def run_check_mode():
    # The managers come first: an outdated manager is what everything else
    # below it depends on.
    installed = package_managers.installed_managers(shell)
    manager_updates = package_managers.check_managers_themselves(shell, installed)
    report.print_manager_updates(manager_updates, any_installed=bool(installed))

    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)

    listed, left_alone = _untracked_apps(app_decisions.load())
    report.print_untracked_apps(listed, left_alone=left_alone)
    return _exit_code(reports, manager_updates)


def run_interactive_mode():
    installed = package_managers.installed_managers(shell)
    manager_updates = package_managers.check_managers_themselves(shell, installed)
    report.print_manager_updates(manager_updates, any_installed=bool(installed))
    failed = apply_updates.run_manager_menu(manager_updates, shell)

    # Everything below is checked afterwards, so the list is what the current
    # tools report rather than what the old ones knew.
    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)

    decisions = app_decisions.load()
    listed, left_alone = _untracked_apps(decisions)
    report.print_untracked_apps(listed, left_alone=left_alone)

    failed += apply_updates.run_upgrade_menu(
        reports, shell, untracked_apps=listed, go_through_apps=_app_walkthrough(decisions)
    )
    return 1 if failed else _exit_code(reports, manager_updates)


def run_retry_app_mode():
    track_apps.run_revisit_menu(app_decisions.load())
    return 0
