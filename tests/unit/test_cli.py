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
    # Honest about what it cannot undo.
    assert "already run has run" in printed


def test_ctrl_c_ends_a_check_the_same_way(monkeypatch):
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.app, "run_check_mode", interrupt)

    assert main(["--check"]) == 130
