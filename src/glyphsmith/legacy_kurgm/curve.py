# src/glyphsmith/legacy_kurgm/curve.py
"""K/curve.ts 的逐行移植：divideCurve（:4-23）/ findOffCurve（:27-49）。

curve.ts 第三个导出 generateFattenCurve（:53-97）已随 T8 在
font/gothic_cd.py::_generate_fatten_curve 落地（当时作为 gothic cd.ts 的
上游依赖一并移植，mincho_cd 复用之），本模块不重复实现。

util.ts 依赖：ternarySearchMin（:61-74）随本模块首次落地；
quadraticBezier（:21-24）为 gothic_cd._quadratic_bezier 的同公式最小副本
（见下）。find_offcurve 的最小二乘目标 = 采样曲线上各点到二次贝塞尔的
偏差平方和，x/y 两维独立三叉搜索（区间 [s±area]，area=8）。
"""
from __future__ import annotations

import math

# ── K/util.ts:21-24 quadraticBezier ─────────────────────────────
# 与 font/gothic_cd.py::_quadratic_bezier 同公式的最小副本：本模块位于
# font 层之下（mincho_cd 模块级 import 本模块），不得反向 import
# font/gothic_cd——那会成环 curve → font/__init__ → mincho → mincho_cd
# → curve（部分初始化模块上 from-import 直接 ImportError）。公式逐字符
# 同源、求值顺序不动，golden 锁定。
def _quadratic_bezier(p1, p2, p3, t):
    s = 1 - t
    return (s * s) * p1 + 2 * (s * t) * p2 + (t * t) * p3


# ── K/util.ts:61-74 ternarySearchMin ────────────────────────────
def ternary_search_min(func, left, right, eps=1e-5):
    """三叉搜索求 func 最小值点（kurgm 精度 eps=1E-5，区间收缩算式照抄）。"""
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
    """按 rate=0.5 把控制多边形一分为二，返回 (cut_index, (off1, off2))：
    off = 各半段的六个数 [ax,ay, cx,cy, bx,by]（c 为新段隐含控制点）。"""
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
    """曲线拟合（kUseCurve）：首末点作锚，在 [sx-8, sx+8]×[sy-8, sy+8] 内
    三叉搜索二次贝塞尔控制点，最小化对整条采样曲线的最小二乘偏差。

    返回 [nx1, ny1, minx, miny, nx2, ny2]（首点 x/y、控制点 x/y、末点 x/y）。
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
