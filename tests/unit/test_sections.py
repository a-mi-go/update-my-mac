"""Sorting what a run found by how much attention it deserves."""

from pathlib import Path

from update_my_mac.checks import Findings
from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.managers.homebrew import behind_the_recipe
from update_my_mac.checks import to_sort_out
from update_my_mac.managers.homebrew import flagged
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


FIX = sections.HOMEBREW_CANNOT_UPDATE
UNTRACKED = sections.UNTRACKED


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


def test_apps_behind_the_recipe_are_not_counted_with_what_homebrew_upgrades_by_itself():
    found = sections.of(Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])],
        apps_behind=[behind()],
    ))

    assert [row.name for row in find("Homebrew", found).rows] == ["git"]
    assert [(row.name, row.note) for row in find(FIX, found).rows] == [("BetterDisplay", "needs --greedy")]


def test_a_version_homebrew_never_installed_makes_its_group_loud():
    found = sections.of(Findings(apps_behind=[behind(recorded="5.0.6")]))

    fix = find(FIX, found)
    assert fix.level == sections.CRITICAL
    assert fix.rows[0].note == "version recorded wrongly"
    assert "Homebrew" not in titles(found)


def test_an_app_with_a_false_record_says_what_its_own_updater_does():
    switched_off = sparkle(automatic=False)
    found = sections.of(Findings(apps_behind=[behind(recorded="5.0.6", updater=switched_off)]))

    assert find(FIX, found).rows[0].note == (
        "version recorded wrongly · auto checking off, last checked 2026-08-16"
    )


def test_an_app_only_left_behind_by_homebrew_is_not_loud():
    found = sections.of(Findings(apps_behind=[behind()]))

    assert find(FIX, found).level == sections.WARNING


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

    twice = find(sections.INSTALLED_TWICE, sections.of(Findings(doubled=[doubled])))

    assert twice.count == 1
    assert len(twice.rows) == 2


def test_an_app_whose_feed_is_quiet_makes_the_untracked_group_loud():
    feed = "https://x.test/appcast.xml"
    found = sections.of(Findings(
        untracked=[app("Air", "1.0", sparkle(feed=feed))],
        offered={feed: appcast.FeedAnswer(error="update source answers 403")},
    ))

    assert titles(found) == [UNTRACKED]
    assert find(UNTRACKED, found).level == sections.CRITICAL
    assert find(UNTRACKED, found).rows[0].note == "update source answers 403, last checked 2026-08-16"


def test_an_app_whose_feed_offers_more_than_it_installed_says_which_version_is_out():
    feed = "https://x.test/appcast.xml"
    found = sections.of(Findings(
        untracked=[app("Dockish", "1.1", sparkle(feed=feed))],
        offered={feed: appcast.FeedAnswer(version="1.2.5")},
    ))

    row = find(UNTRACKED, found).rows[0]
    assert row.version == "1.1 → 1.2.5"
    assert row.note == "1.2.5 is out"


def test_an_app_whose_feed_says_it_is_current_is_not_in_the_report():
    feed = "https://x.test/appcast.xml"
    found = sections.of(Findings(
        untracked=[app("Dockish", "1.2", sparkle(feed=feed))],
        offered={feed: appcast.FeedAnswer(version="1.2")},
    ))

    assert found == []


def test_the_recipe_that_could_take_an_app_over_is_not_named_when_the_app_is_behind_it():
    found = sections.of(Findings(
        untracked=[app("BetterDisplay", "5.0.5")],
        find_cask=lambda a: Cask("betterdisplay", "https://x.test/", "5.0.6"),
    ))

    row = find(UNTRACKED, found).rows[0]
    assert (row.version, row.note) == ("5.0.5 → 5.0.6", "Homebrew has 5.0.6")


def test_the_managers_that_answered_and_had_nothing_to_say_are_named():
    findings = Findings(reports=[
        ManagerReport("brew", "Homebrew", []),
        ManagerReport("npm", "npm (global)", ["eslint  9.0.0 → 9.12.0"]),
        ManagerReport("mas", "Mac App Store", [], "boom"),
    ])

    assert sections.clean_managers(findings) == ["Homebrew"]


def test_each_part_of_the_report_is_counted_apart():
    found = sections.of(Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  2.48.1 → 2.49.0"])],
        untracked=[app("Evoto", "7.1.5")],
        flagged=[flagged.Flagged("old", flagged.DEPRECATED, installed="1")],
    ))

    assert sections.count_findings(found) == (1, 1, 1)


def test_an_untracked_app_says_whether_its_updater_is_off_or_that_nothing_can_check_it(monkeypatch):
    monkeypatch.setattr(to_sort_out, "last_changed", lambda found: None)
    found = sections.of(Findings(untracked=[
        app("Off", "1.0", sparkle(automatic=False, feed="")),
        app("Nothing", "1.0"),
    ]))

    assert [(row.name, row.note) for row in find(UNTRACKED, found).rows] == [
        ("Off", "updater off, last checked 2026-08-16"),
        ("Nothing", "can't check for updates"),
    ]


def test_a_count_says_what_it_counts_where_the_title_does_not():
    found = sections.of(Findings(reports=[
        ManagerReport("mas", "Mac App Store", ["Xcode  14.0 → 14.1"]),
        ManagerReport("brew", "Homebrew", ["git  1 → 2", "jq  1 → 2"]),
    ]))

    assert find("Mac App Store", found).counted() == "1 update available"
    assert find("Homebrew", found).counted() == "2 updates available"


def test_a_title_that_already_names_the_thing_only_gets_the_number():
    found = sections.of(Findings(untracked=[app("Evoto", "7.1.5")]))

    assert find(UNTRACKED, found).counted() == "1"


def test_what_homebrew_holds_wrongly_is_put_right_with_the_rest_and_its_doubts_are_only_worth_knowing():
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

    fix = find(FIX, found)
    assert fix.level == sections.CRITICAL
    assert [row.cells() for row in fix.rows] == [
        ("tap/clerk", "64 → 3.4.1", "differs from the recipe"),
        ("google-trends", "1.0", "disabled, fails gatekeeper check since 2026-10-12"),
        ("charles.dmg", "", "download still attached"),
    ]
    assert find(sections.DEPRECATED, found).rows[0].cells() == ("old", "1", "still works, expect no more updates")


def test_an_app_owned_by_another_user_is_its_own_loud_group():
    found = sections.of(Findings(foreign=[Path("/Applications/Zoom.app")]))

    taken = find(sections.OWNED_BY_ANOTHER_USER, found)
    assert taken.level == sections.CRITICAL
    assert taken.rows[0].cells() == ("Zoom.app", "", "belongs to another user")


def test_what_needs_attention_comes_before_the_updates_and_the_info_and_within_a_part_the_loudest_first():
    found = sections.of(Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  1 → 2"])],
        untracked=[app("Evoto", "7.1.5")],
        foreign=[Path("/Applications/Zoom.app")],
        flagged=[flagged.Flagged("old", flagged.DEPRECATED, installed="1")],
    ))

    assert titles(found) == [
        sections.OWNED_BY_ANOTHER_USER, UNTRACKED, "Homebrew", sections.DEPRECATED,
    ]


def test_every_group_says_which_part_of_the_report_it_belongs_to():
    found = sections.of(Findings(
        reports=[ManagerReport("brew", "Homebrew", ["git  1 → 2"])],
        untracked=[app("Evoto", "7.1.5")],
        flagged=[flagged.Flagged("old", flagged.DEPRECATED, installed="1")],
    ))

    assert [(section.title, section.part) for section in found] == [
        (UNTRACKED, sections.NEED_ATTENTION),
        ("Homebrew", sections.UPDATES_AVAILABLE),
        (sections.DEPRECATED, sections.INFO_ONLY),
    ]


def test_an_app_that_another_app_keeps_current_is_not_in_the_report():
    shortcut = UpdaterStatus(app_updaters.HOST_APP, updated_by="Google Drive")

    assert sections.of(Findings(untracked=[app("Docs", "1.0", shortcut)])) == []


def test_a_homebrew_name_is_shown_without_the_tap_it_comes_from():
    found = sections.of(Findings(reports=[ManagerReport("brew", "Homebrew", [
        "anomalyco/tap/opencode  2.0.30 → 2.0.32",
    ])]))

    assert find("Homebrew", found).rows[0].name == "opencode"


def test_two_packages_whose_short_names_are_the_same_keep_their_full_names():
    found = sections.of(Findings(reports=[ManagerReport("brew", "Homebrew", [
        "one/tap/tool  1 → 2", "two/tap/tool  1 → 2",
    ])]))

    assert [row.name for row in find("Homebrew", found).rows] == ["one/tap/tool", "two/tap/tool"]


def test_a_scoped_npm_name_is_left_whole():
    found = sections.of(Findings(reports=[ManagerReport("npm", "npm (global)", ["@openai/codex  1 → 2"])]))

    assert find("npm (global)", found).rows[0].name == "@openai/codex"


def test_a_long_version_is_cut_after_the_first_part_that_differs():
    found = sections.of(Findings(reports=[ManagerReport("mas", "Mac App Store", [
        "ChatGPT  26.1013.31256 → 26.1021.31345",
        "Gemini  1.128.14.1166 → 1.131.4.1198",
    ])]))

    assert [row.version for row in find("Mac App Store", found).rows] == [
        "26.1013... → 26.1021...", "1.128... → 1.131...",
    ]


def test_a_long_version_that_differs_only_at_the_end_is_kept_whole():
    # Cut earlier, both sides would read the same.
    found = sections.of(Findings(reports=[ManagerReport("mas", "Mac App Store", [
        "ChatGPT  26.1013.31256 → 26.1013.40934",
    ])]))

    assert find("Mac App Store", found).rows[0].version == "26.1013.31256 → 26.1013.40934"


def test_a_reason_every_untracked_app_shares_is_said_once_over_them(monkeypatch):
    import time

    monkeypatch.setattr(
        to_sort_out, "last_changed",
        lambda found: time.mktime((2024, 4, 3, 0, 0, 0, 0, 0, -1)) if found.name == "Old" else None,
    )
    found = sections.of(Findings(untracked=[app("Old"), app("Unknown")]))

    untracked = find(UNTRACKED, found)
    assert untracked.note == to_sort_out.CANNOT_CHECK
    assert [(row.name, row.note) for row in untracked.rows] == [
        ("Old", "unchanged since 2024-04"), ("Unknown", ""),
    ]


def test_different_reasons_stay_on_their_rows(monkeypatch):
    monkeypatch.setattr(to_sort_out, "last_changed", lambda found: None)
    found = sections.of(Findings(untracked=[app("Off", "1.0", sparkle(automatic=False, feed="")), app("Unknown")]))

    untracked = find(UNTRACKED, found)
    assert untracked.note == ""
    assert [row.note for row in untracked.rows] == ["updater off, last checked 2026-08-16", to_sort_out.CANNOT_CHECK]

