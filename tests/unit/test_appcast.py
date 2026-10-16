"""Reading what an app's own update feed offers."""

import json
import urllib.error
from pathlib import Path

from fake_run import use_environment, swap

from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.checks.app_updaters import UpdaterStatus
from update_my_mac.checks.installed_apps import InstalledApp

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
    swap(appcast, "fetch", answering("<html><body>Not found</body></html>"))
    answer = appcast.read_feed(FEED)

    assert answer.version == ""
    assert "answers with something else now" in answer.error


def test_a_feed_that_answers_with_a_code_says_which():
    error = urllib.error.HTTPError(FEED, 403, "Forbidden", {}, None)

    swap(appcast, "fetch", failing(error))
    assert appcast.read_feed(FEED).error == "update source answers 403"


def test_a_feed_that_cannot_be_reached_at_all_says_so():
    swap(appcast, "fetch", failing(urllib.error.URLError("no route")))
    answer = appcast.read_feed(FEED)

    assert "could not be read" in answer.error


def test_a_feed_that_is_not_https_is_left_alone():
    asked = []

    def fetch_one(url):
        asked.append(url)
        return ""

    swap(appcast, "fetch", fetch_one)
    answer = appcast.read_feed("http://appish.app/appcast.xml")

    assert asked == []
    assert "is not https" in answer.error


def test_a_feed_that_names_no_version_says_so():
    swap(appcast, "fetch", answering(appcast_xml()))
    assert "names no version" in appcast.read_feed(FEED).error


def test_every_feed_is_asked_once(tmp_path):
    asked = []

    def fetch_one(url):
        asked.append(url)
        return appcast_xml(item(short="1.2.5"))

    apps = [app("Dockish"), app("Dockish Helper")]
    use_environment({"XDG_CACHE_HOME": str(tmp_path)})
    swap(appcast, "fetch", fetch_one)
    answers = appcast.check(apps)

    assert asked == [FEED]
    assert answers[FEED].version == "1.2.5"


def test_an_app_with_no_feed_is_not_asked_about(tmp_path):
    asked = []

    def fetch_one(url):
        asked.append(url)
        return ""

    use_environment({"XDG_CACHE_HOME": str(tmp_path)})
    swap(appcast, "fetch", fetch_one)
    appcast.check([app(updater=UpdaterStatus())])

    assert asked == []


def test_a_recent_answer_is_not_asked_for_again(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(appcast, "fetch", answering(appcast_xml(item(short="1.2.5"))))
    appcast.check([app()])

    asked = []

    def fetch_one(url):
        asked.append(url)
        return appcast_xml(item(short="9.9"))

    swap(appcast, "fetch", fetch_one)
    answers = appcast.check([app()])

    assert asked == []
    assert answers[FEED].version == "1.2.5"


def test_an_old_answer_is_asked_for_again(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(appcast, "fetch", answering(appcast_xml(item(short="1.2.5"))))
    appcast.check([app()])

    later = lambda moment=__import__("time").time() + appcast.STALE_AFTER_SECONDS + 1: moment
    swap(appcast, "fetch", answering(appcast_xml(item(short="9.9"))))
    swap(appcast.time, "time", later)
    answers = appcast.check([app()])

    assert answers[FEED].version == "9.9"


def test_a_cache_that_cannot_be_read_costs_nothing(tmp_path):
    cache = tmp_path / "update-my-mac" / "appcasts.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("not json at all")

    use_environment({"XDG_CACHE_HOME": str(tmp_path)})
    swap(appcast, "fetch", answering(appcast_xml(item(short="1.2.5"))))
    answers = appcast.check([app()])

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
    use_environment({"XDG_CACHE_HOME": str(tmp_path)})
    swap(appcast, "fetch", fetch_one)
    swap(appcast.time, "time", lambda: next(clock))
    answers = appcast.check(apps)

    assert asked == [FEED]
    assert "no time left" in answers["https://slow.test/appcast.xml"].error


def test_a_version_already_known_survives_one_bad_day(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(appcast, "fetch", answering(appcast_xml(item(short="1.2.5"))))
    appcast.check([app()])

    later = lambda moment=__import__("time").time() + appcast.STALE_AFTER_SECONDS + 1: moment
    swap(appcast, "fetch", failing(urllib.error.URLError("no route")))
    swap(appcast.time, "time", later)
    answers = appcast.check([app()])

    assert answers[FEED].version == "1.2.5"


def test_a_failure_is_asked_about_again_sooner_than_an_answer(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(appcast, "fetch", answering("<html>gone</html>"))
    appcast.check([app()])

    asked = []

    def fetch_one(url):
        asked.append(url)
        return appcast_xml(item(short="1.2.5"))

    later = lambda moment=__import__("time").time() + appcast.STALE_AFTER_A_FAILURE + 1: moment
    swap(appcast, "fetch", fetch_one)
    swap(appcast.time, "time", later)
    answers = appcast.check([app()])

    assert asked == [FEED]
    assert answers[FEED].version == "1.2.5"


def test_a_feed_nobody_has_an_app_for_any_more_is_dropped(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(appcast, "fetch", answering(appcast_xml(item(short="1.2.5"))))
    appcast.check([app()])

    swap(appcast, "fetch", answering(appcast_xml(item(short="2.0"))))
    appcast.check([app(updater=sparkle("https://other.test/appcast.xml"))])

    kept = json.loads(appcast.cache_path().read_text())
    assert list(kept) == ["https://other.test/appcast.xml"]


def test_a_feed_that_went_quiet_says_so_even_though_a_version_is_known(tmp_path):
    # The last version it named is still worth showing, but the run decides
    # whether an app has stopped updating itself by the error, so covering it
    # up would make a dead feed look healthy for good.
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(appcast, "fetch", answering(appcast_xml(item(short="1.2.5"))))
    appcast.check([app()])

    later = lambda moment=__import__("time").time() + appcast.STALE_AFTER_SECONDS + 1: moment
    error = urllib.error.HTTPError(FEED, 403, "Forbidden", {}, None)
    swap(appcast, "fetch", failing(error))
    swap(appcast.time, "time", later)
    answers = appcast.check([app()])

    assert answers[FEED].version == "1.2.5"
    assert answers[FEED].error == "update source answers 403"


def test_the_error_is_remembered_too_so_a_later_run_still_sees_it(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(appcast, "fetch", answering(appcast_xml(item(short="1.2.5"))))
    appcast.check([app()])

    later = lambda moment=__import__("time").time() + appcast.STALE_AFTER_SECONDS + 1: moment
    error = urllib.error.HTTPError(FEED, 403, "Forbidden", {}, None)
    swap(appcast, "fetch", failing(error))
    swap(appcast.time, "time", later)
    appcast.check([app()])

    kept = json.loads(appcast.cache_path().read_text())
    assert kept[FEED]["error"] == "update source answers 403"
    assert kept[FEED]["version"] == "1.2.5"
