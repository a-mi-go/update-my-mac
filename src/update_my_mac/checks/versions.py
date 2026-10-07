"""Comparing two version strings written by people who never agreed on one way.

An app reports what its own developer typed into Info.plist, a Homebrew
recipe carries a build number after a comma, and a Sparkle feed names
whatever the release notes call it. None of it is semver.
"""

import re

# Two versions are only worth comparing when their leading numbers are of
# about the same size. A date-based 2026.1.1.70276 and a counted 14.0.8.69494
# say nothing about each other: one starts from a year, the other from a small
# number, and neither is behind.
COMPARABLE_WITHIN_FACTOR = 10

UNKNOWN = "?"


def numbers_in(version):
    return [int(part) for part in re.findall(r"\d+", version)]


def known(version):
    return bool(version) and version != UNKNOWN


def same_release(ours, theirs):
    """Returns whether they name the same release, ignoring a build after a comma."""
    return ours.strip() == theirs.split(",")[0].strip()


def comparable(ours, theirs):
    """Returns whether the two are numbered the same way."""
    mine, yours = numbers_in(ours), numbers_in(theirs)
    if not mine or not yours:
        return False

    smaller, larger = sorted((mine[0], yours[0]))
    if smaller == 0:
        return larger < COMPARABLE_WITHIN_FACTOR
    return larger <= smaller * COMPARABLE_WITHIN_FACTOR


def is_newer(candidate, than):
    """Returns whether `candidate` is a later version than `than`."""
    if not known(than) or not known(candidate) or same_release(than, candidate):
        return False
    if not comparable(than, candidate):
        return False
    return numbers_in(than) < numbers_in(candidate)


def any_version_matches(ours, theirs):
    """Returns whether any of our versions is the same release as `theirs`."""
    return any(known(one) and same_release(one, theirs) for one in ours)
