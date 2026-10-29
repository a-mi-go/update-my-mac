"""The screen of its own that a run starts on, and goes back from once the first menu is answered."""

import io

import pytest
from rich.console import Console

from update_my_mac.view import output

ENTER, LEAVE = "\x1b[?1049h", "\x1b[?1049l"


@pytest.fixture(autouse=True)
def a_terminal_to_write_to(monkeypatch):
    # The screen is the one thing the run keeps in a module, so it is put back.
    monkeypatch.setattr(output, "_in_full_screen", False)
    monkeypatch.setattr(output.sys.stdin, "isatty", lambda: True)


def terminal(rows=40):
    written = io.StringIO()
    output.console = Console(file=written, force_terminal=True, height=rows, width=100)
    return written


def test_a_run_on_a_terminal_starts_on_a_screen_of_its_own_and_leaves_it():
    written = terminal()

    with output.full_screen():
        assert output.in_full_screen()
        assert written.getvalue().count(ENTER) == 1

    assert not output.in_full_screen()
    assert written.getvalue().count(LEAVE) == 1


def test_leaving_twice_leaves_once():
    # A second leave would put the cursor where the first one found it.
    written = terminal()

    with output.full_screen():
        output.leave_full_screen()
        output.leave_full_screen()

    assert written.getvalue().count(LEAVE) == 1


def test_the_screen_is_left_when_the_run_is_stopped():
    written = terminal()

    with pytest.raises(KeyboardInterrupt):
        with output.full_screen():
            raise KeyboardInterrupt

    assert written.getvalue().count(LEAVE) == 1


def test_what_was_printed_on_the_screen_is_printed_again_when_the_run_ends_on_it():
    written = io.StringIO()
    output.console = output.RecordingConsole(file=written, force_terminal=True, height=40, width=100)

    with pytest.raises(RuntimeError):
        with output.full_screen():
            output.console.print("a check that failed")
            raise RuntimeError

    assert "a check that failed" in written.getvalue().split(LEAVE)[1]


def test_a_pipe_gets_no_screen_of_its_own():
    written = io.StringIO()
    output.console = Console(file=written, width=100)

    with output.full_screen():
        assert not output.in_full_screen()

    assert written.getvalue() == ""


def test_a_terminal_too_short_for_a_menu_below_a_report_stays_on_its_own_screen():
    written = terminal(rows=output.MIN_FULL_SCREEN_ROWS - 1)

    with output.full_screen():
        assert not output.in_full_screen()

    assert ENTER not in written.getvalue()


def recording_console():
    written = io.StringIO()
    output.console = output.RecordingConsole(file=written, force_terminal=True, height=40, width=100)
    return written


def replayed(width=60):
    printed = io.StringIO()
    output.replay(Console(file=printed, width=width, force_terminal=True, color_system=None))
    return printed.getvalue()


def test_what_is_printed_on_the_screen_of_its_own_can_be_printed_again():
    recording_console()

    with output.full_screen():
        output.console.print("Updated: brew")
        output.console.print("[yellow]a warning[/]")

        assert replayed() == "Updated: brew\na warning\n"


def test_nothing_is_kept_when_there_is_no_screen_of_its_own():
    output.console = output.RecordingConsole(file=io.StringIO(), width=100)

    output.console.print("not on a screen of its own")

    assert replayed() == ""


def test_the_spinners_control_codes_are_not_kept():
    from rich.control import Control

    recording_console()

    with output.full_screen():
        output.console.print(Control())
        output.console.print("a line")

        assert replayed() == "a line\n"


def test_what_ran_on_an_earlier_screen_is_not_kept_for_the_next():
    recording_console()
    with output.full_screen():
        output.console.print("first run")

    recording_console()
    with output.full_screen():
        assert replayed() == ""


def test_what_is_printed_after_the_screen_was_left_is_not_kept():
    recording_console()

    with output.full_screen():
        output.console.print("on the screen")
    output.console.print("after it")

    assert replayed() == "on the screen\n"


def test_a_commands_output_is_kept_a_line_at_a_time_without_what_only_moved_the_cursor():
    recording_console()

    with output.full_screen():
        output.remember_command_output(b"==> Updating\r\n10%\r50%\r100%\r\n\x1b[2K\x1b[32mdone\x1b[0m\r\n")
        output.remember_command_output(None)

        assert replayed() == "==> Updating\n100%\ndone\n"


def test_a_line_that_arrives_in_two_pieces_is_kept_once_and_the_last_one_when_the_command_ends():
    recording_console()

    with output.full_screen():
        output.remember_command_output(b"par")
        output.remember_command_output(b"tial\nlast")
        output.remember_command_output(None)

        assert replayed() == "partial\nlast\n"


def test_a_character_split_between_two_pieces_is_not_broken():
    recording_console()
    arrow = "→".encode()

    with output.full_screen():
        output.remember_command_output(b"a " + arrow[:1])
        output.remember_command_output(arrow[1:] + b" b\n")

        assert replayed() == "a → b\n"


def test_print_above_leaves_the_screen_then_prints_what_ran_on_it_and_then_the_rest():
    written = recording_console()

    with output.full_screen():
        output.console.print("earlier output")
        output.print_above(lambda console: console.print("the report"))

    text = written.getvalue()
    assert text.index("\x1b[?1049l") < text.rindex("earlier output") < text.rindex("the report")


def test_the_same_report_is_printed_above_only_once():
    written = recording_console()

    def report(console):
        console.print("the report")

    with output.full_screen():
        output.console.print("earlier output")
        output.print_above(report)
        output.print_above(report)

    text = written.getvalue()
    assert text.count("the report") == 1
    assert text.count("earlier output") == 2


def test_a_run_switches_off_any_mouse_reporting_an_earlier_program_left_on():
    written = terminal()

    with output.full_screen():
        pass

    text = written.getvalue()
    assert text.index(output.MOUSE_REPORTING_OFF) < text.index(ENTER)


def test_a_pipe_gets_no_codes_for_the_mouse_either():
    written = io.StringIO()
    output.console = Console(file=written, width=100)

    with output.full_screen():
        pass

    assert output.MOUSE_REPORTING_OFF not in written.getvalue()

