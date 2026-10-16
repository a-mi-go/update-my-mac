"""Finding the package managers.

A scheduled run starts with PATH=/usr/bin:/bin:/usr/sbin:/sbin, where none of
them live, so the tool adds the usual locations itself rather than relying on a
login shell having done it.
"""

import contextlib
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
    """Returns PATH with the manager locations it does not already have appended.

    This function does not mutate the provided mapping; it returns a string
    suitable for placing in a child process environment.
    """
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
    """Return a child-process environment dict with PATH extended to include
    manager locations.

    This no longer mutates os.environ; callers that need a global change can
    use the ``with_temp_path`` context manager below.
    """
    base_env = os.environ if env is None else env
    child_env = dict(base_env)
    child_env["PATH"] = path_with_managers(base_env)
    return child_env


@contextlib.contextmanager
def with_temp_path(env=None):
    """Temporarily set the process-wide PATH to include manager locations.

    Use this only when code requires a global PATH mutation for legacy reasons.
    Prefer using the dict returned by :func:`prepare` and passing that to
    subprocess callers so the change is local to the child process.
    """
    source_env = os.environ if env is None else env
    new_path = path_with_managers(source_env)
    old = os.environ.get("PATH")
    os.environ["PATH"] = new_path
    try:
        yield
    finally:
        if old is None:
            # Remove the key if it didn't exist before.
            del os.environ["PATH"]
        else:
            os.environ["PATH"] = old
