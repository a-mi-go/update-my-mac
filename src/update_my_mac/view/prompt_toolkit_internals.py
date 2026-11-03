"""The parts of prompt_toolkit that have no public way, kept together so an upgrade breaks them in one place."""

import math

PRIVATE_NAMES = {
    "application": ("_on_resize", "_redraw", "_request_absolute_cursor_position"),
    "renderer": ("_cursor_pos", "_last_screen"),
}


def make_full_screen(app):
    """Makes the menu's application draw on a screen of its own."""
    # Changed in place, because the Ctrl-C handling hangs on this Application.
    app.full_screen = app.renderer.full_screen = True


def wrap_rows(window, label_column, wrap_tokens):
    """Has the window draw what `wrap_tokens` makes of its rows, a wrapped line indented under the label."""
    from prompt_toolkit.filters import Always

    # Only a word longer than the whole line is still cut by the window.
    window.wrap_lines = Always()
    window.get_line_prefix = lambda line_number, wrap_count: [("", " " * label_column)] if wrap_count else []
    rows, drawn = window.content, window.content.text
    rows.text = lambda: wrap_tokens(drawn())


def redraw_on_resize(app, replay_own_screen):
    """Redraws a menu after a resize, which the terminal answers by wrapping the lines already drawn."""
    def on_resize():
        if not replay_own_screen():
            erase_the_wrapped_menu(app)
        app.renderer.reset(leave_alternate_screen=False)
        app._request_absolute_cursor_position()
        app._redraw()

    app._on_resize = on_resize


def erase_the_wrapped_menu(app):
    """Erases from the first menu row, counting the rows each line takes at the new width."""
    out = app.output
    out.write("\r")
    out.cursor_up(rows_above_the_cursor(app.renderer, max(1, out.get_size().columns)))
    out.erase_down()
    out.reset_attributes()
    out.enable_autowrap()
    out.flush()


def rows_above_the_cursor(renderer, width):
    """Returns how many terminal rows lie between the first drawn row and the cursor at this width."""
    cursor = renderer._cursor_pos
    screen = renderer._last_screen
    above = cursor.x // width
    if screen is not None:
        above += sum(rows_taken(screen.data_buffer[y], width) for y in range(cursor.y))
    return above


def rows_taken(row, width):
    """Returns how many terminal rows a drawn line takes at this width."""
    ends = max((x + 1 for x, char in row.items() if char.char != " "), default=0)
    drawn = sum(char.width for x, char in row.items() if x < ends)
    return max(1, math.ceil(drawn / width))
