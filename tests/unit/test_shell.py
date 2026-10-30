import os
import subprocess

from update_my_mac.system import shell


def test_only_web_addresses_are_opened():
    # Anything else here would mean opening a local file or handing the URL to
    # whatever application claims that scheme.
    assert shell.open_in_browser("file:///etc/passwd") is False
    assert shell.open_in_browser("/Applications/Calculator.app") is False
    assert shell.open_in_browser("http://example.com") is False
    assert shell.open_in_browser("") is False


def test_a_command_that_cannot_start_has_no_exit_code():
    # -1 would read as SIGHUP, which is a command that ran and was killed.
    assert shell.stream_command(["/nonexistent/program"]) is None


def test_a_command_that_never_ran_is_not_described_by_a_number():
    assert shell.describe_exit(None) == "could not be run"
    assert shell.describe_exit(2) == "exited with 2"


def test_the_path_moved_to_the_trash_goes_in_as_an_argument_not_as_script(tmp_path, monkeypatch):
    written = tmp_path / "arguments"
    fake = tmp_path / "bin" / "osascript"
    fake.parent.mkdir()
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{written}"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}:/usr/bin:/bin")
    name = 'Evil" & (do shell script "id") & ".app'

    assert shell.move_to_trash(tmp_path / name)

    arguments = written.read_text().splitlines()
    assert arguments[-1] == str(tmp_path / name)
    assert not any(name in script for script in arguments[:-1])


class Status:
    """What the runner starts and stops, and when it did so relative to the output."""

    def __init__(self):
        self.events = []

    def start(self):
        self.events.append("start")

    def stop(self):
        self.events.append("stop")


def test_a_status_shows_until_the_command_first_writes(capfd):
    status = Status()

    code = shell._run_until_it_writes(["sh", "-c", "sleep 0.3; printf hello"], None, status)

    assert code == 0
    assert status.events == ["start", "stop"]
    assert capfd.readouterr().out == "hello"


def test_the_status_has_stopped_before_the_first_byte_is_passed_on(capfd):
    class Marking(Status):
        def stop(self):
            os.write(1, b"[stopped]")
            super().stop()

    shell._run_until_it_writes(["sh", "-c", "printf hello"], None, Marking())

    assert capfd.readouterr().out == "[stopped]hello"


def test_a_command_that_never_writes_still_stops_the_status():
    status = Status()

    assert shell._run_until_it_writes(["sh", "-c", "exit 3"], None, status) == 3
    assert status.events == ["start", "stop"]


def test_the_command_still_sees_a_terminal(capfd):
    shell._run_until_it_writes(["sh", "-c", "[ -t 1 ] && printf yes || printf no"], None, Status())

    assert capfd.readouterr().out == "yes"


def test_something_the_command_left_running_does_not_hold_the_run_up():
    import time

    started = time.time()
    code = shell._run_until_it_writes(["sh", "-c", "(sleep 5 &) ; printf hi"], None, Status())

    assert code == 0
    assert time.time() - started < 2


def test_a_status_is_not_started_when_the_output_is_not_a_terminal():
    status = Status()

    assert shell.stream_command(["true"], silent_status=status) == 0
    assert status.events == []


def test_commands_and_lookups_start_from_the_environment_the_run_set(tmp_path):
    tool = tmp_path / "mytool"
    tool.write_text("#!/bin/sh\necho $MARKER\n")
    tool.chmod(0o755)
    shell.use_environment({"PATH": str(tmp_path), "MARKER": "prepared"})
    try:
        assert shell.find_executable("mytool") == str(tool)
        assert shell.run_command([str(tool)]).stdout == "prepared"
        # An env a caller gives still wins.
        assert shell.run_command([str(tool)], env={"MARKER": "given"}).stdout == "given"
    finally:
        shell.use_environment(None)


def test_a_clipboard_that_is_not_there_is_said_so(monkeypatch):
    monkeypatch.setattr(shell, "find_executable", lambda command: None)

    assert shell.copy_to_clipboard("some text") is False


def test_the_text_for_the_clipboard_is_handed_to_pbcopy_on_its_input(monkeypatch):
    seen = {}

    def fake_run(args, input, text, env):
        seen.update(args=args, input=input)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(shell, "find_executable", lambda command: "/usr/bin/pbcopy")
    monkeypatch.setattr(shell.subprocess, "run", fake_run)

    assert shell.copy_to_clipboard("some text") is True
    assert seen == {"args": ["/usr/bin/pbcopy"], "input": "some text"}


def test_what_a_streamed_command_writes_reaches_a_listener_and_so_does_its_end(capfd):
    class Status:
        def start(self):
            pass

        def stop(self):
            pass

    heard = []
    shell.listen_to_command_output(heard.append)
    try:
        shell._run_until_it_writes(["echo", "hello"], os.environ, Status())
    finally:
        shell.listen_to_command_output(None)

    assert b"hello" in b"".join(piece for piece in heard if piece is not None)
    assert heard[-1] is None
