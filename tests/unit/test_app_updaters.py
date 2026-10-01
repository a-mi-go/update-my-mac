import datetime
import plistlib

from update_my_mac import app_updaters
from update_my_mac.shell import CommandResult


def make_app(tmp_path, name="Thing", info=None, with_sparkle=False):
    app = tmp_path / f"{name}.app"
    contents = app / "Contents"
    contents.mkdir(parents=True)
    if info is not None:
        with open(contents / "Info.plist", "wb") as plist:
            plistlib.dump(info, plist)
    if with_sparkle:
        (contents / "Frameworks" / "Sparkle.framework").mkdir(parents=True)
    return app


class FakeShell:
    """Only `defaults` matters here, and only what it exports."""

    def __init__(self, settings=None, installed=True):
        self.settings = settings
        self.installed = installed
        self.calls = []

    def find_executable(self, command):
        return f"/fake/{command}" if self.installed else None

    def run_command(self, args, success_exit_codes=(0,), env=None):
        self.calls.append(args)
        if self.settings is None:
            return CommandResult(True, "", "")
        return CommandResult(True, plistlib.dumps(self.settings).decode(), "")


def test_an_app_without_sparkle_has_no_updater(tmp_path):
    app = make_app(tmp_path, info={"CFBundleIdentifier": "com.example.thing"})

    status = app_updaters.detect(app, FakeShell())
    assert status.kind == app_updaters.NONE
    assert status.update_method_note() == "no updater"


def test_the_framework_alone_counts_as_an_updater(tmp_path):
    # Codex ships Sparkle and sets its feed in code, not in the plist.
    app = make_app(tmp_path, info={"CFBundleIdentifier": "com.example.codex"}, with_sparkle=True)

    assert app_updaters.detect(app, FakeShell()).kind == app_updaters.SPARKLE


def test_a_feed_alone_counts_as_an_updater(tmp_path):
    app = make_app(tmp_path, info={"SUFeedURL": "https://example.com/appcast.xml"})

    assert app_updaters.detect(app, FakeShell()).kind == app_updaters.SPARKLE


def test_an_updater_nobody_answered_for_is_unclear(tmp_path):
    app = make_app(tmp_path, info={"SUFeedURL": "https://example.com/a.xml"}, with_sparkle=True)

    status = app_updaters.detect(app, FakeShell())
    assert status.is_unclear
    assert not status.looks_after_itself
    assert status.update_method_note() == "never answered"


def test_what_the_developer_shipped_counts_when_nobody_answered(tmp_path):
    app = make_app(
        tmp_path,
        info={"SUFeedURL": "https://example.com/a.xml", "SUEnableAutomaticChecks": True},
        with_sparkle=True,
    )

    assert app_updaters.detect(app, FakeShell()).looks_after_itself


def test_the_users_answer_beats_the_shipped_default(tmp_path):
    app = make_app(
        tmp_path,
        info={
            "CFBundleIdentifier": "com.example.thing",
            "SUFeedURL": "https://example.com/a.xml",
            "SUEnableAutomaticChecks": True,
        },
        with_sparkle=True,
    )
    shell = FakeShell({"SUEnableAutomaticChecks": False})

    status = app_updaters.detect(app, shell)
    assert status.is_switched_off
    assert status.update_method_note() == "checking is off"


def test_silent_installing_is_said_differently(tmp_path):
    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )
    shell = FakeShell({"SUEnableAutomaticChecks": True, "SUAutomaticallyUpdate": True})

    assert app_updaters.detect(app, shell).update_method_note() == "updates itself"


def test_the_last_check_is_shown_as_a_day(tmp_path):
    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )
    shell = FakeShell(
        {
            "SUEnableAutomaticChecks": True,
            "SULastCheckTime": datetime.datetime(2026, 9, 24, 14, 40),
        }
    )

    assert "last checked 2026-09-24" in app_updaters.detect(app, shell).update_method_note()


def test_an_app_without_a_readable_plist_has_no_updater(tmp_path):
    app = make_app(tmp_path, info=None)

    assert app_updaters.detect(app, FakeShell()).kind == app_updaters.NONE


def test_settings_are_not_read_without_a_bundle_id(tmp_path):
    app = make_app(tmp_path, info={"SUFeedURL": "https://x/a.xml"}, with_sparkle=True)
    shell = FakeShell({"SUEnableAutomaticChecks": True})

    app_updaters.detect(app, shell)
    assert shell.calls == []


def test_a_machine_without_defaults_does_not_stop_the_run(tmp_path):
    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )

    assert app_updaters.detect(app, FakeShell(installed=False)).is_unclear


def test_nonsense_from_defaults_is_ignored(tmp_path):
    class BrokenShell(FakeShell):
        def run_command(self, args, success_exit_codes=(0,), env=None):
            return CommandResult(True, "not a plist at all", "")

    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )

    assert app_updaters.detect(app, BrokenShell()).is_unclear


def test_electrons_updater_is_found_by_the_framework_it_ships(tmp_path):
    app = tmp_path / "Exodus.app"
    (app / "Contents" / "Frameworks" / "Squirrel.framework").mkdir(parents=True)

    assert app_updaters.has_squirrel(app)


def test_an_app_with_neither_framework_has_no_updater(tmp_path):
    app = tmp_path / "Quiet.app"
    (app / "Contents" / "Frameworks").mkdir(parents=True)

    assert not app_updaters.has_squirrel(app)
