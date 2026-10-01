import os
import time

import pytest
from rich.text import Text

from update_my_mac import install_command, shell_configs
from fake_terminal import Terminal


class FakeUv:
    """Stands in for uv tool install: creates the command, or fails."""

    def __init__(self, bin_dir, works=True):
        self.bin_dir = bin_dir
        self.works = works
        self.calls = 0

    def __call__(self, project_dir):
        self.calls += 1
        if self.works:
            (self.bin_dir / "update").write_text("# update_my_mac\n")
        return self.works


class FakeUpdateShell:
    """Stands in for uv tool update-shell, which would edit the real shell config."""

    def __init__(self, works=True):
        self.works = works
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.works


@pytest.fixture
def machine(tmp_path):
    """A home, an empty bin dir, and a bare PATH: a first run."""
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    env = {"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin"}
    return home, bin_dir, env


def run(machine, *argv, answers=(), interactive=True, now=None, uv=None, update_shell=None):
    home, bin_dir, env = machine
    terminal = Terminal(*answers)
    uv = uv or FakeUv(bin_dir)
    update_shell = update_shell or FakeUpdateShell()
    code = install_command.main(
        ["--project-dir", "/repo", "--bin-dir", str(bin_dir), *argv],
        ask=terminal.ask,
        out=terminal.out,
        err=terminal.out,
        env=env,
        interactive=interactive,
        now=now,
        install=uv,
        update_shell=update_shell,
    )
    return code, terminal.text, uv


def home_with(machine, relative, content):
    home, _, _ = machine
    path = home / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def installed_before(machine, *links):
    """What an earlier setup would have left in the bin dir."""
    _, bin_dir, _ = machine
    (bin_dir / "update").write_text("# update_my_mac\n")
    for link in links:
        (bin_dir / link).symlink_to(bin_dir / "update")


def test_enter_keeps_the_default_name(machine):
    code, text, uv = run(machine, answers=[""])
    assert code == 0
    assert uv.calls == 1
    assert "Try: update --check" in text


def test_another_name_becomes_a_link_to_the_command(machine):
    _, bin_dir, _ = machine
    code, _, _ = run(machine, "--name", "mac-update", interactive=False)

    assert code == 0
    assert os.readlink(bin_dir / "mac-update") == str(bin_dir / "update")


def test_an_unusable_name_is_asked_for_again(machine):
    code, text, _ = run(machine, answers=["has space", "mac-update"])
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

    code, text, _ = run(machine, "--name", "tool", interactive=False)

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

    code, _, _ = run(machine, interactive=False)
    assert code == 0


def test_a_shell_builtin_is_refused(machine):
    code, text, _ = run(machine, "--name", "cd", interactive=False)
    assert code == 1
    assert "'cd' is already" in text


def test_an_existing_file_is_never_overwritten(machine):
    _, bin_dir, _ = machine
    (bin_dir / "keep-me").write_text("mine\n")

    code, text, uv = run(machine, "--name", "keep-me", interactive=False)

    assert code == 1
    assert "already exists" in text
    assert uv.calls == 0
    assert (bin_dir / "keep-me").read_text() == "mine\n"


def test_a_refused_name_installs_nothing(machine):
    _, bin_dir, _ = machine
    code, _, uv = run(machine, "--name", "cd", interactive=False)

    assert code == 1
    assert uv.calls == 0
    assert not (bin_dir / "update").exists()


def test_a_clash_without_a_terminal_installs_nothing(machine):
    # The case from review: an alias, no terminal to ask on.
    _, bin_dir, _ = machine
    zshrc = home_with(machine, ".zshrc", "alias update=old\n")

    code, text, uv = run(machine, interactive=False)

    assert code == 1
    assert "--name" in text
    assert uv.calls == 0
    assert not (bin_dir / "update").exists()
    assert zshrc.read_text() == "alias update=old\n"


def test_ctrl_c_at_a_question_installs_nothing(machine):
    _, bin_dir, env = machine
    terminal = Terminal()
    uv = FakeUv(bin_dir)

    def ctrl_c(_prompt):
        raise KeyboardInterrupt

    code = install_command.main(
        ["--project-dir", "/repo", "--bin-dir", str(bin_dir)],
        ask=ctrl_c, out=terminal.out, err=terminal.out,
        env=env, interactive=True, install=uv,
    )

    assert code == 130
    assert "Nothing was installed or changed" in terminal.text
    assert uv.calls == 0


def test_running_out_of_input_installs_nothing(machine):
    _, bin_dir, env = machine
    terminal = Terminal()
    uv = FakeUv(bin_dir)

    def end_of_input(_prompt):
        raise EOFError

    code = install_command.main(
        ["--project-dir", "/repo", "--bin-dir", str(bin_dir)],
        ask=end_of_input, out=terminal.out, err=terminal.out,
        env=env, interactive=True, install=uv,
    )

    assert code == 1
    assert uv.calls == 0


def test_a_failed_install_leaves_the_shell_config_alone(machine):
    # "Disable it" is decided before installing but carried out only after.
    _, bin_dir, _ = machine
    zshrc = home_with(machine, ".zshrc", "alias update=old\n")

    code, text, _ = run(machine, answers=["", "2"], uv=FakeUv(bin_dir, works=False))

    assert code == 1
    assert "installing with uv failed" in text
    assert zshrc.read_text() == "alias update=old\n"


def test_choosing_another_name_leaves_the_alias_as_it_was(machine):
    zshrc = home_with(machine, ".zshrc", "alias update=old\n")

    code, text, _ = run(machine, answers=["", "1", "mac-update"])

    assert code == 0
    assert zshrc.read_text() == "alias update=old\n"
    assert "Try: mac-update --check" in text


def test_choosing_to_disable_comments_it_out(machine):
    zshrc = home_with(machine, ".zshrc", "alias update=old\n")

    code, _, _ = run(machine, answers=["", "2"])

    assert code == 0
    assert zshrc.read_text() == "# alias update=old\n"


def test_a_fish_abbreviation_is_disabled_too(machine):
    config = home_with(machine, ".config/fish/config.fish", "abbr -a update old\n")

    code, _, _ = run(machine, answers=["", "2"])

    assert code == 0
    assert config.read_text() == "# abbr -a update old\n"


def test_a_function_block_is_not_offered_for_disabling(machine):
    zshrc = home_with(machine, ".zshrc", "update() {\n  echo old\n}\n")

    code, text, uv = run(machine, answers=["", "2"])

    assert code == 1
    assert "stop here" in text
    assert "disable it" not in text
    assert "spans several lines" in text
    assert uv.calls == 0
    assert zshrc.read_text() == "update() {\n  echo old\n}\n"


def test_a_function_block_can_be_avoided_with_another_name(machine):
    zshrc = home_with(machine, ".zshrc", "update() {\n  echo old\n}\n")

    code, text, _ = run(machine, answers=["", "1", "mac-update"])

    assert code == 0
    assert "Try: mac-update --check" in text
    assert zshrc.read_text() == "update() {\n  echo old\n}\n"


def test_there_is_no_option_to_install_it_hidden(machine):
    home_with(machine, ".zshrc", "alias update=old\n")

    _, text, _ = run(machine, answers=["", "1", "mac-update"])

    assert "3)" not in text


def test_a_stray_answer_asks_again(machine):
    home_with(machine, ".zshrc", "alias update=old\n")

    code, text, _ = run(machine, answers=["", "3", "1", "mac-update"])

    assert code == 0
    assert "Please answer 1 or 2" in text


def test_a_bracket_in_a_path_is_text_not_colour_markup(tmp_path):
    # rich would read "[ird]" as a style and either drop it or fail.
    home = tmp_path / "we[ird]"
    home.mkdir()
    (home / ".zshrc").write_text("alias update=old\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    terminal = Terminal()

    install_command.main(
        ["--project-dir", "/repo", "--bin-dir", str(bin_dir)],
        out=terminal.out,
        err=terminal.out,
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin"},
        interactive=False,
        install=FakeUv(bin_dir),
    )

    assert "we[ird]/.zshrc" in terminal.text


def test_a_first_run_asks_for_a_name(machine):
    _, text, _ = run(machine, answers=[""])
    assert "What should the command be called?" in text
    assert "run before" not in text


def test_a_second_run_offers_to_keep_the_name(machine):
    installed_before(machine, "mac-update")

    code, text, _ = run(machine, answers=[""])

    assert code == 0
    assert "Setup has run before. The command is called mac-update" in text
    assert "What should the command be called?" not in text
    assert "Try: mac-update --check" in text


def test_a_second_run_without_other_names_keeps_update(machine):
    installed_before(machine)

    _, text, _ = run(machine, answers=[""])

    assert "The command is called update" in text
    assert "Try: update --check" in text


def test_a_second_run_can_still_pick_a_new_name(machine):
    _, bin_dir, _ = machine
    installed_before(machine, "mac-update")

    code, text, _ = run(machine, answers=["n", "upd"])

    assert code == 0
    assert os.readlink(bin_dir / "upd") == str(bin_dir / "update")
    assert "Try: upd --check" in text


def test_a_second_run_without_a_terminal_keeps_the_name(machine):
    # Rerunning setup from a script shouldn't quietly fall back to "update".
    installed_before(machine, "mac-update")

    code, text, _ = run(machine, interactive=False)

    assert code == 0
    assert "Try: mac-update --check" in text


def test_a_kept_name_is_still_checked_for_new_clashes(machine):
    # Something may have claimed the name since the last run.
    installed_before(machine, "mac-update")
    home_with(machine, ".zshrc", "alias mac-update=something\n")

    _, text, _ = run(machine, answers=["", "1", "upd"])

    assert "'mac-update' is already defined" in text


def test_something_else_called_update_is_not_an_earlier_setup(machine):
    _, bin_dir, _ = machine
    (bin_dir / "update").write_text("#!/bin/sh\necho someone else's\n")

    assert install_command.names_from_an_earlier_setup(bin_dir) == []


def pretend_calling_shell(monkeypatch, shell, running_for):
    monkeypatch.setattr(shell_configs, "shell_of_process", lambda pid: shell)
    monkeypatch.setattr(shell_configs, "seconds_since_start", lambda pid: running_for)


def test_a_terminal_older_than_its_config_is_warned_about(machine, monkeypatch):
    home_with(machine, ".zshrc", "# edited just now\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text, _ = run(machine, "--calling-pid", "1", interactive=False, now=time.time())

    assert "opened before your shell config last changed" in text
    assert "unalias update" in text


def test_a_fish_terminal_is_told_the_fish_way(machine, monkeypatch):
    home_with(machine, ".config/fish/config.fish", "# edited just now\n")
    pretend_calling_shell(monkeypatch, "fish", running_for=3600)

    _, text, _ = run(machine, "--calling-pid", "1", interactive=False, now=time.time())

    assert "functions -e update" in text
    assert "unalias" not in text


def test_a_terminal_newer_than_its_config_gets_no_warning(machine, monkeypatch):
    zshrc = home_with(machine, ".zshrc", "# old\n")
    long_ago = time.time() - 86400
    os.utime(zshrc, (long_ago, long_ago))
    pretend_calling_shell(monkeypatch, "zsh", running_for=60)

    _, text, _ = run(machine, "--calling-pid", "1", interactive=False, now=time.time())

    assert "opened before" not in text


def test_keeping_the_alias_under_another_name_gets_no_warning(machine, monkeypatch):
    # The alias stays because the user chose that, and the new name was just
    # made up, so no terminal can be holding an old one.
    home_with(machine, ".zshrc", "alias update=old\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text, _ = run(
        machine, "--calling-pid", "1", answers=["", "1", "mac-update"], now=time.time()
    )

    assert "opened before" not in text


def test_a_made_up_name_gets_no_warning(machine, monkeypatch):
    home_with(machine, ".zshrc", "# edited just now\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text, _ = run(
        machine, "--calling-pid", "1", "--name", "mac-update", interactive=False, now=time.time()
    )

    assert "opened before" not in text


def test_disabling_from_an_old_terminal_is_warned_about(machine, monkeypatch):
    home_with(machine, ".zshrc", "alias update=old\n")
    pretend_calling_shell(monkeypatch, "zsh", running_for=3600)

    _, text, _ = run(machine, "--calling-pid", "1", answers=["", "2"], now=time.time())

    assert "opened before your shell config last changed" in text


def test_a_missing_path_entry_is_pointed_out(machine):
    _, bin_dir, env = machine
    env["PATH"] = "/usr/bin:/bin"

    _, text, _ = run(machine, interactive=False)

    assert f"Add {bin_dir} to your PATH" in text
    assert "Done." not in text
    assert "won't be found" in text


def test_a_missing_path_entry_can_be_fixed_on_the_spot(machine):
    _, _, env = machine
    env["PATH"] = "/usr/bin:/bin"
    update_shell = FakeUpdateShell()

    _, text, _ = run(machine, answers=["", ""], update_shell=update_shell)

    assert update_shell.calls == 1
    assert "Open a new terminal, then try: update --check" in text


def test_a_config_that_hides_the_fixed_path_is_pointed_out(machine, monkeypatch):
    _, bin_dir, env = machine
    env["PATH"] = "/usr/bin:/bin"
    env["SHELL"] = "/bin/zsh"
    monkeypatch.setattr(shell_configs, "found_in_new_terminal", lambda shell, name, bin_dir, env: False)

    _, text, _ = run(machine, answers=["", ""])

    assert "still won't find 'update'" in text
    assert "Done." not in text


def test_a_command_a_new_terminal_finds_is_done(machine, monkeypatch):
    _, _, env = machine
    env["PATH"] = "/usr/bin:/bin"
    env["SHELL"] = "/bin/zsh"
    monkeypatch.setattr(shell_configs, "found_in_new_terminal", lambda shell, name, bin_dir, env: True)

    _, text, _ = run(machine, answers=["", ""])

    assert "Open a new terminal, then try: update --check" in text


def test_a_new_terminal_that_cannot_be_asked_does_not_block_done(machine, monkeypatch):
    _, _, env = machine
    env["PATH"] = "/usr/bin:/bin"
    env["SHELL"] = "/bin/zsh"
    monkeypatch.setattr(shell_configs, "found_in_new_terminal", lambda shell, name, bin_dir, env: None)

    _, text, _ = run(machine, answers=["", ""])

    assert "Open a new terminal, then try: update --check" in text


def test_declining_the_path_fix_leaves_the_shell_alone(machine):
    _, bin_dir, env = machine
    env["PATH"] = "/usr/bin:/bin"
    update_shell = FakeUpdateShell()

    _, text, _ = run(machine, answers=["", "n"], update_shell=update_shell)

    assert update_shell.calls == 0
    assert f"Add {bin_dir} to your PATH" in text
    assert "won't be found" in text


def test_a_failed_path_fix_is_not_called_done(machine):
    _, _, env = machine
    env["PATH"] = "/usr/bin:/bin"

    _, text, _ = run(machine, answers=["", "y"], update_shell=FakeUpdateShell(works=False))

    assert "Done." not in text
    assert "won't be found" in text


def test_the_path_is_never_edited_without_a_terminal(machine):
    _, _, env = machine
    env["PATH"] = "/usr/bin:/bin"
    update_shell = FakeUpdateShell()

    run(machine, interactive=False, update_shell=update_shell)

    assert update_shell.calls == 0


def test_another_programs_update_in_the_bin_dir_stops_before_any_question(machine):
    # uv would refuse to replace it anyway, whatever name was chosen.
    _, bin_dir, _ = machine
    (bin_dir / "update").write_text("#!/bin/sh\necho someone else's\n")

    code, text, uv = run(machine, answers=[])

    assert code == 1
    assert "belongs to another program" in text
    assert uv.calls == 0
    assert (bin_dir / "update").read_text() == "#!/bin/sh\necho someone else's\n"
