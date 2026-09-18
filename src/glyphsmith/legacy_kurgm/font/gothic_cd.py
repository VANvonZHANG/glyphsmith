# src/glyphsmith/legacy_kurgm/font/gothic_cd.py
"""The cdDrawU family: a case-by-case direct translation of K/font/gothic/cd.ts
(165 lines).

Three upstream utilities that cd.ts depends on are ported along with it
(private to this module; to be factored out when the T10 mincho cd tables need
them):
- _Pen ← K/pen.ts (pen position/heading, local coords → global coords)
- normalize / quadratic and cubic Bézier (+ derivatives) ← K/util.ts:5-55
- _generate_fatten_curve ← K/curve.ts:53-97 (fatten a curve along its normal
  into left/right outline bands)

push semantics (hard rule 1): in kurgm every contour enters the stack through
Polygons.push (K/polygons.ts:54-84) — fewer than 3 points is rejected; floor
(K/polygon.ts:365-375 rounds the ×10 internal coordinates = user coordinates
truncated to the 0.1 grid); NaN is rejected; degenerate polygons (minx===maxx
or miny===maxy, with the initial values 200/0/200/0 copied verbatim) are
rejected. This module replicates those semantics through push_polygon(), the
single entry point into the Outline; Outline.push itself does not floor (T2
contract), the floor responsibility lives here.

Vertex order is fingerprint-sensitive (hard rule 2): push winding direction and
the position of the first point are always copied from the source, with no
normalisation whatsoever.
"""
from __future__ import annotations

import math

from glyphsmith.outline import Outline

from ..geom2d import _round

_NAN = float("nan")


# ── K/util.ts:5-18 hypot / normalize ────────────────────────────
def _hypot(x: float, y: float) -> float:
    """Faithful replication of V8 Math.hypot (K/util.ts:8 = the Math.hypot
    binding).

    Python math.hypot is (approximately) correctly rounded, whereas V8 uses the
    scaling algorithm max*sqrt((x/max)²+(y/max)²) — the two differ observably
    in the last ULP (measured: hypot(-9.41…,17.64…) → V8 gives
    19.999999999999996 vs Python 20.0, which flips the 0.1-grid floor and hence
    the fingerprint). 200k random pairs agree across the whole sweep. NaN/Inf
    semantics: either ±Inf → +Inf (overriding NaN); otherwise either NaN → NaN;
    all zeros → +0. Two-argument signature (kurgm only ever uses two).
    """
    if math.isinf(x) or math.isinf(y):
        return float("inf")
    if math.isnan(x) or math.isnan(y):
        return _NAN
    m = abs(x) if abs(x) > abs(y) else abs(y)
    if m == 0:
        return 0.0
    nx = x / m
    ny = y / m
    return m * math.sqrt(nx * nx + ny * ny)


def normalize(x: float, y: float, magnitude: float = 1) -> tuple[float, float]:
    """K/util.ts:11-18 normalize: same angle, new magnitude.

    The zero-vector branch copies the source's trick:
    `1 / x === Infinity ? magnitude : -magnitude`
    (+0 → +Infinity → +magnitude; -0 → -Infinity → -magnitude). Python's 1/x
    raises ZeroDivisionError for 0, so copysign is used to tell ±0 apart as an
    equivalent implementation.
    """
    if x == 0 and y == 0:
        return (magnitude if math.copysign(1.0, x) > 0 else -magnitude, 0)
    k = magnitude / _hypot(x, y)
    return (x * k, y * k)


# ── K/util.ts:21-55 Bézier primitives (formulas verbatim, eval order kept) ──
def _quadratic_bezier(p1, p2, p3, t):
    s = 1 - t
    return (s * s) * p1 + 2 * (s * t) * p2 + (t * t) * p3


def _quadratic_bezier_deriv(p1, p2, p3, t):
    return 2 * (t * (p1 - 2 * p2 + p3) - p1 + p2)


def _cubic_bezier(p1, p2, p3, p4, t):
    s = 1 - t
    return (s * s * s) * p1 + 3 * (s * s * t) * p2 + 3 * (s * t * t) * p3 + (t * t * t) * p4


def _cubic_bezier_deriv(p1, p2, p3, p4, t):
    return 3 * (t * (t * (-p1 + 3 * p2 - 3 * p3 + p4) + 2 * (p1 - 2 * p2 + p3)) - p1 + p2)


# ── K/pen.ts:9-68 Pen ───────────────────────────────────────────
class _Pen:
    """K/pen.ts Pen: maps local coordinates to global given pen position and heading."""

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.cos_theta = 1.0
        self.sin_theta = 0.0

    def set_matrix2(self, cos_theta: float, sin_theta: float) -> "_Pen":
        self.cos_theta = cos_theta
        self.sin_theta = sin_theta
        return self

    def set_left(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        # Given: rotate(theta)((-1, 0)) = (dx, dy)
        # Determine: (cos theta, sin theta) = rotate(theta)((1, 0)) = (-dx, -dy)
        return self.set_matrix2(-dx, -dy)

    def set_right(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        return self.set_matrix2(dx, dy)

    def set_up(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        # Given: rotate(theta)((0, -1)) = (dx, dy)
        # Determine: (cos theta, sin theta) = rotate(theta)((1, 0)) = (-dy, dx)
        return self.set_matrix2(-dy, dx)

    def set_down(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        return self.set_matrix2(dy, -dx)

    def move(self, local_dx: float, local_dy: float) -> "_Pen":
        self.x, self.y = self.get_point(local_dx, local_dy)[:2]
        return self

    def get_point(self, local_x: float, local_y: float, off: int = 0):
        return (self.x + self.cos_theta * local_x + -self.sin_theta * local_y,
                self.y + self.sin_theta * local_x + self.cos_theta * local_y,
                off)

    def get_polygon(self, local_points: list[tuple[float, float, int]]
                    ) -> list[tuple[float, float, int]]:
        """K/pen.ts:65-67 getPolygon: map a whole local point list to a global contour."""
        return [self.get_point(x, y, off) for x, y, off in local_points]


# ── K/curve.ts:53-97 generateFattenCurve ────────────────────────
def _generate_fatten_curve(x1, y1, sx1, sy1, sx2, sy2, x2, y2,
                           k_rate, width_func):
    """Fatten a curve: offset ±width along the normal; left/right bands (point order copied)."""
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []

    is_quadratic = sx1 == sx2 and sy1 == sy2
    if is_quadratic:
        # Spline
        x_func = lambda t: _quadratic_bezier(x1, sx1, x2, t)        # noqa: E731
        y_func = lambda t: _quadratic_bezier(y1, sy1, y2, t)        # noqa: E731
        ix_func = lambda t: _quadratic_bezier_deriv(x1, sx1, x2, t)  # noqa: E731
        iy_func = lambda t: _quadratic_bezier_deriv(y1, sy1, y2, t)  # noqa: E731
    else:  # Bezier
        x_func = lambda t: _cubic_bezier(x1, sx1, sx2, x2, t)       # noqa: E731
        y_func = lambda t: _cubic_bezier(y1, sy1, sy2, y2, t)       # noqa: E731
        ix_func = lambda t: _cubic_bezier_deriv(x1, sx1, sx2, x2, t)  # noqa: E731
        iy_func = lambda t: _cubic_bezier_deriv(y1, sy1, sy2, y2, t)  # noqa: E731

    tt = 0.0
    while tt <= 1000:                    # for (let tt = 0; tt <= 1000; tt += kRate)
        t = tt / 1000

        # calculate a dot
        x = x_func(t)
        y = y_func(t)

        # KATAMUKI of vector by BIBUN
        ix = ix_func(t)
        iy = iy_func(t)

        width = width_func(t)

        # line SUICHOKU by vector
        if _round(ix) == 0 and _round(iy) == 0:
            ia, ib = -width, 0           # ????? (source comment)
        else:
            ia, ib = normalize(-iy, ix, width)

        left.append((x - ia, y - ib))
        right.append((x + ia, y + ib))
        tt += k_rate
    return left, right


# ── K/polygons.ts:54-84 Polygons.push (hard rule 1) ─────────────
def _floor10(v: float) -> float:
    """Direct translation of JS Math.floor: NaN/±Inf pass through unchanged
    (Python math.floor raises ValueError/OverflowError for both — found by the
    T16 full-dump smoke: 27 glyphs errored out entirely when NaN coordinates
    reached push, whereas kurgm's floor(NaN)=NaN is then dropped by the
    per-point check)."""
    return math.floor(v) if math.isfinite(v) else v


def push_polygon(outline: Outline, points) -> None:
    """Direct translation of kurgm Polygons.push: the only stack entry point in
    this module (and in the later mincho cd tables).

    1. `polygon.length < 3` → discarded outright (returns without pushing);
    2. `polygon.floor()` (K/polygon.ts:365-375): internal coordinates = user
       coordinates ×10 (K:33 _precision=10, applied on push), and floor rounds
       the internal coordinates → user coordinates truncated to the 0.1 grid —
       this has already happened even if the contour is ultimately rejected (a
       local copy, no side effects);
    3. any NaN coordinate → discarded (floor(NaN)=NaN; the source checks per
       point after updating min/max); Infinity is not intercepted (matching the
       source, it is left to the fingerprint layer to report non-finite);
    4. degenerate rejection: minx===maxx or miny===maxy (initial values
       200/0/200/0 copied verbatim — coordinates all out of range on the same
       side can hit the initial values too, and the semantics follow).
    """
    if len(points) < 3:
        return
    pts = [(_floor10(x * 10) / 10, _floor10(y * 10) / 10, off)
           for x, y, off in points]
    minx = 200
    maxx = 0
    miny = 200
    maxy = 0
    for x, y, _off in pts:
        if x < minx:
            minx = x
        if x > maxx:
            maxx = x
        if y < miny:
            miny = y
        if y > maxy:
            maxy = y
        if math.isnan(x) or math.isnan(y):
            return
    if minx != maxx and miny != maxy:
        outline.contours.append(pts)


# ── K/font/gothic/cd.ts:8-84 curves (the cdDrawU family) ────────
def _cd_draw_curve_u(font, outline,
                     x1, y1, sx1, sy1, sx2, sy2, x2, y2,
                     _ta1=0, _ta2=0) -> None:
    # cd.ts:15-17: the source declares `let a1` / `let a2` and never assigns
    # them, so switch (a1 % 10) is really undefined % 10 = NaN — no case
    # matches, delta1/delta2 stay 0, and both if blocks are dead code (the
    # lib/esm build output is the same). Translated with a NaN sentinel to stay
    # faithful in both structure and runtime behaviour (the parameter names
    # _ta1/_ta2 are copied over — the source never used them either).
    a1 = _NAN
    a2 = _NAN

    delta1 = 0
    m = math.fmod(a1, 10)
    if m == 2:
        delta1 = font.params.k_width
    elif m == 3:
        delta1 = font.params.k_width * font.params.k_kakato

    if delta1 != 0:
        if x1 == sx1 and y1 == sy1:
            dx1, dy1 = 0, delta1        # ????? (source comment)
        else:
            dx1, dy1 = normalize(x1 - sx1, y1 - sy1, delta1)
        x1 += dx1
        y1 += dy1

    delta2 = 0
    m = math.fmod(a2, 10)
    if m == 2:
        delta2 = font.params.k_width
    elif m == 3:
        delta2 = font.params.k_width * font.params.k_kakato

    if delta2 != 0:
        if sx2 == x2 and sy2 == y2:
            dx2, dy2 = 0, -delta2       # ????? (source comment)
        else:
            dx2, dy2 = normalize(x2 - sx2, y2 - sy2, delta2)
        x2 += dx2
        y2 += dy2

    _draw_curve_body(outline, font, x1, y1, sx1, sy1, sx2, sy2, x2, y2)


def _draw_curve_body(outline, font,
                     x1, y1, sx1, sy1, sx2, sy2, x2, y2) -> None:
    left, right = _generate_fatten_curve(
        x1, y1, sx1, sy1, sx2, sy2, x2, y2,
        font.params.k_rate,
        lambda t: font.params.k_width,
    )

    poly = [(x, y, 0) for x, y in left]
    poly2 = [(x, y, 0) for x, y in right]
    # save to polygon
    poly2.reverse()
    poly.extend(poly2)
    push_polygon(outline, poly)


def cd_draw_bezier(font, outline,
                   x1, y1, x2, y2, x3, y3, x4, y4,
                   a1, a2) -> None:
    _cd_draw_curve_u(font, outline, x1, y1, x2, y2, x3, y3, x4, y4, a1, a2)


def cd_draw_curve(font, outline,
                  x1, y1, x2, y2, x3, y3,
                  a1, a2) -> None:
    _cd_draw_curve_u(font, outline, x1, y1, x2, y2, x2, y2, x3, y3, a1, a2)


# ── K/font/gothic/cd.ts:101-165 lines ───────────────────────────
def cd_draw_line(font, outline,
                 tx1, ty1, tx2, ty2,
                 ta1, ta2) -> None:
    if tx1 == tx2 and ty1 > ty2 or tx1 > tx2:
        x1, y1 = tx2, ty2
        x2, y2 = tx1, ty1
        a1, a2 = ta2, ta1
    else:
        x1, y1 = tx1, ty1
        x2, y2 = tx2, ty2
        a1, a2 = ta1, ta2

    pen1 = _Pen(x1, y1)
    pen2 = _Pen(x2, y2)
    if x1 != x2 or y1 != y2:            # ????? (source comment)
        pen1.set_down(x2, y2)
        pen2.set_up(x1, y1)

    w = font.params.k_width
    m = math.fmod(a1, 10)
    if m == 2:
        pen1.move(0, -w)
    elif m == 3:
        pen1.move(0, -w * font.params.k_kakato)

    m = math.fmod(a2, 10)
    if m == 2:
        pen2.move(0, w)
    elif m == 3:
        pen2.move(0, w * font.params.k_kakato)

    # SUICHOKU NO ICHI ZURASHI HA Math.sin TO Math.cos NO IREKAE + x-axis MAINUSU KA
    poly = [pen1.get_point(w, 0),
            pen2.get_point(w, 0),
            pen2.get_point(-w, 0),
            pen1.get_point(-w, 0)]
    if tx1 == tx2:
        poly.reverse()                  # ????? (source comment)

    push_polygon(outline, poly)
