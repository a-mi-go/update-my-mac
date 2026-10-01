"""Sorting what a run found by how much attention it deserves."""

from pathlib import Path

from update_my_mac import app_updaters, appcast, behind_the_recipe, sections
from update_my_mac.app_updaters import UpdaterStatus
from update_my_mac.cask_index import Cask
from update_my_mac.duplicate_commands import Copy, Duplicate
from update_my_mac.installed_apps import InstalledApp
from update_my_mac.package_managers import ManagerReport, ManagerUpdate


def app(name="TokenEater", version="1.0", updater=None):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"),
                        updater or UpdaterStatus())


def sparkle(automatic=True, silently=False, feed="https://x.test/appcast.xml"):
    return UpdaterStatus(app_updaters.SPARKLE, automatic, silently, "2026-08-16", feed)


def behind(name="BetterDisplay", app_version="5.0.5", cask_version="5.0.6", recorded="5.0.5"):
    return behind_the_recipe.Behind(
        app(name, app_version), Cask(name.lower(), "https://x.test/", cask_version), recorded
    )


def titles(found):
    return [section.title for section in found]


def find(title, found):
    return next(section for section in found if section.title == title)


def test_nothing_found_means_no_sections():
    assert sections.of(sections.Findings()) == []


def test_a_check_that_could_not_run_is_the_loudest_thing():
    found = sections.of(sections.Findings(
        reports=[ManagerReport("npm", "npm (global)", [], "ENOTFOUND")]
    ))

    assert titles(found) == ["A check could not run"]
    assert find("A check could not run", found).level == sections.CRITICAL


def test_a_manager_that_failed_both_questions_is_named_once():
    found = sections.of(sections.Findings(
        reports=[ManagerReport("npm", "npm (global)", [], "ENOTFOUND")],
        manager_updates=[ManagerUpdate("npm", "npm (global)", error_message="ENOTFOUND")],
    ))

    assert find("A check could not run", found).count == 1


def test_what_homebrew_reports_and_what_it_overlooks_share_one_section():
    found = sections.of(sections.Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])],
        behind=[behind()],
    ))

    homebrew = find("Homebrew", found)
    assert [row.name for row in homebrew.rows] == ["git", "BetterDisplay"]
    assert homebrew.rows[1].note == "needs --greedy"


def test_a_version_homebrew_never_installed_is_louder_than_an_upgrade():
    found = sections.of(sections.Findings(behind=[behind(recorded="5.0.6")]))

    written_down = find("Homebrew thinks these are current", found)
    assert written_down.level == sections.CRITICAL
    assert "Homebrew" not in titles(found)


def test_every_other_manager_gets_its_own_section():
    found = sections.of(sections.Findings(reports=[
        ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"]),
        ManagerReport("npm", "npm (global)", ["eslint  9.0.0 → 9.12.0"]),
    ]))

    assert titles(found) == ["Mac App Store", "npm (global)"]


def test_a_doubled_command_counts_once_although_it_takes_two_rows():
    doubled = Duplicate("codex", [
        Copy("Homebrew", Path("/a"), "codex", (), "0.157.0"),
        Copy("npm (global)", Path("/b"), "@openai/codex", (), "0.157.1"),
    ])

    twice = find("Installed twice", sections.of(sections.Findings(doubled=[doubled])))

    assert twice.count == 1
    assert len(twice.rows) == 2


def test_an_app_whose_feed_is_quiet_is_not_also_called_self_updating():
    feed = "https://x.test/appcast.xml"
    found = sections.of(sections.Findings(
        untracked=[app("Air", "1.0", sparkle(feed=feed))],
        offered={feed: appcast.FeedAnswer(error="its feed answers 403")},
    ))

    assert titles(found) == ["Their update feed has gone quiet"]


def test_an_app_that_looks_after_itself_is_only_information():
    feed = "https://x.test/appcast.xml"
    found = sections.of(sections.Findings(
        untracked=[app("Dockish", "1.1", sparkle(feed=feed))],
        offered={feed: appcast.FeedAnswer(version="1.2.5")},
    ))

    section = find("They look after themselves", found)
    assert section.level == sections.INFO
    assert section.rows[0].version == "1.1 → 1.2.5"


def test_an_app_with_a_recipe_says_which_one():
    found = sections.of(sections.Findings(
        untracked=[app("BetterDisplay", "5.0.6")],
        find_cask=lambda a: Cask("betterdisplay", "https://x.test/", "5.0.6"),
    ))

    assert find("Untracked apps", found).rows[0].note == "cask betterdisplay"


def test_the_managers_that_answered_and_had_nothing_to_say_are_named():
    findings = sections.Findings(reports=[
        ManagerReport("brew", "Homebrew", []),
        ManagerReport("npm", "npm (global)", ["eslint  9.0.0 → 9.12.0"]),
        ManagerReport("mas", "Mac App Store", [], "boom"),
    ])

    assert sections.clean_managers(findings) == ["Homebrew"]


def test_what_needs_you_is_counted_apart_from_what_can_wait():
    found = sections.of(sections.Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])],
        untracked=[app("Evoto", "7.1.5")],
    ))

    assert sections.counts(found) == (1, 1)


def test_an_updater_that_is_switched_off_is_not_the_same_as_none():
    found = sections.of(sections.Findings(untracked=[
        app("Off", "1.0", sparkle(automatic=False, feed="")),
        app("Nothing", "1.0"),
    ]))

    assert "Their updater is switched off" in titles(found)
    assert find("Their updater is switched off", found).rows[0].name == "Off"
    assert find("Untracked apps", found).rows[0].name == "Nothing"


def test_an_updater_nobody_answered_for_gets_its_own_line():
    found = sections.of(sections.Findings(untracked=[
        app("Unanswered", "1.0", sparkle(automatic=None, feed="")),
    ]))

    section = find("They have an updater, and nothing says whether it runs", found)
    assert section.rows[0].note == "never answered, last checked 2026-08-16"


def test_an_electron_app_is_not_counted_as_having_nothing():
    # Exodus ships Squirrel and keeps itself current, and was listed under
    # "nobody checks these" because only Sparkle was ever looked for.
    electron = UpdaterStatus(app_updaters.SQUIRREL)
    found = sections.of(sections.Findings(untracked=[app("Exodus", "24.33.4", electron)]))

    section = find("They have an updater, and nothing says whether it runs", found)
    assert section.rows[0].name == "Exodus"
    assert "nothing says if it runs" in section.rows[0].note


def test_a_count_says_what_it_counts_where_the_title_does_not():
    found = sections.of(sections.Findings(reports=[
        ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"]),
        ManagerReport("brew", "Homebrew", ["git  1 → 2", "jq  1 → 2"]),
    ]))

    assert find("Mac App Store", found).counted() == "1 update available"
    assert find("Homebrew", found).counted() == "2 updates available"


def test_a_title_that_already_names_the_thing_only_gets_the_number():
    found = sections.of(sections.Findings(untracked=[app("Evoto", "7.1.5")]))

    assert find("Untracked apps", found).counted() == "1"
