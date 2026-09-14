# src/gsrender/legacy_kurgm/rstroke.py
"""RStroke：K/stroke.ts 的忠实移植（渲染语义解码）。"""
from __future__ import annotations

import math

from .geom2d import is_cross, is_cross_box


def _js_mod(a: int, b: int) -> int:
    """JS `%` 语义：截断余数（符号随被除数）= math.fmod；Python 原生 `%` 是
    floor 余数（符号随除数），二者仅在被除数非负或整除（余 0）时一致。
    对真实引擎（kurgm stroke.ts，node 直跑）的 3500 例对照 fuzz 确认负 a2
    下二者不同（a2=-1505 → JS 余 -5 / Python 余 95；a2_opt=-15 → JS opt_1=-5 /
    Python 5），故按 JS 语义实现（简报预案：暴露差异即改 fmod）。"""
    return int(math.fmod(a, b))


def stretch(dp: int, sp: int, p: int, mn: int, mx: int) -> int:
    """K/stroke.ts:3-20。Math.floor 语义 = Python math.floor（向负无穷）。"""
    if p < sp + 100:
        p1, p3, p2, p4 = mn, mn, sp + 100, dp + 100
    else:
        p1, p3, p2, p4 = sp + 100, dp + 100, mx, mx
    return math.floor(((p - p1) / (p2 - p1)) * (p4 - p3) + p3)


class RStroke:
    """kurgm Stroke 类：a1/a2/a3 十进制位域分解 + 几何。"""

    def __init__(self, a1_100: int, a2_100: int, a3_100: int,
                 x1: float, y1: float, x2: float, y2: float,
                 x3: float, y3: float, x4: float, y4: float) -> None:
        self.a1_100, self.a2_100, self.a3_100 = a1_100, a2_100, a3_100
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.x3, self.y3, self.x4, self.y4 = x3, y3, x4, y4
        # 分解（K/stroke.ts:62-74）。余数一律走 _js_mod（JS 截断余数语义，
        # 见其 docstring）；Math.floor 与 Python math.floor 同为向负无穷，直用。
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
        # K/stroke.ts:77-101（switch fall-through 展开）。源 case 组：
        #   0/8/9 → break（无段）；6/7 → x3x4 后 fall-through；
        #   2/12/3/4 → x2x3 后 fall-through；default → 仅 x1x2。
        # 修正说明：简报展开漏写 case 12（源码 92 行），已按源补上。
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
        if not (self.a1_100 == 99 and self.a1_opt == 0):   # 源码标注 always true
            self.x3 = stretch(sx, sx2, self.x3, bmin_x, bmax_x)
            self.y3 = stretch(sy, sy2, self.y3, bmin_y, bmax_y)
            self.x4 = stretch(sx, sx2, self.x4, bmin_x, bmax_x)
            self.y4 = stretch(sy, sy2, self.y4, bmin_y, bmax_y)

    def get_box(self):
        # K/stroke.ts:130-163（switch fall-through 展开）。源码 default 标签
        # 在最前，文本顺序 default 体 → case 2/3/4 体 → case 1/99 体 → case 0：
        #   default 入口（a1∉{0,1,2,3,4,99}，含 6/7）→ x4、x3、x1x2 全含；
        #   case 2/3/4 → x3 + x1x2；case 1/99 → 仅 x1x2；case 0 → 空。
        # 修正说明：简报展开把 x3/x1x2 的覆盖写成 a1∈{2,3,4,6,7}/{1,2,3,4,6,7,99}，
        # 漏掉 default 的 fall-through 覆盖面（如 a1=5/8/9），已按源改为
        # x4 ⟺ a1∉{0,1,2,3,4,99}；x3 ⟺ a1∉{0,1,99}；x1x2 ⟺ a1≠0。
        inf = float("inf")
        min_x, min_y, max_x, max_y = inf, inf, -inf, -inf
        a1 = self.a1_100 if self.a1_opt == 0 else 6
        if a1 not in (0, 1, 2, 3, 4, 99):   # default 入口（含 x4）
            min_x, max_x = min(min_x, self.x4), max(max_x, self.x4)
            min_y, max_y = min(min_y, self.y4), max(max_y, self.y4)
        if a1 not in (0, 1, 99):            # case 2/3/4 体 + default fall-through
            min_x, max_x = min(min_x, self.x3), max(max_x, self.x3)
            min_y, max_y = min(min_y, self.y3), max(max_y, self.y3)
        if a1 != 0:                         # case 1/99 体 + 上游 fall-through
            min_x, max_x = min(min_x, self.x1, self.x2), max(max_x, self.x1, self.x2)
            min_y, max_y = min(min_y, self.y1, self.y2), max(max_y, self.y1, self.y2)
        return {"minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y}
