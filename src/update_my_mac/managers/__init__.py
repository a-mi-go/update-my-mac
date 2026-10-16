"""Every package manager this tool drives: a module each, all registered here."""

from update_my_mac.managers.app_store import AppStore
from update_my_mac.managers.homebrew import Homebrew
from update_my_mac.managers.manager import (
    CheckFailed,
    ManagerReport,
    ManagerUpdate,
    PackageManager,
)
from update_my_mac.managers.npm import Npm
from update_my_mac.managers.pnpm import Pnpm
from update_my_mac.system import shell

MANAGERS = (AppStore(), Homebrew(), Npm(), Pnpm())


def by_key(key):
    return next(manager for manager in MANAGERS if manager.key == key)


def installed():
    return [one for one in MANAGERS if shell.find_executable(one.command) is not None]


def check_what_is_outdated():
    reports = (one.outdated() for one in MANAGERS)
    return [report for report in reports if report is not None]


def check_themselves(managers):
    updates = (one.check_self() for one in managers)
    return [update for update in updates if update is not None]


def still_behind(behind, updated):
    """Returns the managers that did not update, counting an unanswered check."""
    return [one for one in behind if one.error_message or one.key not in updated]
