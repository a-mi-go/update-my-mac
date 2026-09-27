"""Sequencing the steps of a run, independent of how the flags were parsed."""

from update_my_mac import (
    adopt_apps,
    behind_the_recipe,
    fix_things,
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
    """One lookup of Homebrew's casks, shared by the two things that need it."""
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

    if untracked:
        found.append(
            _problem(
                f"yes, get those apps back on track ({len(untracked)})",
                untracked,
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
    each = step.inside()
    done = 0
    for app in apps:
        cask = cask_for(app)
        if cask is None:
            continue
        taken, message = adopt_apps.hand_to_homebrew(app, cask, shell)
        each.say(f"{app.name}: {message}")
        done += 1 if taken else 0
    return done


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

    def find_website(app):
        cask = cask_for(app)
        return cask.homepage if cask else ""

    def go_through_apps(apps, step):
        # This one still asks its own way, one question per app.
        return track_apps.run_untracked_menu(
            apps,
            decisions,
            step.ask,
            step.out,
            find_website=find_website,
            open_url=shell.open_in_browser,
            adopt=lambda app: adopt_apps.hand_to_homebrew(app, cask_for(app), shell),
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

    # Everything that is not an update is offered together, before the menu
    # that is only about updates.
    fix_things.run_fix_menu(_problems(listed, doubled, stale, decisions))

    failed += apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(reports, manager_updates)


def run_retry_app_mode():
    report.print_header()
    track_apps.run_revisit_menu(app_decisions.load())
    return 0
