"""The private parts of prompt_toolkit that the menus rely on are still there."""

from prompt_toolkit.application import Application
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.renderer import Renderer
from prompt_toolkit.styles import Style

from update_my_mac.view import prompt_toolkit_internals


def test_the_private_names_the_menus_rely_on_still_exist():
    renderer = Renderer(Style([]), DummyOutput())
    names = prompt_toolkit_internals.PRIVATE_NAMES

    missing = [name for name in names["application"] if not hasattr(Application, name)]
    missing += [name for name in names["renderer"] if not hasattr(renderer, name)]

    assert missing == []
