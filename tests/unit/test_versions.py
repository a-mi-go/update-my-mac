"""Comparing versions nobody numbered the same way."""

from update_my_mac import versions


def test_a_build_number_after_a_comma_is_the_same_release():
    assert versions.same("4.92.0", "4.92.0,240144")
    assert not versions.same("4.91.0", "4.92.0,240144")


def test_a_later_version_is_later():
    assert versions.is_newer("1.2.5", than="1.1")
    assert not versions.is_newer("1.1", than="1.2.5")


def test_a_version_is_not_newer_than_itself():
    assert not versions.is_newer("5.0.6", than="5.0.6")


def test_an_app_that_says_nothing_is_never_behind():
    assert not versions.is_newer("1.0", than=versions.UNKNOWN)
    assert not versions.is_newer(versions.UNKNOWN, than="1.0")
    assert not versions.is_newer("1.0", than="")


def test_two_schemes_are_not_compared_at_all():
    # Foxit counts from a year, its recipe from a small number.
    assert not versions.comparable("2026.1.1.70276", "14.0.8.69494")
    assert not versions.is_newer("14.0.8.69494", than="2026.1.1.70276")
    assert not versions.is_newer("2026.1.1.70276", than="14.0.8.69494")
    # Juice was reported as 1.0.1 → 2017.06.08170217, which meant nothing.
    assert not versions.comparable("1.0.1", "2017.06.08170217")


def test_the_same_scheme_is_compared():
    assert versions.comparable("4.91.0", "4.92.0,240144")
    assert versions.comparable("26.831.21537", "26.623.141536")


def test_a_version_with_no_numbers_in_it_is_not_compared():
    assert not versions.comparable("beta", "1.0")
