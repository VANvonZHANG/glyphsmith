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
    floor 走 js_floor：JS Math.round(NaN)=NaN 穿透（T16 闭包冒烟 2 字形
    在此 ValueError）。
    """
    return js_floor(v * rate + 0.5) / rate


def js_div(a: float, b: float) -> float:
    """IEEE-754 除法（JS 语义）：b==0 → ±Inf / 0/0 → NaN，不抛
    ZeroDivisionError（T16 全量闭包冒烟：119 字形退化 box 在 stretch 里
    除零，kurgm 出 NaN 坐标由 push_polygon 丢弃）。"""
    if b:
        return a / b
    if a > 0:
        return math.inf
    if a < 0:
        return -math.inf
    return math.nan


def js_floor(v: float) -> float:
    """JS Math.floor：NaN/±Inf 原样穿透（Python math.floor 对两者抛）。"""
    return math.floor(v) if math.isfinite(v) else v


def js_min(a: float, b: float) -> float:
    """JS Math.min：NaN 传染（任一操作数 NaN → NaN）。Python min 遇 NaN
    比较恒 False 会静默丢弃 NaN 保有限值——闭包嵌套 stretch 的 box 污染
    语义（T16 冒烟 84 字形多画）依赖本语义。"""
    if math.isnan(a) or math.isnan(b):
        return math.nan
    return a if a <= b else b


def js_max(a: float, b: float) -> float:
    """JS Math.max：同 js_min，NaN 传染。"""
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
