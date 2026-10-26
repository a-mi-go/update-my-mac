"""Which untracked apps need a decision, and what the evidence for that is."""

import os
import time
from pathlib import Path

from update_my_mac.checks import Findings
from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.checks import to_sort_out
from update_my_mac.checks.app_updaters import UpdaterStatus
from update_my_mac.checks.installed_apps import InstalledApp
from update_my_mac.managers.homebrew import behind_the_recipe
from update_my_mac.managers.homebrew.casks import Cask

FEED = "https://x.test/appcast.xml"


def app(name="Thing", version="1.0", updater=None, bundle_id="", build=""):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"), updater or UpdaterStatus(),
                        bundle_id, build)


def sparkle(automatic=True, feed=FEED):
    return UpdaterStatus(app_updaters.SPARKLE, automatic, False, "2026-08-16", feed)


def concern(found, answer=None, cask=None, **findings):
    offered = {FEED: answer} if answer else {}
    everything = Findings(untracked=[found], offered=offered, find_cask=lambda one: cask, **findings)
    return to_sort_out.concern_about(found, everything)


def test_an_app_whose_feed_says_it_is_current_is_not_a_problem():
    assert concern(app(updater=sparkle()), appcast.FeedAnswer(version="1.0")) is None


def test_an_app_whose_feed_offers_more_than_it_installed_is_a_problem():
    found = concern(app("Dockish", "1.1", sparkle()), appcast.FeedAnswer(version="1.2.5"))

    assert found == to_sort_out.Concern("1.2.5 is out")


def test_an_app_whose_feed_stopped_answering_cannot_wait():
    found = concern(app("Air", updater=sparkle()), appcast.FeedAnswer(error="update source answers 403"))

    assert found.urgent
    assert found.note == "update source answers 403, last checked 2026-08-16"


def test_an_updater_that_is_switched_off_is_a_problem():
    found = concern(app(updater=sparkle(automatic=False, feed="")))

    assert found.note == "updater off, last checked 2026-08-16"
    assert not found.urgent


def test_a_recipe_with_a_newer_version_is_a_problem_and_says_which():
    found = concern(app("Spotify", "1.3.4.258"), cask=Cask("spotify", "https://x.test/", "1.3.6.1921"))

    assert found == to_sort_out.Concern("Homebrew has 1.3.6.1921")


def test_a_recipe_with_the_same_version_says_the_app_is_current():
    assert concern(app("Mounty", "2.4"), cask=Cask("mounty", "https://x.test/", "2.4")) is None


def test_a_recipe_written_with_a_leading_zero_is_the_same_version():
    assert concern(app("Anki", "26.9.3"), cask=Cask("anki", "https://x.test/", "26.09.3")) is None


def test_an_app_ahead_of_its_recipe_is_not_a_problem():
    # Codex updates itself and has run ahead of the cask. Handing it over would
    # only put an older build back.
    assert concern(app("Codex", "26.831.21537"), cask=Cask("codex-app", "https://x.test/", "26.623.141536")) is None


def test_a_recipe_matching_the_build_rather_than_the_short_version_says_the_app_is_current():
    # Dockish says 6.2 for itself and carries 6.2.1 as its build, which is the version the recipe names.
    found = app("Dockish", "6.2", build="6.2.1")

    assert concern(found, cask=Cask("dockish", "https://x.test/", "6.2.1")) is None


def test_an_app_nobody_can_check_is_a_problem_that_says_so_and_since_when(monkeypatch):
    monkeypatch.setattr(to_sort_out, "last_changed", lambda found: time.mktime((2024, 4, 3, 0, 0, 0, 0, 0, -1)))

    assert concern(app("Filestar")) == to_sort_out.Concern(to_sort_out.CANNOT_CHECK, "unchanged since 2024-04")


def test_an_app_nobody_can_check_and_whose_age_is_unknown_still_says_so():
    assert concern(app("Filestar")) == to_sort_out.Concern(to_sort_out.CANNOT_CHECK)


def test_a_recipe_whose_version_cannot_be_compared_leaves_the_app_unchecked():
    found = concern(app("Juice", "1.0.1"), cask=Cask("juice", "https://x.test/", "2017.06.08170217"))

    assert found.note == "can't check for updates"


def test_what_another_app_keeps_current_is_not_a_problem():
    shortcut = UpdaterStatus(app_updaters.HOST_APP, updated_by="Google Drive")

    assert concern(app("Docs", updater=shortcut)) is None


def test_an_app_already_listed_with_what_homebrew_cannot_update_is_not_listed_again():
    found = app("Google Drive")
    behind = behind_the_recipe.Behind(found, Cask("google-drive", "x", "133"), "132")

    assert concern(found, apps_behind=[behind]) is None


def test_apps_that_cannot_wait_come_first():
    quiet, broken = app("Quiet"), app("Broken", updater=sparkle())
    findings = Findings(
        untracked=[quiet, broken],
        offered={FEED: appcast.FeedAnswer(error="update source answers 403")},
        find_cask=lambda one: None,
    )

    assert [found.name for found in to_sort_out.untracked_to_sort_out(findings)] == ["Broken", "Quiet"]


def test_what_apple_updates_is_not_offered_to_homebrew_to_handle():
    safari = app("Safari Technology Preview", "27.0", bundle_id="com.apple.SafariTechnologyPreview")
    other = app("Firefox", "157.0.1")
    findings = Findings(apps_behind=[
        behind_the_recipe.Behind(safari, Cask("stp", "x", "255"), "255"),
        behind_the_recipe.Behind(other, Cask("firefox", "x", "158"), "157.0.1"),
    ])

    assert [item.app.name for item in to_sort_out.homebrew_cannot_update(findings)] == ["Firefox"]


def test_the_age_of_an_app_is_read_from_its_bundle(tmp_path):
    contents = tmp_path / "Thing.app" / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(b"")
    os.utime(contents / "Info.plist", (1_000_000, 1_000_000))

    assert read_from_the_disk(InstalledApp("Thing", "1.0", tmp_path / "Thing.app")) == 1_000_000
    assert read_from_the_disk(app("Gone")) is None


# Taken before conftest swaps it for one that never reads the disk.
read_from_the_disk = to_sort_out.last_changed
