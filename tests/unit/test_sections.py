"""Sorting what a run found by how much attention it deserves."""

from pathlib import Path

from update_my_mac.checks import Findings
from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.managers.homebrew import behind_the_recipe
from update_my_mac.view import sections
from update_my_mac.checks.app_updaters import UpdaterStatus
from update_my_mac.managers.homebrew.casks import Cask
from update_my_mac.checks.duplicate_installations import Copy, Duplicate
from update_my_mac.checks.installed_apps import InstalledApp
from update_my_mac.managers import ManagerReport, ManagerUpdate


def app(name="TokenEater", version="1.0", updater=None):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"),
                        updater or UpdaterStatus())


def sparkle(automatic=True, silently=False, feed="https://x.test/appcast.xml"):
    return UpdaterStatus(app_updaters.SPARKLE, automatic, silently, "2026-08-16", feed)


def behind(name="BetterDisplay", app_version="5.0.5", cask_version="5.0.6", recorded="5.0.5",
           updater=None):
    return behind_the_recipe.Behind(
        app(name, app_version), Cask(name.lower(), "https://x.test/", cask_version), recorded,
        updater or UpdaterStatus(),
    )


def titles(found):
    return [section.title for section in found]


def find(title, found):
    return next(section for section in found if section.title == title)


def test_nothing_found_means_no_sections():
    assert sections.of(Findings()) == []


def test_a_check_that_could_not_run_is_the_loudest_thing():
    found = sections.of(Findings(
        reports=[ManagerReport("npm", "npm (global)", [], "ENOTFOUND")]
    ))

    assert titles(found) == ["Checks that could not run"]
    assert find("Checks that could not run", found).level == sections.CRITICAL


def test_a_manager_that_failed_both_questions_is_named_once():
    found = sections.of(Findings(
        reports=[ManagerReport("npm", "npm (global)", [], "ENOTFOUND")],
        managers_behind=[ManagerUpdate("npm", "npm (global)", error_message="ENOTFOUND")],
    ))

    assert find("Checks that could not run", found).count == 1


def test_homebrew_packages_and_apps_behind_the_recipe_share_one_section():
    found = sections.of(Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])],
        apps_behind=[behind()],
    ))

    homebrew = find("Homebrew", found)
    assert [row.name for row in homebrew.rows] == ["git", "BetterDisplay"]
    assert homebrew.rows[1].note == "needs --greedy"


def test_a_version_homebrew_never_installed_is_louder_than_an_upgrade():
    found = sections.of(Findings(apps_behind=[behind(recorded="5.0.6")]))

    written_down = find("Need action to update", found)
    assert written_down.level == sections.CRITICAL
    assert written_down.rows[0].note == ""
    assert "Homebrew" not in titles(found)


def test_an_app_with_a_false_record_says_what_its_own_updater_does():
    switched_off = sparkle(automatic=False)
    found = sections.of(Findings(apps_behind=[behind(recorded="5.0.6", updater=switched_off)]))

    written_down = find("Need action to update", found)
    assert written_down.rows[0].note == "auto checking off, last checked 2026-08-16"
    assert written_down.note == "fix issues or update manually"


def test_every_other_manager_gets_its_own_section():
    found = sections.of(Findings(reports=[
        ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"]),
        ManagerReport("npm", "npm (global)", ["eslint  9.0.0 → 9.12.0"]),
    ]))

    assert titles(found) == ["Mac App Store", "npm (global)"]


def test_a_doubled_command_counts_once_although_it_takes_two_rows():
    doubled = Duplicate("codex", [
        Copy("Homebrew", Path("/a"), "codex", (), "0.157.0"),
        Copy("npm (global)", Path("/b"), "@openai/codex", (), "0.157.1"),
    ])

    twice = find("Installed twice", sections.of(Findings(doubled=[doubled])))

    assert twice.count == 1
    assert len(twice.rows) == 2


def test_an_app_whose_feed_is_quiet_is_not_also_called_self_updating():
    feed = "https://x.test/appcast.xml"
    found = sections.of(Findings(
        untracked=[app("Air", "1.0", sparkle(feed=feed))],
        offered={feed: appcast.FeedAnswer(error="update source answers 403")},
    ))

    assert titles(found) == ["Update source not answering"]


def test_an_app_that_looks_after_itself_is_only_information():
    feed = "https://x.test/appcast.xml"
    found = sections.of(Findings(
        untracked=[app("Dockish", "1.1", sparkle(feed=feed))],
        offered={feed: appcast.FeedAnswer(version="1.2.5")},
    ))

    section = find("Apps that update themselves", found)
    assert section.level == sections.INFO
    assert section.rows[0].version == "1.1 → 1.2.5"


def test_an_app_with_a_recipe_says_which_one():
    found = sections.of(Findings(
        untracked=[app("BetterDisplay", "5.0.6")],
        find_cask=lambda a: Cask("betterdisplay", "https://x.test/", "5.0.6"),
    ))

    assert find("Untracked apps", found).rows[0].note == "cask betterdisplay"


def test_the_managers_that_answered_and_had_nothing_to_say_are_named():
    findings = Findings(reports=[
        ManagerReport("brew", "Homebrew", []),
        ManagerReport("npm", "npm (global)", ["eslint  9.0.0 → 9.12.0"]),
        ManagerReport("mas", "Mac App Store", [], "boom"),
    ])

    assert sections.clean_managers(findings) == ["Homebrew"]


def test_what_needs_you_is_counted_apart_from_what_can_wait():
    found = sections.of(Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])],
        untracked=[app("Evoto", "7.1.5")],
    ))

    assert sections.count_findings(found) == (1, 1)


def test_an_updater_that_is_switched_off_is_not_the_same_as_none():
    found = sections.of(Findings(untracked=[
        app("Off", "1.0", sparkle(automatic=False, feed="")),
        app("Nothing", "1.0"),
    ]))

    assert "Built-in updater switched off" in titles(found)
    assert find("Built-in updater switched off", found).rows[0].name == "Off"
    assert find("Untracked apps", found).rows[0].name == "Nothing"


def test_an_updater_nobody_answered_for_gets_its_own_line():
    found = sections.of(Findings(untracked=[
        app("Unanswered", "1.0", sparkle(automatic=None, feed="")),
    ]))

    section = find("Built-in updater, state unknown", found)
    assert section.rows[0].note == "last checked 2026-08-16"


def test_an_electron_app_is_not_counted_as_having_nothing():
    # Exodus ships Squirrel and keeps itself current, and was listed under
    # "nobody checks these" because only Sparkle was ever looked for.
    electron = UpdaterStatus(app_updaters.SQUIRREL)
    found = sections.of(Findings(untracked=[app("Exodus", "24.33.4", electron)]))

    section = find("Built-in updater, state unknown", found)
    assert section.rows[0].name == "Exodus"
    assert "Untracked apps" not in titles(found)


def test_a_count_says_what_it_counts_where_the_title_does_not():
    found = sections.of(Findings(reports=[
        ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"]),
        ManagerReport("brew", "Homebrew", ["git  1 → 2", "jq  1 → 2"]),
    ]))

    assert find("Mac App Store", found).counted() == "1 update available"
    assert find("Homebrew", found).counted() == "2 updates available"


def test_a_title_that_already_names_the_thing_only_gets_the_number():
    found = sections.of(Findings(untracked=[app("Evoto", "7.1.5")]))

    assert find("Untracked apps", found).counted() == "1"


def test_what_homebrew_has_doubts_about_is_split_by_how_loud_it_should_be():
    from update_my_mac.managers.homebrew import flagged, mounted_downloads

    found = sections.of(Findings(
        flagged=[
            flagged.Flagged("tap/clerk", flagged.DIFFERS, installed="64", available="3.4.1"),
            flagged.Flagged("google-trends", flagged.DISABLED, True, "1.0",
                            reason="fails gatekeeper check since 2026-10-12"),
            flagged.Flagged("old", flagged.DEPRECATED, installed="1"),
        ],
        mounted=[mounted_downloads.MountedImage(Path("/c/downloads/ab--charles.dmg"), "/dev/disk8")],
    ))

    assert find("Different from Homebrew's recipe", found).level == sections.CRITICAL
    assert find("Different from Homebrew's recipe", found).rows[0].cells() == (
        "tap/clerk", "64 → 3.4.1", "versions cannot be compared")
    assert find("Disabled in Homebrew", found).level == sections.WARNING
    assert find("Deprecated in Homebrew", found).level == sections.INFO
    assert find("Downloads still attached", found).rows[0].name == "charles.dmg"


def test_a_recipe_counting_its_own_way_offers_no_update_for_an_untracked_app():
    found = sections.of(Findings(
        untracked=[app("Safari Technology Preview", "27.0")],
        find_cask=lambda a: Cask("safari-technology-preview", "https://x.test/", "254,142-29069"),
    ))

    assert find("Untracked apps", found).rows[0].version == "27.0"


def test_the_same_numbers_under_an_ordinary_token_still_offer_the_update():
    found = sections.of(Findings(
        untracked=[app("Some App", "27.0")],
        find_cask=lambda a: Cask("some-app", "https://x.test/", "254"),
    ))

    assert find("Untracked apps", found).rows[0].version == "27.0 → 254"
