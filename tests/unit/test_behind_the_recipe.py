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
        [app("BetterDisplay", "5.0.5")],
        index(BetterDisplay=("betterdisplay", "5.0.6")),
        {"betterdisplay": "5.0.6"},
    )

    assert [item.describe() for item in found] == ["BetterDisplay  5.0.5 → 5.0.6"]


def test_an_app_homebrew_never_installed_is_not_one_of_these():
    # It has a recipe but is somebody else's app. The way in is the handover,
    # and an upgrade has nothing to work with.
    found = behind_the_recipe.find(
        [app("BetterDisplay", "5.0.5")], index(BetterDisplay=("betterdisplay", "5.0.6")), {}
    )

    assert found == []


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


def behind_item(name="BetterDisplay", app_version="5.0.5", cask_version="5.0.6",
                recorded="5.0.6"):
    app = InstalledApp(name, app_version, Path(f"/Applications/{name}.app"))
    return behind_the_recipe.Behind(app, Cask(name.lower(), "https://x.test/", cask_version),
                                    recorded)


def test_a_version_homebrew_wrote_down_but_never_installed_needs_a_reinstall():
    # --adopt registered 5.0.6 while the app on disk stayed 5.0.5, so both
    # brew outdated and --greedy have nothing to say about it ever again.
    item = behind_item(recorded="5.0.6")

    assert item.wrongly_recorded
    assert behind_the_recipe.to_reinstall([item]) == ["betterdisplay"]
    assert behind_the_recipe.to_upgrade([item]) == []


def test_a_cask_homebrew_knows_is_old_only_needs_a_greedy_upgrade():
    item = behind_item(recorded="5.0.5")

    assert not item.wrongly_recorded
    assert behind_the_recipe.to_upgrade([item]) == ["betterdisplay"]
    assert behind_the_recipe.to_reinstall([item]) == []


def test_what_homebrew_wrote_down_is_carried_into_the_finding():
    apps = [InstalledApp("BetterDisplay", "5.0.5", Path("/Applications/BetterDisplay.app"))]

    class Casks:
        def for_app(self, path):
            return Cask("betterdisplay", "https://x.test/", "5.0.6")

    found = behind_the_recipe.find(apps, Casks(), {"betterdisplay": "5.0.6"})

    assert found[0].recorded == "5.0.6"
    assert found[0].wrongly_recorded


def test_an_app_counted_differently_from_its_recipe_is_not_called_behind():
    # Foxit reports 2026.1.1.70276 where its recipe says 14.0.8.69494. Listing
    # it as older would send someone off to install a version that is not
    # newer, and nothing in either string says which scheme it belongs to.
    found = behind_the_recipe.find(
        [app("Foxit PDF Editor", "2026.1.1.70276")],
        index(**{"Foxit PDF Editor": ("foxit-pdf-editor", "14.0.8.69494")}),
        {"foxit-pdf-editor": "14.0.8.69494"},
    )

    assert found == []


def test_a_recipe_dated_where_the_app_counts_is_not_called_ahead():
    # Juice was reported as 1.0.1 → 2017.06.08170217, which meant nothing.
    found = behind_the_recipe.find(
        [app("Juice", "1.0.1")],
        index(Juice=("juice", "2017.06.08170217")),
        {"juice": "2017.06.08170217"},
    )

    assert found == []
