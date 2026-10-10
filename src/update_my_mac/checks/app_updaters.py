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

SPARKLE = "sparkle"
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
        """Returns whether an updater is there with nobody having said if it runs."""
        return self.kind != NONE and self.automatic is None

    def update_method_note(self):
        # Squirrel is told its feed and schedule while the app runs, so
        # nothing on disk says whether it is on.
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
    """Returns the vendor's site, taken from the app's own update feed."""
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
    """Returns whether the app ships Sparkle or names a Sparkle feed."""
    framework = app_path / "Contents" / "Frameworks" / "Sparkle.framework"
    return framework.is_dir() or bool(info.get(FEED_URL))


def has_squirrel(app_path):
    """Returns whether the app ships Electron's updater."""
    return (app_path / "Contents" / "Frameworks" / "Squirrel.framework").is_dir()


def read_users_app_settings(bundle_id, shell):
    """Returns the app's own preferences, as `defaults export` reports them."""
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


def _timestamp_to_date(value):
    if isinstance(value, str):
        return value[:10]
    try:
        return time.strftime("%Y-%m-%d", time.localtime(value.timestamp()))
    except AttributeError:
        return ""


def detect(app_path, shell, info=None):
    """Returns what the app's updater is and whether it is switched on."""
    info = read_bundle_info(app_path) if info is None else info
    if not has_sparkle(app_path, info):
        return UpdaterStatus(kind=SQUIRREL) if has_squirrel(app_path) else UpdaterStatus()

    users_answer = read_users_app_settings(info.get("CFBundleIdentifier", ""), shell)
    return UpdaterStatus(
        kind=SPARKLE,
        automatic=_may_check_automatically(users_answer, info),
        installs_silently=bool(users_answer.get(SILENT_INSTALL)),
        last_checked=_timestamp_to_date(users_answer.get(LAST_CHECK)),
        feed_url=info.get(FEED_URL, ""),
    )


def _may_check_automatically(users_answer, developers_default):
    """Returns the user's answer if they gave one, else what the app shipped with."""
    answer = users_answer.get(AUTOMATIC_CHECKS)
    return developers_default.get(AUTOMATIC_CHECKS) if answer is None else answer


def group_by_status(apps):
    """Returns the untracked apps grouped by what looks after them."""
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
