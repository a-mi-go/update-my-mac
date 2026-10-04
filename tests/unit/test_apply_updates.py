import pytest
from rich.console import Console

from update_my_mac import apply_updates
from update_my_mac.apply_updates import CANCEL
from update_my_mac.package_managers import ManagerReport, ManagerUpdate
from update_my_mac.shell import CommandResult

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
    """Records upgrades, and answers the check that follows them.

    `still_outdated` is what each manager reports when asked again after the
    upgrade, keyed by command name. Empty means it has nothing left.
    """

    def __init__(self, exit_code=0, still_outdated=None):
        self.streamed = []
        self.exit_code = exit_code
        self.still_outdated = still_outdated or {}

    def find_executable(self, command):
        return f"/fake/{command}"

    def stream_command(self, args, env=None):
        self.streamed.append(args)
        return self.exit_code

    def run_command(self, args, success_exit_codes=(0,), env=None):
        command = args[0].rsplit("/", 1)[-1]
        return CommandResult(True, self.still_outdated.get(command, ""), "")


class FakeApp:
    def __init__(self, name):
        self.name = name
        self.version = "1.0"


class RecordingWalkthrough:
    """Stands in for going through the untracked apps."""

    def __init__(self):
        self.seen = []

    def __call__(self, apps, ask, out):
        self.seen += [app.name for app in apps]
        ask("> ")
        return len(apps)


def answers(*replies):
    replies = list(replies)
    return lambda _prompt: replies.pop(0)


def quiet_console():
    return Console(file=open("/dev/null", "w"), width=200)


def run(shell, *replies, reports=REPORTS):
    return apply_updates.run_upgrade_menu(reports, shell, quiet_console(), answers(*replies))


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


def test_ctrl_c_at_the_menu_ends_the_run():
    # Nothing below the top catches it, so it leaves through here.
    shell = RecordingShell()

    with pytest.raises(KeyboardInterrupt):
        apply_updates.run_upgrade_menu(
            REPORTS, shell, quiet_console(), raising(KeyboardInterrupt())
        )

    assert shell.streamed == []


def test_a_failed_upgrade_is_reported_back():
    shell = RecordingShell(exit_code=3)

    assert run(shell, "1") == ["brew", "npm"]


def test_ctrl_c_during_an_upgrade_ends_the_run():
    class InterruptedShell(RecordingShell):
        def stream_command(self, args, env=None):
            self.streamed.append(args)
            raise KeyboardInterrupt

    shell = InterruptedShell()

    with pytest.raises(KeyboardInterrupt):
        run(shell, "1")

    # The one it was in the middle of, and nothing after it.
    assert shell.streamed == [["/fake/brew", "upgrade"]]


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

    assert apply_updates.run_manager_menu([], shell, quiet_console(), record).failed == []
    assert asked == []


def test_saying_yes_updates_every_manager_that_is_behind():
    shell = RecordingShell()
    run = apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers("y"))

    assert run.failed == []
    assert run.refreshed == ["brew", "npm"]
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]


def test_anything_but_yes_leaves_the_managers_alone():
    shell = RecordingShell()
    run = apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers(""))

    assert run.failed == []
    # Declining is not the same as every manager being up to date.
    assert run.refreshed == []
    assert shell.streamed == []


def test_no_terminal_leaves_the_managers_alone():
    shell = RecordingShell()
    apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), raising(EOFError()))

    assert shell.streamed == []


def test_a_manager_that_fails_to_update_is_reported_back():
    shell = RecordingShell(exit_code=2)
    run = apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers("yes"))

    assert run.failed == ["brew", "npm"]
    assert run.refreshed == []


def test_the_manager_question_asks_again_when_it_is_not_understood():
    shell = RecordingShell()
    run = apply_updates.run_manager_menu(
        MANAGER_UPDATES, shell, quiet_console(), answers("maybe", "y")
    )

    assert run.failed == []
    assert shell.streamed == [
        ["/fake/brew", "update"],
        ["/fake/npm", "install", "-g", "npm@latest"],
    ]


def test_saying_no_outright_leaves_them_alone():
    shell = RecordingShell()

    run = apply_updates.run_manager_menu(MANAGER_UPDATES, shell, quiet_console(), answers("n"))

    assert run.failed == []
    assert shell.streamed == []


def test_everything_is_not_accepted_with_rubbish_after_it():
    # "1" used to win before the rest of the line was even looked at.
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("1,garbage", entries) is None
    assert numbers("1,9", entries) is None


def test_nothing_wins_over_everything_when_both_are_given():
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("1,4", entries) == CANCEL


def printed_by(action):
    console = Console(width=100, no_color=True)
    with console.capture() as captured:
        action(console)
    return captured.get()


def test_the_run_ends_by_saying_what_actually_changed():
    # The upgrade writes to the terminal and we never see it, so the managers
    # are asked again and the answer is the difference.
    shell = RecordingShell()
    printed = printed_by(
        lambda console: apply_updates.run_upgrade_menu(REPORTS, shell, console, answers("1"))
    )

    assert "Homebrew: 1 updated" in printed
    assert "npm (global): 1 updated" in printed


def test_a_package_that_did_not_move_is_named():
    # This is the case that started it: one app updated, one did not, and the
    # run only said the manager had exited with 1.
    shell = RecordingShell(exit_code=1, still_outdated={"brew": "git 2.48.1 -> 2.49.0"})
    printed = printed_by(
        lambda console: apply_updates.run_upgrade_menu(REPORTS, shell, console, answers("2"))
    )

    assert "Homebrew: 0 of 1 updated, still outdated" in printed
    assert "git 2.48.1 -> 2.49.0" in printed


def test_a_manager_that_cannot_be_asked_again_says_so():
    class SilentShell(RecordingShell):
        def run_command(self, args, success_exit_codes=(0,), env=None):
            return CommandResult(False, "", "brew: boom")

    printed = printed_by(
        lambda console: apply_updates.run_upgrade_menu(
            REPORTS, SilentShell(), console, answers("2")
        )
    )

    assert "Homebrew: could not check again" in printed


def test_a_manager_that_cannot_be_asked_again_counts_as_a_failure():
    # Whether the upgrade worked is then unknown, and the run says so by
    # exiting non-zero rather than by claiming success.
    class SilentShell(RecordingShell):
        def run_command(self, args, success_exit_codes=(0,), env=None):
            return CommandResult(False, "", "brew: boom")

    failed = apply_updates.run_upgrade_menu(
        REPORTS, SilentShell(), quiet_console(), answers("2")
    )

    assert failed == ["brew"]


def test_nothing_is_claimed_after_an_interrupted_run():
    class InterruptedShell(RecordingShell):
        def stream_command(self, args, env=None):
            raise KeyboardInterrupt

    console = Console(width=100, no_color=True)
    with console.capture() as captured:
        with pytest.raises(KeyboardInterrupt):
            apply_updates.run_upgrade_menu(
                REPORTS, InterruptedShell(), console, answers("1")
            )

    # The menu itself says "What should be updated?", so look for the closing
    # lines rather than the word.
    printed = captured.get()
    assert "1 updated" not in printed
    assert "still outdated" not in printed


def test_the_manager_step_closes_the_same_way():
    shell = RecordingShell(exit_code=2)
    printed = printed_by(
        lambda console: apply_updates.run_manager_menu(
            MANAGER_UPDATES, shell, console, answers("y")
        )
    )

    assert "Homebrew: exited with 2" in printed


def test_picking_several_needs_no_everything_or_nothing_option():
    entries = apply_updates.build_menu([
        ManagerReport("brew", "Homebrew", ["git  1 → 2"]),
        ManagerReport("mas", "Mac App Store", ["Xcode  1 → 2"]),
    ])
    asked = []

    def pick(question, choices):
        asked.append((question, [label for _, label in choices]))
        return [choices[1][0]]

    chosen = apply_updates.pick_what_to_update(entries, pick=pick)

    assert [entry.label for entry in chosen] == ["Mac App Store (1 app)"]
    assert asked[0][0] == "What should be updated?"
    assert "Everything" not in asked[0][1]


def test_backing_out_of_the_multi_select_updates_nothing():
    entries = apply_updates.build_menu([ManagerReport("brew", "Homebrew", ["git  1 → 2"])])

    chosen = apply_updates.pick_what_to_update(entries, pick=lambda question, choices: None)

    assert chosen == apply_updates.CANCEL


def test_the_question_is_coloured_rather_than_handed_to_input():
    # input() writes its prompt raw, so markup there would be shown as text.
    console = Console(width=80, force_terminal=True)
    asked = []

    with console.capture() as captured:
        apply_updates._confirm_pm_self_update(console, lambda prompt: asked.append(prompt) or "n")

    assert asked == [""]
    # 36 is cyan, and the whole question wears it.
    assert "\x1b[36m" in captured.get()
    assert "Update them now?" in captured.get()


def test_the_keys_are_asked_first_where_the_terminal_allows_it(monkeypatch):
    monkeypatch.setattr(apply_updates.keys, "available", lambda: True)
    monkeypatch.setattr(apply_updates.keys, "confirm", lambda question, default: True)

    assert apply_updates._confirm_pm_self_update(Console(width=80), None)


def test_a_menu_that_will_not_draw_falls_back_to_the_question(monkeypatch):
    def refuse(question, default):
        raise apply_updates.keys.Unusable("no terminal capability")

    monkeypatch.setattr(apply_updates.keys, "available", lambda: True)
    monkeypatch.setattr(apply_updates.keys, "confirm", refuse)
    console = Console(width=80)

    with console.capture() as captured:
        said = apply_updates._confirm_pm_self_update(console, lambda prompt: "y")

    assert said
    assert "could not be drawn" in captured.get()


def test_a_main_menu_that_will_not_draw_falls_back_to_the_numbered_one(monkeypatch):
    def refuse(entries):
        raise apply_updates.keys.Unusable("no terminal capability")

    monkeypatch.setattr(apply_updates.keys, "available", lambda: True)
    monkeypatch.setattr(apply_updates, "pick_what_to_update", refuse)
    shell = RecordingShell()
    console = Console(width=200)

    with console.capture() as captured:
        apply_updates.run_upgrade_menu(REPORTS, shell, console, answers("1"))

    assert "could not be drawn" in captured.get()
    assert "Homebrew (1 package)" in captured.get()
    assert shell.streamed, "the answer to the numbered menu was acted on"


def test_the_yes_or_no_hint_survives_the_markup():
    # rich reads [y/N] as a style and swallows it unless the bracket is escaped.
    console = Console(width=80, no_color=True)

    with console.capture() as captured:
        apply_updates._confirm_pm_self_update(console, lambda prompt: "n")

    assert "[y/N]" in captured.get()


def test_the_question_is_bold_and_the_marker_coloured():
    # rich's own highlighter picks brackets out of a line and bolds them.
    console = Console(width=80, force_terminal=True)

    with console.capture() as captured:
        apply_updates._confirm_pm_self_update(console, lambda prompt: "n")

    # The question is bold, the marker is cyan, and the hint is neither:
    # dimmed it was barely readable.
    printed = captured.get()
    assert "\x1b[1mUpdate them now?" in printed
    assert "\x1b[36m" in printed
    assert "\x1b[2m" not in printed


def test_a_question_that_defaults_to_yes_says_so_and_takes_an_empty_answer():
    console = Console(width=80, no_color=True)

    with console.capture() as captured:
        said = apply_updates._pick_yes_or_no(console, lambda prompt: "", "Keep it?", default=True)

    assert said
    assert "[Y/n]" in captured.get()


def test_a_line_is_broken_after_the_answer():
    # The question is printed without a line break, because the answer is
    # typed on the same line. In a terminal the Enter that ends the answer
    # breaks it; here nothing does, so this is the one that gets printed.
    console = Console(width=80, no_color=True)

    with console.capture() as captured:
        apply_updates._confirm_pm_self_update(console, lambda prompt: "n")

    assert captured.get().endswith("\n")
    assert captured.get().count("\n") == 1
