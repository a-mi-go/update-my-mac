"""Sequencing the steps of a run, independent of how the flags were parsed."""

import functools

from rich.console import Console

from update_my_mac import (
    adopt_apps,
    sections,
    appcast,
    resolve_issues,
    behind_the_recipe,
    catch_up_casks,
    duplicate_installations,
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


SPINNER = "dots"


def _exit_code(reports, manager_updates=()):
    """Non-zero only when a check could not run, never for outdated packages.

    A manager that could not answer about itself is such a check, which is why
    its updates are counted here too.
    """
    failed = [thing for thing in list(reports) + list(manager_updates) if thing.error_message]
    return 1 if failed else 0


@functools.lru_cache(maxsize=1)
def _casks():
    """Homebrew's list of casks, read once however many steps ask for it.

    It is 400K of JSON on disk and four steps of a run want to look something
    up in it.
    """
    return cask_index.load()


def _website_and_cask():
    """How to find the cask that installs a given app, if there is one."""
    return lambda app: _casks().for_app(app.path)


def _behind_the_recipe(reports):
    """Apps older than their cask, which is the one thing Homebrew never says."""
    brew = next((r for r in reports if r.manager == "brew"), None)
    named = {line.split()[0] for line in (brew.outdated_packages if brew else [])}
    return behind_the_recipe.find(
        installed_apps.find_all(),
        _casks(),
        package_managers.recorded_cask_versions(shell),
        already_reported=named,
    )


def _issues(untracked, doubled, stale, behind, decisions, offered):
    """The kinds of trouble that turned up, as choices the person can pick."""
    cask_for = _website_and_cask()
    found = []

    untracked_problem = _untracked_problem(untracked, cask_for, decisions, offered)
    if untracked_problem:
        found.append(untracked_problem)

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

    if behind:
        found.append(
            _problem(
                f"yes, update the apps Homebrew stopped noticing ({len(behind)})",
                behind,
                _catch_up_walkthrough(),
                _catch_every_app_up,
            )
        )
    return found


def _untracked_problem(untracked, cask_for, decisions, offered):
    """The entry for the apps no manager tracks, or None when none is a problem.

    An app that keeps itself up to date and has run ahead of its recipe is
    doing the job, so it is not one of the things to sort out.
    """
    troubled = [
        app
        for app in untracked
        if track_apps.worth_sorting_out(app, cask_for(app), appcast.answer_for(app, offered))
    ]
    if not troubled:
        return None

    # Counted by what Homebrew has a recipe for, not by what the bulk step can
    # take: a handover that would be a downgrade is still one you can choose.
    known = track_apps.known_to_homebrew([(app, cask_for(app)) for app in troubled])
    label = (
        f"yes, get those apps back on track "
        f"({known} of {len(troubled)} can go to Homebrew)" if known
        else f"yes, go through the apps nobody tracks ({len(troubled)})"
    )
    return _problem(
        label,
        troubled,
        _app_walkthrough(decisions, offered),
        lambda apps, step: _adopt_every_app_we_can(apps, cask_for, step),
    )


def _problem(label, things, walk_through, fix_all):
    """One entry in the menu, with the things it is about tied to it."""
    return resolve_issues.Problem(
        label,
        lambda step: walk_through(things, step),
        lambda step: fix_all(things, step),
    )


def _adopt_every_app_we_can(apps, cask_for, step):
    found = [(app, cask_for(app)) for app in apps]
    return track_apps.adopt_all(found, _adoption(cask_for), step)


def _remove_every_shadowed_copy(duplicates, step):
    return resolve_duplicates.remove_shadowed(duplicates, _removal(), step)


def _catch_every_app_up(behind, step):
    return catch_up_casks.catch_up_all(behind, _brewing(), step)


def _catch_up_walkthrough():
    def go_through_casks(behind, step):
        return catch_up_casks.run_catch_up_menu(behind, _brewing(), step)

    return go_through_casks


def _brewing():
    def run(command):
        executable = shell.find_executable("brew")
        if executable is None:
            return -1
        return shell.stream_command([executable, *command])

    return run


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


def _app_walkthrough(decisions, offered):
    cask_for = _website_and_cask()

    def go_through_apps(apps, step):
        return track_apps.run_untracked_menu(
            apps,
            decisions,
            step,
            find_cask=cask_for,
            adopt=_adoption(cask_for),
            open_url=shell.open_in_browser,
            open_app=shell.open_application,
            offered=offered,
        )

    return go_through_apps


def _untracked_apps(decisions):
    """Untracked apps, minus the ones the user asked not to see again."""
    found = installed_apps.find_untracked(shell)
    listed = [app for app in found if not decisions.is_ignored(app.name)]
    return listed, len(found) - len(listed)


def run_check_mode():
    installed = package_managers.installed_managers(shell)
    managers_behind = _ask_the_managers_about_themselves(installed)
    findings = _check_the_mac(installed, app_decisions.load(), managers_behind)
    report.print_report(findings)
    return _exit_code(findings.reports, findings.manager_updates)


def _ask_the_managers_about_themselves(installed, console=None):
    console = console or Console(highlight=False)
    with console.status(
        "[dim]asking the package managers if they need an update themselves[/]",
        spinner=SPINNER,
    ):
        return package_managers.check_managers_themselves(shell, installed)


def _managers_still_behind(behind, refreshed):
    """One whose check could not run stays, because nobody answered that question."""
    return [one for one in behind if one.error_message or one.key not in refreshed]


def _check_the_mac(installed, decisions, manager_updates=(), console=None):
    console = console or Console(highlight=False)
    findings = sections.Findings(any_manager_installed=bool(installed))
    findings.manager_updates = list(manager_updates)

    with console.status("", spinner=SPINNER) as spinner:
        def now(what):
            spinner.update(f"[dim]{what}[/]")

        now("asking each manager what is outdated")
        findings.reports = package_managers.check_installed(shell)

        now("looking for apps no manager tracks")
        listed, findings.left_alone = _untracked_apps(decisions)
        findings.untracked = listed
        findings.find_cask = _website_and_cask()

        now("reading what each app's own update feed offers")
        findings.offered = appcast.check(listed)

        now("comparing each app against Homebrew's recipe")
        findings.behind = _behind_the_recipe(findings.reports)

        now("looking for app or package duplicates")
        findings.doubled = duplicate_installations.find(shell)

        now("looking for running apps that are no longer installed")
        findings.stale = running_apps.find(shell)

        now("looking for apps owned by another user")
        findings.foreign = installed_apps.owned_by_someone_else()

    return findings


def run_interactive_mode():
    installed = package_managers.installed_managers(shell)
    decisions = app_decisions.load()

    managers_behind = _ask_the_managers_about_themselves(installed)
    managers = apply_updates.run_manager_menu(managers_behind, shell)

    findings = _check_the_mac(
        installed, decisions, _managers_still_behind(managers_behind, managers.refreshed)
    )
    report.print_report(findings)

    # Resolving issues first, so the update menu below lists what is left.
    resolved = resolve_issues.run_resolve_menu(
        _issues(
            findings.untracked, findings.doubled, findings.stale, findings.behind,
            decisions, findings.offered,
        )
    )

    reports = findings.reports
    if resolved:
        # Resolving an issue changes what is outdated, so ask again.
        reports = package_managers.check_installed(shell)
        report.print_outdated_summary(reports)

    failed = managers.failed + apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(reports, findings.manager_updates)


def run_updates_only_mode():
    console = Console(highlight=False)
    installed = package_managers.installed_managers(shell)

    managers_behind = _ask_the_managers_about_themselves(installed, console)
    managers = apply_updates.run_manager_menu(managers_behind, shell)

    with console.status("[dim]asking what is outdated[/]", spinner=SPINNER):
        reports = package_managers.check_installed(shell)

    still_behind = _managers_still_behind(managers_behind, managers.refreshed)
    failed = managers.failed + apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(reports, still_behind)


def run_retry_app_mode():
    track_apps.run_revisit_menu(app_decisions.load())
    return 0
