"""The one place that runs external commands."""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class CommandResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int = 0


# The environment the run's commands start with. None until the run sets one.
_run_environment = None


def use_environment(env):
    """Makes every later command and lookup start from this environment."""
    global _run_environment
    _run_environment = env


def current_environment():
    """Returns the environment a command starts with."""
    return os.environ if _run_environment is None else _run_environment


def find_executable(command):
    return shutil.which(command, path=current_environment().get("PATH"))


def _for_command(env):
    """Returns the environment to run with: the one given, else the run's own."""
    return _run_environment if env is None else env


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
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(False, "", str(exc), -1)

    return CommandResult(
        proc.returncode in success_exit_codes,
        proc.stdout.strip(),
        proc.stderr.strip(),
        proc.returncode,
    )


def stream_command(args, env=None, silent_status=None):
    """Runs a command with the terminal attached.

    Returns its exit code, or None when the command never started. A status,
    which has start() and stop(), shows until the command first writes.
    """
    # Not captured: a password prompt needs the real terminal.
    env = _for_command(env)
    try:
        if silent_status is None or not sys.stdout.isatty():
            return subprocess.run(args, env=env).returncode
        return _run_until_it_writes(args, env, silent_status)
    except (OSError, subprocess.SubprocessError):
        return None


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


def _run_until_it_writes(args, env, status):
    """Runs a command whose output reaches the terminal through a pty.

    The command still sees a terminal, with its colours and progress bars. The
    status shows until its first byte, and stops before that byte is passed on.
    """
    import pty
    import select
    import signal

    out = sys.stdout.fileno()
    master, slave = pty.openpty()
    _copy_window_size(out, master)
    previous = signal.signal(signal.SIGWINCH, lambda *_: _copy_window_size(out, master))
    try:
        process = subprocess.Popen(args, env=env, stdout=slave, stderr=slave)
    except BaseException:
        os.close(slave)
        os.close(master)
        signal.signal(signal.SIGWINCH, previous)
        raise
    os.close(slave)

    sys.stdout.flush()
    status.start()
    waiting = True
    try:
        while True:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                if waiting:
                    status.stop()
                    waiting = False
                _write_all(out, data)
            elif process.poll() is not None:
                # Something it started may still hold the pty open.
                break
        return process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    finally:
        if waiting:
            status.stop()
        signal.signal(signal.SIGWINCH, previous)
        os.close(master)


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
