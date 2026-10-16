import pytest
from rich.console import Console

from update_my_mac.controller import apply_updates

from fake_run import use_shell, MANAGER_UPDATES, RecordingShell, answer_with, answers, printed_by, printing_to, raising
from update_my_mac.controller.apply_updates import CANCEL
from update_my_mac.managers import ManagerReport, ManagerUpdate
from update_my_mac.system.shell import CommandResult

REPORTS = [
    ManagerReport("mas", "Mac App Store", []),
    ManagerReport("brew", "Homebrew", ["git 2.48.1 → 2.49.0"]),
    ManagerReport("npm", "npm (global)", ["typescript 5.4.2 → 5.4.5"]),
    ManagerReport("pnpm", "pnpm (global)", [], "boom"),
]


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


def run(shell, *replies, reports=REPORTS):
    answer_with(answers(*replies))
    use_shell(shell)
    return apply_updates.ask_what_to_update(reports)


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

    failed = update_menu(
        [ManagerReport("brew", "Homebrew", [])], shell, record
    )
    assert failed == []
    assert asked == []


def test_no_terminal_cancels_instead_of_crashing():
    # `update < /dev/null`, or a scheduled run that reached the menu.
    shell = RecordingShell()
    failed = update_menu(REPORTS, shell, raising(EOFError()))

    assert failed == []
    assert shell.streamed == []


def test_ctrl_c_at_the_menu_ends_the_run():
    # Nothing below the top catches it, so it leaves through here.
    shell = RecordingShell()

    with pytest.raises(KeyboardInterrupt):
        update_menu(
            REPORTS, shell, raising(KeyboardInterrupt())
        )

    assert shell.streamed == []


def test_a_failed_upgrade_is_reported_back():
    shell = RecordingShell(exit_code=3)

    assert run(shell, "1") == ["brew", "npm"]


def test_ctrl_c_during_an_upgrade_ends_the_run():
    class InterruptedShell(RecordingShell):
        def stream_command(self, args, env=None, silent_status=None):
            self.streamed.append(args)
            raise KeyboardInterrupt

    shell = InterruptedShell()

    with pytest.raises(KeyboardInterrupt):
        run(shell, "1")

    # The one it was in the middle of, and nothing after it.
    assert shell.streamed == [["/fake/brew", "upgrade"]]


def test_only_the_menu_numbers_are_coloured():
    # Left to rich's highlighter, the brackets in "npm (global)" got coloured too.
    menu = printed_by(
        lambda: apply_updates.print_menu(apply_updates.build_menu(REPORTS)),
        Console(force_terminal=True, color_system="standard", width=200),
    )

    assert "\x1b[36m3)\x1b[0m" in menu
    assert "npm (global)" in menu


def test_the_menu_says_several_numbers_are_allowed():
    menu = printed_by(
        lambda: apply_updates.print_menu(apply_updates.build_menu(REPORTS)),
        Console(width=200, no_color=True),
    )
    assert "separated by commas" in menu
    assert "1) update everything!" in menu
    assert f"4) {apply_updates.prompting.WAY_OUT}exit without updating" in menu


def test_everything_is_not_accepted_with_rubbish_after_it():
    # "1" used to win before the rest of the line was even looked at.
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("1,garbage", entries) is None
    assert numbers("1,9", entries) is None


def test_nothing_wins_over_everything_when_both_are_given():
    entries = apply_updates.build_menu(REPORTS)

    assert numbers("1,4", entries) == CANCEL


def test_the_run_ends_by_saying_what_actually_changed():
    # The upgrade writes to the terminal and we never see it, so the managers
    # are asked again and the answer is the difference.
    shell = RecordingShell()
    printed = printed_by(
        lambda: update_menu(REPORTS, shell, answers("1"))
    )

    assert "Homebrew: 1 updated" in printed
    assert "npm (global): 1 updated" in printed


def test_a_package_that_did_not_move_is_named_without_the_build_in_its_version():
    still = "cursor (3.22.7,37076c6c3f9e253c0fa2305197e45befd13a2268) != 3.24.12,37b865941ccb"
    shell = RecordingShell(exit_code=1, still_outdated={"brew": still})
    printed = printed_by(
        lambda: update_menu(REPORTS, shell, answers("2"))
    )

    assert "cursor" in printed
    assert "3.22.7 → 3.24.12" in printed
    assert "37076c6c" not in printed


def test_a_package_that_did_not_move_is_named():
    # This is the case that started it: one app updated, one did not, and the
    # run only said the manager had exited with 1.
    shell = RecordingShell(exit_code=1, still_outdated={"brew": "git 2.48.1 -> 2.49.0"})
    printed = printed_by(
        lambda: update_menu(REPORTS, shell, answers("2"))
    )

    assert "Homebrew: 0 of 1 updated, still outdated" in printed
    assert "git 2.48.1 -> 2.49.0" in printed


def test_a_manager_that_cannot_be_asked_again_says_so():
    class SilentShell(RecordingShell):
        def run_command(self, args, success_exit_codes=(0,), env=None):
            return CommandResult(False, "", "brew: boom")

    printed = printed_by(
        lambda: update_menu(
            REPORTS, SilentShell(), answers("2")
        )
    )

    assert "Homebrew: could not check again" in printed


def test_a_manager_that_cannot_be_asked_again_counts_as_a_failure():
    # Whether the upgrade worked is then unknown, and the run says so by
    # exiting non-zero rather than by claiming success.
    class SilentShell(RecordingShell):
        def run_command(self, args, success_exit_codes=(0,), env=None):
            return CommandResult(False, "", "brew: boom")

    failed = update_menu(
        REPORTS, SilentShell(), answers("2")
    )

    assert failed == ["brew"]


def test_nothing_is_claimed_after_an_interrupted_run():
    class InterruptedShell(RecordingShell):
        def stream_command(self, args, env=None, silent_status=None):
            raise KeyboardInterrupt

    console = Console(width=100, no_color=True)
    with printing_to(console), console.capture() as captured:
        with pytest.raises(KeyboardInterrupt):
            update_menu(REPORTS, InterruptedShell(), answers("1"))

    # The menu itself says "What should be updated?", so look for the closing
    # lines rather than the word.
    printed = captured.get()
    assert "1 updated" not in printed
    assert "still outdated" not in printed


def two_entries():
    return apply_updates.build_menu([
        ManagerReport("brew", "Homebrew", ["git  1 → 2"]),
        ManagerReport("mas", "Mac App Store", ["Xcode  1 → 2"]),
    ])


def picking(answer_for):
    """A multi-select that records what it was asked and answers from the choices."""
    asked = []

    def pick(question, choices, **options):
        asked.append((question, choices, options))
        return answer_for(choices)

    return pick, asked


def update_menu(reports, shell, ask):
    """Asks the update menu, answering it with `ask`."""
    answer_with(ask)
    use_shell(shell)
    return apply_updates.ask_what_to_update(reports)


def picked_by(pick, entries):
    """Asks the update menu with this multi-select drawing it."""
    apply_updates.arrow_menu.pick_several = pick
    return apply_updates.pick_what_to_update(entries)


def test_the_multi_select_lists_the_entries_then_update_and_exit_apart():
    pick, asked = picking(lambda choices: [])

    picked_by(pick, two_entries())

    question, choices, _ = asked[0]
    assert question == "What should be updated?"
    assert [choice[1] for choice in choices[:2]] == ["Homebrew (1 package)", "Mac App Store (1 app)"]
    assert choices[2] is apply_updates.arrow_menu.BLANK_LINE
    assert choices[3][1] == "⬆ UPDATE (lets do it!)"
    assert choices[4] is None
    assert choices[5][1] == f"{apply_updates.prompting.WAY_OUT}exit without updating"


def test_every_entry_starts_ticked_and_the_pointer_starts_on_update():
    entries = two_entries()
    pick, asked = picking(lambda choices: [])

    picked_by(pick, entries)

    options = asked[0][2]
    assert options["checked"] == entries
    assert options["start_at"] == apply_updates.UPDATE
    assert options["confirm"] == apply_updates.UPDATE
    assert options["ends_menu"] == (apply_updates.CANCEL,)


def test_what_is_ticked_is_what_gets_updated():
    entries = two_entries()
    pick, _ = picking(lambda choices: [entries[1]])

    chosen = picked_by(pick, entries)

    assert [entry.label for entry in chosen] == ["Mac App Store (1 app)"]


def test_exiting_updates_nothing_whatever_is_ticked():
    entries = two_entries()
    pick, _ = picking(lambda choices: [apply_updates.CANCEL])

    assert picked_by(pick, entries) == apply_updates.CANCEL


def test_unticking_everything_updates_nothing():
    pick, _ = picking(lambda choices: [])

    assert picked_by(pick, two_entries()) == apply_updates.CANCEL


def test_backing_out_of_the_multi_select_updates_nothing():
    entries = apply_updates.build_menu([ManagerReport("brew", "Homebrew", ["git  1 → 2"])])

    chosen = picked_by(lambda question, choices, **options: None, entries)

    assert chosen == apply_updates.CANCEL


def test_a_main_menu_that_will_not_draw_falls_back_to_the_numbered_one(monkeypatch):
    def refuse(entries):
        raise apply_updates.arrow_menu.Unusable("no terminal capability")

    monkeypatch.setattr(apply_updates.arrow_menu, "can_be_drawn", lambda: True)
    monkeypatch.setattr(apply_updates, "pick_what_to_update", refuse)
    shell = RecordingShell()
    printed = printed_by(
        lambda: update_menu(REPORTS, shell, answers("1")),
        Console(width=200),
    )

    assert "could not be drawn" in printed
    assert "Homebrew (1 package)" in printed
    assert shell.streamed, "the answer to the numbered menu was acted on"




def test_the_update_menu_is_set_apart_by_a_line():
    printed = printed_by(
        lambda: update_menu(REPORTS, RecordingShell(), answers("4")),
        Console(width=200, no_color=True),
    )

    assert apply_updates.prompting.SEPARATOR_CHARACTER * 84 in printed
    assert printed.index("─") < printed.index("1) update everything!")


def test_no_line_is_drawn_when_there_is_no_menu():
    printed = printed_by(lambda: update_menu(
        [ManagerReport("brew", "Homebrew", [])], RecordingShell(), answers("1"),
    ))

    assert "─" not in printed


def test_the_app_store_upgrade_says_it_may_ask_for_a_password():
    use_shell(RecordingShell())

    printed = printed_by(lambda: apply_updates.upgrade_managers(["mas", "npm"]))

    assert printed.count("It may ask for your password.") == 1
    assert printed.index("Mac App Store") < printed.index("password") < printed.index("npm")


def test_an_app_the_app_store_cannot_download_comes_with_the_likely_reason():
    reports = [ManagerReport("mas", "Mac App Store", ["PDFgear  2.27 → 2.28"])]
    shell = RecordingShell(exit_code=1, still_outdated={"mas": "6469021132  PDFgear  (2.27 -> 2.28)"})

    printed = printed_by(lambda: run(shell, "1", reports=reports))

    assert "PDFgear" in printed
    assert "another Apple Account" in printed


def test_a_manager_without_a_known_reason_adds_no_explanation():
    shell = RecordingShell(exit_code=1, still_outdated={"brew": "git 2.48.1 -> 2.49.0"})

    printed = printed_by(lambda: update_menu(REPORTS, shell, answers("2")))

    assert "Apple Account" not in printed
