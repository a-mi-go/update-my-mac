"""Draw the logo: a gear with a tick, inside a cycle of two arrows.

The shapes are computed from angles and radii rather than written by hand, so
thickness, head size or colours can be changed in one line:

    python docs/logo.py docs/logo.svg
"""

import math
import pathlib
import sys

C = 64.0
OUTER, INNER = 48.0, 36.0
HEAD_OUT, HEAD_IN = 56.0, 28.0


def point(angle, radius):
    a = math.radians(angle)
    return C + radius * math.cos(a), C + radius * math.sin(a)


def fmt(p):
    return f"{p[0]:.2f} {p[1]:.2f}"


def ring_segment(start, end, outer, inner):
    """A filled arc from start to end, angles growing clockwise on screen."""
    large = 1 if (end - start) % 360 > 180 else 0
    return (
        f"M{fmt(point(start, outer))} A{outer} {outer} 0 {large} 1 {fmt(point(end, outer))} "
        f"L{fmt(point(end, inner))} A{inner} {inner} 0 {large} 0 {fmt(point(start, inner))} Z"
    )


def head(at, reach):
    """A triangle across the ring at the end of a segment, pointing onward."""
    return (
        f"M{fmt(point(at + reach, (HEAD_OUT + HEAD_IN) / 2))} "
        f"L{fmt(point(at, HEAD_OUT))} L{fmt(point(at, HEAD_IN))} Z"
    )


def build(background_top, background_bottom, arrow_fill):
    parts = []
    for start, end in ((185, 330), (5, 150)):
        parts.append(ring_segment(start, end, OUTER, INNER))
        parts.append(head(end, 20))
    arrows = "\n".join(f'    <path d="{part}"/>' for part in parts)

    teeth = "\n".join(
        f'    <rect x="{C - 5.5:.2f}" y="{C - 27:.2f}" width="9" height="12" rx="3" '
        f'transform="rotate({i * 45} {C} {C})"/>'
        for i in range(8)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128" role="img" aria-label="update-my-mac logo">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{background_top}"/>
      <stop offset="1" stop-color="{background_bottom}"/>
    </linearGradient>
  </defs>
  <rect x="4" y="4" width="120" height="120" rx="28" fill="url(#bg)"/>

  <!-- The cycle: two arrows, each a ring segment and a head in one shape. -->
  <g fill="#ffffff">
{arrows}
  </g>

  <!-- The gear, with a tick for "checked". -->
  <g fill="#ffffff">
{teeth}
    <circle cx="{C}" cy="{C}" r="20"/>
  </g>
  <circle cx="{C}" cy="{C}" r="12.5" fill="{arrow_fill}"/>
  <path d="M{C - 6.5:.1f} {C:.0f} L{C - 1.5:.1f} {C + 5:.0f} L{C + 7.5:.1f} {C - 6:.0f}" fill="none"
        stroke="#ffffff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1])
    out.write_text(build("#2f6feb", "#1b4fc4", "#1b4fc4"))
    print("wrote", out)
