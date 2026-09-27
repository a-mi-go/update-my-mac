"""Apps that are older than the Homebrew recipe, which Homebrew never says."""

from pathlib import Path

from update_my_mac import behind_the_recipe
from update_my_mac.cask_index import Cask, CaskIndex
from update_my_mac.installed_apps import InstalledApp


def app(name, version):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"))


def index(**by_app):
    return CaskIndex({
        f"{name}.app": {"token": token, "homepage": "", "version": version}
        for name, (token, version) in by_app.items()
    })


def test_an_app_older_than_its_recipe_is_found():
    found = behind_the_recipe.find(
        [app("BetterDisplay", "5.0.5")], index(BetterDisplay=("betterdisplay", "5.0.6"))
    )

    assert [item.describe() for item in found] == ["BetterDisplay  5.0.5 → 5.0.6"]


def test_an_app_newer_than_its_recipe_is_left_alone():
    # The Codex recipe sat weeks behind the app.
    found = behind_the_recipe.find(
        [app("Codex", "26.831.21537")], index(Codex=("codex-app", "26.623.141536"))
    )

    assert found == []


def test_a_build_number_after_the_comma_is_not_a_difference():
    found = behind_the_recipe.find(
        [app("Cursor", "3.22.7")], index(Cursor=("cursor", "3.22.7,37076c6c"))
    )

    assert found == []


def test_an_app_no_recipe_knows_is_not_reported():
    assert behind_the_recipe.find([app("TokenEater", "5.13.0")], index()) == []


def test_an_unreadable_version_is_not_compared():
    found = behind_the_recipe.find(
        [app("resolume arena", "?")], index(**{"resolume arena": ("resolume-arena", "7.2")})
    )

    assert found == []


def test_the_comparison_reads_numbers_and_not_text():
    assert behind_the_recipe.is_behind("5.0.5", "5.0.6")
    assert behind_the_recipe.is_behind("2.9", "2.10")
    assert not behind_the_recipe.is_behind("2.10", "2.9")
    assert not behind_the_recipe.is_behind("", "5.0.6")
