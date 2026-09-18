"""2D geometry primitives: a line-by-line port of kurgm kage-engine's K/2d.ts
(cross is an internal helper; round is a direct translation of K/util.ts:85-87)."""
from __future__ import annotations

import math

# Reference : http://www.cam.hi-ho.ne.jp/strong_warriors/teacher/chapter0{4,5}.html


def _round(v: float, rate: float = 1e8) -> float:
    """K/util.ts round(v, rate=1E8) = Math.round(v*rate)/rate.

    JS Math.round is half-up (0.5 towards +∞) whereas Python round is banker's
    rounding, so math.floor(x + 0.5) is used as the direct translation (only
    for float boundaries of the 0.49999999999999994 kind is there a known
    difference from JS; inside KAGE's coordinate domain the cross products are
    integer values times 1e5 and are unaffected). floor goes through js_floor:
    JS Math.round(NaN)=NaN passes through (the T16 closure smoke found 2 glyphs
    raising ValueError here).
    """
    return js_floor(v * rate + 0.5) / rate


def js_div(a: float, b: float) -> float:
    """IEEE-754 division (JS semantics): b==0 → ±Inf / 0/0 → NaN, without
    raising ZeroDivisionError (T16 full closure smoke: in 119 glyphs a
    degenerate box divided by zero inside stretch, and kurgm's resulting NaN
    coordinates were dropped by push_polygon)."""
    if b:
        return a / b
    if a > 0:
        return math.inf
    if a < 0:
        return -math.inf
    return math.nan


def js_floor(v: float) -> float:
    """JS Math.floor: NaN/±Inf pass through unchanged (Python math.floor raises for both)."""
    return math.floor(v) if math.isfinite(v) else v


def js_min(a: float, b: float) -> float:
    """JS Math.min: NaN contagion (either operand NaN → NaN). Python's min
    compares False against NaN and would silently drop it in favour of a finite
    value — the box-poisoning semantics of nested closure stretches (the T16
    smoke found 84 glyphs drawn with extra ink) depend on this."""
    if math.isnan(a) or math.isnan(b):
        return math.nan
    return a if a <= b else b


def js_max(a: float, b: float) -> float:
    """JS Math.max: as js_min, NaN contagion."""
    if math.isnan(a) or math.isnan(b):
        return math.nan
    return a if a >= b else b


def _cross(x1: float, y1: float, x2: float, y2: float) -> float:
    """Cross product of two vectors"""
    return x1 * y2 - x2 * y1


def is_cross(
    x11: float, y11: float, x12: float, y12: float,
    x21: float, y21: float, x22: float, y22: float,
) -> bool:
    cross_1112_2122 = _cross(x12 - x11, y12 - y11, x22 - x21, y22 - y21)
    if math.isnan(cross_1112_2122):
        return True  # for backward compatibility...
    if cross_1112_2122 == 0:
        # parallel
        return False  # XXX should check if segments overlap?

    cross_1112_1121 = _cross(x12 - x11, y12 - y11, x21 - x11, y21 - y11)
    cross_1112_1122 = _cross(x12 - x11, y12 - y11, x22 - x11, y22 - y11)
    cross_2122_2111 = _cross(x22 - x21, y22 - y21, x11 - x21, y11 - y21)
    cross_2122_2112 = _cross(x22 - x21, y22 - y21, x12 - x21, y12 - y21)

    return _round(cross_1112_1121 * cross_1112_1122, 1e5) <= 0 and \
        _round(cross_2122_2111 * cross_2122_2112, 1e5) <= 0


def is_cross_box(
    x1: float, y1: float, x2: float, y2: float,
    bx1: float, by1: float, bx2: float, by2: float,
) -> bool:
    if is_cross(x1, y1, x2, y2, bx1, by1, bx2, by1):
        return True
    if is_cross(x1, y1, x2, y2, bx2, by1, bx2, by2):
        return True
    if is_cross(x1, y1, x2, y2, bx1, by2, bx2, by2):
        return True
    if is_cross(x1, y1, x2, y2, bx1, by1, bx1, by2):
        return True
    return False
