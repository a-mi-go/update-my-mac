"""What an app's own update feed says the newest version is.

An app no package manager tracks usually still knows where to look for its
own updates. That feed is the only place a version it could update to is
written down, and a feed that has stopped answering is why an app quietly
stopped updating itself.
"""

import json
import os
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

from update_my_mac import versions

SPARKLE = "{http://www.andymatuschak.org/xml-namespaces/sparkle}"
# A failure is asked about again far sooner than an answer, because a quiet
# feed takes an app out of "these update themselves". A host that was briefly
# down should not hold that verdict for a whole day.
STALE_AFTER_SECONDS = 6 * 60 * 60
STALE_AFTER_A_FAILURE = 30 * 60

# A budget as well as a timeout, because `--check` runs unattended and twenty
# apps behind slow hosts would otherwise wait one timeout at a time.
TIMEOUT_PER_FEED_SECONDS = 15
BUDGET_FOR_ALL_FEEDS_SECONDS = 30


class NotAnAppcast(Exception):
    """What came back is not a feed at all."""


@dataclass(frozen=True)
class FeedAnswer:
    """What a feed said, and what went wrong asking it.

    Both at once when a feed that used to answer has stopped: the version is
    the last one it named, and the error is the state it is in now. Dropping
    either would be a lie, and dropping the error would be the worse one,
    because a feed going quiet is how an app stops updating itself.
    """
    version: str = ""
    error: str = ""


def cache_path(env):
    base = env.get("XDG_CACHE_HOME") or os.path.join(env.get("HOME", ""), ".cache")
    return Path(base) / "update-my-mac" / "appcasts.json"


def _version_of(item):
    """The version an appcast entry offers, as a person would read it.

    Sparkle writes it either as a child element or as an attribute on the
    download, and the human-readable one is the short string.
    """
    enclosure = item.find("enclosure")
    for found in (
        item.findtext(f"{SPARKLE}shortVersionString"),
        enclosure.get(f"{SPARKLE}shortVersionString") if enclosure is not None else None,
        item.findtext(f"{SPARKLE}version"),
        enclosure.get(f"{SPARKLE}version") if enclosure is not None else None,
    ):
        if found and found.strip():
            return found.strip()
    return ""


def newest_version(feed):
    """The highest version an appcast offers.

    Raises NotAnAppcast when the answer is not a feed, which is what a host
    that dropped one serves in its place.
    """
    try:
        root = ElementTree.fromstring(feed)
    except ElementTree.ParseError:
        raise NotAnAppcast
    if root.tag.split("}")[-1].lower() not in ("rss", "feed"):
        raise NotAnAppcast
    offered = [
        version for version in (_version_of(item) for item in root.iter("item")) if version
    ]
    if not offered:
        return ""
    # Newest first is the convention, not a rule, so the numbers decide.
    return max(offered, key=versions.numbers_in)


def fetch(url):
    """The feed's text. Raises urllib's errors, which the caller turns into words."""
    request = urllib.request.Request(url, headers={"User-Agent": "update-my-mac"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_PER_FEED_SECONDS) as response:
        return response.read().decode("utf-8", "replace")


def read_feed(url, fetch_one=fetch):
    """Ask one feed what it offers."""
    if not url.startswith("https://"):
        return FeedAnswer(error="its feed is not served over https, so it was not read")

    try:
        feed = fetch_one(url)
    except urllib.error.HTTPError as failure:
        return FeedAnswer(error=f"its feed answers {failure.code}")
    except (urllib.error.URLError, OSError, ValueError) as failure:
        return FeedAnswer(error=f"its feed could not be read ({failure})")

    try:
        version = newest_version(feed)
    except NotAnAppcast:
        # Sparkle reports this as an improperly signed update, which is why
        # nobody ever guesses that the feed itself is gone.
        return FeedAnswer(error="its feed is not an appcast any more")

    if not version:
        return FeedAnswer(error="its feed names no version")
    return FeedAnswer(version=version)


def check(apps, env=None, fetch_one=fetch, now=time.time):
    """Ask every app's feed what it offers. Returns the answers by feed URL.

    Kept for a few hours, because a feed is checked once per app and a run
    that looks at twenty apps should not wait for twenty round trips twice.
    """
    env = os.environ if env is None else env
    cached = _read_cache(cache_path(env))
    answers = {}
    started = now()

    for app in apps:
        url = app.updater.feed_url
        if not url or url in answers:
            continue

        kept = _still_good(cached.get(url), now)
        if kept is not None:
            answers[url] = kept
            continue
        if now() - started >= BUDGET_FOR_ALL_FEEDS_SECONDS:
            answers[url] = FeedAnswer(error="there was no time left to ask its feed")
            continue

        answer = read_feed(url, fetch_one)
        # A version that once came back is still worth showing, but it never
        # covers up the fact that the feed is not answering now.
        known = cached.get(url, {}).get("version", "")
        if answer.error and known:
            answer = FeedAnswer(version=known, error=answer.error)
        answers[url] = answer
        cached[url] = {
            "version": answer.version,
            "error": answer.error,
            "fetched": now(),
        }

    _write_cache(cache_path(env), _only_asked_about(cached, apps))
    return answers


def _still_good(kept, now):
    """The kept answer while it is recent enough to reuse, otherwise None."""
    if not kept:
        return None
    keep_for = STALE_AFTER_A_FAILURE if kept.get("error") else STALE_AFTER_SECONDS
    if now() - kept.get("fetched", 0) >= keep_for:
        return None
    return FeedAnswer(kept.get("version", ""), kept.get("error", ""))


def _only_asked_about(cached, apps):
    """The cache without the feeds of apps that are not installed any more."""
    wanted = {app.updater.feed_url for app in apps if app.updater.feed_url}
    return {url: answer for url, answer in cached.items() if url in wanted}


def answer_for(app, answers):
    return answers.get(app.updater.feed_url, FeedAnswer())


def offers_newer(app, answer):
    """Whether the feed names a version later than the one installed.

    An app names two versions for itself, and a feed may be written against
    either of them.
    """
    if versions.any_version_matches(app.versions_named(), answer.version):
        return False
    return versions.is_newer(answer.version, than=app.version)


def _read_cache(path):
    try:
        stored = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def _write_cache(path, answers):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(answers))
    except OSError:
        # A cache that cannot be written costs a round trip next time, and
        # nothing else.
        pass
