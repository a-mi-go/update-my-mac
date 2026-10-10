"""The warning that a Ctrl-C leaves behind lives in a module, so it outlives
a test. Cleared before each one, or a test that presses Ctrl-C once would
make the next test's first press count as the second."""

import pytest

from update_my_mac.view import prompting


@pytest.fixture(autouse=True)
def forget_the_interrupt_warning():
    prompting.answered()
