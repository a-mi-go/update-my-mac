"""What the run found, sorted by how much of your attention it deserves.

The checks are named after what they look at, which is no help when you are
reading the result. A section is named after what you would do about it, and
how loud it is says what happens if you do nothing.
"""

from dataclasses import dataclass, field

from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.checks import versions

# Critical: a crooked state that should be taken care of, such as Homebrew
#   holding a version it never installed, a feed that has stopped answering,
#   or a check that could not run.
# Warning: updates might be hindered. Worth a look in the "sort things out"
#   menu.
# Info: updates are available, or something could be made better.
CRITICAL, WARNING, INFO = "critical", "warning", "info"

UPDATES = "update available"


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


@dataclass
class Findings:
    """Everything one run turned up, before anyone decides how to show it."""

    managers_behind: list = field(default_factory=list)
    reports: list = field(default_factory=list)
    untracked: list = field(default_factory=list)
    offered: dict = field(default_factory=dict)
    left_alone: int = 0
    doubled: list = field(default_factory=list)
    apps_behind: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    foreign: list = field(default_factory=list)
    find_cask: object = None
    any_manager_installed: bool = True


def of(findings):
    """Returns the sections that have rows, loudest first."""
    built = (
        _checks_that_failed(findings)
        + _false_version_recorded(findings)
        + _feeds_gone_quiet(findings)
        + _owned_by_someone_else(findings)
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
    return change.strip()


def _checks_that_failed(findings):
    """Returns a section naming each manager that could not answer, once."""
    # Each manager is asked twice, about itself and about its packages.
    failed = {}
    for thing in list(findings.managers_behind) + list(findings.reports):
        if thing.error_message:
            failed.setdefault(thing.label, thing.error_message)
    rows = [Row(label, "", f"check failed: {message}") for label, message in failed.items()]
    return [Section(CRITICAL, "A check could not run", "this report is incomplete", rows)]


def _false_version_recorded(findings):
    rows = [
        Row(item.app.name, item.version_change())
        for item in findings.apps_behind
        if item.false_version_recorded
    ]
    return [
        Section(CRITICAL, "No upgrade will fetch these", "only a reinstall will", rows)
    ]


def _feeds_gone_quiet(findings):
    rows = [
        Row(app.name, app.version, appcast.answer_for(app, findings.offered).error)
        for app in findings.untracked
        if appcast.answer_for(app, findings.offered).error
    ]
    return [
        Section(CRITICAL, "Their update feed has gone quiet",
                "they cannot update themselves any more", rows)
    ]


def _owned_by_someone_else(findings):
    rows = [Row(path.name, "", "chown it to yourself first") for path in findings.foreign]
    return [
        Section(CRITICAL, "Owned by another user",
                "an upgrade would break halfway through", rows)
    ]


def _homebrew_outdated(findings):
    """Returns what brew outdated says, and what it overlooks."""
    report = next((r for r in findings.reports if r.manager == "brew"), None)
    rows = []
    if report and not report.error_message:
        rows += [_package_row(package) for package in report.outdated_packages]
    rows += [
        Row(item.app.name, item.version_change(), "needs --greedy")
        for item in findings.apps_behind
        if not item.false_version_recorded
    ]
    note = "what it reports, and what it overlooks" if findings.apps_behind else ""
    section = Section(WARNING, "Homebrew", note, rows, counted_as=UPDATES)
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
        built.append(Section(WARNING, report.label, "one menu answer away", rows,
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
        Section(WARNING, "The package managers themselves",
                "worth doing before the rest", rows, counted_as=UPDATES)
    ]


def _installed_twice(findings):
    rows = []
    for duplicate in findings.doubled:
        rows.append(Row(duplicate.command, duplicate.winner.describe(), "runs now"))
        rows += [Row("", copy.describe(), "never used") for copy in duplicate.shadowed]
    return [
        Section(WARNING, "Installed twice", "PATH picks the winner", rows,
                # One row per copy, so the count cannot come from the rows.
                count=len(findings.doubled), counted_as="command")
    ]


def _not_restarted(findings):
    rows = [Row(app.name, app.version, app.comment()) for app in findings.stale]
    return [
        Section(WARNING, "Updated but not restarted",
                "still running the old version", rows)
    ]


def _untracked_apps(findings):
    """Returns sections for the apps no manager tracks, split by what watches them."""
    unattended, switched_off, unclear, self_updating = app_updaters.group_by_status(
        _untracked_not_already_listed(findings)
    )
    return [
        Section(INFO, "They look after themselves", "nothing to do",
                _rows_for_apps(self_updating, findings)),
        Section(INFO, "Their updater is switched off", "turning it on would keep them current",
                _rows_for_apps(switched_off, findings)),
        Section(INFO, "They have an updater, and nothing says whether it runs",
                "it may never have run", _rows_for_apps(unclear, findings)),
        # Untracked, not unknown: a recipe can exist for a copy Homebrew
        # never installed.
        Section(INFO, "Untracked apps", "nothing says they update themselves",
                _rows_for_apps(unattended, findings)),
    ]


def _rows_for_apps(apps, findings):
    return [
        Row(app.name, _updates_available(app, findings), _what_is_known_about(app, findings))
        for app in apps
    ]


def _what_is_known_about(app, findings):
    """Returns what updates this app, or the recipe that could take it over."""
    if app.updater.kind != app_updaters.NONE:
        return app.updater.update_method_note()
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
    if appcast.offers_newer(app, answer):
        return f"{app.version} → {answer.version}"

    cask = findings.find_cask(app) if findings.find_cask else None
    if cask and not versions.any_version_matches(app.versions_named(), cask.version):
        if versions.is_newer(cask.version, than=app.version):
            return f"{app.version} → {cask.version}"
    return app.version
