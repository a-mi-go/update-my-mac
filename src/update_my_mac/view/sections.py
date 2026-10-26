"""What the run found, sorted by how much of your attention it deserves.

The checks are named after what they look at, which is no help when you are
reading the result. A section is named after what you would do about it, and
how loud it is says what happens if you do nothing.
"""

from dataclasses import dataclass

from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.checks import to_sort_out
from update_my_mac.checks import versions
from update_my_mac.managers.homebrew import flagged
from update_my_mac.managers.homebrew import mounted_downloads

# Critical: a crooked state that should be taken care of, such as Homebrew
#   holding a version it never installed, a feed that has stopped answering,
#   or a check that could not run.
# Warning: needs a decision, or updates are waiting.
# Info: nothing to do, only worth knowing.
CRITICAL, WARNING, INFO = "critical", "warning", "info"
LOUDEST_FIRST = (CRITICAL, WARNING, INFO)

# The three parts of the report, in the order it shows them.
NEED_ATTENTION, UPDATES_AVAILABLE, INFO_ONLY = "Need attention", "Updates available", "Info"
PARTS = (NEED_ATTENTION, UPDATES_AVAILABLE, INFO_ONLY)

# The groups each option of the first menu deals with, one each.
HOMEBREW_CANNOT_UPDATE = "Homebrew cannot update these"
UNTRACKED = "Untracked apps"
OWNED_BY_ANOTHER_USER = "Owned by another user"
INSTALLED_TWICE = "Installed twice"
DEPRECATED = "Deprecated in Homebrew"

UPDATES = "update available"
# A version longer than this is cut, but never to fewer parts than the second.
LONG_VERSION = 10
MIN_VERSION_PARTS = 2

STILL_ATTACHED = "still attached, the next upgrade cannot attach it again"
NOT_RESTARTED = "Updated but the old version is still running"


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
    part: str = NEED_ATTENTION

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
        + _homebrew_cannot_update(findings)
        + _untracked_to_sort_out(findings)
        + _owned_by_someone_else(findings)
        + _installed_twice(findings)
        + _not_restarted(findings)
        + _homebrew_outdated(findings)
        + _outdated_per_manager(findings)
        + _managers_needing_an_update(findings)
        + _only_worth_knowing(findings)
    )
    shown = [section for section in built if section.rows]
    return sorted(shown, key=lambda section: (PARTS.index(section.part), LOUDEST_FIRST.index(section.level)))


def clean_managers(findings):
    """Returns the managers that were asked and had nothing to report."""
    return [
        report.label
        for report in findings.reports
        if not report.error_message and not report.outdated_packages
    ]


def count_findings(sections):
    """Returns how many findings each part of the report holds, in the order of PARTS."""
    return tuple(sum(s.count for s in sections if s.part == part) for part in PARTS)


def doubt_about(item):
    """Returns what Homebrew holds against a package it flagged."""
    return "versions cannot be compared" if item.kind == flagged.DIFFERS else item.reason


def download_name(image):
    # Homebrew prefixes the file name with a hash and two dashes.
    return image.path.name.split("--", 1)[-1]


def _checks_that_failed(findings):
    """Returns a section naming each manager that could not answer, once."""
    # Each manager is asked twice, about itself and about its packages.
    failed = {}
    for thing in list(findings.managers_behind) + list(findings.reports):
        if thing.error_message:
            failed.setdefault(thing.label, thing.error_message)
    rows = [Row(label, "", f"check failed: {message}") for label, message in failed.items()]
    return [Section(CRITICAL, "Checks that could not run", "results below are incomplete", rows)]


def _own_updater_note(updater):
    """Returns what the app's own updater is doing, where it has one."""
    if updater.kind == app_updaters.NONE:
        return ""
    return updater.update_method_note()


def _homebrew_outdated(findings):
    """Returns the packages Homebrew's own upgrade will update."""
    report = next((r for r in findings.reports if r.manager == "brew"), None)
    rows = []
    if report and not report.error_message:
        rows += _package_rows(report.outdated_packages)
    section = Section(WARNING, "Homebrew", "update from the menu below", rows,
                      counted_as=UPDATES, part=UPDATES_AVAILABLE)
    if report and report.ignored_taps:
        named = ", ".join(report.ignored_taps)
        section.rows.append(Row("", "", f"nothing from {named} was checked"))
    return [section]


def _package_rows(packages):
    """Returns a manager's "name  1.2.3 → 1.2.4" lines as rows, shortened where that loses nothing."""
    split = [package.partition("  ") for package in packages]
    short = [_short_name(name) for name, _, _ in split]
    return [
        # A short name two packages share would hide which one is meant.
        Row(brief if short.count(brief) == 1 else name, _shortened(versions.change_without_builds(change)))
        for (name, _, change), brief in zip(split, short)
    ]


def _short_name(name):
    return name.rsplit("/", 1)[-1] if name.count("/") >= 2 else name


def _shortened(change):
    """Returns "old → new" with long versions cut after the first part that differs."""
    old, arrow, new = change.partition(" → ")
    if not arrow or max(len(old), len(new)) <= LONG_VERSION:
        return change
    before, after = old.split("."), new.split(".")
    differs = next((at for at, (a, b) in enumerate(zip(before, after)) if a != b), len(before))
    kept = max(differs + 1, MIN_VERSION_PARTS)

    def cut(parts):
        return ".".join(parts[:kept]) + ("..." if len(parts) > kept else "")

    return f"{cut(before)} → {cut(after)}"


def _outdated_per_manager(findings):
    """Returns one section per manager other than Homebrew, named after the manager."""
    built = []
    for report in findings.reports:
        if report.manager == "brew" or report.error_message:
            continue
        rows = _package_rows(report.outdated_packages)
        built.append(Section(WARNING, report.label, "update from the menu below", rows,
                             counted_as=UPDATES, part=UPDATES_AVAILABLE))
    return built


def _managers_needing_an_update(findings):
    rows = [
        Row(update.label, "", update.description or "can be refreshed")
        for update in findings.managers_behind
        if not update.error_message
    ]
    return [
        Section(WARNING, "The package managers themselves", "update these first", rows,
                counted_as=UPDATES, part=UPDATES_AVAILABLE)
    ]


def _installed_twice(findings):
    rows = []
    for duplicate in findings.doubled:
        rows.append(Row(duplicate.command, duplicate.winner.describe(), "runs now"))
        rows += [Row("", copy.describe(), "never used") for copy in duplicate.shadowed]
    return [
        Section(WARNING, INSTALLED_TWICE, "", rows,
                # One row per copy, so the count cannot come from the rows.
                count=len(findings.doubled), counted_as="command")
    ]


def _not_restarted(findings):
    rows = [Row(app.name, app.version, app.comment()) for app in findings.stale]
    return [
        Section(WARNING, NOT_RESTARTED, "", rows)
    ]


def _homebrew_cannot_update(findings):
    items = to_sort_out.homebrew_cannot_update(findings)
    wrong = any(_is_wrong(item) for item in items)
    rows = [_row_for_homebrew_trouble(item) for item in items]
    return [Section(CRITICAL if wrong else WARNING, HOMEBREW_CANNOT_UPDATE, "", rows)]


def _is_wrong(item):
    """Returns whether Homebrew holds something it should not, not only something old."""
    if isinstance(item, flagged.Flagged):
        return item.kind == flagged.DIFFERS
    if isinstance(item, mounted_downloads.MountedImage):
        return False
    return item.false_version_recorded


def _row_for_homebrew_trouble(item):
    if isinstance(item, mounted_downloads.MountedImage):
        return Row(download_name(item), "", "download still attached")
    if isinstance(item, flagged.Flagged):
        change = versions.change_without_builds(f"{item.installed} → {item.available}") \
            if item.available else item.installed
        return Row(item.name, change, _what_homebrew_holds_against(item))
    if not item.false_version_recorded:
        return Row(item.app.name, item.version_change(), "needs --greedy")
    own = _own_updater_note(item.updater)
    return Row(item.app.name, item.version_change(),
               "version recorded wrongly" + (f" · {own}" if own else ""))


def _what_homebrew_holds_against(item):
    if item.kind == flagged.DIFFERS:
        return "differs from the recipe"
    return f"disabled, {item.reason}" if item.reason else "disabled"


def _untracked_to_sort_out(findings):
    concerns = to_sort_out.untracked_concerns(findings)
    reasons = {concern.reason for _, concern in concerns}
    # One reason for several of them is said once, over the rows.
    shared = reasons.pop() if len(reasons) == 1 and len(concerns) > 1 else ""
    rows = [
        Row(app.name, _updates_available(app, findings), concern.detail if shared else concern.note)
        for app, concern in concerns
    ]
    urgent = any(concern.urgent for _, concern in concerns)
    return [Section(CRITICAL if urgent else WARNING, UNTRACKED, shared, rows)]


def _owned_by_someone_else(findings):
    rows = [Row(path.name, "", "belongs to another user") for path in findings.foreign]
    return [Section(CRITICAL, OWNED_BY_ANOTHER_USER, "", rows)]


def _only_worth_knowing(findings):
    deprecated = [
        Row(item.name, item.installed, item.reason or "still works, expect no more updates")
        for item in to_sort_out.only_worth_knowing(findings)
    ]
    return [Section(INFO, DEPRECATED, "", deprecated, part=INFO_ONLY)]


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


def _pluralised(noun, count):
    return noun if count == 1 else f"{noun}s"
