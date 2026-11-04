"""The private parts of prompt_toolkit that the menus rely on are still there."""

from types import SimpleNamespace

from prompt_toolkit.application import Application
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.renderer import Renderer
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.styles import Style

from update_my_mac.view import prompt_toolkit_internals


def test_a_resize_erases_the_wrapped_menu_unless_a_screen_of_its_own_is_replayed(monkeypatch):
    erased = []
    monkeypatch.setattr(prompt_toolkit_internals, "erase_the_wrapped_menu", erased.append)
    redrawn = []
    renderer = SimpleNamespace(reset=lambda leave_alternate_screen: redrawn.append("reset"))
    app = SimpleNamespace(
        renderer=renderer,
        _request_absolute_cursor_position=lambda: redrawn.append("cursor"),
        _redraw=lambda: redrawn.append("redraw"),
    )

    prompt_toolkit_internals.redraw_on_resize(app, lambda: False)
    app._on_resize()
    assert erased == [app]

    prompt_toolkit_internals.redraw_on_resize(app, lambda: True)
    app._on_resize()
    assert erased == [app]
    assert redrawn == ["reset", "cursor", "redraw"] * 2


def test_the_private_names_the_menus_rely_on_still_exist():
    renderer = Renderer(Style([]), DummyOutput())
    names = prompt_toolkit_internals.PRIVATE_NAMES

    missing = [name for name in names["application"] if not hasattr(Application, name)]
    missing += [name for name in names["renderer"] if not hasattr(renderer, name)]
    missing += [name for name in names["prompt_session"] if not hasattr(PromptSession, name)]

    assert missing == []
