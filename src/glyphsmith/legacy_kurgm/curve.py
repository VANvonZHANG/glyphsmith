# src/glyphsmith/legacy_kurgm/curve.py
"""Line-by-line port of K/curve.ts: divideCurve (:4-23) / findOffCurve (:27-49).

curve.ts's third export, generateFattenCurve (:53-97), already landed with T8
in font/gothic_cd.py::_generate_fatten_curve (ported then as an upstream
dependency of gothic cd.ts, and reused by mincho_cd), so this module does not
reimplement it.

util.ts dependencies: ternarySearchMin (:61-74) lands here for the first time
with this module; quadraticBezier (:21-24) is a minimal copy of
gothic_cd._quadratic_bezier with the same formula (see below). find_offcurve's
least-squares objective is the sum of squared deviations from each point on the
sampled curve to a quadratic Bézier, with independent ternary searches in the x
and y dimensions (interval [s±area], area=8).
"""
from __future__ import annotations

import math

# ── K/util.ts:21-24 quadraticBezier ─────────────────────────────
# A minimal copy of font/gothic_cd.py::_quadratic_bezier with the same formula:
# this module sits below the font layer (mincho_cd imports it at module level),
# so it must not import font/gothic_cd back — that would create the cycle
# curve → font/__init__ → mincho → mincho_cd → curve (a from-import on a
# partially initialised module is an immediate ImportError). The formula is
# character-for-character the same and the evaluation order is untouched,
# locked by golden.
def _quadratic_bezier(p1, p2, p3, t):
    s = 1 - t
    return (s * s) * p1 + 2 * (s * t) * p2 + (t * t) * p3


# ── K/util.ts:61-74 ternarySearchMin ────────────────────────────
def ternary_search_min(func, left, right, eps=1e-5):
    """Ternary search for the minimiser of func (kurgm's eps=1E-5; interval shrinking copied)."""
    while left + eps < right:
        x1 = left + (right - left) / 3
        x2 = right - (right - left) / 3
        y1 = func(x1)
        y2 = func(x2)
        if y1 < y2:
            right = x2
        else:
            left = x1
    return left + (right - left) / 2


# ── K/curve.ts:4-23 divideCurve ─────────────────────────────────
def divide_curve(x1, y1, sx1, sy1, x2, y2, curve):
    """Split the control polygon in two at rate=0.5, returning
    (cut_index, (off1, off2)): off = the six numbers of each half
    [ax,ay, cx,cy, bx,by] (c being the new segment's implied control point)."""
    rate = 0.5
    cut = math.floor(len(curve) * rate)
    cut_rate = cut / len(curve)
    tx1 = x1 + (sx1 - x1) * cut_rate
    ty1 = y1 + (sy1 - y1) * cut_rate
    tx2 = sx1 + (x2 - sx1) * cut_rate
    ty2 = sy1 + (y2 - sy1) * cut_rate
    tx3 = tx1 + (tx2 - tx1) * cut_rate
    ty3 = ty1 + (ty2 - ty1) * cut_rate

    # must think about 0 : <0
    return cut, ([x1, y1, tx1, ty1, tx3, ty3], [tx3, ty3, tx2, ty2, x2, y2])


# ── K/curve.ts:27-49 findOffCurve ───────────────────────────────
def find_offcurve(curve, sx, sy):
    """Curve fitting (kUseCurve): anchor on the first and last points, and
    ternary-search the quadratic Bézier control point inside
    [sx-8, sx+8]×[sy-8, sy+8] to minimise the least-squares deviation from the
    whole sampled curve.

    Returns [nx1, ny1, minx, miny, nx2, ny2] (first point x/y, control point
    x/y, last point x/y).
    """
    nx1, ny1 = curve[0]
    nx2, ny2 = curve[len(curve) - 1]

    area = 8

    def error_x(tx):
        diff = 0
        for i, p in enumerate(curve):
            t = i / (len(curve) - 1)
            x = _quadratic_bezier(nx1, tx, nx2, t)

            diff = diff + (p[0] - x) ** 2
        return diff

    def error_y(ty):
        diff = 0
        for i, p in enumerate(curve):
            t = i / (len(curve) - 1)
            y = _quadratic_bezier(ny1, ty, ny2, t)

            diff = diff + (p[1] - y) ** 2
        return diff

    minx = ternary_search_min(error_x, sx - area, sx + area)
    miny = ternary_search_min(error_y, sy - area, sy + area)

    return [nx1, ny1, minx, miny, nx2, ny2]
