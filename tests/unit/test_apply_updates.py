from rich.console import Console

from update_my_mac import apply_updates
from update_my_mac.apply_updates import CANCEL, EVERYTHING
from update_my_mac.package_managers import ManagerReport

REPORTS = [
    ManagerReport("mas", "Mac App Store", []),
    ManagerReport("brew", "Homebrew", ["git 2.48.1 → 2.49.0"]),
    ManagerReport("npm", "npm (global)", ["typescript 5.4.2 → 5.4.5"]),
    ManagerReport("pnpm", "pnpm (global)", [], "boom"),
]


class RecordingShell:
    def __init__(self):
        self.streamed = []

    def find_executable(self, command):
        return f"/fake/{command}"

    def stream_command(self, args, env=None):
        self.streamed.append(args)
        return 0


def answers(*replies):
    replies = list(replies)
    return lambda _prompt: replies.pop(0)


def quiet_console():
    return Console(file=open("/dev/null", "w"), width=200)


def test_only_managers_with_something_outdated_are_offered():
    assert apply_updates.upgradable_manager_keys(REPORTS) == ["brew", "npm"]


def test_menu_numbering():
    keys = ["brew", "npm"]
    assert apply_updates.parse_menu_answer("1", keys) == EVERYTHING
    assert apply_updates.parse_menu_answer("2", keys) == "brew"
    assert apply_updates.parse_menu_answer("3", keys) == "npm"
    assert apply_updates.parse_menu_answer("0", keys) == CANCEL


def test_empty_answer_cancels():
    # Enter on its own is the safe choice, not "upgrade everything".
    assert apply_updates.parse_menu_answer("", ["brew"]) == CANCEL


def test_nonsense_is_not_understood():
    assert apply_updates.parse_menu_answer("9", ["brew"]) is None
    assert apply_updates.parse_menu_answer("yes please", ["brew"]) is None


def test_cancelling_upgrades_nothing():
    shell = RecordingShell()
    used = apply_updates.run_upgrade_menu(REPORTS, shell, quiet_console(), answers("0"))
    assert used == []
    assert shell.streamed == []


def test_choosing_everything_upgrades_each_outdated_manager():
    shell = RecordingShell()
    used = apply_updates.run_upgrade_menu(REPORTS, shell, quiet_console(), answers("1"))
    assert used == ["brew", "npm"]
    assert shell.streamed == [
        ["/fake/brew", "upgrade"],
        ["/fake/npm", "update", "-g"],
    ]


def test_choosing_one_manager_leaves_the_others_alone():
    shell = RecordingShell()
    used = apply_updates.run_upgrade_menu(REPORTS, shell, quiet_console(), answers("3"))
    assert used == ["npm"]
    assert shell.streamed == [["/fake/npm", "update", "-g"]]


def test_a_bad_answer_asks_again():
    shell = RecordingShell()
    used = apply_updates.run_upgrade_menu(
        REPORTS, shell, quiet_console(), answers("what", "2")
    )
    assert used == ["brew"]


def test_a_failed_check_is_not_offered_for_upgrade():
    # pnpm errored rather than reporting packages, so upgrading it makes no sense.
    assert "pnpm" not in apply_updates.upgradable_manager_keys(REPORTS)


def test_nothing_outdated_means_no_prompt():
    shell = RecordingShell()
    asked = []

    def record(prompt):
        asked.append(prompt)
        return "1"

    used = apply_updates.run_upgrade_menu(
        [ManagerReport("brew", "Homebrew", [])], shell, quiet_console(), record
    )
    assert used == []
    assert asked == []


def test_a_single_candidate_is_not_offered_twice(capsys):
    console = Console(width=200, no_color=True)
    apply_updates.print_menu(["brew"], console)

    menu = capsys.readouterr().out
    assert "Everything" not in menu
    assert "1) Homebrew" in menu
