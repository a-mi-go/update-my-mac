"""Sequencing the steps of a run, independent of how the flags were parsed."""

import functools
import getpass

from update_my_mac.managers.homebrew import brew
from update_my_mac.checks import Findings
from update_my_mac.checks import app_decisions
from update_my_mac.checks import appcast
from update_my_mac.checks import to_sort_out
from update_my_mac.controller import apply_updates
from update_my_mac.controller import self_update
from update_my_mac.managers.homebrew import behind_the_recipe
from update_my_mac.managers.homebrew import casks
from update_my_mac.managers.homebrew import flagged
from update_my_mac.managers.homebrew import mounted_downloads
from update_my_mac.controller import homebrew_fixes
from update_my_mac.checks import duplicate_installations
from update_my_mac.checks import installed_apps
from update_my_mac import managers
from update_my_mac.view import output
from update_my_mac.view import report
from update_my_mac.view import sections
from update_my_mac.controller import resolve_duplicates
from update_my_mac.controller import resolve_by_command
from update_my_mac.controller import resolve_issues
from update_my_mac.controller import restart_apps
from update_my_mac.checks import running_apps
from update_my_mac.controller import track_apps


def run_check_mode():
    installed = managers.installed()
    managers_behind = _check_the_managers(installed)
    findings = _check_the_mac(installed, app_decisions.load())
    findings.managers_behind = managers_behind
    report.print_report(findings)
    return _exit_code(findings.reports, findings.managers_behind)


def run_interactive_mode():
    # One screen from the start to the first menu; the report goes to the normal one after it.
    with output.full_screen():
        return _run_interactive()


def _run_interactive():
    installed = managers.installed()
    decisions = app_decisions.load()

    managers_behind = _check_the_managers(installed)
    result = self_update.update_managers(managers_behind)
    _clean_up(installed)

    findings = _check_the_mac(installed, decisions)
    findings.managers_behind = managers.still_behind(managers_behind, result.updated)

    # Resolving issues first, so the update menu below lists what is left.
    updates = _Updates(findings.reports)
    resolved = resolve_issues.ask_what_to_fix(
        _issues(findings, decisions),
        above=lambda console: report.print_to(console, findings),
        updates=updates,
    )

    reports = updates.reports()
    if resolved:
        report.print_outdated_summary(reports)

    failed = result.failed + apply_updates.ask_what_to_update(reports)
    _offer_to_restart_what_the_updates_replaced(findings.stale)
    return 1 if failed else _exit_code(reports, findings.managers_behind)


def run_updates_only_mode():
    installed = managers.installed()

    managers_behind = _check_the_managers(installed)
    result = self_update.update_managers(managers_behind)
    _clean_up(installed)

    with output.console.status("[dim]asking what is outdated[/]", spinner=report.SPINNER):
        reports = managers.check_what_is_outdated()

    failed = result.failed + apply_updates.ask_what_to_update(reports)
    _offer_to_restart_what_the_updates_replaced()
    return 1 if failed else _exit_code(
        reports, managers.still_behind(managers_behind, result.updated)
    )


def run_retry_app_mode():
    track_apps.ask_about_the_ignored(app_decisions.load())
    return 0


def _check_the_managers(installed):
    with output.console.status(
        "[dim]asking the package managers if they need an update themselves[/]",
        spinner=report.SPINNER,
    ):
        return managers.check_themselves(installed)


def _check_the_mac(installed, decisions):
    findings = Findings(any_manager_installed=bool(installed))

    with output.console.status("", spinner=report.SPINNER) as spinner:
        def now(what):
            spinner.update(f"[dim]{what}[/]")

        now("asking each manager what is outdated")
        findings.reports = managers.check_what_is_outdated()

        now("looking for apps no manager tracks")
        listed, findings.left_alone = _untracked_apps(decisions)
        findings.untracked = listed
        findings.find_cask = _website_and_cask()

        now("reading what each app's own update feed offers")
        findings.offered = appcast.check(listed)

        now("comparing each app against Homebrew's recipe")
        findings.apps_behind = _behind_the_recipe(findings.reports)

        now("looking for app or package duplicates")
        findings.doubled = duplicate_installations.find()

        now("looking for running apps that are no longer installed")
        findings.stale = running_apps.find()

        now("looking for apps owned by another user")
        findings.foreign = installed_apps.owned_by_someone_else()

        now("asking Homebrew what it has doubts about")
        findings.flagged = _flagged_by_homebrew(findings.reports)
        findings.mounted = mounted_downloads.find()

    return findings


def _untracked_apps(decisions):
    """Returns untracked apps, minus the ones the user asked not to see again."""
    found = installed_apps.find_untracked()
    listed = [app for app in found if not decisions.is_ignored(app.file_stem)]
    return listed, len(found) - len(listed)


def _website_and_cask():
    """Returns a lookup for the cask that installs a given app."""
    return lambda app: _casks().for_app(app.path)


@functools.lru_cache(maxsize=1)
def _casks():
    """Returns Homebrew's list of casks, read once however many steps ask for it."""
    return casks.load()


def _behind_the_recipe(reports):
    """Returns the apps older than their cask."""
    recorded = brew.recorded_cask_versions()
    return behind_the_recipe.find(
        installed_apps.find_all(),
        _casks(),
        recorded,
        already_reported=_names_homebrew_reported(reports),
        recorded_at=brew.recorded_cask_times(recorded),
        would_install=brew.versions_homebrew_would_install(),
    )


def _names_homebrew_reported(reports):
    """Returns the names on Homebrew's own outdated list."""
    brew_report = next((r for r in reports if r.manager == "brew"), None)
    return {line.split()[0] for line in (brew_report.outdated_packages if brew_report else [])}


def _flagged_by_homebrew(reports):
    """Returns what Homebrew flagged that its outdated list does not already name."""
    installed = brew.installed_packages(managers.by_key("brew").environment())
    return flagged.find(installed, _names_homebrew_reported(reports))


def _exit_code(reports, managers_behind=()):
    """Returns non-zero only when a check could not run, never for outdated packages."""
    failed = [thing for thing in list(reports) + list(managers_behind) if thing.error_message]
    return 1 if failed else 0


def _clean_up(installed):
    """Clears out what the managers no longer need"""
    apply_updates.run_each_manager(
        [manager.key for manager in installed if manager.cleanup_args],
        "Cleaning up", lambda manager, status: manager.cleanup(status), dotted=True,
    )


class _Updates:
    """What the managers would update, asked again once a step of the first menu put something right."""

    def __init__(self, reports):
        self._reports = reports
        self._out_of_date = False

    def something_changed(self):
        self._out_of_date = True

    def reports(self):
        if self._out_of_date:
            with output.console.status("[dim]asking what is outdated[/]", spinner=report.SPINNER):
                self._reports = managers.check_what_is_outdated()
            self._out_of_date = False
        return self._reports

    def count(self):
        return report.count_outdated_packages(self.reports())


def _issues(findings, decisions):
    """Returns the kinds of trouble that turned up, as choices, in the order the report lists them."""
    findings.find_cask = findings.find_cask or _website_and_cask()
    by_group = {
        sections.HOMEBREW_CANNOT_UPDATE: _homebrew_problem(findings),
        sections.UNTRACKED: _untracked_problem(findings, decisions),
        sections.OWNED_BY_ANOTHER_USER: _take_over_problem(findings),
        sections.INSTALLED_TWICE: _copies_problem(findings),
        sections.NOT_RESTARTED: _restart_problem(findings),
    }
    listed = [section.title for section in sections.of(findings)]
    return [by_group[title] for title in listed if by_group.get(title) is not None]


def _homebrew_problem(findings):
    items = to_sort_out.blocking_brew_upgrade(findings)
    if not items:
        return None
    caskroom = brew.caskroom() if findings.apps_behind else None
    return _problem(
        lambda left: f"⎷ fix apps & packages Homebrew cannot update ({len(left)})",
        [_fix_for(item, caskroom) for item in items],
        resolve_by_command.ask_what_to_do,
        resolve_by_command.run_all,
    )


def _fix_for(item, caskroom):
    if isinstance(item, mounted_downloads.MountedImage):
        return homebrew_fixes.fix_for_image(item)
    if isinstance(item, flagged.Flagged):
        return homebrew_fixes.fix_for_flagged(item)
    return homebrew_fixes.fix_for_behind(item, caskroom)


def _untracked_problem(findings, decisions):
    """Returns the entry for the apps no manager tracks, or None when none is a problem."""
    troubled = to_sort_out.untracked_to_sort_out(findings)
    if not troubled:
        return None
    cask_for = findings.find_cask

    # Counted by what Homebrew has a recipe for, not by what the bulk step can
    # take: a handover that would be a downgrade is still one you can choose.
    def label(left):
        known = track_apps.known_to_homebrew([(app, cask_for(app)) for app in left])
        homebrew = f", {known} can be added to Homebrew" if known else ""
        return f"⎷ go through untracked apps ({len(left)}{homebrew})"

    def go_through_apps(apps, step):
        return track_apps.ask_what_to_do(apps, decisions, step, find_cask=cask_for, offered=findings.offered)

    def adopt_every_app_we_can(apps, step):
        return track_apps.adopt_all([(app, cask_for(app)) for app in apps], step)

    return _problem(label, troubled, go_through_apps, adopt_every_app_we_can)


def _take_over_problem(findings):
    if not findings.foreign:
        return None
    return _problem(
        lambda left: f"⎷ take over apps owned by another user ({len(left)})",
        [_take_over(path) for path in findings.foreign],
        resolve_by_command.ask_what_to_do,
        resolve_by_command.run_all,
    )


def _take_over(path):
    """Returns the fix that makes an app yours, so its updates can replace it."""
    return resolve_by_command.Fix(
        path.name, "belongs to another user",
        resolve_by_command.Option("", ("sudo", "chown", "-R", getpass.getuser(), str(path)), "taken over"),
    )


def _copies_problem(findings):
    if not findings.doubled:
        return None
    return _problem(
        lambda left: f"⎷ uninstall the unused {'copy' if len(left) == 1 else 'copies'} ({len(left)})",
        findings.doubled,
        resolve_duplicates.ask_what_to_do,
        resolve_duplicates.remove_shadowed,
    )


def _restart_problem(findings):
    if not findings.stale:
        return None
    return _problem(
        lambda left: f"⎷ restart updated apps ({len(left)})",
        findings.stale,
        restart_apps.ask_what_to_do,
        _restart_every_app,
    )


def _problem(label_for, things, walk_through, fix_all):
    """Returns one entry in the menu, with the things it is about tied to it.

    Each step returns what it dealt with, and that leaves the entry.
    """
    # Its own list, as the run's findings are read again after the menu.
    things = list(things)

    def dealing_with(step_through):
        def run(step):
            dealt_with = step_through(things, step)
            things[:] = [thing for thing in things if not any(thing is done for done in dealt_with)]
            return len(dealt_with)

        return run

    def refresh(problem):
        problem.label = label_for(things)
        return bool(things)

    return resolve_issues.Problem(
        label_for(things), dealing_with(walk_through), dealing_with(fix_all), refresh
    )


def _restart_every_app(apps, step):
    per_item = step.inside()
    restarted = []
    for app in apps:
        taken, message = restart_apps.restart(app)
        per_item.print_indented(f"{app.display_name}: {message}")
        if taken:
            restarted.append(app)
    return restarted


def _offer_to_restart_what_the_updates_replaced(already_offered=()):
    offered = {app.bundle for app in already_offered}
    replaced = [app for app in running_apps.find() if app.bundle not in offered]
    restart_apps.ask_after_the_update(replaced)
