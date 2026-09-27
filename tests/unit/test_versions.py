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


def test_a_leading_number_ten_times_the_other_is_not_compared():
    # Refusing costs a sentence saying nobody can tell. Guessing wrong here
    # would call a downgrade an update.
    assert not versions.comparable("1.6.0", "12.0.0")
    assert not versions.comparable("5.0.6", "20210402")


def test_an_ordinary_jump_in_the_leading_number_is_still_compared():
    assert versions.comparable("9.0.4", "10.0.1")
    assert versions.is_newer("10.0.1", than="9.0.4")
    assert versions.comparable("136.0", "137.0")


def test_a_version_starting_at_zero_is_compared_with_its_neighbours():
    assert versions.comparable("0.62.0", "0.63.0")
    assert versions.comparable("0.9", "5.0")
    # But not with something out of a different world.
    assert not versions.comparable("0.9", "2026.1")


def test_the_same_scheme_is_compared():
    assert versions.comparable("4.91.0", "4.92.0,240144")
    assert versions.comparable("26.831.21537", "26.623.141536")


def test_a_version_with_no_numbers_in_it_is_not_compared():
    assert not versions.comparable("beta", "1.0")
