"""Sequencing the steps of a run, independent of how the flags were parsed."""

import functools

from rich.console import Console

from update_my_mac.managers.homebrew import adopting
from update_my_mac.checks import app_decisions
from update_my_mac.checks import appcast
from update_my_mac.controller import apply_updates
from update_my_mac.controller import self_update
from update_my_mac.managers.homebrew import behind_the_recipe
from update_my_mac.managers.homebrew import casks
from update_my_mac.controller import catch_up_casks
from update_my_mac.checks import duplicate_installations
from update_my_mac.checks import installed_apps
from update_my_mac import managers
from update_my_mac.view import report
from update_my_mac.controller import resolve_duplicates
from update_my_mac.controller import resolve_issues
from update_my_mac.controller import restart_apps
from update_my_mac.checks import running_apps
from update_my_mac.view import sections
from update_my_mac.system import shell
from update_my_mac.controller import track_apps


SPINNER = "dots"


def _exit_code(reports, managers_behind=()):
    """Non-zero only when a check could not run, never for outdated packages.

    A manager that could not answer about itself is such a check, which is why
    its updates are counted here too.
    """
    failed = [thing for thing in list(reports) + list(managers_behind) if thing.error_message]
    return 1 if failed else 0


@functools.lru_cache(maxsize=1)
def _casks():
    """Homebrew's list of casks, read once however many steps ask for it.

    It is 400K of JSON on disk and four steps of a run want to look something
    up in it.
    """
    return casks.load()


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
        managers.recorded_cask_versions(shell),
        already_reported=named,
    )


def _issues(findings, decisions):
    """The kinds of trouble that turned up, as choices the person can pick."""
    cask_for = _website_and_cask()
    found = []

    untracked_problem = _untracked_problem(
        findings.untracked, cask_for, decisions, findings.offered
    )
    if untracked_problem:
        found.append(untracked_problem)

    if findings.doubled:
        found.append(
            _problem(
                f"yes, I don't need apps installed twice ({len(findings.doubled)})",
                findings.doubled,
                _duplicate_walkthrough(),
                _remove_every_shadowed_copy,
            )
        )

    if findings.stale:
        found.append(
            _problem(
                f"yes, restart updated apps ({len(findings.stale)})",
                findings.stale,
                _restart_walkthrough(),
                _restart_every_app,
            )
        )

    if findings.apps_behind:
        found.append(
            _problem(
                f"yes, update the apps Homebrew stopped noticing ({len(findings.apps_behind)})",
                findings.apps_behind,
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


def _catch_every_app_up(apps_behind, step):
    return catch_up_casks.catch_up_all(apps_behind, _brewing(), step)


def _catch_up_walkthrough():
    def go_through_casks(apps_behind, step):
        return catch_up_casks.run_catch_up_menu(apps_behind, _brewing(), step)

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
        return adopting.hand_to_homebrew(app, cask_for(app), shell)

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
    installed = managers.installed_managers(shell)
    managers_behind = _check_the_managers(installed)
    findings = _check_the_mac(installed, app_decisions.load())
    findings.managers_behind = managers_behind
    report.print_report(findings)
    return _exit_code(findings.reports, findings.managers_behind)


def _check_the_managers(installed, console=None):
    console = console or Console(highlight=False)
    with console.status(
        "[dim]asking the package managers if they need an update themselves[/]",
        spinner=SPINNER,
    ):
        return managers.check_themselves(shell, installed)


def _check_the_mac(installed, decisions, console=None):
    console = console or Console(highlight=False)
    findings = sections.Findings(any_manager_installed=bool(installed))

    with console.status("", spinner=SPINNER) as spinner:
        def now(what):
            spinner.update(f"[dim]{what}[/]")

        now("asking each manager what is outdated")
        findings.reports = managers.check_installed(shell)

        now("looking for apps no manager tracks")
        listed, findings.left_alone = _untracked_apps(decisions)
        findings.untracked = listed
        findings.find_cask = _website_and_cask()

        now("reading what each app's own update feed offers")
        findings.offered = appcast.check(listed)

        now("comparing each app against Homebrew's recipe")
        findings.apps_behind = _behind_the_recipe(findings.reports)

        now("looking for app or package duplicates")
        findings.doubled = duplicate_installations.find(shell)

        now("looking for running apps that are no longer installed")
        findings.stale = running_apps.find(shell)

        now("looking for apps owned by another user")
        findings.foreign = installed_apps.owned_by_someone_else()

    return findings


def run_interactive_mode():
    installed = managers.installed_managers(shell)
    decisions = app_decisions.load()

    managers_behind = _check_the_managers(installed)
    picked = self_update.pick_managers(managers_behind)
    result = self_update.update_managers(picked, shell)

    findings = _check_the_mac(installed, decisions)
    findings.managers_behind = managers.still_behind(managers_behind, result.updated)
    report.print_report(findings)

    # Resolving issues first, so the update menu below lists what is left.
    resolved = resolve_issues.run_resolve_menu(_issues(findings, decisions))

    reports = findings.reports
    if resolved:
        reports = managers.check_installed(shell)
        report.print_outdated_summary(reports)

    failed = result.failed + apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(reports, findings.managers_behind)


def run_updates_only_mode():
    console = Console(highlight=False)
    installed = managers.installed_managers(shell)

    managers_behind = _check_the_managers(installed, console)
    picked = self_update.pick_managers(managers_behind)
    result = self_update.update_managers(picked, shell)

    with console.status("[dim]asking what is outdated[/]", spinner=SPINNER):
        reports = managers.check_installed(shell)

    failed = result.failed + apply_updates.run_upgrade_menu(reports, shell)
    return 1 if failed else _exit_code(
        reports, managers.still_behind(managers_behind, result.updated)
    )


def run_retry_app_mode():
    track_apps.run_revisit_menu(app_decisions.load())
    return 0
