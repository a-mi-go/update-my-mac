"""Installed packages Homebrew has doubts about, which `brew outdated` never mentions.

A version scheme that went from build 64 to 3.4.1 reads as newer, so the
package is never called outdated. A disabled package is skipped by every
upgrade. An app thrown away in the Finder stays recorded, and its upgrade
fails. A formula from a third-party tap can also have its later major version
under another name, in its own tap or in homebrew/core, which no upgrade of the
installed one ever reaches. None of it shows up unless Homebrew is asked about
each package.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from update_my_mac.checks import versions
from update_my_mac.managers.homebrew import brew

DIFFERS, DISABLED, DEPRECATED, APP_MISSING = "differs", "disabled", "deprecated", "app missing"
SUCCESSOR, NEWER_IN_CORE = "successor", "newer in core"
VERSIONED_NAME = re.compile(r"(?P<base>.+?)(?:-v|@)(?P<major>\d+)")


@dataclass
class Flagged:
    name: str
    kind: str
    is_cask: bool = False
    installed: str = ""
    available: str = ""
    reason: str = ""
    switch_to: str = ""


def find(installed, already_reported=()):
    """Returns what Homebrew flagged in its description of the installed packages."""
    found = [_formula(one) for one in installed.get("formulae", []) if _is_installed(one)]
    found += [_cask(one) for one in installed.get("casks", []) if one.get("installed")]
    return _not_reported(found, already_reported)


def successors_in_tap(installed, taps, already_reported=()):
    """Returns the third-party formulae whose tap offers a later major version as a formula of its own."""
    tap_names = {tap.get("name"): tap.get("formula_names") or [] for tap in taps}
    found = [_successor(formula, tap_names.get(formula.get("tap"), [])) for formula in _third_party(installed)]
    return _not_reported(found, already_reported)


def names_also_in_core(installed, taps):
    """Returns the names of third-party formulae that homebrew/core has a formula of as well."""
    core = next((set(tap.get("formula_names") or []) for tap in taps if tap.get("name") == brew.CORE_TAP), set())
    return {formula["name"] for formula in _third_party(installed) if formula["name"] in core}


def newer_in_core(installed, in_core, already_reported=()):
    """Returns the third-party formulae of which homebrew/core has a later major version under the same name."""
    latest = {
        formula.get("name"): (formula.get("versions") or {}).get("stable")
        for formula in in_core.get("formulae", [])
    }
    found = [_newer_in_core(formula, latest.get(formula["name"])) for formula in _third_party(installed)]
    return _not_reported(found, already_reported)


def casks_missing_their_app(described):
    """Returns the tokens of the installed casks in Homebrew's description whose app is no longer there."""
    return {
        cask.get("token", "") for cask in described.get("casks", [])
        if cask.get("installed") and _app_is_missing(cask)
    }


def _not_reported(found, already_reported):
    return [item for item in found if item and brew.without_tap(item.name) not in already_reported]


def _third_party(installed):
    """Returns the installed, unpinned release formulae from taps other than homebrew/core."""
    return [
        formula for formula in installed.get("formulae", [])
        if _is_installed(formula) and formula.get("tap") != brew.CORE_TAP and not formula.get("pinned")
        and not _held_version(formula).startswith("HEAD")
    ]


def _held_version(formula):
    return _without_revision(formula["installed"][-1].get("version", ""))


def _successor(formula, tap_formula_names):
    """Returns the flag for a later major version the tap names separately, or None."""
    name, held = formula["name"], _held_version(formula)
    major = _major(held)
    if major is None or VERSIONED_NAME.fullmatch(name):
        return None

    later = {}
    for full_name in tap_formula_names:
        match = VERSIONED_NAME.fullmatch(brew.without_tap(full_name))
        if match and match["base"] == name and int(match["major"]) > major:
            later[int(match["major"])] = full_name
    if not later:
        return None

    successor = later[max(later)]
    reason = f"a later major version is the formula {brew.without_tap(successor)}"
    return Flagged(formula.get("full_name") or name, SUCCESSOR, installed=held, reason=reason, switch_to=successor)


def _newer_in_core(formula, latest):
    held = _held_version(formula)
    if not latest or not versions.is_newer(latest, held) or _major(latest) <= _major(held):
        return None
    return Flagged(
        formula.get("full_name") or formula["name"], NEWER_IN_CORE, installed=held, available=latest,
        reason=f"{brew.CORE_TAP} has {latest} under the same name", switch_to=f"{brew.CORE_TAP}/{formula['name']}",
    )


def _major(version):
    numbers = versions.numbers_in(version)
    return numbers[0] if numbers else None


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
    if _app_is_missing(cask):
        return Flagged(token, APP_MISSING, True, cask["installed"])
    if cask.get("disabled"):
        return Flagged(token, DISABLED, True, cask["installed"], reason=_reason(cask, "disable"))
    if cask.get("deprecated"):
        return Flagged(token, DEPRECATED, True, cask["installed"],
                       reason=_reason(cask, "deprecation"))
    return None


def _app_is_missing(cask):
    """Returns whether an app Homebrew put in place for the cask is no longer there."""
    targets = [
        artifact["target"] for artifact in cask.get("artifacts", [])
        if isinstance(artifact, dict) and "app" in artifact and artifact.get("target")
    ]
    return any(not Path(target).exists() for target in targets)
