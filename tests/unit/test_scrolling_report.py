"""The report above a menu: its lines, the selection over every control of the screen, and the scrolling."""

from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType

from update_my_mac.system import shell
from update_my_mac.view import scrolling_report
from update_my_mac.view.scrolling_report import Scrolling, ScrollingReport, Selectable, Selection


def numbered(count):
    def print_report(console):
        for number in range(count):
            console.print(f"line {number}")

    return print_report


def words(console):
    console.print("alpha beta gamma")
    console.print("delta   epsilon")
    console.print("zeta")


def text_of(content):
    return [
        "".join(text for _, text, *_ in content.get_line(at)) for at in range(content.line_count)
    ]


def test_the_whole_report_is_the_content_and_its_height_is_the_number_of_lines():
    report = ScrollingReport(numbered(20))

    assert text_of(report.create_content(40, 5)) == [f"line {n}" for n in range(20)]
    assert report.preferred_height(40, 1000, False, None) == 20


def test_the_report_is_printed_again_at_the_width_it_is_given():
    widths = []

    def print_report(console):
        widths.append(console.width)
        console.print("a line")

    report = ScrollingReport(print_report)
    report.create_content(40, 5)
    report.create_content(40, 5)
    report.preferred_height(40, 1000, False, None)
    report.create_content(60, 5)

    assert widths == [40, 60]


def test_what_ran_before_comes_first_and_the_screen_starts_at_the_bottom(monkeypatch):
    shown_the_end = []
    monkeypatch.setattr(
        scrolling_report.output, "replay", lambda console: console.print("earlier 1\nearlier 2")
    )
    report = ScrollingReport(numbered(2))
    report.show_the_end = lambda: shown_the_end.append(True)

    assert text_of(report.create_content(40, 5)) == ["earlier 1", "earlier 2", "line 0", "line 1"]
    assert shown_the_end == [True]


def test_the_screen_is_put_at_the_bottom_only_when_it_is_first_drawn(monkeypatch):
    shown_the_end = []
    monkeypatch.setattr(scrolling_report.output, "replay", lambda console: console.print("earlier"))
    report = ScrollingReport(numbered(2))
    report.show_the_end = lambda: shown_the_end.append(True)

    report.create_content(40, 5)
    report.create_content(60, 5)

    assert shown_the_end == [True]


class Pane:
    vertical_scroll = 0


def scrolling(print_report=numbered(3)):
    report = ScrollingReport(print_report)
    pane = Pane()
    selection = Selection()
    return Scrolling(pane, report, selection), pane, report, selection


class MenuKeys:
    def __init__(self):
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.keys import Keys

        self.moved = []
        self.bindings = KeyBindings()
        self.bindings.add(Keys.Up)(lambda event: self.moved.append("up"))
        self.bindings.add(Keys.Down)(lambda event: self.moved.append("down"))
        self.bindings.add(Keys.ControlC)(lambda event: self.moved.append("ctrl-c"))


def keys_of(scrolling_, menu=None):
    bindings = scrolling_.key_bindings((menu or MenuKeys()).bindings)
    return {getattr(binding.keys[0], "value", binding.keys[0]): binding.handler for binding in bindings.bindings}


def test_the_status_line_names_the_keys_until_something_was_copied():
    scrolling_, _, _, selection = scrolling()

    assert "Page Up/Down" in scrolling_.status_line()[0][1]
    assert "Cmd-C" in scrolling_.status_line()[0][1]
    selection.notice = "copied 4 characters"
    assert "copied 4 characters" in scrolling_.status_line()[0][1]


def test_the_status_line_says_there_is_more_above_when_something_ran_before(monkeypatch):
    monkeypatch.setattr(scrolling_report.output, "replay", lambda console: console.print("earlier"))
    scrolling_, _, report, _ = scrolling()
    report.create_content(40, 5)

    assert "what ran before" in scrolling_.status_line()[0][1]


def test_the_page_keys_move_the_pane_by_a_page_and_never_above_its_top():
    scrolling_, pane, _, _ = scrolling()
    keys = keys_of(scrolling_)

    keys["pagedown"](None)
    assert pane.vertical_scroll > 0
    page = pane.vertical_scroll

    keys["pageup"](None)
    keys["pageup"](None)
    assert pane.vertical_scroll == 0
    assert page > 1


def test_home_and_end_go_to_the_ends_and_the_pane_clamps_the_end():
    scrolling_, pane, _, _ = scrolling()
    keys = keys_of(scrolling_)

    keys["end"](None)
    assert pane.vertical_scroll >= 1_000_000

    keys["home"](None)
    assert pane.vertical_scroll == 0


def test_the_arrows_still_move_the_menu_and_take_the_pane_to_it():
    scrolling_, pane, _, _ = scrolling()
    menu = MenuKeys()
    keys = keys_of(scrolling_, menu)

    keys["up"](None)
    keys["down"](None)

    assert menu.moved == ["up", "down"]
    assert pane.vertical_scroll >= 1_000_000


def test_ctrl_c_takes_the_pane_to_the_menu_where_its_warning_appears():
    scrolling_, pane, _, _ = scrolling()
    menu = MenuKeys()

    keys_of(scrolling_, menu)["c-c"](None)

    assert menu.moved == ["ctrl-c"]
    assert pane.vertical_scroll >= 1_000_000


def test_scrolling_takes_the_note_about_a_copy_away():
    scrolling_, _, _, selection = scrolling()
    selection.notice = "copied 4 characters"

    scrolling_.by(1)

    assert selection.notice == ""


def test_the_pane_is_scrolled_to_the_end_when_the_report_asks():
    _, pane, report, _ = scrolling()

    report.show_the_end()

    assert pane.vertical_scroll == scrolling_report.TO_THE_END


class Screen:
    def __init__(self, monkeypatch, print_report=words, below="a line below"):
        self.copied = []
        self.now = 100.0
        monkeypatch.setattr(shell, "copy_to_clipboard", lambda text: self.copied.append(text) or True)
        monkeypatch.setattr(scrolling_report.time, "monotonic", lambda: self.now)
        self.scrolling, self.pane, self.report, self.selection = scrolling(print_report)
        self.controls = [Selectable(self.report, self.selection)]
        if below:
            self.controls.append(Selectable(FormattedTextControl(below), self.selection))
        self.draw()

    def draw(self, width=40):
        return [control.create_content(width, 10) for control in self.controls]

    def event(self, kind, x, y, control=0):
        self.controls[control].mouse_handler(MouseEvent(Point(x, y), kind, MouseButton.LEFT, frozenset()))

    def press(self, x, y, control=0):
        self.event(MouseEventType.MOUSE_DOWN, x, y, control)

    def drag_to(self, x, y, control=0):
        self.event(MouseEventType.MOUSE_MOVE, x, y, control)

    def release(self, x, y, control=0):
        self.event(MouseEventType.MOUSE_UP, x, y, control)

    def drag(self, start, end, control=0, end_control=None):
        self.press(*start, control)
        self.drag_to(*end, control if end_control is None else end_control)
        self.release(*end, control if end_control is None else end_control)

    def highlighted(self, line, control=0):
        content = self.draw()[control]
        return "".join(text for style, text, *_ in content.get_line(line) if "reverse" in style)


def test_dragging_over_text_selects_it_and_copies_it_on_release(monkeypatch):
    screen = Screen(monkeypatch)

    screen.drag((6, 0), (9, 0))

    assert screen.copied == ["beta"]
    assert screen.highlighted(0) == "beta"


def test_a_selection_over_several_lines_takes_the_rest_of_the_first_and_the_start_of_the_last(monkeypatch):
    screen = Screen(monkeypatch)

    screen.drag((11, 0), (3, 2))

    assert screen.copied == ["gamma\ndelta   epsilon\nzeta"]


def test_dragging_backwards_selects_the_same(monkeypatch):
    screen = Screen(monkeypatch)

    screen.drag((9, 0), (6, 0))

    assert screen.copied == ["beta"]


def test_a_click_that_goes_nowhere_selects_and_copies_nothing(monkeypatch):
    screen = Screen(monkeypatch)

    screen.press(3, 0)
    screen.release(3, 0)

    assert screen.copied == []
    assert screen.highlighted(0) == ""


def test_a_double_click_selects_the_word_under_the_pointer(monkeypatch):
    screen = Screen(monkeypatch)

    for _ in range(2):
        screen.press(8, 0)
        screen.release(8, 0)

    assert screen.copied[-1] == "beta"


def test_a_triple_click_selects_the_line(monkeypatch):
    screen = Screen(monkeypatch)

    for _ in range(3):
        screen.press(8, 0)
        screen.release(8, 0)

    assert screen.copied[-1] == "alpha beta gamma"


def test_two_clicks_too_far_apart_in_time_are_two_single_clicks(monkeypatch):
    screen = Screen(monkeypatch)

    screen.press(8, 0)
    screen.release(8, 0)
    screen.now += 5
    screen.press(8, 0)
    screen.release(8, 0)

    assert screen.copied == []


def test_what_is_below_the_report_can_be_selected_too(monkeypatch):
    screen = Screen(monkeypatch)

    screen.drag((2, 0), (5, 0), control=1)

    assert screen.copied == ["line"]
    assert screen.highlighted(0, control=1) == "line"


def test_a_selection_can_run_from_the_report_into_what_is_below_it(monkeypatch):
    screen = Screen(monkeypatch)

    screen.drag((2, 2), (3, 0), control=0, end_control=1)

    assert screen.copied == ["ta\na li"]


def test_a_line_that_the_window_draws_a_prefix_before_can_be_selected_with_the_prefix(monkeypatch):
    screen = Screen(monkeypatch, below=None)
    screen.controls.append(
        Selectable(FormattedTextControl("the answer"), screen.selection, lambda line, wraps: [("", "Q? ")])
    )
    screen.draw()

    screen.drag((0, 0), (7, 0), control=1)

    assert screen.copied == ["Q? the a"]


def test_the_wheel_over_any_control_scrolls_the_pane(monkeypatch):
    screen = Screen(monkeypatch)
    screen.pane.vertical_scroll = 0

    screen.event(MouseEventType.SCROLL_DOWN, 0, 0, control=1)

    assert screen.pane.vertical_scroll == scrolling_report.WHEEL_ROWS


def test_the_control_still_gets_the_mouse_events_the_selection_does_not_take(monkeypatch):
    class Control(FormattedTextControl):
        handled = []

        def mouse_handler(self, mouse_event):
            self.handled.append(mouse_event.event_type)
            return "handled by the control"

    screen = Screen(monkeypatch, below=None)
    selectable = Selectable(Control("below"), screen.selection)
    selectable.create_content(40, 5)

    result = selectable.mouse_handler(
        MouseEvent(Point(0, 0), MouseEventType.MOUSE_MOVE, MouseButton.NONE, frozenset())
    )

    assert result == "handled by the control"
    assert Control.handled == [MouseEventType.MOUSE_MOVE]


def test_the_status_line_says_how_much_was_copied(monkeypatch):
    screen = Screen(monkeypatch)

    screen.drag((6, 0), (9, 0))

    assert "copied 4 characters, they are on the clipboard already" in screen.scrolling.status_line()[0][1]


def test_a_selection_that_could_not_be_copied_says_so(monkeypatch):
    screen = Screen(monkeypatch)
    monkeypatch.setattr(shell, "copy_to_clipboard", lambda text: False)

    screen.drag((6, 0), (9, 0))

    assert "could not copy" in screen.scrolling.status_line()[0][1]


def test_resizing_drops_the_selection_because_its_positions_no_longer_mean_anything(monkeypatch):
    screen = Screen(monkeypatch)
    screen.drag((6, 0), (9, 0))

    screen.draw(width=30)

    assert screen.highlighted(0) == ""


def test_what_was_drawn_before_does_not_count_when_it_is_not_drawn_again(monkeypatch):
    screen = Screen(monkeypatch)
    screen.selection.forget_what_was_drawn()
    screen.drag((6, 2), (3, 0), control=0, end_control=1)

    assert screen.copied == [""]


def test_cmd_c_copies_the_selection_again(monkeypatch):
    screen = Screen(monkeypatch)
    screen.drag((6, 0), (9, 0))
    screen.copied.clear()

    keys_of(screen.scrolling)["f24"](None)

    assert screen.copied == ["beta"]


def test_cmd_c_with_nothing_selected_says_so(monkeypatch):
    screen = Screen(monkeypatch)

    keys_of(screen.scrolling)["f24"](None)

    assert screen.copied == []
    assert "nothing is selected" in screen.scrolling.status_line()[0][1]


def test_a_click_does_not_take_the_pane_to_the_menu(monkeypatch):
    screen = Screen(monkeypatch)
    screen.pane.vertical_scroll = 5

    screen.press(0, 1)

    assert screen.pane.vertical_scroll == 5


class Terminal:
    def __init__(self):
        self.written = []

    def write_raw(self, data):
        self.written.append(data)

    def flush(self):
        pass


def keys_read_from(sequence):
    from prompt_toolkit.input.vt100_parser import Vt100Parser

    read = []
    Vt100Parser(read.append).feed(sequence)
    return [press.key for press in read]


def test_while_the_terminal_reports_modifiers_cmd_c_and_the_keys_that_would_change_are_understood():
    from prompt_toolkit.keys import Keys

    with scrolling_report.reporting_keys_with_modifiers(Terminal()):
        assert keys_read_from("\x1b[99;9u") == [Keys.F24]
        assert keys_read_from("\x1b[99;5u") == [Keys.ControlC]
        assert keys_read_from("\x1b[113;5u") == [Keys.ControlQ]
        assert keys_read_from("\x1b[27u") == [Keys.Escape]


def test_the_keys_are_read_as_before_once_the_menu_is_over():
    with scrolling_report.reporting_keys_with_modifiers(Terminal()):
        pass

    assert keys_read_from("\x1b[99;9u") != [scrolling_report.Keys.F24]


def test_the_terminal_is_asked_to_report_modifiers_and_asked_to_stop_afterwards():
    terminal = Terminal()

    try:
        with scrolling_report.reporting_keys_with_modifiers(terminal):
            assert terminal.written == [scrolling_report.PUSH_KITTY_DISAMBIGUATE]
            raise KeyboardInterrupt
    except KeyboardInterrupt:
        pass

    assert terminal.written == [scrolling_report.PUSH_KITTY_DISAMBIGUATE, scrolling_report.POP_KITTY_FLAGS]
