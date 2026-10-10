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

MANAGERS = (AppStore(), Homebrew(), Npm(), Pnpm())


def by_key(key, managers=MANAGERS):
    return next(manager for manager in managers if manager.key == key)


def installed(shell, managers=MANAGERS):
    return [one for one in managers if shell.find_executable(one.command) is not None]


def check_what_is_outdated(shell, managers=MANAGERS):
    reports = (one.outdated(shell) for one in managers)
    return [report for report in reports if report is not None]


def check_themselves(shell, managers=MANAGERS):
    updates = (one.check_self(shell) for one in managers)
    return [update for update in updates if update is not None]


def still_behind(behind, updated):
    """Returns the managers that did not update, counting an unanswered check."""
    return [one for one in behind if one.error_message or one.key not in updated]
