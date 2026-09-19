# src/glyphsmith/pen/centerline.py
"""Stroke centerline extraction: RStroke -> flattened polyline.

Which of a stroke's four points a type uses mirrors legacy_kurgm's
get_control_segments exactly (so pen and legacy always agree on the geometry
the data denotes). One deliberate deviation (spec §4.3.1): `quad` and `cubic`
are sampled as true Bezier curves instead of their control polygons.
"""
from __future__ import annotations

import math

FLATTEN_TOL = 0.25      # max chord height, KAGE units (the 200x200 box)
_MAX_DEPTH = 10         # recursion backstop for pathological input

# Point counts, mirroring get_control_segments: the 6/7 group uses x3x4, the
# 2/3/4/12 group uses x2x3, everything else x1x2.
_USES = {6: 4, 7: 4, 2: 3, 3: 3, 4: 3, 12: 3}
_NO_SEGMENT = (0, 8, 9)


def extract(stroke) -> list[tuple[float, float]]:
    """The stroke's centerline as a polyline; [] when the type draws nothing.

    Dispatching on `a1_100 if a1_opt == 0 else 1` reproduces
    get_control_segments' handling of a1-bitfield rows (a1_opt != 0 -> a plain
    line). Non-finite input returns the raw control polygon unchanged: the nib
    layer detects it and drops the stroke with a warning, and returning here
    keeps every caller free of NaN loops.
    """
    a1 = stroke.a1_100 if stroke.a1_opt == 0 else 1
    if a1 in _NO_SEGMENT:
        return []
    pts = [(stroke.x1, stroke.y1), (stroke.x2, stroke.y2),
           (stroke.x3, stroke.y3), (stroke.x4, stroke.y4)][:_USES.get(a1, 2)]
    if not all(math.isfinite(v) for p in pts for v in p):
        return [(float(x), float(y)) for x, y in pts]
    if a1 == 2:
        return [pts[0]] + _flatten_quad(pts[0], pts[1], pts[2])
    if a1 == 6:
        return [pts[0]] + _flatten_cubic(pts[0], pts[1], pts[2], pts[3])
    return [(float(x), float(y)) for x, y in pts]


def arc_length(pts) -> float:
    """Polyline length."""
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


# Half-open [lo, hi) sectors over phi = atan2(dy, dx) in degrees, y-down.
# Exhaustive and non-overlapping (spec §4.2.1): [-180,-170) and [170,180] are
# handled separately below because atan2 returns a closed 180.
SECTORS = ((-10.0, 10.0, "horizontal"), (10.0, 70.0, "right-falling"),
           (70.0, 110.0, "vertical"), (110.0, 170.0, "left-falling"),
           (-170.0, -110.0, "left-falling"), (-110.0, -70.0, "vertical"),
           (-70.0, -10.0, "rising"))


def classify_orientation(pts) -> str:
    """The stroke's width-profile band, from its start->end chord (spec §4.2.1).

    The chord (not the arc) is what the design fixes: calligraphic direction is
    about where the stroke goes, and a bent stroke like 竖弯钩 still reads as a
    vertical. Degenerate centerlines fall back to "horizontal" — the nib layer
    drops zero-length strokes anyway, so the value only has to be total.
    """
    if len(pts) < 2:
        return "horizontal"
    dx = pts[-1][0] - pts[0][0]
    dy = pts[-1][1] - pts[0][1]
    if dx == 0.0 and dy == 0.0:
        return "horizontal"
    phi = math.degrees(math.atan2(dy, dx))
    if phi < -170.0 or phi >= 170.0:
        return "horizontal"
    for lo, hi, name in SECTORS:
        if lo <= phi < hi:
            return name
    return "horizontal"


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _dist_to_line(p, a, b) -> float:
    """Distance from p to segment ab; falls back to |p-a| when a == b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    if n == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / n


def _flatten_quad(p0, c, p1, out=None, depth=0):
    """De Casteljau subdivision until the control point's chord height <= tol."""
    out = [] if out is None else out
    if depth >= _MAX_DEPTH or _dist_to_line(c, p0, p1) <= FLATTEN_TOL:
        out.append(p1)
        return out
    a, b = _mid(p0, c), _mid(c, p1)
    m = _mid(a, b)
    _flatten_quad(p0, a, m, out, depth + 1)
    _flatten_quad(m, b, p1, out, depth + 1)
    return out


def _flatten_cubic(p0, c0, c1, p1, out=None, depth=0):
    """Same, with both control points tested against the chord."""
    out = [] if out is None else out
    if depth >= _MAX_DEPTH or max(_dist_to_line(c0, p0, p1),
                                  _dist_to_line(c1, p0, p1)) <= FLATTEN_TOL:
        out.append(p1)
        return out
    a, b, c = _mid(p0, c0), _mid(c0, c1), _mid(c1, p1)
    d, e = _mid(a, b), _mid(b, c)
    m = _mid(d, e)
    _flatten_cubic(p0, a, d, m, out, depth + 1)
    _flatten_cubic(m, e, c, p1, out, depth + 1)
    return out


# The five band *names* classify_orientation can return, in canonical order.
# The wrap-around sectors live in classify_orientation itself, so the names are
# all a style file needs to key its width profile on.
BANDS = tuple(sorted({name for _lo, _hi, name in SECTORS}))


def vertex_ts(pts) -> list[float]:
    """Arc-length-normalised parameter per vertex, in [0, 1] (spec §4.2.2: the
    width profile is keyed on t, so a long and a short stroke share one recipe)."""
    if len(pts) < 2:
        return [0.0] * len(pts)
    cum, total = [0.0], 0.0
    for i in range(len(pts) - 1):
        total += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        cum.append(total)
    if total <= 0.0:
        return [0.0] * len(pts)
    return [c / total for c in cum]
