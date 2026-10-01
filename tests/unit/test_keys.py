"""Answering a menu with the arrow keys, and not doing so anywhere else."""

from update_my_mac import keys, prompting

from fake_terminal import Terminal


def test_the_keys_are_not_offered_without_a_terminal():
    # Every test and every pipe runs here, and every one of them types.
    assert not keys.available()


def test_a_step_types_by_default_where_there_is_no_terminal():
    terminal = Terminal("1")

    assert prompting.Step(terminal.out, terminal.ask).choose([("a", "one")]) == "a"


def test_a_step_can_be_told_which_way_to_ask():
    typed = prompting.Step(Terminal("1").out, Terminal("1").ask, with_keys=False)

    assert not typed.with_keys
    assert prompting.Step(with_keys=True).with_keys


def test_going_inside_keeps_the_way_of_asking():
    inner = prompting.Step(with_keys=False).inside().inside()

    assert not inner.with_keys


def test_a_missing_library_means_typing_rather_than_crashing(monkeypatch):
    # An installed command from before the library was added would otherwise
    # fall over in the middle of a run.
    monkeypatch.setattr(keys.importlib.util, "find_spec", lambda name: None)

    assert not keys.available()


def answers(key):
    """A menu that returns this answer, whatever is shown."""
    return lambda question, entries: key


def choices():
    return [("adopt", "get them back on track"), ("all", "fix everything"), ("no", "not now")]


def test_a_line_the_cursor_skips_sets_the_way_out_apart(monkeypatch):
    seen = []
    monkeypatch.setattr(keys, "pick_one",
                        lambda question, entries: seen.append(entries) or "adopt")

    prompting.Step(with_keys=True).choose(choices())

    # None is drawn as a separator, which questionary will not land on.
    assert seen[0][2] is None
    assert [entry[0] for entry in seen[0] if entry] == ["adopt", "all", "no"]


def test_the_answer_comes_straight_back(monkeypatch):
    # Each choice carries the answer it stands for, so nothing is counted
    # back around the line.
    monkeypatch.setattr(keys, "pick_one", answers("no"))

    assert prompting.Step(with_keys=True).choose(choices()) == "no"


def test_backing_out_stops_the_step(monkeypatch):
    monkeypatch.setattr(keys, "pick_one", lambda question, entries: None)

    try:
        prompting.Step(with_keys=True).choose(choices())
    except prompting.Stopped:
        return
    raise AssertionError("escape should stop the step")


def test_the_question_is_handed_to_the_menu_that_draws_it(monkeypatch):
    asked = []
    monkeypatch.setattr(keys, "pick_one",
                        lambda question, entries: asked.append(question) or "adopt")

    prompting.Step(with_keys=True).choose(choices(), "[bold]What should we do?[/]")

    # Without the markup, which the menu would print as text.
    assert asked == ["What should we do?"]


def test_a_menu_that_will_not_draw_falls_back_to_typing(monkeypatch):
    # Whatever went wrong in the library, there is always the other way.
    def refuse(question, entries):
        raise keys.Unusable("no terminal capability")

    monkeypatch.setattr(keys, "pick_one", refuse)
    terminal = Terminal("3")

    chosen = prompting.Step(terminal.out, terminal.ask, with_keys=True).choose(choices())

    assert chosen == "no"
    assert "could not be drawn" in terminal.text


def resolved(part):
    """What a part of a question actually looks like once drawn.

    questionary merges its own style under ours, so what matters is the
    result rather than what was asked for.
    """
    from prompt_toolkit.styles import merge_styles
    from questionary.constants import DEFAULT_STYLE

    merged = merge_styles([DEFAULT_STYLE, keys._style()])
    return merged.get_attrs_for_style_str(f"class:{part}")


def test_the_question_stays_bold_and_plain():
    # A question looks like a question; the colour belongs to what the
    # cursor is on.
    attrs = resolved("question")

    assert attrs.color == ""
    assert attrs.bold


def test_the_cursor_is_what_wears_the_colour():
    for part in ("qmark", "pointer", "highlighted"):
        assert resolved(part).color == "00ffff", part


def test_the_answer_is_left_in_the_terminals_own_colour():
    # It is the answer, not part of the asking. questionary would paint it
    # orange and bold.
    attrs = resolved("answer")

    assert attrs.color == ""
    assert not attrs.bold


def test_the_hint_is_readable_rather_than_dimmed():
    # Grey on a dark terminal was barely there.
    attrs = resolved("instruction")

    assert attrs.color == ""
    assert not attrs.bold
