"""Whether an untracked app looks after itself.

Most third party Mac apps that update themselves use Sparkle, and Sparkle
leaves two readable traces: what the developer built in, in the app's own
Info.plist, and what the user answered, in the app's preferences. An app with
neither is the one that really goes stale unnoticed.
"""

import plistlib
import time
from dataclasses import dataclass

SPARKLE = "sparkle"
NONE = "none"

# What the developer shipped and what the user chose, in that order of doubt.
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

    def describe(self):
        if self.kind == NONE:
            return "no updater"
        if self.automatic is None:
            answer = "never answered"
        elif self.automatic:
            answer = "installs updates itself" if self.installs_silently else "checks by itself"
        else:
            answer = "checking is off"
        return f"{answer}, last checked {self.last_checked}" if self.last_checked else answer


def read_bundle_info(app_path):
    try:
        with open(app_path / "Contents" / "Info.plist", "rb") as plist:
            return plistlib.load(plist)
    except (OSError, plistlib.InvalidFileException):
        return {}


def has_sparkle(app_path, info):
    """Sparkle can be linked without a feed in the plist, and the other way round.

    Codex ships the framework and sets its feed in code; some apps keep the key
    from an older build without the framework. Either trace is enough to say
    the app has an updater.
    """
    framework = app_path / "Contents" / "Frameworks" / "Sparkle.framework"
    return framework.is_dir() or bool(info.get(FEED_URL))


def read_user_settings(bundle_id, shell):
    """What the user answered, read as the app's own preferences.

    `defaults export` is used rather than the preference file, because macOS
    keeps preferences in a daemon and the file on disk can be stale or absent.
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
        return UpdaterStatus()

    settings = read_user_settings(info.get("CFBundleIdentifier", ""), shell)
    # The user's answer wins. Without one, the developer's default applies, and
    # without that there is nothing to go on.
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
