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
from xml.parsers.expat import ExpatError

from update_my_mac.system import shell

SPARKLE = "sparkle"
SQUIRREL = "Electron updater"
KEYSTONE = "Google's updater"
OWN = "its own updater"
HOST_APP = "host app"
NONE = "none found"

# What Google's updater writes into the apps it keeps current.
KEYSTONE_KEYS = ("KSProductID", "KSUpdateURL", "KSChannelID")
# Apps that another app installs and updates, by the start of their bundle id.
HOSTS = {"com.google.drivefs.shortcuts.": "Google Drive", "com.apple.": "macOS"}
CHROME_SHORTCUT = "CrAppModeShortcutID"

AUTOMATIC_CHECKS = "SUEnableAutomaticChecks"
SILENT_INSTALL = "SUAutomaticallyUpdate"
LAST_CHECK = "SULastCheckTime"
SKIPPED_VERSION = "SUSkippedVersion"
FEED_URL = "SUFeedURL"


@dataclass
class UpdaterStatus:
    kind: str = NONE
    automatic: object = None
    installs_silently: bool = False
    last_checked: str = ""
    feed_url: str = ""
    skipped: str = ""
    updated_by: str = ""

    @property
    def looks_after_itself(self):
        """Returns whether an updater is there and nobody switched it off."""
        return self.kind != NONE and self.automatic is not False

    @property
    def is_switched_off(self):
        return self.kind != NONE and self.automatic is False

    @property
    def is_unclear(self):
        """Returns whether an updater is there with nobody having said if it runs."""
        return self.kind != NONE and self.automatic is None

    def how_it_updates(self):
        """Returns in a few words which updater the app has and what it is set to do."""
        if self.kind != SPARKLE:
            return self._describe_non_sparkle_updater()
        setting, history = self._sparkle_setting(), self.history_note()
        return f"{setting}, {history}" if history else setting

    def _describe_non_sparkle_updater(self):
        """Returns the updater's name, or the app that updates it."""
        if self.kind == HOST_APP:
            return f"updated with {self.updated_by}"
        return self.kind

    def _sparkle_setting(self):
        if self.automatic is None:
            return "state unknown"
        if not self.automatic:
            return "auto checking off"
        return "installs updates" if self.installs_silently else "checks only"

    def history_note(self):
        """Returns when the updater last checked for updates and which update was skipped."""
        parts = []
        if self.last_checked:
            parts.append(f"last checked {self.last_checked}")
        if self.skipped:
            parts.append(f"skipped version {self.skipped}")
        return ", ".join(parts)


def vendor_site(feed_url):
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
    """Returns whether the app ships the Sparkle updater or names a Sparkle feed."""
    framework = app_path / "Contents" / "Frameworks" / "Sparkle.framework"
    return framework.is_dir() or bool(info.get(FEED_URL))


def has_squirrel(app_path):
    """Returns whether the app ships Electron's updater."""
    return (app_path / "Contents" / "Frameworks" / "Squirrel.framework").is_dir()


def read_users_app_settings(bundle_id):
    """Returns the user's settings for the app, or none where they can't be read."""
    exported = _exported_preferences(bundle_id)
    if not exported.strip():
        return {}
    try:
        settings = plistlib.loads(exported.encode())
    except (ValueError, ExpatError):
        return {}
    return settings if isinstance(settings, dict) else {}


def _exported_preferences(bundle_id):
    """Returns the plist text `defaults export` prints for the app, or "" when it prints none."""
    if not bundle_id:
        return ""
    executable = shell.find_executable("defaults")
    if executable is None:
        return ""
    result = shell.run_command([executable, "export", bundle_id, "-"], (0,))
    return result.stdout if result.success else ""


def detect(app_path, info=None):
    """Returns what the app's updater is and whether it is switched on, or none for a bundle it can't read."""
    info = read_bundle_info(app_path) if info is None else info
    try:
        return _detect_readable(app_path, info)
    except OSError:
        return UpdaterStatus()


def _detect_readable(app_path, info):
    if not has_sparkle(app_path, info):
        return _detect_non_sparkle_updater(app_path, info)

    users_settings = read_users_app_settings(info.get("CFBundleIdentifier", ""))
    return UpdaterStatus(
        kind=SPARKLE,
        automatic=_may_check_automatically(users_settings, info),
        installs_silently=bool(users_settings.get(SILENT_INSTALL)),
        last_checked=_timestamp_to_date(users_settings.get(LAST_CHECK)),
        feed_url=info.get(FEED_URL, ""),
        skipped=str(users_settings.get(SKIPPED_VERSION) or ""),
    )


def _detect_non_sparkle_updater(app_path, info):
    """Returns the updater an app without Sparkle ships, judged by the traces it leaves in the bundle."""
    contents = app_path / "Contents"
    bundle_id = info.get("CFBundleIdentifier", "")
    host = next((name for prefix, name in HOSTS.items() if bundle_id.startswith(prefix)), "")
    if host or CHROME_SHORTCUT in info:
        return UpdaterStatus(kind=HOST_APP, updated_by=host or "Chrome")
    if has_squirrel(app_path):
        return UpdaterStatus(kind=SQUIRREL)
    if any(key in info for key in KEYSTONE_KEYS):
        return UpdaterStatus(kind=KEYSTONE)
    if (contents / "Resources" / "app-update.yml").is_file() or _names_an_updater(contents):
        return UpdaterStatus(kind=OWN)
    return UpdaterStatus()


def _names_an_updater(contents):
    for place in ("Frameworks", "MacOS", "Library/LaunchServices"):
        folder = contents / place
        if folder.is_dir() and any("updat" in entry.name.lower() for entry in folder.iterdir()):
            return True
    return False


def _may_check_automatically(users_settings, developers_default):
    """Returns the user's answer if they gave one, else what the app shipped with."""
    answer = users_settings.get(AUTOMATIC_CHECKS)
    return developers_default.get(AUTOMATIC_CHECKS) if answer is None else answer


def _timestamp_to_date(value):
    if isinstance(value, str):
        return value[:10]
    try:
        return time.strftime("%Y-%m-%d", time.localtime(value.timestamp()))
    except AttributeError:
        return ""
