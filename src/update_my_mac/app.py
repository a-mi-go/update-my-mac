"""Sequencing the steps of a run, independent of how the flags were parsed."""

from update_my_mac import (
    adopt_apps,
    fix_things,
    behind_the_recipe,
    duplicate_commands,
    app_decisions,
    apply_updates,
    cask_index,
    installed_apps,
    package_managers,
    report,
    resolve_duplicates,
    restart_apps,
    running_apps,
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
    """One lookup of Homebrew's casks, shared by the steps that need it."""
    casks = None

    def cask_for(app):
        nonlocal casks
        if casks is None:
            casks = cask_index.load()
        return casks.for_app(app.path)

    return cask_for


def _behind_the_recipe():
    """Apps older than their cask, which is the one thing Homebrew never says."""
    return behind_the_recipe.find(installed_apps.find_all(), cask_index.load())


def _problems(untracked, doubled, stale, decisions):
    """The kinds of trouble that turned up, as choices the person can pick."""
    cask_for = _website_and_cask()
    found = []

    # An app that keeps itself up to date and has run ahead of its recipe is
    # not a problem, so it is not one of the things to sort out.
    troubled = [app for app in untracked if track_apps.worth_sorting_out(app, cask_for(app))]
    if troubled:
        # Counted by what Homebrew has a recipe for, not by what the step can
        # sweep up in one go: an app it would have to put back a version is
        # still one you can hand over. Without a single one, all the step can
        # do is stop listing an app, and it says so instead of promising a
        # handover it cannot make.
        known = track_apps.known_to_homebrew([(app, cask_for(app)) for app in troubled])
        label = (
            f"yes, get those apps back on track "
            f"({known} of {len(troubled)} can go to Homebrew)" if known
            else f"yes, go through the {len(troubled)} apps nobody tracks "
                 f"(none of them can go to Homebrew)"
        )
        found.append(
            _problem(
                label,
                troubled,
                _app_walkthrough(decisions),
                lambda apps, step: _adopt_every_app_we_can(apps, cask_for, step),
            )
        )

    if doubled:
        found.append(
            _problem(
                f"yes, I don't need apps installed twice ({len(doubled)})",
                doubled,
                _duplicate_walkthrough(),
                _remove_every_shadowed_copy,
            )
        )

    if stale:
        found.append(
            _problem(
                f"yes, restart updated apps ({len(stale)})",
                stale,
                _restart_walkthrough(),
                _restart_every_app,
            )
        )

    return found


def _problem(label, things, walk_through, fix_all):
    """One entry in the menu, with the things it is about tied to it."""
    return fix_things.Problem(
        label,
        lambda step: walk_through(things, step),
        lambda step: fix_all(things, step),
    )


def _adopt_every_app_we_can(apps, cask_for, step):
    found = [(app, cask_for(app)) for app in apps]
    return track_apps.adopt_all(found, _adoption(cask_for), step)


def _remove_every_shadowed_copy(duplicates, step):
    return resolve_duplicates.remove_shadowed(duplicates, _removal(), step)


def _restart_every_app(apps, step):
    each = step.inside()
    done = 0
    for app in apps:
        taken, message = restart_apps.restart(app, shell)
        each.say(f"{app.name}: {message}")
        done += 1 if taken else 0
    return done


def _removal():
    def remove(copy):
        executable = shell.find_executable(copy.remove_with[0])
        if executable is None:
            return -1
        return shell.stream_command([executable, *copy.remove_with[1:]])

    return remove


def _adoption(cask_for):
    def adopt(app):
        return adopt_apps.hand_to_homebrew(app, cask_for(app), shell)

    return adopt


def _restart_walkthrough():
    def go_through_restarts(apps, step):
        return restart_apps.run_restart_menu(
            apps, lambda app: restart_apps.restart(app, shell), step
        )

    return go_through_restarts


def _duplicate_walkthrough():
    remove = _removal()

    def go_through_duplicates(duplicates, step):
        return resolve_duplicates.run_duplicate_menu(duplicates, remove, step)

    return go_through_duplicates


def _app_walkthrough(decisions):
    cask_for = _website_and_cask()

    def go_through_apps(apps, step):
        return track_apps.run_untracked_menu(
            apps,
            decisions,
            step,
            find_cask=cask_for,
            adopt=_adoption(cask_for),
        )

    return go_through_apps


def _untracked_apps(decisions):
    """Untracked apps, minus the ones the user asked not to see again."""
    found = installed_apps.find_untracked(shell)
    listed = [app for app in found if not decisions.is_ignored(app.name)]
    return listed, len(found) - len(listed)


def run_check_mode():
    report.print_header()
    # The managers come first: an outdated manager is what everything else
    # below it depends on.
    installed = package_managers.installed_managers(shell)
    manager_updates = package_managers.check_managers_themselves(shell, installed)
    report.print_manager_updates(manager_updates, any_installed=bool(installed))

    reports = package_managers.check_installed(shell)
    report.print_outdated_summary(reports)

    listed, left_alone = _untracked_apps(app_decisions.load())
    report.print_untracked_apps(listed, left_alone=left_alone)
    report.print_foreign_owners(installed_apps.owned_by_someone_else())
    report.print_duplicate_commands(duplicate_commands.find(shell))
    report.print_behind_the_recipe(_behind_the_recipe())
    report.print_still_running_old(running_apps.find(shell))
    return _exit_code(reports, manager_updates)


def run_interactive_mode():
    report.print_header()
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
    report.print_foreign_owners(installed_apps.owned_by_someone_else())
    doubled = duplicate_commands.find(shell)
    report.print_duplicate_commands(doubled)
    report.print_behind_the_recipe(_behind_the_recipe())
    stale = running_apps.find(shell)
    report.print_still_running_old(stale)

    # Sorting things out comes before the updates, so the menu below lists
    # what is still outdated after it.
    sorted_out = fix_things.run_fix_menu(_problems(listed, doubled, stale, decisions))
    if sorted_out:
        # Handing an app to Homebrew or pulling a cask up to its recipe changes
        # what is outdated, and the menu numbers below would otherwise stand
        # for what was true before any of that.
        reports = package_managers.check_installed(shell)
        report.print_outdated_summary(reports)

    failed += apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(reports, manager_updates)


def run_retry_app_mode():
    report.print_header()
    track_apps.run_revisit_menu(app_decisions.load())
    return 0
