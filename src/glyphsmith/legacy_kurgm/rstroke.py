# src/glyphsmith/legacy_kurgm/rstroke.py
"""RStroke: a faithful port of K/stroke.ts (decoding the rendering semantics)."""
from __future__ import annotations

import math

from .geom2d import is_cross, is_cross_box, js_div, js_floor, js_max, js_min


def _js_mod(a: int, b: int) -> int:
    """JS `%` semantics: truncated remainder (sign follows the dividend) =
    math.fmod; Python's native `%` is a floor remainder (sign follows the
    divisor), and the two agree only when the dividend is non-negative or the
    division is exact (remainder 0). A 3500-case differential fuzz against the
    real engine (kurgm stroke.ts, run directly under node) confirmed that the
    two differ for negative a2 (a2=-1505 → JS remainder -5 / Python 95;
    a2_opt=-15 → JS opt_1=-5 / Python 5), so JS semantics are implemented here
    (the brief's contingency: expose the difference and switch to fmod)."""
    return int(math.fmod(a, b))


def stretch(dp: int, sp: int, p: int, mn: int, mx: int) -> int:
    """K/stroke.ts:3-20. Division/floor use JS semantics (a 0 divisor → ±Inf/NaN
    passes through, and polygons with NaN coordinates are dropped by
    push_polygon — the T16 full closure smoke found 119 such glyphs)."""
    if p < sp + 100:
        p1, p3, p2, p4 = mn, mn, sp + 100, dp + 100
    else:
        p1, p3, p2, p4 = sp + 100, dp + 100, mx, mx
    return js_floor(js_div(p - p1, p2 - p1) * (p4 - p3) + p3)


class RStroke:
    """kurgm's Stroke class: decimal bitfield decomposition of a1/a2/a3 + geometry."""

    def __init__(self, a1_100: int, a2_100: int, a3_100: int,
                 x1: float, y1: float, x2: float, y2: float,
                 x3: float, y3: float, x4: float, y4: float) -> None:
        self.a1_100, self.a2_100, self.a3_100 = a1_100, a2_100, a3_100
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.x3, self.y3, self.x4, self.y4 = x3, y3, x4, y4
        # decomposition (K/stroke.ts:62-74). Remainders always go through
        # _js_mod (JS truncated-remainder semantics, see its docstring);
        # Math.floor and Python math.floor both round towards negative
        # infinity, so they are used directly.
        self.a1_opt = math.floor(self.a1_100 / 100); self.a1_100 = _js_mod(self.a1_100, 100)
        self.a2_opt = math.floor(self.a2_100 / 100); self.a2_100 = _js_mod(self.a2_100, 100)
        self.a2_opt_1 = _js_mod(self.a2_opt, 10)
        self.a2_opt_2 = _js_mod(math.floor(self.a2_opt / 10), 10)
        self.a2_opt_3 = math.floor(self.a2_opt / 100)
        self.a3_opt = math.floor(self.a3_100 / 100); self.a3_100 = _js_mod(self.a3_100, 100)
        self.a3_opt_1 = _js_mod(self.a3_opt, 10)
        self.a3_opt_2 = math.floor(self.a3_opt / 10)

    @classmethod
    def from_gsf(cls, stroke) -> "RStroke":
        pts = tuple(stroke.pts) + ((0, 0),) * 4
        return cls(stroke.a1, stroke.a2, stroke.a3,
                   pts[0][0], pts[0][1], pts[1][0], pts[1][1],
                   pts[2][0], pts[2][1], pts[3][0], pts[3][1])

    def get_control_segments(self):
        # K/stroke.ts:77-101 (the switch fall-through unrolled). Source case
        # groups: 0/8/9 → break (no segment); 6/7 → fall through after x3x4;
        # 2/12/3/4 → fall through after x2x3; default → x1x2 only.
        # Correction note: the brief's unrolling omitted case 12 (source line
        # 92); restored from the source.
        res = []
        a1 = self.a1_100 if self.a1_opt == 0 else 1
        if a1 in (6, 7):
            res.insert(0, (self.x3, self.y3, self.x4, self.y4))
        if a1 in (2, 3, 4, 12) or a1 in (6, 7):
            res.insert(0, (self.x2, self.y2, self.x3, self.y3))
        if a1 not in (0, 8, 9):
            res.insert(0, (self.x1, self.y1, self.x2, self.y2))
        return res

    def is_cross(self, bx1, by1, bx2, by2):
        return any(is_cross(x1, y1, x2, y2, bx1, by1, bx2, by2)
                   for x1, y1, x2, y2 in self.get_control_segments())

    def is_cross_box(self, bx1, by1, bx2, by2):
        return any(is_cross_box(x1, y1, x2, y2, bx1, by1, bx2, by2)
                   for x1, y1, x2, y2 in self.get_control_segments())

    def apply_stretch(self, sx, sx2, sy, sy2,
                      bmin_x, bmax_x, bmin_y, bmax_y):    # K/stroke.ts:115-128
        self.x1 = stretch(sx, sx2, self.x1, bmin_x, bmax_x)
        self.y1 = stretch(sy, sy2, self.y1, bmin_y, bmax_y)
        self.x2 = stretch(sx, sx2, self.x2, bmin_x, bmax_x)
        self.y2 = stretch(sy, sy2, self.y2, bmin_y, bmax_y)
        if not (self.a1_100 == 99 and self.a1_opt == 0):   # source annotates this "always true"
            self.x3 = stretch(sx, sx2, self.x3, bmin_x, bmax_x)
            self.y3 = stretch(sy, sy2, self.y3, bmin_y, bmax_y)
            self.x4 = stretch(sx, sx2, self.x4, bmin_x, bmax_x)
            self.y4 = stretch(sy, sy2, self.y4, bmin_y, bmax_y)

    def get_box(self):
        # K/stroke.ts:130-163 (the switch fall-through unrolled). The source's
        # default label comes first, and the textual order is default body →
        # case 2/3/4 body → case 1/99 body → case 0:
        #   default entry (a1∉{0,1,2,3,4,99}, including 6/7) → x4, x3 and x1x2
        #     are all included;
        #   case 2/3/4 → x3 + x1x2; case 1/99 → x1x2 only; case 0 → empty.
        # Correction note: the brief's unrolling wrote the x3/x1x2 coverage as
        # a1∈{2,3,4,6,7}/{1,2,3,4,6,7,99}, missing the default fall-through
        # coverage (e.g. a1=5/8/9); restored from the source to
        # x4 ⟺ a1∉{0,1,2,3,4,99}; x3 ⟺ a1∉{0,1,99}; x1x2 ⟺ a1≠0.
        inf = float("inf")
        min_x, min_y, max_x, max_y = inf, inf, -inf, -inf
        a1 = self.a1_100 if self.a1_opt == 0 else 6
        # min/max use JS semantics (NaN contagion, K/stroke.ts Math.min/max) —
        # the NaN coordinates of a degenerate stretch must infect the box with
        # NaN, which in turn makes the outer stretch all NaN (the polygon is
        # dropped by push); Python's min would silently drop the NaN and keep a
        # finite value.
        if a1 not in (0, 1, 2, 3, 4, 99):   # default entry (includes x4)
            min_x, max_x = js_min(min_x, self.x4), js_max(max_x, self.x4)
            min_y, max_y = js_min(min_y, self.y4), js_max(max_y, self.y4)
        if a1 not in (0, 1, 99):            # case 2/3/4 body + default fall-through
            min_x, max_x = js_min(min_x, self.x3), js_max(max_x, self.x3)
            min_y, max_y = js_min(min_y, self.y3), js_max(max_y, self.y3)
        if a1 != 0:                         # case 1/99 body + upstream fall-through
            min_x, max_x = js_min(js_min(min_x, self.x1), self.x2), \
                js_max(js_max(max_x, self.x1), self.x2)
            min_y, max_y = js_min(js_min(min_y, self.y1), self.y2), \
                js_max(js_max(max_y, self.y1), self.y2)
        return {"minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y}
