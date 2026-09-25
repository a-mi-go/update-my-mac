from rich.console import Console

from update_my_mac import apply_updates
from update_my_mac.apply_updates import CANCEL
from update_my_mac.package_managers import ManagerReport, ManagerUpdate

REPORTS = [
    ManagerReport("mas", "Mac App Store", []),
    ManagerReport("brew", "Homebrew", ["git 2.48.1 → 2.49.0"]),
    ManagerReport("npm", "npm (global)", ["typescript 5.4.2 → 5.4.5"]),
    ManagerReport("pnpm", "pnpm (global)", [], "boom"),
]

MANAGER_UPDATES = [
    ManagerUpdate("brew", "Homebrew", "index is 3 days old"),
    ManagerUpdate("npm", "npm (global)", "npm  12.0.2 → 12.1.0"),
]


class RecordingShell:
    def __init__(self, exit_code=0):
        self.streamed = []
        self.exit_code = exit_code

    def find_executable(self, command):
        return f"/fake/{command}"

    def stream_command(self, args, env=None):
        self.streamed.append(args)
        return self.exit_code


class FakeApp:
    def __init__(self, name):
        self.name = name
        self.version = "1.0"


class FakeDecisions:
    def __init__(self):
        self.ignored = []

    def is_ignored(self, name):
        return name in self.ignored

    def ignore(self, name, version, now=None):
        self.ignored.append(name)

    def save(self):
        return True


def answers(*replies):
    replies = list(replies)
    return lambda _prompt: replies.pop(0)


def quiet_console():
    return Console(file=open("/dev/null", "w"), width=200)


def run(shell, *replies, reports=REPORTS, untracked_apps=(), decisions=None):
    return apply_updates.run_upgrade_menu(
        reports, shell, quiet_console(), answers(*replies), untracked_apps, decisions
    )


def test_only_managers_with_something_outdated_get_an_entry():
    entries = apply_updates.build_menu(REPORTS)

    assert [entry.label for entry in entries] == [
        "Homebrew (1 package)",
        "npm (global) (1 package)",
    ]


def test_the_app_store_counts_apps_not_packages():
    reports = [ManagerReport("mas", "Mac App Store", ["Pages 14.0 → 14.1"])]

    assert apply_updates.build_menu(reports)[0].label == "Mac App Store (1 app)"


def test_a_failed_check_is_not_offered_for_upgrade():
    # pnpm errored rather than reporting packages, so upgrading it makes no sense.
    assert not any("pnpm" in entry.keys for entry in apply_updates.build_menu(REPORTS))


def test_the_managers_themselves_are_not_in_this_menu():
    # They are dealt with before it, so that what it lists is already current.
    entries = apply_updates.build_menu(REPORTS)

    assert all(entry.kind == apply_updates.PACKAGES for entry in entries)


def numbers(answer, entries):
    chosen = apply_updates.parse_menu_answer(answer, entries)
    return chosen if chosen == CANCEL or chosen is None else [e.label for e in chosen]


def test_everything_comes_first_and_nothing_comes_last():
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("1", entries) == [entry.label for entry in entries]
    assert numbers("4", entries) == CANCEL


def test_several_numbers_can_be_given_at_once():
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("2,3", entries) == ["Homebrew (1 package)", "npm (global) (1 package)"]
    assert numbers(" 3 , 2 ", entries) == ["npm (global) (1 package)", "Homebrew (1 package)"]


def test_the_same_number_twice_is_counted_once():
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("2,2", entries) == ["Homebrew (1 package)"]


def test_empty_answer_cancels():
    # Enter on its own is the safe choice, not "update everything".
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("", entries) == CANCEL
    assert numbers("0", entries) == CANCEL


def test_nonsense_is_not_understood():
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("9", entries) is None
    assert numbers("yes please", entries) is None
    assert numbers("2,nope", entries) is None


def test_cancelling_updates_nothing():
    shell = RecordingShell()

    assert run(shell, "4") == []
    assert shell.streamed == []


def test_everything_upgrades_each_manager_with_work():
    shell = RecordingShell()

    assert run(shell, "1") == []
    assert shell.streamed == [["/fake/brew", "upgrade"], ["/fake/npm", "update", "-g"]]


def test_choosing_one_manager_leaves_the_others_alone():
    shell = RecordingShell()
    run(shell, "3")

    assert shell.streamed == [["/fake/npm", "update", "-g"]]


def test_a_bad_answer_asks_again():
    shell = RecordingShell()
    run(shell, "what", "2")

    assert shell.streamed == [["/fake/brew", "upgrade"]]


def test_nothing_to_do_means_no_prompt():
    shell = RecordingShell()
    asked = []

    def record(prompt):
        asked.append(prompt)
        return "1"

    failed = apply_updates.run_upgrade_menu(
        [ManagerReport("brew", "Homebrew", [])], shell, quiet_console(), record
    )
    assert failed == []
    assert asked == []


def raising(exception):
    def ask(_prompt):
        raise exception

    return ask


def test_no_terminal_cancels_instead_of_crashing():
    # `update < /dev/null`, or a scheduled run that reached the menu.
    shell = RecordingShell()
    failed = apply_updates.run_upgrade_menu(REPORTS, shell, quiet_console(), raising(EOFError()))

    assert failed == []
    assert shell.streamed == []


def test_ctrl_c_cancels_instead_of_crashing():
    shell = RecordingShell()
    failed = apply_updates.run_upgrade_menu(
        REPORTS, shell, quiet_console(), raising(KeyboardInterrupt())
    )

    assert failed == []
    assert shell.streamed == []


def test_a_failed_upgrade_is_reported_back():
    shell = RecordingShell(exit_code=3)

    assert run(shell, "1") == ["brew", "npm"]


def test_ctrl_c_during_an_upgrade_stops_the_rest():
    class InterruptedShell(RecordingShell):
        def stream_command(self, args, env=None):
            self.streamed.append(args)
            raise KeyboardInterrupt

    shell = InterruptedShell()

    assert run(shell, "1") == ["brew"]
    assert shell.streamed == [["/fake/brew", "upgrade"]]


def test_the_untracked_apps_come_last_in_the_menu():
    entries = apply_updates.build_menu(REPORTS, [FakeApp("Docker")])

    assert entries[-1].kind == apply_updates.UNTRACKED_APPS
    assert entries[-1].label == "untracked apps (1 to go through)"


def test_without_untracked_apps_there_is_no_such_entry():
    entries = apply_updates.build_menu(REPORTS, [])

    assert not any(entry.kind == apply_updates.UNTRACKED_APPS for entry in entries)


def test_going_through_the_apps_is_one_of_the_choices():
    shell = RecordingShell()
    decisions = FakeDecisions()
    # Entry 4 is the apps, then "1" leaves the only app alone.
    run(shell, "4", "1", untracked_apps=[FakeApp("Docker")], decisions=decisions)

    assert decisions.ignored == ["Docker"]
    assert shell.streamed == []


def test_the_apps_are_asked_about_before_anything_is_upgraded():
    order = []

    class WatchingShell(RecordingShell):
        def stream_command(self, args, env=None):
            order.append("upgrade")
            return 0

    def ask(prompt):
        if prompt == "> " and not order:
            order.append("ask")
            return "1"
        return "2"

    apply_updates.run_upgrade_menu(
        REPORTS, WatchingShell(), quiet_console(), ask, [FakeApp("Docker")], FakeDecisions()
    )

    assert order[0] == "ask"


def test_only_the_menu_numbers_are_coloured():
    # Left to rich's highlighter, the brackets in "npm (global)" got coloured too.
    console = Console(force_terminal=True, color_system="standard", width=200)
    with console.capture() as captured:
        apply_updates.print_menu(apply_updates.build_menu(REPORTS), console)
    menu = captured.get()

    assert "\x1b[1;36m3)\x1b[0m" in menu
    assert "npm (global)" in menu


def test_the_menu_says_several_numbers_are_allowed(capsys):
    console = Console(width=200, no_color=True)
    apply_updates.print_menu(apply_updates.build_menu(REPORTS), console)

    menu = capsys.readouterr().out
    assert "separated by commas" in menu
    assert "1) Everything" in menu
    assert "4) Nothing" in menu


def test_no_manager_update_means_no_question():
    shell = RecordingShell()
    asked = []

    def record(prompt):
        asked.append(prompt)
        return "y"

    assert apply_updates.run_manager_menu([], shell, quiet_console(), record) == []
    assert asked == []


def test_saying_yes_updates_every_manager_that_is_behind():
    shell = RecordingShell()
    failed = apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers("y"))

    assert failed == []
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]


def test_anything_but_yes_leaves_the_managers_alone():
    shell = RecordingShell()
    failed = apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers(""))

    assert failed == []
    assert shell.streamed == []


def test_no_terminal_leaves_the_managers_alone():
    shell = RecordingShell()
    apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), raising(EOFError()))

    assert shell.streamed == []


def test_a_manager_that_fails_to_update_is_reported_back():
    shell = RecordingShell(exit_code=2)
    failed = apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers("yes"))

    assert failed == ["brew", "npm"]


def test_the_manager_question_asks_again_when_it_is_not_understood():
    shell = RecordingShell()
    failed = apply_updates.run_manager_menu(
        MANAGER_UPDATES, shell, quiet_console(), answers("maybe", "y")
    )

    assert failed == []
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]


def test_saying_no_outright_leaves_them_alone():
    shell = RecordingShell()

    assert apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers("n")) == []
    assert shell.streamed == []


def test_everything_is_not_accepted_with_rubbish_after_it():
    # "1" used to win before the rest of the line was even looked at.
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("1,garbage", entries) is None
    assert numbers("1,9", entries) is None


def test_nothing_wins_over_everything_when_both_are_given():
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("1,4", entries) == CANCEL
