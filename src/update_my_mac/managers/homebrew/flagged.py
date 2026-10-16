"""Installed packages Homebrew has doubts about, which `brew outdated` never mentions.

A version scheme that went from build 64 to 3.4.1 reads as newer, so the
package is never called outdated. A disabled package is skipped by every
upgrade. Neither shows up anywhere unless Homebrew is asked about each package.
"""

import re
from dataclasses import dataclass

from update_my_mac.checks import versions

DIFFERS, DISABLED, DEPRECATED = "differs", "disabled", "deprecated"


@dataclass
class Flagged:
    name: str
    kind: str
    is_cask: bool = False
    installed: str = ""
    available: str = ""
    reason: str = ""


def find(installed, already_reported=()):
    """Returns what Homebrew flagged in its description of the installed packages."""
    found = [_formula(one) for one in installed.get("formulae", []) if _is_installed(one)]
    found += [_cask(one) for one in installed.get("casks", []) if one.get("installed")]
    return [item for item in found if item and item.name.rsplit("/", 1)[-1] not in already_reported]


def _formula(formula):
    name = formula.get("full_name") or formula.get("name", "")
    reason = _reason(formula, "disable")
    if formula.get("disabled"):
        return Flagged(name, DISABLED, reason=reason)
    if formula.get("deprecated"):
        return Flagged(name, DEPRECATED, reason=_reason(formula, "deprecation"))

    stable = (formula.get("versions") or {}).get("stable")
    held = [one.get("version", "") for one in formula["installed"]]
    if formula.get("outdated") or formula.get("pinned") or not stable:
        return None
    if any(version.startswith("HEAD") or _without_revision(version) == stable for version in held):
        return None
    # A newer version Homebrew does not know yet is no reason to go back.
    if versions.comparable(_without_revision(held[-1]), stable):
        return None
    return Flagged(name, DIFFERS, installed=held[-1], available=stable)


def _reason(package, prefix):
    reason = str(package.get(f"{prefix}_reason") or "").replace("_", " ")
    date = package.get(f"{prefix}_date")
    return f"{reason} since {date}" if reason and date else reason


def _without_revision(version):
    return re.sub(r"_\d+$", "", version)


def _is_installed(formula):
    return bool(formula.get("installed"))


def _cask(cask):
    token = cask.get("token", "")
    if cask.get("disabled"):
        return Flagged(token, DISABLED, True, cask["installed"], reason=_reason(cask, "disable"))
    if cask.get("deprecated"):
        return Flagged(token, DEPRECATED, True, cask["installed"],
                       reason=_reason(cask, "deprecation"))
    return None
