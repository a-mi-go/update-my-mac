"""The warning that a Ctrl-C leaves behind lives in a module, so it outlives
a test. Cleared before each one, or a test that presses Ctrl-C once would
make the next test's first press count as the second."""

import pytest

import fake_run

from update_my_mac.checks import to_sort_out
from update_my_mac.system import shell
from update_my_mac.view import arrow_menu
from update_my_mac.view import output
from update_my_mac.view import prompting


@pytest.fixture(autouse=True)
def forget_the_interrupt_warning():
    prompting.answered()


@pytest.fixture(autouse=True)
def restore_where_the_run_reads_and_prints():
    """A test may point these at a fake terminal; the next one starts afresh."""
    saved = (prompting.print_unwrapped, prompting.read_answer, output.console, arrow_menu.can_be_drawn, arrow_menu.pick_several)
    yield
    (prompting.print_unwrapped, prompting.read_answer, output.console,
     arrow_menu.can_be_drawn, arrow_menu.pick_several) = saved


@pytest.fixture(autouse=True)
def no_real_bundles():
    """The age of an app is read from the disk, and the apps a test names may exist on this Mac."""
    real = to_sort_out.last_changed
    to_sort_out.last_changed = lambda app: None
    yield
    to_sort_out.last_changed = real


@pytest.fixture(autouse=True)
def forget_what_the_screen_kept():
    """What a run keeps of its own screen outlives the screen, so a test starts without it."""
    output._remembered.clear()
    output._remembering = False
    output._unfinished_line = ""


def _no_real_commands(*args, **kwargs):
    raise AssertionError("a test reached the real shell; give it a fake with use_shell()")


@pytest.fixture(autouse=True)
def no_real_shell(request):
    """Every command goes to a fake, except in the tests of the shell itself."""
    names = ("find_executable", "run_command", "stream_command", "open_in_browser",
             "ask_application_to_quit", "open_application", "is_running", "copy_to_clipboard",
             "move_to_trash")
    saved = {name: getattr(shell, name) for name in names}
    if request.module.__name__ != "test_shell":
        for name in names:
            setattr(shell, name, _no_real_commands)
    yield
    for name, function in saved.items():
        setattr(shell, name, function)
    # A test of the CLI sets the run's environment; the next test starts without.
    shell.use_environment(None)


@pytest.fixture(autouse=True)
def undo_what_a_test_swapped():
    yield
    fake_run.undo_swaps()
