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
#
# This is a rule of thumb and it cannot be anything else, because nothing in
# a version string says which scheme it belongs to. What it is built for is
# to refuse rather than to guess: a pair it wrongly refuses is described as
# "no telling which is newer", while a pair it wrongly accepts would be
# called an update or a downgrade, and one of those gets acted on.
FAR_APART = 10

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

    smaller, larger = sorted((mine[0], yours[0]))
    if smaller == 0:
        return larger < FAR_APART
    return larger <= smaller * FAR_APART


def is_newer(candidate, than):
    """Whether `candidate` is a later version than `than`, as far as anyone can tell."""
    if not known(than) or not known(candidate) or same(than, candidate):
        return False
    if not comparable(than, candidate):
        return False
    return numbers_in(than) < numbers_in(candidate)


def any_version_matches(ours, theirs):
    """Whether any of our versions is the same release as `theirs`.

    An app gives two: the version it shows a person and the build behind it.
    A recipe can name either one, so comparing only the first can call an app
    outdated when its build already matches.
    """
    return any(known(one) and same(one, theirs) for one in ours)
