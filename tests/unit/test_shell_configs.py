import os
import shutil
import time

import pytest

from update_my_mac import shell_configs


def make_home(tmp_path, **files):
    """A home directory holding the given config files, by relative path."""
    home = tmp_path / "home"
    for relative, content in files.items():
        path = home / relative.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    home.mkdir(exist_ok=True)
    return home


def found(name, home, **extra_env):
    env = {"HOME": str(home), **extra_env}
    return [
        (d.kind, d.path.name, d.line_number, d.can_disable)
        for d in shell_configs.find_shadowing_definitions(name, env)
    ]


def test_zsh_and_bash_aliases_are_found_with_their_line(tmp_path):
    home = make_home(
        tmp_path,
        **{".zshrc": "# mine\nalias update='echo old'\n", ".bashrc": "alias update=old\n"},
    )
    assert found("update", home) == [
        ("alias", ".zshrc", 2, True),
        ("alias", ".bashrc", 1, True),
    ]


def test_a_zsh_global_alias_counts_too(tmp_path):
    home = make_home(tmp_path, **{".zshrc": "alias -g update=old\n"})
    assert found("update", home) == [("alias", ".zshrc", 1, True)]


def test_a_function_is_found_but_not_offered_for_editing(tmp_path):
    home = make_home(tmp_path, **{".zshrc": "update() {\n  echo old\n}\n"})
    assert found("update", home) == [("function", ".zshrc", 1, False)]


def test_similar_names_are_not_confused(tmp_path):
    home = make_home(
        tmp_path, **{".zshrc": "alias updater=x\nalias update2=x\nalias my_update=x\n"}
    )
    assert found("update", home) == []


def test_a_dot_in_the_name_is_a_literal_dot(tmp_path):
    home = make_home(tmp_path, **{".zshrc": "alias macXupdate=x\n"})
    assert found("mac.update", home) == []


def test_a_fish_alias_in_either_spelling(tmp_path):
    home = make_home(
        tmp_path,
        **{".config__fish__config.fish": 'alias update "echo old"\nalias update=\'echo old\'\n'},
    )
    assert found("update", home) == [
        ("alias", "config.fish", 1, True),
        ("alias", "config.fish", 2, True),
    ]


def test_fish_abbreviations_with_and_without_options(tmp_path):
    home = make_home(
        tmp_path,
        **{".config__fish__conf.d__abbr.fish": "abbr -a update x\nabbr --add -g update x\nabbr update x\n"},
    )
    assert [kind for kind, *_ in found("update", home)] == ["abbreviation"] * 3


def test_erasing_an_abbreviation_is_not_defining_one(tmp_path):
    home = make_home(
        tmp_path,
        **{".config__fish__config.fish": "abbr -e update\nabbr --erase update\n"},
    )
    assert found("update", home) == []


def test_a_fish_function_block_is_not_offered_for_editing(tmp_path):
    home = make_home(
        tmp_path,
        **{".config__fish__conf.d__mine.fish": "function update\n    echo old\nend\n"},
    )
    assert found("update", home) == [("function", "mine.fish", 1, False)]


def test_a_fish_function_file_is_the_whole_definition(tmp_path):
    home = make_home(
        tmp_path, **{".config__fish__functions__update.fish": "function update; end\n"}
    )
    assert found("update", home) == [("function", "update.fish", 0, True)]


def test_xdg_config_home_is_where_fish_looks(tmp_path):
    home = make_home(tmp_path)
    elsewhere = tmp_path / "xdg"
    (elsewhere / "fish").mkdir(parents=True)
    (elsewhere / "fish" / "config.fish").write_text("alias update x\n")

    assert found("update", home, XDG_CONFIG_HOME=str(elsewhere)) == [
        ("alias", "config.fish", 1, True)
    ]


def test_disabling_comments_out_and_backs_up_once(tmp_path):
    home = make_home(tmp_path, **{".zshrc": "alias update=a\nexport X=1\nalias update=b\n"})
    zshrc = home / ".zshrc"
    definitions = shell_configs.find_shadowing_definitions("update", {"HOME": str(home)})

    shell_configs.disable(definitions)

    assert zshrc.read_text() == "# alias update=a\nexport X=1\n# alias update=b\n"
    backups = list(home.glob(".zshrc.bak-*"))
    assert len(backups) == 1
    # The backup is the file as it was, not after the first of the two edits.
    assert backups[0].read_text() == "alias update=a\nexport X=1\nalias update=b\n"


def test_disabling_moves_a_fish_function_file_where_fish_wont_load_it(tmp_path):
    home = make_home(
        tmp_path, **{".config__fish__functions__update.fish": "function update; end\n"}
    )
    definitions = shell_configs.find_shadowing_definitions("update", {"HOME": str(home)})

    shell_configs.disable(definitions)

    functions = home / ".config" / "fish" / "functions"
    assert not (functions / "update.fish").exists()
    assert [p.name.startswith("update.fish.disabled-") for p in functions.iterdir()] == [True]


def test_what_cannot_be_disabled_is_left_alone(tmp_path):
    home = make_home(tmp_path, **{".zshrc": "update() {\n  echo old\n}\n"})
    definitions = shell_configs.find_shadowing_definitions("update", {"HOME": str(home)})

    assert shell_configs.disable(definitions) == []
    assert (home / ".zshrc").read_text() == "update() {\n  echo old\n}\n"


def test_elapsed_time_in_each_format_ps_uses():
    assert shell_configs.parse_elapsed("00:05") == 5
    assert shell_configs.parse_elapsed("01:02:03") == 3723
    assert shell_configs.parse_elapsed("2-01:00:00") == 2 * 86400 + 3600
    assert shell_configs.parse_elapsed("") is None
    assert shell_configs.parse_elapsed("Mo. 21 Sep.") is None


def test_config_changed_since(tmp_path):
    config = tmp_path / ".zshrc"
    config.write_text("")
    now = time.time()
    os.utime(config, (now, now))

    assert shell_configs.config_changed_since(now - 60, [config])
    assert not shell_configs.config_changed_since(now + 60, [config])
    assert not shell_configs.config_changed_since(now, [tmp_path / "missing"])


def test_the_clearing_line_is_in_the_shells_own_language():
    assert "unalias update" in shell_configs.clear_line("zsh", "update")
    assert "unset -f update" in shell_configs.clear_line("bash", "update")
    assert shell_configs.clear_line("fish", "update").startswith("functions -e update")


def test_this_process_is_not_a_shell():
    assert shell_configs.shell_of_process(os.getpid()) is None


def test_builtins_are_recognised_per_shell():
    assert shell_configs.builtin_in("bash", "cd")
    assert not shell_configs.builtin_in("bash", "update")


def a_tool_in(tmp_path):
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    tool = tool_dir / "mytool"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    return tool_dir


def new_terminal_env(home):
    return {"HOME": str(home), "PATH": "/usr/bin:/bin"}


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_a_command_added_to_path_in_zshenv_is_found_in_a_new_terminal(tmp_path):
    tool_dir = a_tool_in(tmp_path)
    home = make_home(tmp_path, **{".zshenv": f'export PATH="{tool_dir}:$PATH"\n'})

    assert shell_configs.found_in_new_terminal("zsh", "mytool", new_terminal_env(home)) is True


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_a_zshrc_that_sets_path_from_scratch_hides_the_command(tmp_path):
    tool_dir = a_tool_in(tmp_path)
    home = make_home(tmp_path, **{
        ".zshenv": f'export PATH="{tool_dir}:$PATH"\n',
        ".zshrc": "export PATH=/usr/bin:/bin\n",
    })

    assert shell_configs.found_in_new_terminal("zsh", "mytool", new_terminal_env(home)) is False


def test_a_shell_that_is_not_installed_is_unknown(tmp_path):
    env = {"HOME": str(tmp_path), "PATH": str(tmp_path)}

    assert shell_configs.found_in_new_terminal("zsh", "mytool", env) is None
