import pytest

from update_my_mac import __version__, cli
from update_my_mac.cli import build_argument_parser, main


def test_help_lists_every_mode(capsys):
    with pytest.raises(SystemExit) as exc:
        build_argument_parser().parse_args(["--help"])
    assert exc.value.code == 0

    help_text = capsys.readouterr().out
    for flag in ("--check", "--background", "--retry-app"):
        assert flag in help_text


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        build_argument_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_modes_are_mutually_exclusive(capsys):
    with pytest.raises(SystemExit) as exc:
        build_argument_parser().parse_args(["--check", "--background"])
    assert exc.value.code == 2
    assert "not allowed with" in capsys.readouterr().err


def test_unimplemented_modes_exit_non_zero(capsys):
    for argv in (["--background"],):
        assert main(argv) == 1
        assert "not implemented yet" in capsys.readouterr().out


def test_the_help_names_the_command_it_was_given(capsys):
    with pytest.raises(SystemExit):
        build_argument_parser("mac-update").parse_args(["--help"])
    assert capsys.readouterr().out.startswith("usage: mac-update")


def test_ctrl_c_ends_the_run_with_a_word_about_it(monkeypatch, capsys):
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.app, "run_interactive_mode", interrupt)

    # 130 is what a shell reports for a program stopped by Ctrl-C.
    assert main([]) == 130
    printed = capsys.readouterr().out
    assert "Stopped." in printed
    assert "Keep your mind open and your software updated." in printed


def test_ctrl_c_ends_a_check_the_same_way(monkeypatch):
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.app, "run_check_mode", interrupt)

    assert main(["--check"]) == 130


def test_updates_only_goes_straight_to_the_updates(monkeypatch):
    ran = []
    monkeypatch.setattr(cli.app, "run_updates_only_mode", lambda: ran.append("updates") or 0)
    monkeypatch.setattr(cli.app, "run_interactive_mode", lambda: ran.append("full") or 0)

    assert main(["--updates-only"]) == 0
    assert ran == ["updates"]


def test_updates_only_cannot_be_combined_with_another_mode(capsys):
    with pytest.raises(SystemExit):
        main(["--updates-only", "--check"])

    assert "not allowed with" in capsys.readouterr().err


def on_a_terminal(monkeypatch):
    import sys

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)


def test_a_run_that_finishes_leaves_a_blank_line(monkeypatch, capsys):
    on_a_terminal(monkeypatch)
    monkeypatch.setattr(cli.app, "run_check_mode", lambda: 0)

    assert main(["--check"]) == 0
    assert capsys.readouterr().out == "\n"


def test_a_run_stopped_with_ctrl_c_leaves_a_blank_line(monkeypatch, capsys):
    on_a_terminal(monkeypatch)

    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.app, "run_interactive_mode", interrupt)

    assert main([]) == 130
    assert capsys.readouterr().out.endswith("\n\n")


def test_help_and_version_leave_a_blank_line_too(monkeypatch, capsys):
    on_a_terminal(monkeypatch)

    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.endswith(f"{__version__}\n\n")


def test_a_run_that_fails_leaves_a_blank_line_before_the_error(monkeypatch, capsys):
    on_a_terminal(monkeypatch)

    def fail():
        raise RuntimeError("boom")

    monkeypatch.setattr(cli.app, "run_check_mode", fail)

    with pytest.raises(RuntimeError):
        main(["--check"])
    assert capsys.readouterr().out == "\n"


def test_a_log_or_a_pipe_gets_no_extra_line(monkeypatch, capsys):
    monkeypatch.setattr(cli.app, "run_check_mode", lambda: 0)

    assert main(["--check"]) == 0
    assert capsys.readouterr().out == ""
