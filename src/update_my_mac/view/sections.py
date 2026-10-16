"""What the run found, sorted by how much of your attention it deserves.

The checks are named after what they look at, which is no help when you are
reading the result. A section is named after what you would do about it, and
how loud it is says what happens if you do nothing.
"""

from dataclasses import dataclass

from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.checks import versions
from update_my_mac.managers.homebrew import flagged

# Critical: a crooked state that should be taken care of, such as Homebrew
#   holding a version it never installed, a feed that has stopped answering,
#   or a check that could not run.
# Warning: updates might be hindered. Worth a look in the "sort things out"
#   menu.
# Info: updates are available, or something could be made better.
CRITICAL, WARNING, INFO = "critical", "warning", "info"

UPDATES = "update available"

STILL_ATTACHED = "still attached, the next upgrade cannot attach it again"
NOT_RESTARTED = "Updated but the old version is still running"


def _pluralised(noun, count):
    return noun if count == 1 else f"{noun}s"


@dataclass
class Row:
    name: str
    version: str = ""
    note: str = ""

    def cells(self):
        return (self.name, self.version, self.note)


@dataclass
class Section:
    level: str
    title: str
    note: str
    rows: list
    count: int = 0
    # What the number counts, left empty where the title already says it.
    counted_as: str = ""

    def __post_init__(self):
        self.count = self.count or len(self.rows)

    def counted(self):
        """Returns the number and what it counts, singular or plural to match."""
        if not self.counted_as:
            return str(self.count)
        noun, _, rest = self.counted_as.partition(" ")
        return f"{self.count} {_pluralised(noun, self.count)} {rest}".rstrip()


def of(findings):
    """Returns the sections that have rows, loudest first."""
    built = (
        _checks_that_failed(findings)
        + _false_version_recorded(findings)
        + _feeds_gone_quiet(findings)
        + _owned_by_someone_else(findings)
        + _flagged_by_homebrew(findings)
        + _mounted_downloads(findings)
        + _homebrew_outdated(findings)
        + _outdated_per_manager(findings)
        + _managers_needing_an_update(findings)
        + _installed_twice(findings)
        + _not_restarted(findings)
        + _untracked_apps(findings)
    )
    return [section for section in built if section.rows]


def clean_managers(findings):
    """Returns the managers that were asked and had nothing to report."""
    return [
        report.label
        for report in findings.reports
        if not report.error_message and not report.outdated_packages
    ]


def count_findings(sections):
    """Returns how many findings need your attention, and how many can wait."""
    needs_you = sum(s.count for s in sections if s.level in (CRITICAL, WARNING))
    can_wait = sum(s.count for s in sections if s.level == INFO)
    return needs_you, can_wait


def _version_change(change):
    """Returns a manager's "1.2.3 → 1.2.4" as it should be shown."""
    return versions.change_without_builds(change)


def _checks_that_failed(findings):
    """Returns a section naming each manager that could not answer, once."""
    # Each manager is asked twice, about itself and about its packages.
    failed = {}
    for thing in list(findings.managers_behind) + list(findings.reports):
        if thing.error_message:
            failed.setdefault(thing.label, thing.error_message)
    rows = [Row(label, "", f"check failed: {message}") for label, message in failed.items()]
    return [Section(CRITICAL, "Checks that could not run", "results below are incomplete", rows)]


def _false_version_recorded(findings):
    rows = [
        Row(item.app.name, item.version_change(), _own_updater_note(item.updater))
        for item in findings.apps_behind
        if item.false_version_recorded
    ]
    return [
        Section(CRITICAL, "Need action to update",
                "fix issues or update manually", rows)
    ]


def _own_updater_note(updater):
    """Returns what the app's own updater is doing, where it has one."""
    if updater.kind == app_updaters.NONE:
        return ""
    return updater.update_method_note()


def _feeds_gone_quiet(findings):
    rows = [
        Row(app.name, app.version, appcast.answer_for(app, findings.offered).error)
        for app in findings.untracked
        if appcast.answer_for(app, findings.offered).error
    ]
    return [
        Section(CRITICAL, "Update source not answering", "update manually", rows)
    ]


def _owned_by_someone_else(findings):
    rows = [Row(path.name, "", "chown it to yourself first") for path in findings.foreign]
    return [
        Section(CRITICAL, "Owned by another user", "take ownership before updating", rows)
    ]


def doubt_about(item):
    """Returns what Homebrew holds against a package it flagged."""
    return "versions cannot be compared" if item.kind == flagged.DIFFERS else item.reason


def download_name(image):
    # Homebrew prefixes the file name with a hash and two dashes.
    return image.path.name.split("--", 1)[-1]


def _flagged_by_homebrew(findings):
    """Returns what Homebrew has doubts about, one section per kind of doubt."""
    def rows(kind):
        return [
            Row(item.name, versions.change_without_builds(f"{item.installed} → {item.available}")
                if item.available else item.installed, doubt_about(item))
            for item in findings.flagged
            if item.kind == kind
        ]

    return [
        Section(CRITICAL, "Different from Homebrew's recipe", "reinstall to match it",
                rows(flagged.DIFFERS)),
        Section(WARNING, "Disabled in Homebrew", "never updated, uninstall or replace",
                rows(flagged.DISABLED)),
        Section(INFO, "Deprecated in Homebrew", "still works, expect no more updates",
                rows(flagged.DEPRECATED)),
    ]


def _mounted_downloads(findings):
    rows = [Row(download_name(image), "", STILL_ATTACHED) for image in findings.mounted]
    return [
        Section(WARNING, "Downloads still attached", "detach them so upgrades can run", rows)
    ]


def _homebrew_outdated(findings):
    """Returns Homebrew's outdated packages, plus the apps behind their recipe."""
    report = next((r for r in findings.reports if r.manager == "brew"), None)
    rows = []
    if report and not report.error_message:
        rows += [_package_row(package) for package in report.outdated_packages]
    rows += [
        Row(item.app.name, item.version_change(), "needs --greedy")
        for item in findings.apps_behind
        if not item.false_version_recorded
    ]
    section = Section(WARNING, "Homebrew", "update from the menu below", rows,
                      counted_as=UPDATES)
    if report and report.ignored_taps:
        named = ", ".join(report.ignored_taps)
        section.rows.append(Row("", "", f"nothing from {named} was checked"))
    return [section]


def _outdated_per_manager(findings):
    """Returns one section per manager other than Homebrew, named after the manager."""
    built = []
    for report in findings.reports:
        if report.manager == "brew" or report.error_message:
            continue
        rows = [_package_row(package) for package in report.outdated_packages]
        built.append(Section(WARNING, report.label, "update from the menu below", rows,
                             counted_as=UPDATES))
    return built


def _package_row(package):
    name, _, change = package.partition("  ")
    return Row(name, _version_change(change))


def _managers_needing_an_update(findings):
    rows = [
        Row(update.label, "", update.description or "can be refreshed")
        for update in findings.managers_behind
        if not update.error_message
    ]
    return [
        Section(WARNING, "The package managers themselves", "update these first", rows, counted_as=UPDATES)
    ]


def _installed_twice(findings):
    rows = []
    for duplicate in findings.doubled:
        rows.append(Row(duplicate.command, duplicate.winner.describe(), "runs now"))
        rows += [Row("", copy.describe(), "never used") for copy in duplicate.shadowed]
    return [
        Section(WARNING, "Installed twice", "uninstall the unused copy", rows,
                # One row per copy, so the count cannot come from the rows.
                count=len(findings.doubled), counted_as="command")
    ]


def _not_restarted(findings):
    rows = [Row(app.name, app.version, app.comment()) for app in findings.stale]
    return [
        Section(WARNING, NOT_RESTARTED, "restart the app", rows)
    ]


def _untracked_apps(findings):
    """Returns sections for the apps no manager tracks, split by what watches them."""
    unattended, switched_off, unclear, self_updating = app_updaters.group_by_status(
        _untracked_not_already_listed(findings)
    )
    return [
        Section(INFO, "Apps that update themselves", "nothing to do",
                _rows_for_apps(self_updating, findings)),
        Section(INFO, "Built-in updater switched off", "update manually or activate autoupdate",
                _rows_for_apps(switched_off, findings)),
        Section(INFO, "Built-in updater, state unknown", "check for updates in the app", _rows_for_apps(unclear, findings)),
        # Untracked, not unknown: a recipe can exist for a copy Homebrew
        # never installed.
        Section(INFO, "Untracked apps", "no package manager, no built-in updater found",
                _rows_for_apps(unattended, findings)),
    ]


def _rows_for_apps(apps, findings):
    return [
        Row(app.name, _updates_available(app, findings), _what_is_known_about(app, findings))
        for app in apps
    ]


def _what_is_known_about(app, findings):
    """Returns when the updater last checked, or the recipe that could take it over."""
    if app.updater.kind != app_updaters.NONE:
        # The section these rows sit under already names the updater's state.
        return app.updater.history_note()
    cask = findings.find_cask(app) if findings.find_cask else None
    if not cask:
        return ""
    # Only that a recipe exists; what handing it over would mean differs.
    return f"cask {cask.token}"


def _untracked_not_already_listed(findings):
    """Returns untracked apps, minus the ones already named in a louder section."""
    return [
        app for app in findings.untracked
        if not appcast.answer_for(app, findings.offered).error
    ]


def _updates_available(app, findings):
    """Returns the installed version, and the newer one on offer for it."""
    answer = appcast.answer_for(app, findings.offered)
    shown = versions.without_build(app.version)
    if appcast.offers_newer(app, answer):
        return f"{shown} → {versions.without_build(answer.version)}"

    cask = findings.find_cask(app) if findings.find_cask else None
    if cask and not versions.any_version_matches(app.versions_named(), cask.version):
        if versions.is_newer(cask.version, than=app.version):
            return f"{shown} → {versions.without_build(cask.version)}"
    return shown
