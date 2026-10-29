import datetime
import plistlib
from fake_run import use_shell

from update_my_mac.checks import app_updaters
from update_my_mac.system.shell import CommandResult


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

    use_shell(FakeShell())
    status = app_updaters.detect(app)
    assert status.kind == app_updaters.NONE
    assert status.update_method_note() == "none found"


def test_the_framework_alone_counts_as_an_updater(tmp_path):
    # Codex ships Sparkle and sets its feed in code, not in the plist.
    app = make_app(tmp_path, info={"CFBundleIdentifier": "com.example.codex"}, with_sparkle=True)

    use_shell(FakeShell())
    assert app_updaters.detect(app).kind == app_updaters.SPARKLE


def test_a_feed_alone_counts_as_an_updater(tmp_path):
    app = make_app(tmp_path, info={"SUFeedURL": "https://example.com/appcast.xml"})

    use_shell(FakeShell())
    assert app_updaters.detect(app).kind == app_updaters.SPARKLE


def test_an_updater_nobody_answered_for_still_looks_after_the_app(tmp_path):
    app = make_app(tmp_path, info={"SUFeedURL": "https://example.com/a.xml"}, with_sparkle=True)

    use_shell(FakeShell())
    status = app_updaters.detect(app)
    assert status.is_unclear
    assert status.looks_after_itself
    assert status.update_method_note() == "state unknown"


def test_what_the_developer_shipped_counts_when_nobody_answered(tmp_path):
    app = make_app(
        tmp_path,
        info={"SUFeedURL": "https://example.com/a.xml", "SUEnableAutomaticChecks": True},
        with_sparkle=True,
    )

    use_shell(FakeShell())
    assert app_updaters.detect(app).looks_after_itself


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

    use_shell(shell)
    status = app_updaters.detect(app)
    assert status.is_switched_off
    assert status.update_method_note() == "auto checking off"


def test_silent_installing_is_said_differently(tmp_path):
    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )
    shell = FakeShell({"SUEnableAutomaticChecks": True, "SUAutomaticallyUpdate": True})

    use_shell(shell)
    assert app_updaters.detect(app).update_method_note() == "installs updates"


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

    use_shell(shell)
    assert "last checked 2026-09-24" in app_updaters.detect(app).update_method_note()


def test_an_app_without_a_readable_plist_has_no_updater(tmp_path):
    app = make_app(tmp_path, info=None)

    use_shell(FakeShell())
    assert app_updaters.detect(app).kind == app_updaters.NONE


def test_settings_are_not_read_without_a_bundle_id(tmp_path):
    app = make_app(tmp_path, info={"SUFeedURL": "https://x/a.xml"}, with_sparkle=True)
    shell = FakeShell({"SUEnableAutomaticChecks": True})

    use_shell(shell)
    app_updaters.detect(app)
    assert shell.calls == []


def test_a_machine_without_defaults_does_not_stop_the_run(tmp_path):
    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )

    use_shell(FakeShell(installed=False))
    assert app_updaters.detect(app).is_unclear


def test_nonsense_from_defaults_is_ignored(tmp_path):
    class BrokenShell(FakeShell):
        def run_command(self, args, success_exit_codes=(0,), env=None):
            return CommandResult(True, "not a plist at all", "")

    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )

    use_shell(BrokenShell())
    assert app_updaters.detect(app).is_unclear


def test_electrons_updater_is_found_by_the_framework_it_ships(tmp_path):
    app = tmp_path / "Exodus.app"
    (app / "Contents" / "Frameworks" / "Squirrel.framework").mkdir(parents=True)

    assert app_updaters.has_squirrel(app)


def test_an_app_with_neither_framework_has_no_updater(tmp_path):
    app = tmp_path / "Quiet.app"
    (app / "Contents" / "Frameworks").mkdir(parents=True)

    assert not app_updaters.has_squirrel(app)


def test_a_skipped_update_is_part_of_what_the_updater_note_says(tmp_path):
    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )
    shell = FakeShell({"SUEnableAutomaticChecks": False, "SUSkippedVersion": "317"})

    use_shell(shell)
    status = app_updaters.detect(app)

    assert status.skipped == "317"
    assert status.update_method_note() == "auto checking off, skipped version 317"
    assert status.history_note() == "skipped version 317"


def test_no_skipped_update_adds_nothing(tmp_path):
    app = make_app(
        tmp_path,
        info={"CFBundleIdentifier": "com.example.thing", "SUFeedURL": "https://x/a.xml"},
        with_sparkle=True,
    )

    use_shell(FakeShell({"SUEnableAutomaticChecks": True}))
    status = app_updaters.detect(app)

    assert status.skipped == ""
    assert "skipped" not in status.update_method_note()


def detected(tmp_path, info=None, inside=()):
    app = make_app(tmp_path, info=info or {})
    for place in inside:
        target = app / "Contents" / place
        target.parent.mkdir(parents=True, exist_ok=True)
        if place.endswith(".yml"):
            target.write_text("provider: github\n")
        else:
            target.mkdir()
    use_shell(FakeShell())
    return app_updaters.detect(app)


def test_googles_updater_is_found_by_what_it_writes_into_the_app(tmp_path):
    status = detected(tmp_path, {"KSProductID": "com.google.Chrome"})

    assert status.kind == app_updaters.KEYSTONE
    assert status.looks_after_itself
    assert status.update_method_note() == "Google's updater"


def test_an_updater_shipped_as_a_program_of_its_own_is_found(tmp_path):
    assert detected(tmp_path, inside=["MacOS/updater.app"]).kind == app_updaters.OWN


def test_an_updater_of_the_vendors_own_is_found_by_its_name(tmp_path):
    assert detected(tmp_path, inside=["Frameworks/ZoomAutoUpdater.app"]).kind == app_updaters.OWN


def test_electrons_other_updater_is_found_by_its_settings_file(tmp_path):
    assert detected(tmp_path, inside=["Resources/app-update.yml"]).kind == app_updaters.OWN


def test_a_shortcut_google_drive_installs_is_updated_with_google_drive(tmp_path):
    status = detected(tmp_path, {"CFBundleIdentifier": "com.google.drivefs.shortcuts.docs"})

    assert status.kind == app_updaters.HOST_APP
    assert status.update_method_note() == "updated with Google Drive"


def test_a_web_app_chrome_made_is_updated_with_chrome(tmp_path):
    status = detected(tmp_path, {"CrAppModeShortcutID": "abc"})

    assert status.update_method_note() == "updated with Chrome"


def test_an_app_with_a_folder_it_may_not_read_has_no_updater(tmp_path):
    app = make_app(tmp_path, info={})
    locked = app / "Contents" / "MacOS"
    locked.mkdir()
    locked.chmod(0)
    use_shell(FakeShell())
    try:
        assert app_updaters.detect(app).kind == app_updaters.NONE
    finally:
        locked.chmod(0o755)


def test_an_app_without_any_trace_of_an_updater_has_none(tmp_path):
    status = detected(tmp_path, {"CFBundleIdentifier": "com.example.thing"}, inside=["Frameworks/Other.framework"])

    assert status.kind == app_updaters.NONE
    assert not status.looks_after_itself

