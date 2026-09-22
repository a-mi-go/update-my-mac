"""What setup.sh hands over to once the command is installed: choose its name,
deal with anything in the shell config that would shadow it, and say what is
left to do.

    python -m update_my_mac.finish_setup --bin-dir DIR [--calling-pid PID] [--name NAME]
"""

import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

from update_my_mac import shell_configs

USABLE_NAME = re.compile(r"[A-Za-z0-9._-]+")
NAME_QUESTION = 'What should the command be called? (Enter for "update", or type another name): '


def build_argument_parser():
    parser = argparse.ArgumentParser(prog="./setup.sh")
    parser.add_argument("--name", help="call the command NAME instead of asking")
    parser.add_argument("--bin-dir", required=True, help=argparse.SUPPRESS)
    parser.add_argument("--calling-pid", type=int, help=argparse.SUPPRESS)
    return parser


def is_this_tool(path, bin_dir):
    installed = Path(bin_dir) / "update"
    if installed.exists() and Path(path).resolve() == installed.resolve():
        return True
    # Another copy of it, such as a development environment's console script.
    try:
        with open(path, "rb") as script:
            return b"update_my_mac" in script.read(4096)
    except OSError:
        return False


def already_taken_by(name, bin_dir, env):
    """Something else answering to name: a program on PATH, or a builtin."""
    found = shutil.which(name, path=env.get("PATH", ""))
    if found and not is_this_tool(found, bin_dir):
        return found
    for shell in ("bash", "zsh", "fish"):
        if shell_configs.builtin_in(shell, name):
            return f"a {shell} builtin"
    return None


def ask_for_name(ask):
    return ask(NAME_QUESTION).strip() or "update"


def link_under_name(name, bin_dir, out):
    """Point name at the installed update. False if something else is there."""
    target = Path(bin_dir) / name
    installed = Path(bin_dir) / "update"
    if target.is_symlink() and os.readlink(target) == str(installed):
        return True  # an earlier run already did this
    if target.exists() or target.is_symlink():
        out(f"setup: {target} already exists — not touching it.", file=sys.stderr)
        return False
    target.symlink_to(installed)
    out(f"  {name} -> {installed}")
    return True


def choose_name(name, bin_dir, env, ask, out, interactive):
    """Settle on a name that nothing else already answers to. None to give up."""
    while True:
        if not USABLE_NAME.fullmatch(name):
            out(f"setup: '{name}' is not a usable command name.", file=sys.stderr)
        elif taken := already_taken_by(name, bin_dir, env):
            out(f"setup: '{name}' is already {taken}.", file=sys.stderr)
        else:
            return name
        if not interactive:
            return None
        name = ask_for_name(ask)


# What resolve_shadowing can end in. There is deliberately no "install it and
# let the definition win": the command would be installed but unreachable.
CLEAR = "clear"
DISABLED = "disabled"
RENAME = "rename"
STOP = "stop"


def resolve_shadowing(name, env, ask, out, interactive):
    """Deal with definitions of name in the shell config, until none is left."""
    while True:
        definitions = shell_configs.find_shadowing_definitions(name, env)
        if not definitions:
            return CLEAR

        out()
        out(f"'{name}' is already defined in your shell config:")
        for definition in definitions:
            out(f"  {definition.describe()}")
        if not interactive:
            out("It would hide the command. Run setup again with --name to pick")
            out("another name, or remove it first.")
            return STOP

        # A function spanning several lines can't be commented out safely, so
        # disabling is only offered when everything found can be.
        stuck = [definition for definition in definitions if not definition.can_disable]
        out("  1) keep it, and call the command something else")
        if stuck:
            out("  2) stop here — remove it yourself, then run setup again")
        else:
            out("  2) disable it")
        choice = ask("> ").strip()

        if choice == "1":
            return RENAME
        if choice == "2" and stuck:
            for definition in stuck:
                out(f"  the {definition.kind} in {definition.path}:{definition.line_number}")
                out("  spans several lines, so it isn't edited automatically")
            return STOP
        if choice == "2":
            for change in shell_configs.disable(definitions):
                out(f"  {change}")
            return DISABLED
        out("Please answer 1 or 2.")


def warn_if_terminal_is_stale(name, calling_pid, env, out, now, disabled_something):
    """Point out a terminal holding a definition its config no longer has.

    A definition lives in the memory of the shell that loaded it, and nothing
    outside that shell can ask it what it has. What can be told is whether it
    started before its config last changed.

    That alone would also flag a name the user just made up, which no terminal
    can be holding. So it only counts when a definition was disabled just now,
    or for the default name, which earlier installs and setups may have used.
    """
    if not disabled_something and name != "update":
        return
    if calling_pid is None:
        return
    shell = shell_configs.shell_of_process(calling_pid)
    elapsed = shell_configs.seconds_since_start(calling_pid)
    if shell is None or elapsed is None:
        return

    started_at = now - elapsed
    files = shell_configs.config_files_for(shell, name, env)
    if not shell_configs.config_changed_since(started_at, files):
        return
    if shell_configs.find_shadowing_definitions(name, env):
        return

    out()
    out("This terminal was opened before your shell config last changed, so it may")
    out(f"still hold an old '{name}' definition. Run this to clear it from this")
    out("terminal, open a new tab, or rerun setup and pick another name:")
    out(f"  {shell_configs.clear_line(shell, name)}")


def main(argv=None, ask=input, out=print, env=None, interactive=None, now=None):
    args = build_argument_parser().parse_args(argv)
    env = os.environ if env is None else env
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    now = time.time() if now is None else now

    name = args.name
    if name is None:
        name = ask_for_name(ask) if interactive else "update"

    disabled_something = False
    while True:
        name = choose_name(name, args.bin_dir, env, ask, out, interactive)
        if name is None:
            return 1
        outcome = resolve_shadowing(name, env, ask, out, interactive)
        if outcome == STOP:
            return 1
        if outcome == RENAME:
            name = ask_for_name(ask)
            continue
        disabled_something = outcome == DISABLED
        break

    if name != "update" and not link_under_name(name, args.bin_dir, out):
        return 1

    if args.bin_dir not in env.get("PATH", "").split(os.pathsep):
        out()
        out(f"Add {args.bin_dir} to your PATH, or run: uv tool update-shell")

    warn_if_terminal_is_stale(name, args.calling_pid, env, out, now, disabled_something)

    out()
    out(f"Done. Try: {name} --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
