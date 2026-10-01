"""Whether an untracked app looks after itself.

Most third party Mac apps that update themselves use Sparkle, and Sparkle
leaves two readable traces: what the developer built in, in the app's own
Info.plist, and what the user answered, in the app's preferences. An app with
neither is the one that really goes stale unnoticed.
"""

import plistlib
import time
from dataclasses import dataclass
import urllib.parse

# The common third-party updater, which writes its settings where they can
# be read.
SPARKLE = "sparkle"
# Electron's updater. The app passes it a feed address and a schedule while
# it runs, so nothing on disk says whether it is on or what it checks.
SQUIRREL = "squirrel"
NONE = "none"

AUTOMATIC_CHECKS = "SUEnableAutomaticChecks"
SILENT_INSTALL = "SUAutomaticallyUpdate"
LAST_CHECK = "SULastCheckTime"
FEED_URL = "SUFeedURL"


@dataclass
class UpdaterStatus:
    kind: str = NONE
    automatic: object = None
    installs_silently: bool = False
    last_checked: str = ""
    feed_url: str = ""

    @property
    def looks_after_itself(self):
        return self.kind != NONE and self.automatic is True

    @property
    def is_switched_off(self):
        return self.kind != NONE and self.automatic is False

    @property
    def is_unclear(self):
        """An updater is there, but nobody ever said whether it should run."""
        return self.kind != NONE and self.automatic is None

    def update_method_note(self):
        if self.kind == SQUIRREL:
            return "own updater, nothing says if it runs"
        if self.kind != SPARKLE:
            return "no updater"
        if self.automatic is None:
            answer = "never answered"
        elif self.automatic:
            answer = "updates itself" if self.installs_silently else "checks only"
        else:
            answer = "checking is off"
        return f"{answer}, last checked {self.last_checked}" if self.last_checked else answer


def site_behind(feed_url):
    """The vendor's site, from the feed the app checks for its own updates.

    The feed itself is XML nobody wants to read. Its host is as close to a
    download page as an app that no manager tracks ever gets.
    """
    if not feed_url:
        return ""
    parsed = urllib.parse.urlparse(feed_url)
    return f"https://{parsed.netloc}/" if parsed.netloc else ""


def read_bundle_info(app_path):
    try:
        with open(app_path / "Contents" / "Info.plist", "rb") as plist:
            return plistlib.load(plist)
    except (OSError, plistlib.InvalidFileException):
        return {}


def has_sparkle(app_path, info):
    """Sparkle can be linked without a feed in the plist, and the other way round.

    An app can ship the framework and set its feed at runtime, and another can
    keep the key from an older build without the framework. Either trace is
    enough to say the app has an updater.
    """
    framework = app_path / "Contents" / "Frameworks" / "Sparkle.framework"
    return framework.is_dir() or bool(info.get(FEED_URL))


def has_squirrel(app_path):
    """Whether the app ships Electron's updater."""
    return (app_path / "Contents" / "Frameworks" / "Squirrel.framework").is_dir()


def read_users_app_settings(bundle_id, shell):
    """What the user answered, read as the app's own preferences.

    `defaults export` rather than the file, which macOS can leave stale.
    """
    if not bundle_id:
        return {}

    executable = shell.find_executable("defaults")
    if executable is None:
        return {}

    result = shell.run_command([executable, "export", bundle_id, "-"], (0,))
    if not result.success or not result.stdout.strip():
        return {}

    try:
        exported = plistlib.loads(result.stdout.encode())
    except Exception:
        return {}
    return exported if isinstance(exported, dict) else {}


def _as_day(value):
    """A date out of whatever Sparkle wrote down, as "2026-09-24".

    It stores a date object, which becomes that day in local time, or a
    timestamp string such as "2026-09-24T14:40:00Z", which is cut to its date.
    """
    if isinstance(value, str):
        return value[:10]
    try:
        return time.strftime("%Y-%m-%d", time.localtime(value.timestamp()))
    except AttributeError:
        return ""


def detect(app_path, shell, info=None):
    """What the app's updater is and whether it is switched on."""
    info = read_bundle_info(app_path) if info is None else info
    if not has_sparkle(app_path, info):
        # Squirrel records nothing, so finding it is all there is.
        return UpdaterStatus(kind=SQUIRREL) if has_squirrel(app_path) else UpdaterStatus()

    settings = read_users_app_settings(info.get("CFBundleIdentifier", ""), shell)
    # The user's answer wins over the developer's default.
    automatic = settings.get(AUTOMATIC_CHECKS)
    if automatic is None:
        automatic = info.get(AUTOMATIC_CHECKS)

    return UpdaterStatus(
        kind=SPARKLE,
        automatic=automatic,
        installs_silently=bool(settings.get(SILENT_INSTALL)),
        last_checked=_as_day(settings.get(LAST_CHECK)),
        feed_url=info.get(FEED_URL, ""),
    )


def group_by_status(apps):
    """Split untracked apps by what looks after them.

    The first group is the point of the whole exercise: nothing on the machine
    will ever tell you these are behind. An updater that was switched off and
    one nobody ever answered for are kept apart, because saying "switched off"
    about the second would be a claim we cannot make.
    """
    unattended, switched_off, unclear, self_updating = [], [], [], []
    for app in apps:
        if app.updater.kind == NONE:
            unattended.append(app)
        elif app.updater.looks_after_itself:
            self_updating.append(app)
        elif app.updater.is_switched_off:
            switched_off.append(app)
        else:
            unclear.append(app)
    return unattended, switched_off, unclear, self_updating
