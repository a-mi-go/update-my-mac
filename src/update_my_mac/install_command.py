"""Everything setup.sh does once uv is available: settle on a name for the
command, install it, and deal with whatever in the shell config would hide it.

    python -m update_my_mac.install_command --project-dir DIR --bin-dir DIR
                                            [--calling-pid PID] [--name NAME]

Every question is asked, and every conflict decided, before anything is
installed or edited. Stopping at any point before that leaves the machine as it
was; a failed install leaves the shell config untouched.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from update_my_mac import shell_configs

DEFAULT_NAME = "update"
USABLE_NAME = re.compile(r"[A-Za-z0-9._-]+")
NAME_QUESTION = 'What should the command be called? (Enter for "update", or type another name): '

# How a clash with the shell config gets resolved. There is deliberately no
# "install it and let the definition win": the command would be unreachable.
CLEAR = "clear"
DISABLE = "disable"
RENAME = "rename"
STOP = "stop"


def build_argument_parser():
    parser = argparse.ArgumentParser(prog="./setup.sh")
    parser.add_argument("--name", help="call the command NAME instead of asking")
    parser.add_argument("--project-dir", required=True, help=argparse.SUPPRESS)
    parser.add_argument("--bin-dir", required=True, help=argparse.SUPPRESS)
    parser.add_argument("--calling-pid", type=int, help=argparse.SUPPRESS)
    return parser


def is_this_tool(path):
    """Returns whether path is this tool's command: uv's script, or a link to it."""
    try:
        with open(path, "rb") as script:
            return b"update_my_mac" in script.read(4096)
    except OSError:
        return False


def names_from_an_earlier_setup(bin_dir):
    """Returns the names an earlier run left in the bin dir, or [] on a first run."""
    installed = Path(bin_dir) / DEFAULT_NAME
    if not is_this_tool(installed):
        return []
    links = sorted(
        entry.name
        for entry in Path(bin_dir).iterdir()
        if entry.is_symlink() and os.readlink(entry) == str(installed)
    )
    return links or [DEFAULT_NAME]


def already_taken_by(name, env):
    """Returns something else answering to name: a program on PATH, or a builtin."""
    found = shutil.which(name, path=env.get("PATH", ""))
    if found and not is_this_tool(found):
        return found
    for shell in ("bash", "zsh", "fish"):
        if shell_configs.builtin_in(shell, name):
            return f"a {shell} builtin"
    return None


def ask_for_name(ask):
    return ask(NAME_QUESTION).strip() or DEFAULT_NAME


def first_name(args, ask, out, interactive):
    """Returns the name to start from: given, kept from an earlier run, or asked for."""
    if args.name:
        return args.name

    earlier = names_from_an_earlier_setup(args.bin_dir)
    if not earlier:
        return ask_for_name(ask) if interactive else DEFAULT_NAME
    if not interactive:
        return earlier[0]

    shown = ", ".join(f"[bold]{name}[/]" for name in earlier)
    out(f"Setup has run before. The command is called {shown}.")
    answer = ask("Keep it? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        return earlier[0]
    return ask_for_name(ask)


def occupied_in_bin_dir(name, bin_dir):
    """Returns whether something not ours sits where the link for name would go."""
    if name == DEFAULT_NAME:
        return False  # uv's own file, which the install replaces
    target = Path(bin_dir) / name
    installed = Path(bin_dir) / DEFAULT_NAME
    if target.is_symlink() and os.readlink(target) == str(installed):
        return False  # an earlier run's link
    return target.exists() or target.is_symlink()


def usable_name(name, bin_dir, env, ask, err, interactive):
    """Settles on a name nothing else answers to. Returns None if the person gives up."""
    while True:
        if not USABLE_NAME.fullmatch(name):
            err(f"[yellow]setup: '{escape(name)}' is not a usable command name.[/]")
        elif occupied_in_bin_dir(name, bin_dir):
            err(f"[yellow]setup: {escape(str(Path(bin_dir) / name))} already exists, so it is left alone.[/]")
        elif taken := already_taken_by(name, env):
            err(f"[yellow]setup: '{name}' is already {escape(taken)}.[/]")
        else:
            return name
        if not interactive:
            return None
        name = ask_for_name(ask)


def decide_about_shadowing(name, env, ask, out, interactive):
    """Returns how to handle definitions of name in the shell config."""
    while True:
        definitions = shell_configs.find_shadowing_definitions(name, env)
        if not definitions:
            return CLEAR, []

        out()
        out(f"[yellow]'[bold]{name}[/bold]' is already defined in your shell config:[/]")
        for definition in definitions:
            out(f"  {escape(definition.describe())}")
        if not interactive:
            out("It would hide the command. Run setup again with --name to pick")
            out("another name, or remove it first.")
            return STOP, []

        # A function spanning several lines can't be commented out safely, so
        # disabling is only offered when everything found can be.
        stuck = [definition for definition in definitions if not definition.can_disable]
        # The colour rich gives numbers in the tool's upgrade menu, so both look alike.
        out("  [bold cyan]1)[/] keep it, and call the command something else")
        if stuck:
            out("  [bold cyan]2)[/] stop here, remove it yourself, then run setup again")
        else:
            out("  [bold cyan]2)[/] disable it")
        choice = ask("> ").strip()

        if choice == "1":
            return RENAME, []
        if choice == "2" and stuck:
            for definition in stuck:
                out(f"  the {definition.kind} in {escape(str(definition.path))}:{definition.line_number}")
                out("  spans several lines, so it isn't edited automatically")
            return STOP, []
        if choice == "2":
            return DISABLE, definitions
        out("[yellow]Please answer 1 or 2.[/]")


def install_with_uv(project_dir):
    # --editable so a git pull updates the command, with no reinstall.
    return subprocess.run(["uv", "tool", "install", "--editable", str(project_dir)]).returncode == 0


def update_shell_with_uv():
    return subprocess.run(["uv", "tool", "update-shell"]).returncode == 0


def link_under_name(name, bin_dir, out):
    """Points name at the installed update."""
    target = Path(bin_dir) / name
    installed = Path(bin_dir) / DEFAULT_NAME
    if target.is_symlink():
        return  # an earlier run's link
    target.symlink_to(installed)
    out(f"  [bold]{name}[/] -> {escape(str(installed))}")


def warn_if_terminal_is_stale(name, calling_pid, env, out, now, disabled_something):
    """Points out a terminal that started before its config last changed."""
    if not disabled_something and name != DEFAULT_NAME:
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

    # Each out() is its own piece of markup, so every line opens and closes its own.
    out()
    out("[yellow]This terminal was opened before your shell config last changed, so it may[/]")
    out(f"[yellow]still hold an old '[bold]{name}[/bold]' definition.[/] Run this to clear it from this")
    out("terminal, open a new tab, or rerun setup and pick another name:")
    out(f"  [bold]{escape(shell_configs.clear_line(shell, name))}[/]")


# Where each shell's PATH is usually set from scratch, for the warning.
CONFIG_HINT = {"zsh": "~/.zshrc", "bash": "~/.bashrc", "fish": "~/.config/fish/config.fish"}


def shell_in_use(calling_pid, env):
    """zsh, bash or fish: what the calling process is, else what $SHELL says, else None."""
    shell = shell_configs.shell_of_process(calling_pid) if calling_pid is not None else None
    shell = shell or os.path.basename(env.get("SHELL", ""))
    return shell if shell in CONFIG_HINT else None


def settle_name(args, env, ask, out, err, interactive):
    """Returns (name, definitions to disable), or (None, []) to stop."""
    name = first_name(args, ask, out, interactive)
    while True:
        name = usable_name(name, args.bin_dir, env, ask, err, interactive)
        if name is None:
            return None, []
        decision, definitions = decide_about_shadowing(name, env, ask, out, interactive)
        if decision == STOP:
            return None, []
        if decision == RENAME:
            name = ask_for_name(ask)
            continue
        return name, definitions


def run(args, ask, out, err, env, interactive, now, install, update_shell):
    # uv always installs the command as `update`, whatever it ends up called, and
    # won't replace a file there it didn't create. Better said now than after
    # every question has been answered.
    installed = Path(args.bin_dir) / DEFAULT_NAME
    if installed.exists() and not is_this_tool(installed):
        err(f"[yellow]setup: {escape(str(installed))} belongs to another program.[/]")
        err("uv installs this tool under that name, so move it aside first.")
        return 1

    name, to_disable = settle_name(args, env, ask, out, err, interactive)
    if name is None:
        return 1

    path_missing = args.bin_dir not in env.get("PATH", "").split(os.pathsep)
    fix_path = False
    if path_missing and interactive:
        answer = ask(f"{args.bin_dir} is not on your PATH. Add it with 'uv tool update-shell'? [Y/n] ")
        fix_path = answer.strip().lower() in ("", "y", "yes")

    # Only now that every question is answered does anything change.
    if not install(args.project_dir):
        err("[yellow]setup: installing with uv failed; nothing else was changed.[/]")
        return 1

    for change in shell_configs.disable(to_disable):
        out(f"  {escape(change)}")
    if name != DEFAULT_NAME:
        link_under_name(name, args.bin_dir, out)

    path_fixed = path_missing and fix_path and update_shell()
    shell = shell_in_use(args.calling_pid, env) if path_fixed else None
    config_resets_path = False
    if shell:
        out()
        out("Checking that a new terminal finds it. This reads your whole shell config and can take a moment.")
        config_resets_path = shell_configs.found_in_new_terminal(shell, name, args.bin_dir, env) is False
    if config_resets_path:
        out()
        out(f"[yellow]A new terminal still won't find '[bold]{name}[/bold]'.[/] Something in your shell config")
        out(f"(for {shell}, usually [bold]{CONFIG_HINT[shell]}[/]) sets PATH from scratch, for example")
        out("[bold]export PATH=/usr/local/bin:/usr/bin[/] without the old value. Make it keep the old")
        out(f"value, or add [bold]{escape(args.bin_dir)}[/] to it.")
    elif path_missing and not path_fixed:
        out()
        out(f"[yellow]Add {escape(args.bin_dir)} to your PATH[/], or run: [bold]uv tool update-shell[/]")

    warn_if_terminal_is_stale(name, args.calling_pid, env, out, now, bool(to_disable))

    out()
    if config_resets_path:
        out(f"[yellow]Installed, but a new terminal won't find '{name}' until that is fixed.[/]")
    elif path_fixed:
        out(f"[green]Done.[/] Open a new terminal, then try: [bold]{name} --check[/]")
    elif path_missing:
        out(f"[yellow]Installed, but '{name}' won't be found until that is on your PATH.[/]")
    else:
        out(f"[green]Done.[/] Try: [bold]{name} --check[/]")
    return 0


def main(argv=None, ask=input, out=None, err=None, env=None, interactive=None, now=None,
         install=install_with_uv, update_shell=update_shell_with_uv):
    args = build_argument_parser().parse_args(argv)
    # Plain text when it isn't a terminal or NO_COLOR is set, as in the tool.
    # soft_wrap, so a long path stays on one line and can still be copied.
    out = out or Console(highlight=False, soft_wrap=True).print
    err = err or Console(stderr=True, highlight=False, soft_wrap=True).print
    env = os.environ if env is None else env
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    now = time.time() if now is None else now

    try:
        return run(args, ask, out, err, env, interactive, now, install, update_shell)
    except KeyboardInterrupt:
        # Every question comes before the install, so stopping here changes nothing.
        out()
        err("[yellow]Setup stopped.[/] Nothing was installed or changed.")
        return 130
    except EOFError:
        out()
        err("[yellow]Setup stopped: no more input to answer with.[/] Nothing was changed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
