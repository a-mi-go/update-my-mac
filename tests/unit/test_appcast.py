"""Reading what an app's own update feed offers."""

import json
import urllib.error
from pathlib import Path

from update_my_mac import app_updaters, appcast
from update_my_mac.app_updaters import UpdaterStatus
from update_my_mac.installed_apps import InstalledApp

FEED = "https://appish.app/dockish/appcast.xml"


def sparkle(url=FEED):
    return UpdaterStatus(app_updaters.SPARKLE, True, False, "2026-08-16", url)


def app(name="Dockish", version="1.1", updater=None):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"),
                        updater or sparkle())


def appcast_xml(*items):
    entries = "".join(items)
    return (
        '<?xml version="1.0"?>'
        '<rss version="2.0" '
        'xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">'
        f"<channel><title>Updates</title>{entries}</channel></rss>"
    )


def item(short=None, enclosure_short=None):
    inside = f"<sparkle:shortVersionString>{short}</sparkle:shortVersionString>" if short else ""
    attribute = f' sparkle:shortVersionString="{enclosure_short}"' if enclosure_short else ""
    return f'<item><title>A release</title>{inside}<enclosure url="x.zip"{attribute}/></item>'


def answering(text):
    def fetch_one(_url):
        return text

    return fetch_one


def failing(error):
    def fetch_one(_url):
        raise error

    return fetch_one


def test_the_version_is_read_from_the_entry():
    assert appcast.newest_version(appcast_xml(item(short="1.2.5"))) == "1.2.5"


def test_the_version_is_read_from_the_download_when_the_entry_is_silent():
    assert appcast.newest_version(appcast_xml(item(enclosure_short="1.2.5"))) == "1.2.5"


def test_the_highest_version_wins_not_the_first_one():
    # Newest first is a convention, not a rule.
    feed = appcast_xml(item(short="1.2"), item(short="1.10"), item(short="1.9"))

    assert appcast.newest_version(feed) == "1.10"


def test_a_feed_with_no_entries_offers_nothing():
    assert appcast.newest_version(appcast_xml()) == ""


def test_an_error_page_in_place_of_a_feed_is_said_out_loud():
    # A host that dropped the feed serves its 404 page, and Sparkle then calls
    # the update improperly signed.
    answer = appcast.read_feed(FEED, answering("<html><body>Not found</body></html>"))

    assert answer.version == ""
    assert "not an appcast any more" in answer.error


def test_a_feed_that_answers_with_a_code_says_which():
    error = urllib.error.HTTPError(FEED, 403, "Forbidden", {}, None)

    assert appcast.read_feed(FEED, failing(error)).error == "its feed answers 403"


def test_a_feed_that_cannot_be_reached_at_all_says_so():
    answer = appcast.read_feed(FEED, failing(urllib.error.URLError("no route")))

    assert "could not be read" in answer.error


def test_a_feed_that_is_not_https_is_left_alone():
    asked = []

    def fetch_one(url):
        asked.append(url)
        return ""

    answer = appcast.read_feed("http://appish.app/appcast.xml", fetch_one)

    assert asked == []
    assert "not served over https" in answer.error


def test_a_feed_that_names_no_version_says_so():
    assert "names no version" in appcast.read_feed(FEED, answering(appcast_xml())).error


def test_every_feed_is_asked_once(tmp_path):
    asked = []

    def fetch_one(url):
        asked.append(url)
        return appcast_xml(item(short="1.2.5"))

    apps = [app("Dockish"), app("Dockish Helper")]
    answers = appcast.check(apps, {"XDG_CACHE_HOME": str(tmp_path)}, fetch_one)

    assert asked == [FEED]
    assert answers[FEED].version == "1.2.5"


def test_an_app_with_no_feed_is_not_asked_about(tmp_path):
    asked = []

    def fetch_one(url):
        asked.append(url)
        return ""

    appcast.check([app(updater=UpdaterStatus())], {"XDG_CACHE_HOME": str(tmp_path)}, fetch_one)

    assert asked == []


def test_a_recent_answer_is_not_asked_for_again(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    appcast.check([app()], env, answering(appcast_xml(item(short="1.2.5"))))

    asked = []

    def fetch_one(url):
        asked.append(url)
        return appcast_xml(item(short="9.9"))

    answers = appcast.check([app()], env, fetch_one)

    assert asked == []
    assert answers[FEED].version == "1.2.5"


def test_an_old_answer_is_asked_for_again(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    appcast.check([app()], env, answering(appcast_xml(item(short="1.2.5"))))

    later = lambda: __import__("time").time() + appcast.STALE_AFTER_SECONDS + 1
    answers = appcast.check(
        [app()], env, answering(appcast_xml(item(short="9.9"))), now=later
    )

    assert answers[FEED].version == "9.9"


def test_a_cache_that_cannot_be_read_costs_nothing(tmp_path):
    cache = tmp_path / "update-my-mac" / "appcasts.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("not json at all")

    answers = appcast.check(
        [app()], {"XDG_CACHE_HOME": str(tmp_path)},
        answering(appcast_xml(item(short="1.2.5"))),
    )

    assert answers[FEED].version == "1.2.5"
    assert json.loads(cache.read_text())[FEED]["version"] == "1.2.5"


def test_a_feed_offering_what_is_already_installed_is_not_an_update():
    assert not appcast.offers_newer(app(version="1.2.5"), appcast.FeedAnswer("1.2.5"))
    assert appcast.offers_newer(app(version="1.1"), appcast.FeedAnswer("1.2.5"))


def test_an_app_nobody_asked_about_has_no_answer():
    assert appcast.answer_for(app(), {}) == appcast.FeedAnswer()


def test_a_feed_is_left_unasked_once_the_time_is_up(tmp_path):
    asked = []
    clock = iter([0, 0, 0, appcast.BUDGET_FOR_ALL_FEEDS_SECONDS + 1, appcast.BUDGET_FOR_ALL_FEEDS_SECONDS + 1])

    def fetch_one(url):
        asked.append(url)
        return appcast_xml(item(short="1.2.5"))

    apps = [app("Dockish"), app("Slow", updater=sparkle("https://slow.test/appcast.xml"))]
    answers = appcast.check(
        apps, {"XDG_CACHE_HOME": str(tmp_path)}, fetch_one, now=lambda: next(clock)
    )

    assert asked == [FEED]
    assert "no time left" in answers["https://slow.test/appcast.xml"].error


def test_a_version_already_known_survives_one_bad_day(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    appcast.check([app()], env, answering(appcast_xml(item(short="1.2.5"))))

    later = lambda: __import__("time").time() + appcast.STALE_AFTER_SECONDS + 1
    answers = appcast.check(
        [app()], env, failing(urllib.error.URLError("no route")), now=later
    )

    assert answers[FEED].version == "1.2.5"


def test_a_failure_is_asked_about_again_sooner_than_an_answer(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    appcast.check([app()], env, answering("<html>gone</html>"))

    asked = []

    def fetch_one(url):
        asked.append(url)
        return appcast_xml(item(short="1.2.5"))

    later = lambda: __import__("time").time() + appcast.STALE_AFTER_A_FAILURE + 1
    answers = appcast.check([app()], env, fetch_one, now=later)

    assert asked == [FEED]
    assert answers[FEED].version == "1.2.5"


def test_a_feed_nobody_has_an_app_for_any_more_is_dropped(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    appcast.check([app()], env, answering(appcast_xml(item(short="1.2.5"))))

    appcast.check([app(updater=sparkle("https://other.test/appcast.xml"))], env,
                  answering(appcast_xml(item(short="2.0"))))

    kept = json.loads(appcast.cache_path(env).read_text())
    assert list(kept) == ["https://other.test/appcast.xml"]


def test_a_feed_that_went_quiet_says_so_even_though_a_version_is_known(tmp_path):
    # The last version it named is still worth showing, but the run decides
    # whether an app has stopped updating itself by the error, so covering it
    # up would make a dead feed look healthy for good.
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    appcast.check([app()], env, answering(appcast_xml(item(short="1.2.5"))))

    later = lambda: __import__("time").time() + appcast.STALE_AFTER_SECONDS + 1
    error = urllib.error.HTTPError(FEED, 403, "Forbidden", {}, None)
    answers = appcast.check([app()], env, failing(error), now=later)

    assert answers[FEED].version == "1.2.5"
    assert answers[FEED].error == "its feed answers 403"


def test_the_error_is_remembered_too_so_a_later_run_still_sees_it(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    appcast.check([app()], env, answering(appcast_xml(item(short="1.2.5"))))

    later = lambda: __import__("time").time() + appcast.STALE_AFTER_SECONDS + 1
    error = urllib.error.HTTPError(FEED, 403, "Forbidden", {}, None)
    appcast.check([app()], env, failing(error), now=later)

    kept = json.loads(appcast.cache_path(env).read_text())
    assert kept[FEED]["error"] == "its feed answers 403"
    assert kept[FEED]["version"] == "1.2.5"
