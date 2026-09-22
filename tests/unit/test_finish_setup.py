import os
import time

import pytest
from rich.text import Text

from update_my_mac import finish_setup, shell_configs


class Terminal:
    """Scripted answers in, everything printed collected."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.lines = []

    def ask(self, prompt):
        self.lines.append(prompt)
        return self.answers.pop(0)

    def out(self, *parts, **_):
        # What a person would read, without the colour markup.
        self.lines.append(Text.from_markup(" ".join(str(part) for part in parts)).plain)

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture
def machine(tmp_path):
    """A home, a bin dir holding the installed command, and a bare PATH."""
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "update").write_text("#!/bin/sh\n# update_my_mac\n")
    env = {"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin"}
    return home, bin_dir, env


def run(machine, *argv, answers=(), interactive=True, now=None):
    home, bin_dir, env = machine
    terminal = Terminal(*answers)
    code = finish_setup.main(
        ["--bin-dir", str(bin_dir), *argv],
        ask=terminal.ask,
        out=terminal.out,
        err=terminal.out,
        env=env,
        interactive=interactive,
        now=now,
    )
    return code, terminal.text


def test_enter_keeps_the_default_name(machine):
    code, text = run(machine, answers=[""])
    assert code == 0
    assert "Try: update --check" in text


def test_another_name_becomes_a_link_to_the_command(machine):
    _, bin_dir, _ = machine
    code, _ = run(machine, "--name", "mac-update", interactive=False)

    assert code == 0
    assert os.readlink(bin_dir / "mac-update") == str(bin_dir / "update")


def test_an_unusable_name_without_a_terminal_fails(machine):
    code, text = run(machine, "--name", "../escaped", interactive=False)
    assert code == 1
    assert "not a usable command name" in text


def test_an_unusable_name_is_asked_for_again(machine):
    code, text = run(machine, answers=["has space", "mac-update"])
    assert code == 0
    assert "not a usable command name" in text
    assert "Try: mac-update --check" in text


def test_a_name_another_program_has_is_refused(machine):
    _, bin_dir, env = machine
    other = bin_dir.parent / "other"
    other.mkdir()
    (other / "tool").write_text("#!/bin/sh\n")
    (other / "tool").chmod(0o755)
    env["PATH"] += f":{other}"

    code, text = run(machine, "--name", "tool", interactive=False)

    assert code == 1
    assert f"'tool' is already {other / 'tool'}" in text


def test_another_copy_of_this_tool_is_not_a_conflict(machine):
    # A development environment's own `update` is still this tool.
    _, bin_dir, env = machine
    venv = bin_dir.parent / "venv"
    venv.mkdir()
    (venv / "update").write_text("from update_my_mac.cli import main\n")
    (venv / "update").chmod(0o755)
    env["PATH"] = f"{venv}:{env['PATH']}"

    code, _ = run(machine, interactive=False)
    assert code == 0


def test_a_shell_builtin_is_refused(machine):
    code, text = run(machine, "--name", "cd", interactive=False)
    assert code == 1
    assert "'cd' is already" in text


def test_an_existing_file_is_never_overwritten(machine):
    _, bin_dir, _ = machine
    (bin_dir / "keep-me").write_text("mine\n")

    code, text = run(machine, "--name", "keep-me", interactive=False)

    assert code == 1
    assert "already exists" in text
    assert (bin_dir / "keep-me").read_text() == "mine\n"


def home_with(machine, relative, content):
    home, _, _ = machine
    path = home / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_without_a_terminal_a_definition_stops_setup_untouched(machine):
    # Installing anyway would leave a command the alias hides.
    zshrc = home_with(machine, ".zshrc", "alias update=old\n")

    code, text = run(machine, interactive=False)

    assert code == 1
    assert "already defined in your shell config" in text
    assert "--name" in text
    assert zshrc.read_text() == "alias update=old\n"


def test_choosing_another_name_leaves_the_alias_as_it_was(machine):
    zshrc = home_with(machine, ".zshrc", "alias update=old\n")

    code, text = run(machine, answers=["", "1", "mac-update"])

    assert code == 0
    assert zshrc.read_text() == "alias update=old\n"
    assert "Try: mac-update --check" in text


def test_choosing_to_disable_comments_it_out(machine):
    zshrc = home_with(machine, ".zshrc", "alias update=old\n")

    code, _ = run(machine, answers=["", "2"])

    assert code == 0
    assert zshrc.read_text() == "# alias update=old\n"


def test_a_fish_abbreviation_is_disabled_too(machine):
    config = home_with(machine, ".config/fish/config.fish", "abbr -a update old\n")

    code, _ = run(machine, answers=["", "2"])

    assert code == 0
    assert config.read_text() == "# abbr -a update old\n"


def test_a_function_block_is_not_offered_for_disabling(machine):
    zshrc = home_with(machine, ".zshrc", "update() {\n  echo old\n}\n")

    code, text = run(machine, answers=["", "2"])

    assert code == 1
    assert "stop here" in text
    assert "disable it" not in text
    assert "spans several lines" in text
    assert zshrc.read_text() == "update() {\n  echo old\n}\n"


def test_a_function_block_can_be_avoided_with_another_name(machine):
    zshrc = home_with(machine, ".zshrc", "update() {\n  echo old\n}\n")

    code, text = run(machine, answers=["", "1", "mac-update"])

    assert code == 0
    assert "Try: mac-update --check" in text
    assert zshrc.read_text() == "update() {\n  echo old\n}\n"


def test_there_is_no_option_to_install_it_hidden(machine):
    home_with(machine, ".zshrc", "alias update=old\n")

    _, text = run(machine, answers=["", "1", "mac-update"])

    assert "3)" not in text


def test_a_stray_answer_asks_again(machine):
    home_with(machine, ".zshrc", "alias update=old\n")

    code, text = run(machine, answers=["", "3", "1", "mac-update"])

    assert code == 0
    assert "Please answer 1 or 2" in text


def pretend_calling_shell(monkeypatch, shell, running_for):
    monkeypatch.setattr(shell_configs, "shell_of_process", lambda pid: shell)
    monkeypatch.setattr(shell_configs, "seconds_since_start", lambda pid: running_for)


def test_a_terminal_older_than_its_config_is_warned_about(machine, monkeypatch):
    home_with(machine, ".zshrc", "# edited just now\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text = run(machine, "--calling-pid", "1", interactive=False, now=time.time())

    assert "opened before your shell config last changed" in text
    assert "unalias update" in text


def test_a_fish_terminal_is_told_the_fish_way(machine, monkeypatch):
    home_with(machine, ".config/fish/config.fish", "# edited just now\n")
    pretend_calling_shell(monkeypatch, "fish", running_for=3600)

    _, text = run(machine, "--calling-pid", "1", interactive=False, now=time.time())

    assert "functions -e update" in text
    assert "unalias" not in text


def test_a_terminal_newer_than_its_config_gets_no_warning(machine, monkeypatch):
    zshrc = home_with(machine, ".zshrc", "# old\n")
    long_ago = time.time() - 86400
    os.utime(zshrc, (long_ago, long_ago))
    pretend_calling_shell(monkeypatch, "zsh", running_for=60)

    _, text = run(machine, "--calling-pid", "1", interactive=False, now=time.time())

    assert "opened before" not in text


def test_keeping_the_alias_under_another_name_gets_no_warning(machine, monkeypatch):
    # The alias stays because the user chose that, and the new name was just
    # made up, so no terminal can be holding an old one.
    home_with(machine, ".zshrc", "alias update=old\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text = run(
        machine, "--calling-pid", "1", answers=["", "1", "mac-update"], now=time.time()
    )

    assert "opened before" not in text


def test_a_made_up_name_gets_no_warning(machine, monkeypatch):
    home_with(machine, ".zshrc", "# edited just now\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text = run(
        machine, "--calling-pid", "1", "--name", "mac-update", interactive=False, now=time.time()
    )

    assert "opened before" not in text


def test_disabling_from_an_old_terminal_is_warned_about(machine, monkeypatch):
    home_with(machine, ".zshrc", "alias update=old\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text = run(machine, "--calling-pid", "1", answers=["", "2"], now=time.time())

    assert "opened before your shell config last changed" in text


def test_a_missing_path_entry_is_pointed_out(machine):
    _, bin_dir, env = machine
    env["PATH"] = "/usr/bin:/bin"

    _, text = run(machine, interactive=False)

    assert f"Add {bin_dir} to your PATH" in text


def test_a_bracket_in_a_path_is_text_not_colour_markup(tmp_path):
    # rich would read "[ird]" as a style and either drop it or fail.
    home = tmp_path / "we[ird]"
    home.mkdir()
    (home / ".zshrc").write_text("alias update=old\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "update").write_text("# update_my_mac\n")
    terminal = Terminal()

    finish_setup.main(
        ["--bin-dir", str(bin_dir)],
        out=terminal.out,
        err=terminal.out,
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin"},
        interactive=False,
    )

    assert "we[ird]/.zshrc" in terminal.text


def interrupted_by(exception):
    def ask(_prompt):
        raise exception

    return ask


def test_ctrl_c_at_a_question_stops_without_a_traceback(machine):
    _, bin_dir, env = machine
    terminal = Terminal()

    code = finish_setup.main(
        ["--bin-dir", str(bin_dir)],
        ask=interrupted_by(KeyboardInterrupt()),
        out=terminal.out,
        err=terminal.out,
        env=env,
        interactive=True,
    )

    assert code == 130
    assert "Setup stopped" in terminal.text


def test_running_out_of_input_stops_too(machine):
    _, bin_dir, env = machine
    terminal = Terminal()

    code = finish_setup.main(
        ["--bin-dir", str(bin_dir)],
        ask=interrupted_by(EOFError()),
        out=terminal.out,
        err=terminal.out,
        env=env,
        interactive=True,
    )

    assert code == 1
    assert "no more input" in terminal.text
