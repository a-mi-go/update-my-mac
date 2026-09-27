from pathlib import Path

from rich.text import Text

from update_my_mac import app_decisions, track_apps
from update_my_mac.installed_apps import InstalledApp


class Terminal:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.lines = []

    def ask(self, prompt):
        self.lines.append(prompt)
        return self.answers.pop(0)

    def out(self, *parts, **_):
        self.lines.append(Text.from_markup(" ".join(str(part) for part in parts)).plain)

    @property
    def text(self):
        return "\n".join(self.lines)


def app(name, version="1.0"):
    return InstalledApp(name, version, Path(f"/Applications/{name}.app"))


def decisions_in(tmp_path):
    return app_decisions.AppDecisions(tmp_path / "apps.json")


def test_nothing_is_asked_when_every_app_is_accounted_for(tmp_path):
    terminal = Terminal()

    ignored = track_apps.run_untracked_menu([], decisions_in(tmp_path), terminal.ask, terminal.out)

    assert ignored == 0
    assert terminal.text == ""


def test_an_answer_that_means_nothing_keeps_the_app_listed(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("")

    ignored = track_apps.run_untracked_menu([app("TokenEater")], decisions, terminal.ask, terminal.out)

    assert ignored == 0
    assert decisions.ignored_names() == []
    assert not (tmp_path / "apps.json").exists()


def test_leaving_an_app_alone_is_remembered(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("1")

    ignored = track_apps.run_untracked_menu([app("TokenEater", "5.12.2")], decisions, terminal.ask, terminal.out)

    assert ignored == 1
    assert decisions_in(tmp_path).is_ignored("TokenEater")


def test_keeping_an_app_listed_writes_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("2")

    track_apps.run_untracked_menu([app("TokenEater")], decisions, terminal.ask, terminal.out)

    assert not (tmp_path / "apps.json").exists()


def test_stopping_partway_keeps_what_was_decided_so_far(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("1", "5")

    ignored = track_apps.run_untracked_menu(
        [app("First"), app("Second"), app("Third")], decisions, terminal.ask, terminal.out
    )

    assert ignored == 1
    stored = decisions_in(tmp_path)
    assert stored.ignored_names() == ["First"]
    assert not stored.is_ignored("Third")


def test_apps_already_left_alone_are_not_asked_about_again(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("TokenEater", "5.12.2")
    terminal = Terminal()

    ignored = track_apps.run_untracked_menu([app("TokenEater")], decisions, terminal.ask, terminal.out)

    assert ignored == 0
    assert terminal.text == ""


def test_without_a_terminal_nothing_is_asked(tmp_path):
    terminal = Terminal()

    track_apps.run_untracked_menu(
        [app("TokenEater")], decisions_in(tmp_path), terminal.ask, terminal.out, interactive=False
    )

    assert terminal.text == ""


def test_revisiting_says_so_when_there_is_nothing_to_revisit(tmp_path):
    terminal = Terminal()

    track_apps.run_revisit_menu(decisions_in(tmp_path), terminal.ask, terminal.out)

    assert "No apps are being left alone" in terminal.text


def test_an_app_can_be_brought_back(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.ignore("Beta", "2.0")
    decisions.save()
    terminal = Terminal("2")

    brought_back = track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out)

    assert brought_back == 1
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]
    assert "Beta will be listed again" in terminal.text


def test_answering_nothing_leaves_the_list_as_it_is(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal("0")

    brought_back = track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out)

    assert brought_back == 0
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def test_without_a_terminal_it_only_lists(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal()

    track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out, interactive=False)

    assert "Alpha" in terminal.text
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def raising(exception):
    def ask(_prompt):
        raise exception

    return ask


def test_no_more_input_stops_instead_of_crashing(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal()

    ignored = track_apps.run_untracked_menu(
        [app("TokenEater")], decisions, raising(EOFError()), terminal.out
    )

    assert ignored == 0
    assert not (tmp_path / "apps.json").exists()


def test_ctrl_c_partway_keeps_what_was_decided(tmp_path):
    decisions = decisions_in(tmp_path)
    answers = iter(["1"])

    def ask(_prompt):
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt

    ignored = track_apps.run_untracked_menu(
        [app("First"), app("Second")], decisions, ask, Terminal().out
    )

    assert ignored == 1
    assert decisions_in(tmp_path).ignored_names() == ["First"]


def test_ctrl_c_while_revisiting_changes_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()

    brought_back = track_apps.run_revisit_menu(
        decisions, raising(KeyboardInterrupt()), Terminal().out
    )

    assert brought_back == 0
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def test_a_decision_that_cannot_be_saved_is_said_out_loud(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    decisions = app_decisions.AppDecisions(locked / "update-my-mac" / "apps.json")
    terminal = Terminal("1")

    ignored = track_apps.run_untracked_menu([app("TokenEater")], decisions, terminal.ask, terminal.out)

    assert ignored == 1
    assert "won't be remembered" in terminal.text


def test_bringing_an_app_back_that_cannot_be_saved_says_so(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    (tmp_path / "apps.json").chmod(0o400)
    tmp_path.chmod(0o500)
    terminal = Terminal("1")

    try:
        brought_back = track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out)
    finally:
        tmp_path.chmod(0o700)

    assert brought_back == 0
    assert "won't be remembered" in terminal.text


def test_choosing_none_of_them_says_nothing(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal("0")

    brought_back = track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out)

    assert brought_back == 0
    assert "Answer a number" not in terminal.text


def test_an_answer_outside_the_list_is_pointed_out(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("Alpha", "1.0")
    decisions.save()
    terminal = Terminal("7")

    brought_back = track_apps.run_revisit_menu(decisions, terminal.ask, terminal.out)

    assert brought_back == 0
    assert "Answer a number from 1 to 1" in terminal.text
    assert decisions_in(tmp_path).ignored_names() == ["Alpha"]


def website_for(known):
    return lambda app: known.get(app.name, "")


class Opener:
    def __init__(self, works=True):
        self.opened = []
        self.works = works

    def __call__(self, url):
        self.opened.append(url)
        return self.works


def test_where_an_app_came_from_is_shown_and_opened(tmp_path):
    terminal = Terminal("4", "2")
    opener = Opener()

    track_apps.run_untracked_menu(
        [app("Docker")],
        decisions_in(tmp_path),
        terminal.ask,
        terminal.out,
        find_website=website_for({"Docker": "https://www.docker.com/"}),
        open_url=opener,
    )

    assert "https://www.docker.com/" in terminal.text
    assert opener.opened == ["https://www.docker.com/"]


def test_showing_it_is_not_a_decision(tmp_path):
    # After looking, the same app is asked about again.
    decisions = decisions_in(tmp_path)
    terminal = Terminal("4", "1")

    ignored = track_apps.run_untracked_menu(
        [app("Docker")],
        decisions,
        terminal.ask,
        terminal.out,
        find_website=website_for({"Docker": "https://www.docker.com/"}),
        open_url=Opener(),
    )

    assert ignored == 1
    assert decisions_in(tmp_path).is_ignored("Docker")


def test_an_app_nobody_knows_the_origin_of_says_so(tmp_path):
    terminal = Terminal("4", "2")
    opener = Opener()

    track_apps.run_untracked_menu(
        [app("TokenEater")],
        decisions_in(tmp_path),
        terminal.ask,
        terminal.out,
        find_website=website_for({}),
        open_url=opener,
    )

    assert "Nothing on this Mac says where that app came from" in terminal.text
    assert opener.opened == []


def test_a_browser_that_will_not_open_is_said_out_loud(tmp_path):
    terminal = Terminal("4", "2")

    track_apps.run_untracked_menu(
        [app("Docker")],
        decisions_in(tmp_path),
        terminal.ask,
        terminal.out,
        find_website=website_for({"Docker": "https://www.docker.com/"}),
        open_url=Opener(works=False),
    )

    assert "Could not open that in a browser" in terminal.text


def test_the_origin_is_only_looked_up_when_someone_asks(tmp_path):
    asked_about = []

    def find_website(app):
        asked_about.append(app.name)
        return ""

    terminal = Terminal("2")
    track_apps.run_untracked_menu(
        [app("Docker")], decisions_in(tmp_path), terminal.ask, terminal.out,
        find_website=find_website,
    )

    assert asked_about == []


def adopting(taken, message="done"):
    def adopt(_app):
        return taken, message

    return adopt


def test_an_app_can_be_handed_to_homebrew(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("3")

    ignored = track_apps.run_untracked_menu(
        [app("BetterDisplay")], decisions, terminal.ask, terminal.out,
        adopt=adopting(True, "Homebrew looks after it now, as betterdisplay."),
    )

    assert "Homebrew looks after it now, as betterdisplay." in terminal.text
    # Handed over, so it is neither ignored nor asked about again.
    assert ignored == 0
    assert decisions_in(tmp_path).ignored_names() == []


def test_an_app_with_no_recipe_is_asked_about_again(tmp_path):
    terminal = Terminal("3", "2")

    track_apps.run_untracked_menu(
        [app("TokenEater")], decisions_in(tmp_path), terminal.ask, terminal.out,
        adopt=adopting(False, "Homebrew has no recipe for this app."),
    )

    assert "Homebrew has no recipe for this app." in terminal.text


def test_a_failed_handover_leaves_the_app_undecided(tmp_path):
    decisions = decisions_in(tmp_path)
    terminal = Terminal("3", "1")

    ignored = track_apps.run_untracked_menu(
        [app("BetterDisplay")], decisions, terminal.ask, terminal.out,
        adopt=adopting(False, "Homebrew could not take it over."),
    )

    # The second answer still counted, so nothing was swallowed.
    assert ignored == 1


def test_without_homebrew_the_choice_says_so(tmp_path):
    terminal = Terminal("3", "2")

    track_apps.run_untracked_menu(
        [app("BetterDisplay")], decisions_in(tmp_path), terminal.ask, terminal.out
    )

    assert "Homebrew is not installed" in terminal.text


def test_the_menu_offers_the_handover(tmp_path):
    terminal = Terminal("5")
    track_apps.run_untracked_menu(
        [app("BetterDisplay")], decisions_in(tmp_path), terminal.ask, terminal.out
    )

    assert "3) let Homebrew take it over" in terminal.text
