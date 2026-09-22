"""What in zsh, bash or fish configuration would shadow a command.

An alias, a shell function or a fish abbreviation all win over anything on
PATH, so a leftover one quietly hides the installed command.
"""

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

ZSH_CONFIGS = (".zshenv", ".zprofile", ".zshrc", ".zlogin")
BASH_CONFIGS = (".bashrc", ".bash_profile", ".profile")


@dataclass
class ShadowingDefinition:
    kind: str  # "alias", "function" or "abbreviation"
    path: Path
    line_number: int = 0  # 0: the whole file is the definition
    can_disable: bool = True

    def describe(self):
        if self.line_number:
            return f"{self.kind} in {self.path}:{self.line_number}"
        return f"{self.kind} in {self.path}"


def fish_config_dir(env):
    base = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME", ""), ".config")
    return Path(base) / "fish"


def _matching_lines(path, patterns):
    """(line number, kind, can_disable) for each line matching one of patterns."""
    if not path.is_file():
        return []
    found = []
    for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        for kind, pattern, can_disable in patterns:
            if pattern.search(line):
                found.append((number, kind, can_disable))
                break
    return found


def _posix_patterns(name):
    word = re.escape(name)
    return [
        ("alias", re.compile(rf"^\s*alias\s+(-\w+\s+)*{word}="), True),
        # A function spans lines, so commenting out its first one would leave
        # the rest dangling. Those are pointed out, not edited.
        ("function", re.compile(rf"^\s*(function\s+{word}\b|{word}\s*\(\s*\))"), False),
    ]


def _fish_patterns(name):
    word = re.escape(name)
    return [
        ("alias", re.compile(rf"^\s*alias\s+{word}(=|\s)"), True),
        (
            "abbreviation",
            # Options before the name, but not an abbr --erase line.
            re.compile(rf"^\s*abbr(\s+-(?!e\b|-erase\b)\S+)*\s+{word}(\s|$)"),
            True,
        ),
        ("function", re.compile(rf"^\s*function\s+{word}(\s|;|$)"), False),
    ]


def find_shadowing_definitions(name, env):
    home = Path(env.get("HOME", ""))
    found = []

    for file_name in ZSH_CONFIGS + BASH_CONFIGS:
        path = home / file_name
        for number, kind, can_disable in _matching_lines(path, _posix_patterns(name)):
            found.append(ShadowingDefinition(kind, path, number, can_disable))

    fish_dir = fish_config_dir(env)
    fish_files = [fish_dir / "config.fish", *sorted((fish_dir / "conf.d").glob("*.fish"))]
    for path in fish_files:
        for number, kind, can_disable in _matching_lines(path, _fish_patterns(name)):
            found.append(ShadowingDefinition(kind, path, number, can_disable))

    # fish autoloads functions/<name>.fish the first time <name> is used.
    function_file = fish_dir / "functions" / f"{name}.fish"
    if function_file.is_file():
        found.append(ShadowingDefinition("function", function_file))

    return found


def disable(definitions, now=None):
    """Comment out single lines, move function files aside. Returns what changed.

    Each file is backed up once before its lines change, so two definitions in
    the same file don't leave a backup that already has the first edit in it.
    """
    stamp = time.strftime("%Y%m%d%H%M%S", time.localtime(now))
    changes = []
    lines_by_file = {}

    for definition in definitions:
        if not definition.can_disable:
            continue
        if definition.line_number == 0:
            moved_to = definition.path.with_name(f"{definition.path.name}.disabled-{stamp}")
            definition.path.rename(moved_to)
            changes.append(f"moved {definition.path} to {moved_to.name}")
        else:
            lines_by_file.setdefault(definition.path, []).append(definition.line_number)

    for path, numbers in lines_by_file.items():
        backup = path.with_name(f"{path.name}.bak-{stamp}")
        counter = 1
        while backup.exists():
            backup = path.with_name(f"{path.name}.bak-{stamp}-{counter}")
            counter += 1
        shutil.copy2(path, backup)
        lines = path.read_text().splitlines(keepends=True)
        for number in numbers:
            lines[number - 1] = "# " + lines[number - 1]
        path.write_text("".join(lines))
        changes.append(f"commented out {path} (kept a copy as {backup.name})")

    return changes


def shell_of_process(pid):
    """zsh, bash or fish if that process is one of them, else None."""
    try:
        command = subprocess.run(
            ["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        return None
    # A login shell shows up as "-zsh".
    name = os.path.basename(command).lstrip("-")
    return name if name in ("zsh", "bash", "fish") else None


def seconds_since_start(pid):
    """How long a process has been running, from ps's elapsed time.

    Elapsed time rather than the start date, because ps writes the date in the
    user's language, and "Mo. 21 Sep." is no fun to parse.
    """
    try:
        elapsed = subprocess.run(
            ["ps", "-o", "etime=", "-p", str(pid)], capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        return None
    return parse_elapsed(elapsed)


def parse_elapsed(elapsed):
    """ps's [[dd-]hh:]mm:ss in seconds, or None for anything else."""
    if not re.fullmatch(r"(\d+-)?(\d+:){1,2}\d+", elapsed or ""):
        return None
    days = 0
    if "-" in elapsed:
        day_part, elapsed = elapsed.split("-", 1)
        days = int(day_part)
    parts = [int(part) for part in elapsed.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    hours, minutes, seconds = parts
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def config_files_for(shell, name, env):
    home = Path(env.get("HOME", ""))
    if shell == "zsh":
        return [home / file_name for file_name in ZSH_CONFIGS]
    if shell == "bash":
        return [home / file_name for file_name in BASH_CONFIGS]
    if shell == "fish":
        fish_dir = fish_config_dir(env)
        return [
            fish_dir / "config.fish",
            *(fish_dir / "conf.d").glob("*.fish"),
            fish_dir / "functions" / f"{name}.fish",
        ]
    return []


def config_changed_since(started_at, files):
    changed = [path.stat().st_mtime for path in files if path.exists()]
    return bool(changed) and max(changed) > started_at


def clear_line(shell, name):
    """What to type into an already open terminal to forget an old definition."""
    if shell == "fish":
        return f"functions -e {name}; abbr -e {name} 2>/dev/null"
    return f"unalias {name} 2>/dev/null; unset -f {name} 2>/dev/null; hash -r"


def builtin_in(shell, name):
    """Whether shell has a builtin or keyword called name, if shell is installed."""
    if shutil.which(shell) is None:
        return False
    # The name travels as an argument, never as part of the script.
    scripts = {
        "bash": [
            "bash", "-c",
            'case "$(type -t "$1")" in builtin|keyword) exit 0;; esac; exit 1',
            "_", name,
        ],
        "zsh": [
            "zsh", "-fc",
            'case "$(whence -w -- "$1")" in *": builtin"|*": reserved") exit 0;; esac; exit 1',
            "_", name,
        ],
        "fish": ["fish", "--no-config", "-c", "builtin -q -- $argv[1]", name],
    }
    try:
        return subprocess.run(scripts[shell], capture_output=True).returncode == 0
    except OSError:
        return False
