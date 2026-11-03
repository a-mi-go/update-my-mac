"""The one place that runs external commands."""

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class CommandResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int = 0


# The environment the run's commands start with. None until the run sets one.
_run_environment = None

_command_output_listener = None

SILENCE_BEFORE_STATUS_SECONDS = 2
KEPT_OUTPUT_BYTES = 100_000
KILL_AFTER_CTRL_C_SECONDS = 5
STDIN = 0
KEYBOARD = STDIN
TRAILING_COLOR_AND_CURSOR_CODES = re.compile(rb"(?:\x1b\[(?:\?25[hl]|[0-9;]*m|0?K))+$")
_last_streamed = bytearray()


def listen_to_command_output(listener):
    """Passes what a streamed command writes to the listener, and None when it ends."""
    global _command_output_listener
    _command_output_listener = listener


def use_environment(env):
    """Makes every later command and lookup start from this environment."""
    global _run_environment
    _run_environment = env


def current_environment():
    """Returns the environment a command starts with."""
    return os.environ if _run_environment is None else _run_environment


def find_executable(command):
    return shutil.which(command, path=current_environment().get("PATH"))


def run_command(args, success_exit_codes=(0,), env=None, timeout=120):
    """Runs a command and returns its output, keeping the two streams apart."""
    # success_exit_codes is for managers like npm, which exits 1 when it finds
    # updates.
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_for_command(env),
            # Out of the terminal's reach, so a Ctrl-C that only warns does not stop it.
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(False, "", str(exc), -1)

    return CommandResult(
        proc.returncode in success_exit_codes,
        proc.stdout.strip(),
        proc.stderr.strip(),
        proc.returncode,
    )


def stream_command(args, env=None, status_while_silent=None, rewrite=None):
    """Runs a command with the terminal attached.

    Returns its exit code, or None when the command never started. A status,
    which has start() and stop(), shows whenever the command is not writing.
    With a status, `rewrite` turns each piece of output into what is shown.
    """
    env = _for_command(env)
    _last_streamed.clear()
    try:
        if status_while_silent is None or not sys.stdout.isatty():
            return subprocess.run(args, env=env).returncode
        return _run_in_pty_with_status(args, env, status_while_silent, rewrite)
    except (OSError, subprocess.SubprocessError):
        return None


def output_of_last_streamed_command():
    """Returns what the last streamed command wrote to its terminal, as far as it is kept."""
    return bytes(_last_streamed).decode("utf-8", errors="replace")


def copy_to_clipboard(text):
    """Puts the text on the clipboard. Returns whether it worked."""
    executable = find_executable("pbcopy")
    if executable is None:
        return False
    try:
        # Without a UTF-8 locale pbcopy reads the text as something older.
        env = {**current_environment(), "LANG": "en_US.UTF-8"}
        return subprocess.run([executable], input=text, text=True, env=env).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def describe_exit(exit_code):
    """Returns how a streamed command ended, as a phrase to put after its name."""
    return "could not be run" if exit_code is None else f"exited with {exit_code}"


def open_in_browser(url):
    """Opens an https address. Returns whether it worked."""
    if not url.startswith("https://"):
        return False

    executable = find_executable("open")
    if executable is None:
        return False
    return run_command([executable, url]).success


def ask_application_to_quit(bundle_id):
    """Asks an app to quit the way the Quit menu item does."""
    executable = find_executable("osascript")
    if executable is None:
        return False
    return run_command(
        [executable, "-e", f'tell application id "{bundle_id}" to quit']
    ).success


def move_to_trash(path):
    """Moves a file or an app to the Trash, where it can be put back. Returns whether it worked."""
    executable = find_executable("osascript")
    if executable is None:
        return False
    # The path goes in as an argument, so a quote in an app's name stays text.
    return run_command([
        executable,
        "-e", "on run argv",
        "-e", "set thePath to POSIX file (item 1 of argv)",
        "-e", 'tell application "Finder" to delete thePath',
        "-e", "end run",
        str(path),
    ]).success


def open_application(path):
    executable = find_executable("open")
    if executable is None:
        return False
    return run_command([executable, "-a", str(path)]).success


def is_running(pid):
    executable = find_executable("ps")
    if executable is None:
        return False
    return run_command([executable, "-p", str(pid)], (0, 1)).exit_code == 0


def _for_command(env):
    """Returns the environment to run with: the one given, else the run's own."""
    return _run_environment if env is None else env


def _run_in_pty_with_status(args, env, status, rewrite=None):
    """Runs a command whose output reaches the terminal through a pty.

    The command still sees a terminal, with its colors and progress bars. The
    status shows while it is silent, and stops before the next byte is passed on.
    The pty is the command's own terminal, so what sudo asks reaches the screen
    the same way, and what is typed is passed on to it.
    """
    import pty
    import select

    out = sys.stdout.fileno()
    master, slave = pty.openpty()
    _copy_window_size(out, master)
    previous = signal.signal(signal.SIGWINCH, lambda *_: _copy_window_size(out, master))
    try:
        process = subprocess.Popen(
            args, env=env, stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, preexec_fn=_make_stdin_the_controlling_terminal,
        )
    except BaseException:
        os.close(slave)
        os.close(master)
        signal.signal(signal.SIGWINCH, previous)
        raise
    os.close(slave)

    sys.stdout.flush()
    keyboard_settings_before = _switch_to_unbuffered_keys()
    inputs_to_pass_on = [KEYBOARD] if keyboard_settings_before else []
    waiting = True
    status.start()
    quiet_since = None
    at_line_start = False
    stopping_since = None
    try:
        # Read on while it stops: macOS holds a command's exit until its output is read.
        while True:
            try:
                while True:
                    ready, _, _ = select.select([master, *inputs_to_pass_on], [], [], 0.1)
                    if KEYBOARD in inputs_to_pass_on and KEYBOARD in ready:
                        _write_all(master, os.read(KEYBOARD, 1024))
                    if master in ready:
                        try:
                            data = os.read(master, 65536)
                        except OSError:
                            break
                        if not data:
                            break
                        shown = rewrite(data) if rewrite else data
                        _last_streamed.extend(data)
                        del _last_streamed[:-KEPT_OUTPUT_BYTES]
                        if not shown:
                            continue
                        if waiting:
                            status.stop()
                            waiting = False
                        _write_all(out, shown)
                        if _command_output_listener is not None:
                            _command_output_listener(shown)
                        quiet_since = time.monotonic()
                        text = TRAILING_COLOR_AND_CURSOR_CODES.sub(b"", data)
                        if text:
                            at_line_start = text.endswith(b"\n")
                    elif process.poll() is not None:
                        # Something it started may still hold the pty open.
                        break
                    elif stopping_since is not None and time.monotonic() - stopping_since >= KILL_AFTER_CTRL_C_SECONDS:
                        process.kill()
                    elif not waiting and at_line_start and time.monotonic() - quiet_since >= SILENCE_BEFORE_STATUS_SECONDS:
                        status.start()
                        waiting = True
                break
            except KeyboardInterrupt:
                stopping_since = stopping_since or time.monotonic()
                _interrupt(process)
        exit_code = process.wait()
        if stopping_since is not None:
            raise KeyboardInterrupt
        return exit_code
    except BaseException:
        process.kill()
        raise
    finally:
        if waiting:
            status.stop()
        if keyboard_settings_before:
            import termios

            termios.tcsetattr(KEYBOARD, termios.TCSANOW, keyboard_settings_before)
        if _command_output_listener is not None:
            _command_output_listener(None)
        signal.signal(signal.SIGWINCH, previous)
        os.close(master)
        process.wait()


def _interrupt(process):
    """Sends Ctrl-C to the command and what it started."""
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        pass


def _make_stdin_the_controlling_terminal():
    """Makes the command's stdin, its pty, the terminal it answers to."""
    import fcntl
    import termios

    fcntl.ioctl(STDIN, termios.TIOCSCTTY, 0)


def _switch_to_unbuffered_keys():
    """Switches the keyboard to key-by-key without echo. Returns the settings from before, or None without a terminal."""
    import termios
    import tty

    if not os.isatty(KEYBOARD):
        return None
    settings_before = termios.tcgetattr(KEYBOARD)
    # Ctrl-C still reaches this run rather than being passed on.
    tty.setcbreak(KEYBOARD, termios.TCSANOW)
    return settings_before


def _copy_window_size(source, target):
    import fcntl
    import termios

    try:
        fcntl.ioctl(target, termios.TIOCSWINSZ, fcntl.ioctl(source, termios.TIOCGWINSZ, b"\0" * 8))
    except OSError:
        pass


def _write_all(descriptor, data):
    while data:
        data = data[os.write(descriptor, data):]
