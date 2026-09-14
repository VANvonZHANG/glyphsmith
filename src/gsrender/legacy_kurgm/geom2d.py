"""2D 几何基元：kurgm kage-engine K/2d.ts 的逐行移植（cross 为内部辅助，
round 为 K/util.ts:85-87 的直译）。"""
from __future__ import annotations

import math

# Reference : http://www.cam.hi-ho.ne.jp/strong_warriors/teacher/chapter0{4,5}.html


def _round(v: float, rate: float = 1e8) -> float:
    """K/util.ts round(v, rate=1E8) = Math.round(v*rate)/rate。

    JS Math.round 是 half-up（0.5 向 +∞），Python round 是 banker's rounding，
    故用 math.floor(x + 0.5) 直译（仅 0.49999999999999994 级浮点边界与 JS
    有已知差异；KAGE 坐标域内叉积均为整数值乘 1e5，不受影响）。
    """
    return math.floor(v * rate + 0.5) / rate


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
