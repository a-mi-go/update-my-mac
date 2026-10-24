from update_my_mac.view.prompting import BULLET
from pathlib import Path

from fake_run import swap

import pytest

from rich.text import Text

from update_my_mac.checks import app_decisions
from update_my_mac.checks import app_updaters
from update_my_mac.checks import appcast
from update_my_mac.controller import track_apps
from update_my_mac.managers.homebrew.casks import Cask
from update_my_mac.checks.app_updaters import UpdaterStatus
from update_my_mac.checks.installed_apps import InstalledApp
from fake_terminal import Terminal


def app(name, version="1.0"):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"))


def decisions_in(tmp_path):
    return app_decisions.AppDecisions(tmp_path / "apps.json")

    # With nothing Homebrew could take over there is nothing to do in bulk, so the
    # question is skipped and the first answer is already about the first app.


ADOPT_ALL, DECIDE_AFTER_ADOPT_ALL = "1", "2"
# Inside the walk-through, for an app Homebrew cannot take over.
IGNORE, LATER, CANCEL = "1", "2", "3"
# And for one it can, where "add to Homebrew" takes the first place.
ADOPT, IGNORE_AFTER_ADOPT = "1", "2"


# The apps here are 1.0, and Homebrew can only take over the version its
# recipe already carries.
def cask(token="betterdisplay", homepage="https://example.test/", version="1.0"):
    return Cask(token, homepage, version)


def cask_for(known):
    return lambda app: known.get(app.file_stem)


def test_nothing_is_asked_when_every_app_is_accounted_for(tmp_path):
    terminal = Terminal()

    dealt_with = track_apps.ask_what_to_do([], decisions_in(tmp_path), terminal.step)

    assert len(dealt_with) == 0
    assert terminal.text == ""


def test_an_answer_that_means_nothing_is_asked_again(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("", LATER)

    dealt_with = track_apps.ask_what_to_do(
        [app("TokenEater")], decisions, terminal.step
    )

    assert len(dealt_with) == 0
    assert "Didn't catch that" in terminal.text
    assert not (tmp_path / "apps.json").exists()


def test_leaving_an_app_alone_is_remembered(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal(IGNORE)

    dealt_with = track_apps.ask_what_to_do(
        [app("TokenEater", "5.12.2")], decisions, terminal.step
    )

    assert len(dealt_with) == 1
    assert decisions_in(tmp_path).is_ignored("TokenEater")


def test_leaving_an_app_alone_is_remembered_by_its_file_name(tmp_path):
    iterm = InstalledApp("iTerm", "3.5", Path("/Applications/iTerm.app"), display_name="iTerm2")

    track_apps.ask_what_to_do([iterm], decisions_in(tmp_path), Terminal(IGNORE).step)

    assert decisions_in(tmp_path).is_ignored("iTerm")
    assert not decisions_in(tmp_path).is_ignored("iTerm2")


def test_keeping_an_app_listed_writes_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal(LATER)

    track_apps.ask_what_to_do([app("TokenEater")], decisions, terminal.step)

    assert not (tmp_path / "apps.json").exists()


def test_doing_nothing_asks_about_no_app_at_all(tmp_path):
    terminal = Terminal("3")

    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopting(True): adopt(app))
    dealt_with = track_apps.ask_what_to_do([app("BetterDisplay"), app("Other")], decisions_in(tmp_path), terminal.step, find_cask=cask_for({"BetterDisplay": cask()}))

    assert len(dealt_with) == 0
    assert "BetterDisplay" not in terminal.text


def test_nothing_to_do_in_bulk_goes_straight_into_the_walk_through(tmp_path):
    # A question with one answer is not worth asking.
    terminal = Terminal(LATER)

    track_apps.ask_what_to_do(
        [app("TokenEater")], decisions_in(tmp_path), terminal.step
    )

    assert "What should we do with them?" not in terminal.text
    assert "TokenEater" in terminal.text


def test_stopping_partway_keeps_what_was_decided_so_far(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal(IGNORE, CANCEL)

    dealt_with = track_apps.ask_what_to_do(
        [app("First"), app("Second"), app("Third")], decisions, terminal.step
    )

    assert len(dealt_with) == 1
    stored = decisions_in(tmp_path)
    assert stored.ignored_names() == ["First"]
    assert not stored.is_ignored("Third")


def test_apps_already_left_alone_are_not_asked_about_again(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("TokenEater", "5.12.2")
    terminal = Terminal()

    dealt_with = track_apps.ask_what_to_do(
        [app("TokenEater")], decisions, terminal.step
    )

    assert len(dealt_with) == 0
    assert terminal.text == ""




def test_revisiting_says_so_when_there_is_nothing_to_revisit(tmp_path):
    terminal = Terminal()

    track_apps.ask_about_the_ignored(decisions_in(tmp_path), terminal.step)

    assert "No apps are being left alone" in terminal.text


def test_an_app_can_be_brought_back(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.ignore("Beta", "2.0")
    decisions.save()
    terminal = Terminal("2")

    brought_back = track_apps.ask_about_the_ignored(decisions, terminal.step)

    assert brought_back == 1
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]
    assert "Beta will be listed again" in terminal.text


def test_answering_nothing_leaves_the_list_as_it_is(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal("0")

    brought_back = track_apps.ask_about_the_ignored(decisions, terminal.step)

    assert brought_back == 0
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]




def test_no_more_input_stops_instead_of_crashing(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal(then=EOFError)

    dealt_with = track_apps.ask_what_to_do(
        [app("TokenEater")], decisions, terminal.step
    )

    assert len(dealt_with) == 0
    assert not (tmp_path / "apps.json").exists()


def test_running_out_of_input_partway_keeps_what_was_decided(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal(IGNORE, then=EOFError)

    dealt_with = track_apps.ask_what_to_do(
        [app("First"), app("Second")], decisions, terminal.step
    )

    assert len(dealt_with) == 1
    assert decisions_in(tmp_path).ignored_names() == ["First"]


def test_running_out_of_input_while_revisiting_changes_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()

    brought_back = track_apps.ask_about_the_ignored(
        decisions, Terminal(then=EOFError).step
    )

    assert brought_back == 0
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def test_a_decision_that_cannot_be_saved_is_said_out_loud(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    decisions = app_decisions.AppDecisions(locked / "update-my-mac" / "apps.json")
    terminal = Terminal(IGNORE)

    dealt_with = track_apps.ask_what_to_do(
        [app("TokenEater")], decisions, terminal.step
    )

    assert len(dealt_with) == 1
    assert "won't be remembered" in terminal.text


def test_bringing_an_app_back_that_cannot_be_saved_says_so(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    (tmp_path / "apps.json").chmod(0o400)
    tmp_path.chmod(0o500)
    terminal = Terminal("1")

    try:
        brought_back = track_apps.ask_about_the_ignored(decisions, terminal.step)
    finally:
        tmp_path.chmod(0o700)

    assert brought_back == 0
    assert "won't be remembered" in terminal.text


def test_choosing_none_of_them_says_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal("0")

    brought_back = track_apps.ask_about_the_ignored(decisions, terminal.step)

    assert brought_back == 0
    assert "Answer a number" not in terminal.text


def test_an_answer_outside_the_list_is_pointed_out(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal("7")

    brought_back = track_apps.ask_about_the_ignored(decisions, terminal.step)

    assert brought_back == 0
    assert "Answer a number from 1 to 1" in terminal.text
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def adopting(taken, message="done"):
    def adopt(_app):
        return taken, message

    return adopt


def test_an_app_can_be_handed_to_homebrew(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal(ADOPT)

    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopting(True, "Homebrew looks after it now, as betterdisplay."): adopt(app))
    dealt_with = track_apps.ask_what_to_do([app("BetterDisplay")], decisions, terminal.step, find_cask=cask_for({"BetterDisplay": cask()}))

    assert "Homebrew looks after it now, as betterdisplay." in terminal.text
    # Handed over, so it is dealt with without being ignored.
    assert len(dealt_with) == 1
    assert decisions_in(tmp_path).ignored_names() == []


def test_an_app_with_no_recipe_is_not_offered_the_handover(tmp_path):
    terminal = Terminal(LATER)

    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopting(True): adopt(app))
    track_apps.ask_what_to_do([app("TokenEater")], decisions_in(tmp_path), terminal.step, find_cask=cask_for({}))

    assert "add to Homebrew" not in terminal.text


def test_a_failed_handover_leaves_the_app_undecided(tmp_path):
    decisions = decisions_in(tmp_path)
    # Adopting it did not work, so the same app is asked about again.
    terminal = Terminal(DECIDE_AFTER_ADOPT_ALL, ADOPT, IGNORE_AFTER_ADOPT)

    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopting(False, "Homebrew could not take it over."): adopt(app))
    dealt_with = track_apps.ask_what_to_do([app("BetterDisplay")], decisions, terminal.step, find_cask=cask_for({"BetterDisplay": cask()}))

    # The second answer still counted, so nothing was swallowed.
    assert len(dealt_with) == 1
    assert decisions_in(tmp_path).is_ignored("BetterDisplay")


def test_the_menu_says_which_cask_would_take_the_app(tmp_path):
    terminal = Terminal(DECIDE_AFTER_ADOPT_ALL, "4")

    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopting(True): adopt(app))
    track_apps.ask_what_to_do([app("BetterDisplay")], decisions_in(tmp_path), terminal.step, find_cask=cask_for({"BetterDisplay": cask()}))

    assert f"1) {BULLET}add to Homebrew (betterdisplay 1.0)" in terminal.text


def test_all_of_them_at_once_skips_the_ones_without_a_recipe(tmp_path):
    asked = []
    terminal = Terminal(ADOPT_ALL)

    def adopt(app):
        asked.append(app.file_stem)
        return True, "done"

    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopt: adopt(app))
    dealt_with = track_apps.ask_what_to_do([app("BetterDisplay"), app("TokenEater")], decisions_in(tmp_path), terminal.step, find_cask=cask_for({"BetterDisplay": cask()}))

    assert asked == ["BetterDisplay"]
    assert len(dealt_with) == 1


def test_the_menu_counts_how_many_homebrew_could_take(tmp_path):
    terminal = Terminal("3")

    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopting(True): adopt(app))
    track_apps.ask_what_to_do([app("BetterDisplay"), app("TokenEater")], decisions_in(tmp_path), terminal.step, find_cask=cask_for({"BetterDisplay": cask()}))

    assert "add all to Homebrew (1 of 2)" in terminal.text


def test_a_recipe_ahead_of_the_app_counts_because_it_can_be_downloaded():
    found = [(app("BetterDisplay", "5.0.5"), cask(version="5.0.6"))]

    assert track_apps.ready_for_homebrew(found) == 1


def test_a_recipe_behind_the_app_is_not_counted():
    # Taking it over would mean going back a version.
    found = [(app("BetterDisplay", "5.0.7"), cask(version="5.0.6"))]

    assert track_apps.ready_for_homebrew(found) == 0


def test_a_recipe_that_matches_is_counted():
    found = [(app("BetterDisplay", "5.0.6"), cask(version="5.0.6"))]

    assert track_apps.ready_for_homebrew(found) == 1


def test_an_app_that_can_only_go_back_a_version_still_counts_as_known():
    # It can be handed over, just not without saying what that costs.
    found = [(app("Codex", "26.831.21537"), cask(version="26.623.141536"))]

    assert track_apps.known_to_homebrew(found) == 1
    assert track_apps.ready_for_homebrew(found) == 0


def test_an_app_with_no_recipe_counts_as_neither():
    found = [(app("TokenEater", "1.0"), None)]

    assert track_apps.known_to_homebrew(found) == 0
    assert track_apps.ready_for_homebrew(found) == 0

    # An app with an updater and a feed is offered both, so its own options sit
    # two places further down than an app with neither.


START_IT, LATER_AFTER_START = "1", "4"
LATER_AFTER_SITE = "3"


def sparkle_app(name="Dockish", version="1.1", feed="https://appish.app/appcast.xml"):
    return InstalledApp(
        name,
        version,
        Path(f"/Applications/{name}.app"),
        UpdaterStatus(app_updaters.SPARKLE, True, False, "2026-08-16", feed),
    )


def test_an_app_with_an_updater_can_be_asked_to_update_itself(tmp_path):
    started = []
    terminal = Terminal(START_IT, LATER_AFTER_START)

    swap(track_apps.shell, "open_application", lambda path: started.append(path) or True)
    track_apps.ask_what_to_do([sparkle_app()], decisions_in(tmp_path), terminal.step)

    assert f"1) {BULLET}open Dockish and let it update itself" in terminal.text
    assert started == [Path("/Applications/Dockish.app")]
    # Starting it settles nothing, so the same app is asked about again.
    assert f"2) {BULLET}download and install manually" in terminal.text


def test_an_app_that_will_not_start_says_so(tmp_path):
    terminal = Terminal(START_IT, LATER_AFTER_START)

    swap(track_apps.shell, "open_application", lambda path: False)
    track_apps.ask_what_to_do([sparkle_app()], decisions_in(tmp_path), terminal.step)

    assert "would not start" in terminal.text


def test_an_app_with_no_updater_is_not_offered_to_be_started(tmp_path):
    terminal = Terminal(LATER)

    swap(track_apps.shell, "open_application", lambda path: True)
    track_apps.ask_what_to_do([app("Evoto")], decisions_in(tmp_path), terminal.step)

    assert "let it update itself" not in terminal.text


def test_an_app_whose_feed_is_gone_is_not_told_to_ask_it(tmp_path):
    # Starting it only makes it check a feed that is not there any more.
    feed = "https://appish.app/appcast.xml"
    terminal = Terminal(LATER_AFTER_SITE)

    swap(track_apps.shell, "open_application", lambda path: True)
    track_apps.ask_what_to_do([sparkle_app(feed=feed)], decisions_in(tmp_path), terminal.step, offered={feed: appcast.FeedAnswer(error="update source answers 403")})

    assert "let it update itself" not in terminal.text
    assert "But update source answers 403." in terminal.text


def test_what_the_feed_offers_is_said_before_the_options(tmp_path):
    feed = "https://appish.app/appcast.xml"
    terminal = Terminal(LATER_AFTER_SITE)

    track_apps.ask_what_to_do(
        [sparkle_app(feed=feed)],
        decisions_in(tmp_path),
        terminal.step,
        offered={feed: appcast.FeedAnswer(version="1.2.5")},
    )

    assert "Update source offers 1.2.5." in terminal.text


def self_updating(name="Codex", version="26.831.21537"):
    return InstalledApp(
        name,
        version,
        Path(f"/Applications/{name}.app"),
        UpdaterStatus(app_updaters.SPARKLE, True, True, "2026-09-23", ""),
    )


def test_an_app_that_keeps_itself_ahead_of_its_recipe_is_no_problem():
    # Codex updates itself and has run ahead of the cask. Offering to hand it
    # over would only put an older build back, so it is not mentioned at all.
    behind_it = cask(token="codex-app", version="26.623.141536")

    assert not track_apps.worth_sorting_out(self_updating(), behind_it)


def test_an_app_that_looks_after_itself_and_has_nothing_pending_is_no_problem():
    assert not track_apps.worth_sorting_out(
        self_updating("uTorrent Web", "1.6.0"), None
    )
    assert not track_apps.worth_sorting_out(
        self_updating("uTorrent Web", "1.6.0"),
        None,
        appcast.FeedAnswer(version="1.6.0"),
    )


def test_a_recipe_matching_the_build_rather_than_the_short_version_is_no_problem():
    # Dockish says 6.2 for itself and carries 6.2.1 as its build, which is the
    # version the recipe names.
    on_disk = InstalledApp(
        "Dockish",
        "6.2",
        Path("/Applications/Dockish.app"),
        UpdaterStatus(app_updaters.SPARKLE, True, True, "2026-09-23", ""),
        build="6.2.1",
    )

    assert not track_apps.worth_sorting_out(on_disk, cask(version="6.2.1"))


def test_an_app_whose_own_feed_offers_more_than_it_installed_is_a_problem():
    # Dockish says it checks by itself, sits on 1.1, and its feed has 1.2.5.
    # Whatever it is doing, it is not updating itself.
    pending = appcast.FeedAnswer(version="1.2.5")

    assert track_apps.worth_sorting_out(self_updating("Dockish", "1.1"), None, pending)


def test_an_app_whose_feed_stopped_answering_is_a_problem():
    broken = appcast.FeedAnswer(error="update source answers 403")

    assert track_apps.worth_sorting_out(
        self_updating("Air", "262.579.44"), None, broken
    )


def test_an_app_that_does_not_update_itself_is_still_worth_asking_about():
    quiet = app("Codex", "26.831.21537")
    behind_it = cask(token="codex-app", version="26.623.141536")

    assert track_apps.worth_sorting_out(quiet, behind_it)


def test_a_self_updating_app_its_recipe_leads_is_still_worth_asking_about():
    # The recipe knowing a newer version is evidence it stopped keeping up.
    ahead = cask(token="codex-app", version="26.999.1")

    assert track_apps.worth_sorting_out(self_updating(), ahead)


def test_one_app_has_no_walk_through_to_cancel(tmp_path):
    swap(track_apps.adopting, "hand_to_homebrew", lambda app, cask, adopt=adopting(True): adopt(app))
    ask = lambda apps, terminal: track_apps.ask_what_to_do(apps, decisions_in(tmp_path), terminal.step, find_cask=cask_for({}))
    one, two = Terminal("2"), Terminal("2", "2", "2")

    ask([app("A")], one)
    ask([app("A"), app("B")], two)

    assert "cancel the walk-through" not in one.text
    assert "cancel the walk-through" in two.text


def test_an_app_left_alone_is_remembered_even_if_the_run_is_interrupted_after(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal(IGNORE, then=KeyboardInterrupt)

    with pytest.raises(KeyboardInterrupt):
        track_apps.ask_what_to_do(
            [app("First"), app("Second")], decisions, terminal.step
        )

    assert decisions_in(tmp_path).ignored_names() == ["First"]
