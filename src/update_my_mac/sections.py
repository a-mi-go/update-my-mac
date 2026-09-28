"""What the run found, sorted by how much of your attention it deserves.

The checks are named after what they look at, which is no help when you are
reading the result. A section is named after what you would do about it, and
how loud it is says what happens if you do nothing.
"""

from dataclasses import dataclass, field

from update_my_mac import adopt_apps, app_updaters, appcast, versions

# What ignoring it costs. Critical is not "you have updates", it is "nothing
# will tell you about this again": Homebrew holding a version it never
# installed, a feed that has stopped answering, a check that could not run.
CRITICAL, WARNING, INFO = "critical", "warning", "info"


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
    # Usually one per row, but a doubled command takes a row for each copy.
    count: int = 0

    def __post_init__(self):
        self.count = self.count or len(self.rows)


@dataclass
class Findings:
    """Everything one run turned up, before anyone decides how to show it."""

    manager_updates: list = field(default_factory=list)
    reports: list = field(default_factory=list)
    untracked: list = field(default_factory=list)
    offered: dict = field(default_factory=dict)
    left_alone: int = 0
    doubled: list = field(default_factory=list)
    behind: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    foreign: list = field(default_factory=list)
    find_cask: object = None
    any_manager_installed: bool = True


def of(findings):
    """The sections worth printing, loudest first."""
    built = (
        _checks_that_failed(findings)
        + _wrongly_recorded(findings)
        + _feeds_gone_quiet(findings)
        + _owned_by_someone_else(findings)
        + _homebrew(findings)
        + _other_managers(findings)
        + _managers_themselves(findings)
        + _installed_twice(findings)
        + _not_restarted(findings)
        + _untracked_apps(findings)
    )
    return [section for section in built if section.rows]


def clean_managers(findings):
    """The managers that were asked and had nothing to report.

    Worth naming: silence about a manager reads as "not checked" rather than
    "nothing to do", and which of them ran is the whole point of a check.
    """
    return [
        report.label
        for report in findings.reports
        if not report.error_message and not report.outdated_packages
    ]


def counts(sections):
    """How many findings need you, and how many can wait."""
    needs_you = sum(s.count for s in sections if s.level in (CRITICAL, WARNING))
    can_wait = sum(s.count for s in sections if s.level == INFO)
    return needs_you, can_wait


def _split(change):
    """A manager's "1.2.3 → 1.2.4" as it should be shown."""
    return change.strip()


def _checks_that_failed(findings):
    """A manager that could not answer, named once however it failed.

    A manager can fail both the question about itself and the question about
    its packages, and hearing that twice says nothing more than hearing it
    once.
    """
    failed = {}
    for thing in list(findings.manager_updates) + list(findings.reports):
        if thing.error_message:
            failed.setdefault(thing.label, thing.error_message)
    rows = [Row(label, "", f"check failed: {message}") for label, message in failed.items()]
    return [Section(CRITICAL, "A check could not run", "this report is incomplete", rows)]


def _wrongly_recorded(findings):
    rows = [
        Row(item.app.name, item.version_change(), "needs a reinstall")
        for item in findings.behind
        if item.wrongly_recorded
    ]
    return [
        Section(
            CRITICAL,
            "Homebrew recorded a version it never installed",
            "no upgrade will touch these",
            rows,
        )
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


def _homebrew(findings):
    """What brew outdated says, and what it overlooks, in one place."""
    report = next((r for r in findings.reports if r.manager == "brew"), None)
    rows = []
    if report and not report.error_message:
        rows += [_package_row(package) for package in report.outdated_packages]
    rows += [
        Row(item.app.name, item.version_change(), "needs --greedy")
        for item in findings.behind
        if not item.wrongly_recorded
    ]
    note = "what it reports, and what it overlooks" if findings.behind else ""
    section = Section(WARNING, "Homebrew", note, rows)
    if report and report.ignored_taps:
        named = ", ".join(report.ignored_taps)
        section.rows.append(Row("", "", f"nothing from {named} was checked"))
    return [section]


def _other_managers(findings):
    """One section per manager, so a name says who would do the upgrading."""
    built = []
    for report in findings.reports:
        if report.manager == "brew" or report.error_message:
            continue
        rows = [_package_row(package) for package in report.outdated_packages]
        built.append(Section(WARNING, report.label, "one menu answer away", rows))
    return built


def _package_row(package):
    name, _, change = package.partition("  ")
    return Row(name, _split(change))


def _managers_themselves(findings):
    rows = [
        Row(update.label, "", update.description or "can be refreshed")
        for update in findings.manager_updates
        if not update.error_message
    ]
    return [
        Section(WARNING, "The package managers themselves",
                "worth doing before the rest", rows)
    ]


def _installed_twice(findings):
    rows = []
    for duplicate in findings.doubled:
        rows.append(Row(duplicate.command, duplicate.winner.describe(), "runs now"))
        rows += [Row("", copy.describe(), "never used") for copy in duplicate.shadowed]
    return [
        Section(WARNING, "Installed twice", "PATH picks the winner", rows,
                count=len(findings.doubled))
    ]


def _not_restarted(findings):
    rows = [Row(app.name, app.version, app.comment()) for app in findings.stale]
    return [
        Section(WARNING, "Updated but not restarted",
                "still running the old version", rows)
    ]


def _untracked_apps(findings):
    """The apps no manager tracks, split by whether anything watches them.

    An updater that is switched off is a different situation from no updater
    at all: one of them can be turned back on.
    """
    unattended, switched_off, unclear, self_updating = app_updaters.group_by_status(
        _undecided(findings)
    )
    return [
        Section(INFO, "They look after themselves", "nothing to do",
                _app_rows(self_updating, findings)),
        Section(INFO, "Their updater is switched off", "turning it on would keep them current",
                _app_rows(switched_off, findings)),
        Section(INFO, "They have an updater, and nothing says whether it runs",
                "it may never have run", _app_rows(unclear, findings)),
        Section(INFO, "Nobody checks these", "no manager, no updater",
                _app_rows(unattended, findings)),
    ]


def _app_rows(apps, findings):
    return [Row(app.name, _available(app, findings), _about(app, findings)) for app in apps]


def _about(app, findings):
    """What is worth saying next to an untracked app."""
    if app.updater.kind != app_updaters.NONE:
        return app.updater.describe()
    cask = findings.find_cask(app) if findings.find_cask else None
    if not cask:
        return ""
    if cask.installs_a_package:
        return f"Homebrew knows it as {cask.token}, as an installer"
    return f"Homebrew has {cask.token}"


def _undecided(findings):
    """Untracked apps, minus the ones already named in a louder section."""
    return [
        app for app in findings.untracked
        if not appcast.answer_for(app, findings.offered).error
    ]


def _available(app, findings):
    """The installed version, and the newer one on offer for it."""
    answer = appcast.answer_for(app, findings.offered)
    if appcast.offers_newer(app, answer):
        return f"{app.version} → {answer.version}"

    cask = findings.find_cask(app) if findings.find_cask else None
    if cask and versions.is_newer(cask.version, than=app.version):
        return f"{app.version} → {cask.version}"
    return app.version
