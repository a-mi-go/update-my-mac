"""Comparing two version strings written by people who never agreed on one way.

An app reports what its own developer typed into Info.plist, a Homebrew
recipe carries a build number after a comma, and a Sparkle feed names
whatever the release notes call it. None of it is semver.
"""

import re

# A version starting at a year and one starting at a small number are two
# different schemes, not one ahead of the other. Foxit reports 2026.1.1.70276
# where its recipe says 14.0.8.69494, and neither is behind.
A_YEAR = 1900
A_COUNTER = 100

UNKNOWN = "?"


def numbers_in(version):
    return [int(part) for part in re.findall(r"\d+", version)]


def known(version):
    return bool(version) and version != UNKNOWN


def same(ours, theirs):
    """Whether the two name the same release.

    A recipe often carries a build number after a comma, such as
    "4.92.0,240144", where the app reports only "4.92.0".
    """
    return ours.strip() == theirs.split(",")[0].strip()


def comparable(ours, theirs):
    """Whether the two are numbered the same way, so one can be ahead at all."""
    mine, yours = numbers_in(ours), numbers_in(theirs)
    if not mine or not yours:
        return False
    starts = sorted((mine[0], yours[0]))
    return not (starts[0] < A_COUNTER and starts[1] >= A_YEAR)


def is_newer(candidate, than):
    """Whether `candidate` is a later version than `than`, as far as anyone can tell."""
    if not known(than) or not known(candidate) or same(than, candidate):
        return False
    if not comparable(than, candidate):
        return False
    return numbers_in(than) < numbers_in(candidate)
