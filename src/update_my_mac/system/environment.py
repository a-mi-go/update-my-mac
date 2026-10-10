"""Finding the package managers.

A scheduled run starts with PATH=/usr/bin:/bin:/usr/sbin:/sbin, where none of
them live, so the tool adds the usual locations itself rather than relying on a
login shell having done it.
"""

import os

PREFIXES = ("/opt/homebrew", "/usr/local", "/opt/local")

# Set UPDATE_MY_MAC_PREFIXES to look somewhere else entirely, such as a Homebrew
# in an unusual place or a Nix profile, or to an empty string to look nowhere.
PREFIX_OVERRIDE = "UPDATE_MY_MAC_PREFIXES"


def prefixes(env):
    configured = env.get(PREFIX_OVERRIDE)
    if configured is None:
        return PREFIXES
    return tuple(entry for entry in configured.split(os.pathsep) if entry)


def manager_directories(env):
    """Returns everywhere a package manager might be, most personal first."""
    home = env.get("HOME", "")
    # pnpm refuses to run unless its own global bin directory is on PATH.
    pnpm_home = env.get("PNPM_HOME") or os.path.join(home, "Library", "pnpm")

    directories = [
        pnpm_home,
        os.path.join(pnpm_home, "bin"),
        os.path.join(home, ".local", "bin"),
        os.path.join(home, ".cargo", "bin"),
    ]
    for prefix in prefixes(env):
        directories.append(os.path.join(prefix, "bin"))
        directories.append(os.path.join(prefix, "sbin"))
    return directories


def path_with_managers(env, exists=os.path.isdir):
    """Returns PATH with the manager locations it does not already have appended."""
    entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    for directory in manager_directories(env):
        # Absolute only: without HOME these come out relative, and a relative
        # PATH entry runs whatever the current directory happens to contain.
        if not os.path.isabs(directory) or directory in entries:
            continue
        if exists(directory):
            entries.append(directory)
    return os.pathsep.join(entries)


def prepare(env=None):
    env = os.environ if env is None else env
    env["PATH"] = path_with_managers(env)
