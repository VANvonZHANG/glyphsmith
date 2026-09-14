# src/gsrender/legacy_kurgm/font/gothic_cd.py
"""cdDrawU 家族：K/font/gothic/cd.ts（165 行）的逐 case 直译。

一并移植 cd.ts 依赖的三个上游工具（本模块私有；mincho cd 表 T10 需要时再
提取共享）：
- _Pen ← K/pen.ts（局部坐标 → 全局坐标的笔位置/姿态）
- normalize / 二三次 Bézier(+导数) ← K/util.ts:5-55
- _generate_fatten_curve ← K/curve.ts:53-97（曲线沿法线增肥为左右轮廓带）

push 语义（铁律 1）：kurgm 中一切轮廓经 Polygons.push（K/polygons.ts:54-84）
入栈——少于 3 点拒绝；floor（K/polygon.ts:365-375 对 ×10 内部坐标取整 =
用户坐标截断到 0.1 网格）；NaN 拒绝；退化（minx===maxx 或 miny===maxy，
初值 200/0/200/0 照抄）拒绝。本模块以 push_polygon() 为唯一落 Outline 入口
复刻该语义；Outline.push 本身不 floor（T2 契约），floor 责任在此。

顶点顺序指纹敏感（铁律 2）：push 顺/逆时针、首点位置一律照抄源，
不做任何规整。
"""
from __future__ import annotations

import math

from gsrender.outline import Outline

from ..geom2d import _round

_NAN = float("nan")


# ── K/util.ts:5-18 hypot / normalize ────────────────────────────
def normalize(x: float, y: float, magnitude: float = 1) -> tuple[float, float]:
    """K/util.ts:11-18 normalize：同角度、新模长的向量。

    零向量分支照抄源的奇技：`1 / x === Infinity ? magnitude : -magnitude`
    （+0 → +Infinity → +magnitude；-0 → -Infinity → -magnitude）。Python
    1/x 对 0 抛 ZeroDivisionError，用 copysign 区分 ±0 等价实现。
    """
    if x == 0 and y == 0:
        return (magnitude if math.copysign(1.0, x) > 0 else -magnitude, 0)
    k = magnitude / math.hypot(x, y)
    return (x * k, y * k)


# ── K/util.ts:21-55 Bézier 基元（算式逐项照抄，浮点求值顺序不动）──
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
    """K/pen.ts Pen：按笔位置与朝向把局部坐标换算为全局坐标。"""

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.cos_theta = 1.0
        self.sin_theta = 0.0

    def _set_matrix2(self, cos_theta: float, sin_theta: float) -> "_Pen":
        self.cos_theta = cos_theta
        self.sin_theta = sin_theta
        return self

    def set_left(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        # Given: rotate(theta)((-1, 0)) = (dx, dy)
        # Determine: (cos theta, sin theta) = rotate(theta)((1, 0)) = (-dx, -dy)
        return self._set_matrix2(-dx, -dy)

    def set_right(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        return self._set_matrix2(dx, dy)

    def set_up(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        # Given: rotate(theta)((0, -1)) = (dx, dy)
        # Determine: (cos theta, sin theta) = rotate(theta)((1, 0)) = (-dy, dx)
        return self._set_matrix2(-dy, dx)

    def set_down(self, other_x: float, other_y: float) -> "_Pen":
        dx, dy = normalize(other_x - self.x, other_y - self.y)
        return self._set_matrix2(dy, -dx)

    def move(self, local_dx: float, local_dy: float) -> "_Pen":
        self.x, self.y = self.get_point(local_dx, local_dy)[:2]
        return self

    def get_point(self, local_x: float, local_y: float, off: int = 0):
        return (self.x + self.cos_theta * local_x + -self.sin_theta * local_y,
                self.y + self.sin_theta * local_x + self.cos_theta * local_y,
                off)


# ── K/curve.ts:53-97 generateFattenCurve ────────────────────────
def _generate_fatten_curve(x1, y1, sx1, sy1, sx2, sy2, x2, y2,
                           k_rate, width_func):
    """曲线增肥：沿法线偏移 ±width，产出左右两条轮廓带（点序照抄源）。"""
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
            ia, ib = -width, 0           # ?????（源注释）
        else:
            ia, ib = normalize(-iy, ix, width)

        left.append((x - ia, y - ib))
        right.append((x + ia, y + ib))
        tt += k_rate
    return left, right


# ── K/polygons.ts:54-84 Polygons.push（铁律 1）──────────────────
def push_polygon(outline: Outline, points) -> None:
    """kurgm Polygons.push 的直译：本模块（及后续 mincho cd 表）的唯一落栈口。

    1. `polygon.length < 3` → 直接丢弃（返回不入栈）；
    2. `polygon.floor()`（K/polygon.ts:365-375）：内部坐标 = 用户坐标 ×10
       （K:33 _precision=10，push 时乘），floor 对内部坐标取整 → 用户坐标
       截断到 0.1 网格——即使轮廓最终被拒绝也已完成（本地副本，无副作用）；
    3. NaN 任一坐标 → 丢弃（floor(NaN)=NaN，源在 min/max 更新后逐点检查）；
       Infinity 不被拦截（与源一致，交由指纹层报 non-finite）；
    4. 退化拒绝：minx===maxx 或 miny===maxy（初值 200/0/200/0 照抄——
       全部坐标同侧越界时可能同时触到初值，语义随之）。
    """
    if len(points) < 3:
        return
    pts = [(math.floor(x * 10) / 10, math.floor(y * 10) / 10, off)
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


# ── K/font/gothic/cd.ts:8-84 曲线（cdDrawU 家族）────────────────
def _cd_draw_curve_u(font, outline,
                     x1, y1, sx1, sy1, sx2, sy2, x2, y2,
                     _ta1=0, _ta2=0) -> None:
    # cd.ts:15-17：源声明 let a1 / let a2 后从未赋值，switch (a1 % 10)
    # 实为 undefined % 10 = NaN——无 case 命中，delta1/delta2 恒 0，两个
    # if 块为死代码（lib/esm 编译产物同此）。以 NaN 哨兵直译，保持结构与
    # 运行时行为双忠实（参数名 _ta1/_ta2 照抄，即源中本就未用）。
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
            dx1, dy1 = 0, delta1        # ?????（源注释）
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
            dx2, dy2 = 0, -delta2       # ?????（源注释）
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


# ── K/font/gothic/cd.ts:101-165 直线 ────────────────────────────
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
    if x1 != x2 or y1 != y2:            # ?????（源注释）
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
        poly.reverse()                  # ?????（源注释）

    push_polygon(outline, poly)
