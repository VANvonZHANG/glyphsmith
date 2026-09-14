# src/gsrender/legacy_kurgm/font/mincho_cd.py
"""cdDrawU 家族：K/font/mincho/cd.ts（847 行）的逐 case 直译。

与 gothic_cd 的分工：共享工具（normalize/_Pen/push_polygon/
_generate_fatten_curve）留在 gothic_cd（T8 移植时的宿主），本模块只装
mincho 专属表；_Pen 为 mincho 补了 set_matrix2/get_polygon（pen.ts 原有，
gothic 版未用到）。

参数表（cd.ts 各导出函数签名尾部的小整数通道）：
- cdDrawCurveU：opt1（竖画变细量 tate）、haneAdjustment、opt3、opt4
  （来自 dfDrawFont 的 tateAdjustment 拆分 % 10 / floor(/10) 与 a3 位）；
- cdDrawLine：opt1（tate/mage 变细量）、urokoAdjustment、kakatoAdjustment。
width 公式 kMinWidthT = font.kMinWidthT - opt1 / 2 逐字照抄。

undefined 语义（cd.ts:45/86）：delta1/delta2 缺省（switch 未命中）时
x1=y1=undefined——后续 body/head/tail 三段各自跳过。Python 用 None 直译。
（源注释 "was NaN in original code"：kage 祖传 NaN 方案的现行为即 undefined。）

JS % 与 switch：a1 % 100 用 math.fmod（JS 截断余数）；drawCurveHead/
drawCurveTail/cdDrawLine 的 switch(a1)/switch(a2) 用【原值】匹配——a1=132
（kirikuchi 打包位）不命中 case 22，只有 drawCurveBody 的 suiheisen 分支
认 132。逐处照抄，勿顺手归一。

JS 数组越界 → undefined → NaN：kAdjustKakatoL/R、kAdjustUrokoX/Y 的索引
超出时源不抛错、坐标变 NaN 后被 Polygons.push 拒绝；Python 会 IndexError，
以 _js_index 等价复刻（越界/负索引 → NaN，负索引在 JS 中同样 undefined）。

顶点顺序指纹敏感（铁律 2）：push 顺/逆时针、首点位置一律照抄源。
"""
from __future__ import annotations

import math

from gsrender.outline import Outline

from ..curve import divide_curve as _divide_curve
from ..curve import find_offcurve as _find_offcurve
from .gothic_cd import (_Pen, _generate_fatten_curve, _hypot, normalize,
                        push_polygon)

_NAN = float("nan")


def _js_index(arr: list, i: int) -> float:
    """JS arr[i] 越界（含负索引）→ undefined → 参与算术后为 NaN。"""
    if 0 <= i < len(arr):
        return arr[i]
    return _NAN


def _floor_poly(pts: list[tuple[float, float, int]]) -> list[tuple[float, float, int]]:
    """K/polygon.ts:365-375 Polygon.floor()：对 ×10 内部坐标取整 = 用户坐标
    截断到 0.1 网格（drawCurveBody suiheisen 分支在 push 前的原位调用）。"""
    return [(math.floor(x * 10) / 10, math.floor(y * 10) / 10, off)
            for x, y, off in pts]


# ── K/curve.ts 移植（T11 落地于 ..curve）────────────────────────
# _divide_curve / _find_offcurve 见模块顶部 import（别名保持调用点不变）；
# generateFattenCurve（curve.ts:53-97）仍由 gothic_cd._generate_fatten_curve
# 提供（T8 宿主，mincho 两个分支共用）。


# ── K/font/mincho/cd.ts:8-122 cdDrawCurveU ──────────────────────
def cd_draw_curve_u(font, outline,
                    x1_, y1_, sx1, sy1, sx2, sy2, x2_, y2_,
                    ta1, ta2,
                    opt1, hane_adjustment, opt3, opt4) -> None:
    a1 = ta1
    a2 = ta2
    p = font.params

    k_min_width_t = p.k_min_width_t - opt1 / 2

    x1 = x1_
    y1 = y1_
    delta1 = None
    m = math.fmod(a1, 100)
    if m in (0, 7, 27):
        delta1 = -1 * p.k_min_width_y * 0.5
    elif m in (1, 2, 6, 22, 32):        # ... must be 32 / changed
        delta1 = 0
    elif m == 12:
        # case 32:
        delta1 = p.k_min_width_y

    if delta1 is None:
        x1 = y1 = None                  # ????? (was NaN in original code)
    elif delta1 != 0:
        if x1 == sx1 and y1 == sy1:
            dx1, dy1 = 0, delta1        # ?????
        else:
            dx1, dy1 = normalize(x1 - sx1, y1 - sy1, delta1)
        x1 += dx1
        y1 += dy1

    corner_offset = 0
    if x1 is not None and y1 is not None \
            and (a1 == 22 or a1 == 27) and a2 == 7 and k_min_width_t > 6:
        contour_length = _hypot(sx1 - x1, sy1 - y1) \
            + _hypot(sx2 - sx1, sy2 - sy1) + _hypot(x2_ - sx2, y2_ - sy2)
        if contour_length < 100:
            corner_offset = (k_min_width_t - 6) * ((100 - contour_length) / 100)
            x1 += corner_offset

    x2 = x2_
    y2 = y2_
    m = math.fmod(a2, 100)
    if m in (0, 1, 7, 9, 15, 14, 17, 5):    # 15->5 / 14->4 / 17 no need
        delta2 = 0
    elif m == 8:                            # get shorten for tail's circle
        delta2 = -1 * k_min_width_t * 0.5
    else:
        delta2 = delta1                     # ?????

    if delta2 is None:
        x2 = y2 = None                      # ????? (was NaN in original code)
    elif delta2 != 0:
        if sx2 == x2 and sy2 == y2:
            dx2, dy2 = 0, -delta2           # ?????
        else:
            dx2, dy2 = normalize(x2 - sx2, y2 - sy2, delta2)
        x2 += dx2
        y2 += dy2

    if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
        _draw_curve_body(
            font, outline,
            x1, y1, sx1, sy1, sx2, sy2, x2, y2,
            a1, a2,
            k_min_width_t, opt3, opt4)

    if x1 is not None and y1 is not None:
        is_up_to_bottom = False if y2 is None else y1 <= y2
        _draw_curve_head(
            outline, font,
            x1, y1, sx1, sy1,
            a1, k_min_width_t, is_up_to_bottom, corner_offset)

    if x2 is not None and y2 is not None:
        is_bottom_to_up = False if y1 is None else y2 <= y1
        _draw_curve_tail(
            outline, font,
            sx2, sy2, x2, y2,
            a1, a2,
            k_min_width_t, hane_adjustment, opt4, is_bottom_to_up)


# ── K/font/mincho/cd.ts:124-277 drawCurveBody ───────────────────
def _draw_curve_body(font, outline,
                     x1, y1, sx1, sy1, sx2, sy2, x2, y2,
                     a1, a2,
                     k_min_width_t, opt3, opt4) -> None:
    p = font.params
    is_quadratic = sx1 == sx2 and sy1 == sy2

    # ---------------------------------------------------------------

    if is_quadratic and font.k_use_curve:
        # Spline
        # generating fatten curve -- begin

        hosomi = 0.5
        if (a1 == 7 and a2 == 0):          # L2RD: fatten
            def deltad_func(t): return t ** hosomi * 1.1    # should be kL2RDfatten ?
        elif a1 == 7:
            def deltad_func(t): return t ** hosomi
        elif a2 == 7:
            def deltad_func(t): return (1 - t) ** hosomi
        elif opt3 > 0:                     # should be (opt3 > 0 || opt4 > 0) ?
            def deltad_func(t):                           # ??????
                return 1 - opt3 / 2 / (k_min_width_t - opt4 / 2) \
                    + opt3 / 2 / (k_min_width_t - opt4) * t
        else:
            def deltad_func(t): return 1

        def width_func(t):
            deltad = deltad_func(t)
            if deltad < 0.15:
                deltad = 0.15
            return k_min_width_t * deltad

        curve_l, curve_r = _generate_fatten_curve(
            x1, y1, sx1, sy1, sx1, sy1, x2, y2,
            10,
            width_func)                    # L and R

        index_l, (off_l1, off_l2) = _divide_curve(
            x1, y1, sx1, sy1, x2, y2, curve_l)
        curve_l1 = curve_l[:index_l + 1]
        curve_l2 = curve_l[index_l:]
        index_r, (off_r1, off_r2) = _divide_curve(
            x1, y1, sx1, sy1, x2, y2, curve_r)

        ncl1 = _find_offcurve(curve_l1, off_l1[2], off_l1[3])
        ncl2 = _find_offcurve(curve_l2, off_l2[2], off_l2[3])

        poly = [(ncl1[0], ncl1[1], 0),
                (ncl1[2], ncl1[3], 1),
                (ncl1[4], ncl1[5], 0),
                (ncl2[2], ncl2[3], 1),
                (ncl2[4], ncl2[5], 0)]

        poly2 = [(curve_r[0][0], curve_r[0][1], 0),
                 (off_r1[2] - (ncl1[2] - off_l1[2]),
                  off_r1[3] - (ncl1[3] - off_l1[3]), 1),
                 (curve_r[index_r][0], curve_r[index_r][1], 0),
                 (off_r2[2] - (ncl2[2] - off_l2[2]),
                  off_r2[3] - (ncl2[3] - off_l2[3]), 1),
                 (curve_r[-1][0], curve_r[-1][1], 0)]

        poly2.reverse()
        poly.extend(poly2)
        push_polygon(outline, poly)
        # generating fatten curve -- end
    else:
        hosomi = 0.5
        if _hypot(x2 - x1, y2 - y1) < 50:
            hosomi += 0.4 * (1 - _hypot(x2 - x1, y2 - y1) / 50)

        if (a1 == 7 or a1 == 27) and a2 == 0:      # L2RD: fatten
            def deltad_func(t): return t ** hosomi * p.k_l2r_dfatten
        elif a1 == 7 or a1 == 27:
            if is_quadratic:                       # ?????
                def deltad_func(t): return t ** hosomi
            else:
                def deltad_func(t): return (t ** hosomi) ** 0.7   # make fatten
        elif a2 == 7:
            def deltad_func(t): return (1 - t) ** hosomi
        elif is_quadratic and (opt3 > 0 or opt4 > 0):             # ?????
            def deltad_func(t):
                return ((p.k_min_width_t - opt3 / 2) - (opt4 - opt3) / 2 * t) \
                    / p.k_min_width_t
        else:
            def deltad_func(t): return 1

        def width_func(t):
            deltad = deltad_func(t)
            if deltad < 0.15:
                deltad = 0.15
            return k_min_width_t * deltad

        left, right = _generate_fatten_curve(
            x1, y1, sx1, sy1, sx2, sy2, x2, y2,
            p.k_rate,
            width_func)

        poly = [(x, y, 0) for x, y in left]
        poly2 = [(x, y, 0) for x, y in right]
        # copy to polygon structure

        # suiheisen ni setsuzoku
        if a1 == 132 or a1 == 22 and ((y1 > y2) if is_quadratic else (x1 > sx1)):   # ?????
            poly = _floor_poly(poly)
            poly2 = _floor_poly(poly2)
            for index in range(len(poly2) - 1):
                point1 = poly2[index]
                point2 = poly2[index + 1]
                if point1[1] <= y1 <= point2[1]:
                    newx1 = point2[0] + (point1[0] - point2[0]) * (y1 - point2[1]) \
                        / (point1[1] - point2[1])
                    newy1 = y1
                    point3 = poly[0]
                    point4 = poly[1]
                    if a1 == 132:                 # ?????
                        newx2 = point3[0] + (point4[0] - point3[0]) * (y1 - point3[1]) \
                            / (point4[1] - point3[1])
                        newy2 = y1
                    else:
                        newx2 = point3[0] + (point4[0] - point3[0] + 1) * (y1 - point3[1]) \
                            / (point4[1] - point3[1])          # "+ 1"?????
                        newy2 = y1 + 1                          # "+ 1"?????

                    del poly2[:index]
                    poly2[0] = (newx1, newy1, 0)
                    poly.insert(0, (newx2, newy2, 0))
                    break

        poly2.reverse()
        poly.extend(poly2)
        push_polygon(outline, poly)


# ── K/font/mincho/cd.ts:279-388 drawCurveHead ───────────────────
def _draw_curve_head(outline, font,
                     x1, y1, sx1, sy1,
                     a1, k_min_width_t, is_up_to_bottom, corner_offset) -> None:
    p = font.params
    # process for head of stroke

    if a1 == 12:
        pen1 = _Pen(x1, y1)
        if x1 != sx1:                     # ?????
            pen1.set_down(sx1, sy1)
        push_polygon(outline, pen1.get_polygon([
            (-k_min_width_t, 0, 0),
            (k_min_width_t, 0, 0),
            (-k_min_width_t, -k_min_width_t, 0),
        ]))
    elif a1 == 0:
        if is_up_to_bottom:               # from up to bottom
            pen1 = _Pen(x1, y1)
            if x1 != sx1:                 # ?????
                pen1.set_down(sx1, sy1)
            type_ = math.atan2(abs(y1 - sy1), abs(x1 - sx1)) / math.pi * 2 - 0.4
            if type_ > 0:
                type_ *= 2
            else:
                type_ *= 16
            pm = -1 if type_ < 0 else 1
            push_polygon(outline, pen1.get_polygon([
                (-k_min_width_t, 1, 0),   # 1 ???
                (k_min_width_t, 0, 0),
                (-pm * k_min_width_t, -p.k_min_width_y * abs(type_), 0),
            ]))
            # if(x1 > x2){ poly.reverse(); }
            # beginning of the stroke
            move = -type_ * p.k_min_width_y if type_ < 0 else 0
            if x1 == sx1 and y1 == sy1:   # ?????
                # type === -6.4 && pm === -1 && move === 6.4 * kMinWidthY
                push_polygon(outline, pen1.get_polygon([
                    (k_min_width_t, -move, 0),
                    (k_min_width_t * 1.5, p.k_min_width_y - move, 0),
                    (k_min_width_t - 2, p.k_min_width_y * 2 + 1, 0),
                ]))
            else:
                push_polygon(outline, pen1.get_polygon([
                    (k_min_width_t, -move, 0),
                    (k_min_width_t * 1.5, p.k_min_width_y - move * 1.2, 0),
                    (k_min_width_t - 2, p.k_min_width_y * 2 - move * 0.8 + 1, 0),
                ]))
                # if(x1 < x2){ poly2.reverse(); }
        else:                             # bottom to up
            pen1 = _Pen(x1, y1)
            if x1 == sx1:
                pen1.set_matrix2(0, 1)    # ?????
            else:
                pen1.set_right(sx1, sy1)
            push_polygon(outline, pen1.get_polygon([
                (0, k_min_width_t, 0),
                (0, -k_min_width_t, 0),
                (-p.k_min_width_y, -k_min_width_t, 0),
            ]))
            # if(x1 < x2){ poly.reverse(); }
            # beginning of the stroke
            push_polygon(outline, pen1.get_polygon([
                (0, k_min_width_t, 0),
                (p.k_min_width_y, k_min_width_t * 1.5, 0),
                (p.k_min_width_y * 3, k_min_width_t * 0.5, 0),
            ]))
            # if(x1 < x2){ poly2.reverse(); }
    elif a1 in (22, 27):
        # box's up-right corner, any time same degree
        if a1 == 27:
            extra = [(0, k_min_width_t + 2, 0),
                     (0, 0.5, 0)]
        else:
            extra = [(-k_min_width_t, k_min_width_t + 4, 0)]
        push_polygon(outline, _Pen(x1 - corner_offset, y1).get_polygon(
            [(-k_min_width_t, -p.k_min_width_y, 0),
             (0, -p.k_min_width_y - p.k_width, 0),
             (k_min_width_t + p.k_width, p.k_min_width_y, 0),
             (k_min_width_t, k_min_width_t - 1, 0)] + extra))


# ── K/font/mincho/cd.ts:390-492 drawCurveTail ───────────────────
def _draw_curve_tail(outline, font,
                     sx2, sy2, x2, y2,
                     a1, a2,
                     k_min_width_t, hane_adjustment, opt4, is_bottom_to_up) -> None:
    p = font.params
    # process for tail

    if a2 in (1, 8, 15):
        # the last filled circle ... it can change 15->5
        k_min_width_t2 = p.k_min_width_t - opt4 / 2
        pen2 = _Pen(x2, y2)
        if sx2 == x2:
            pen2.set_matrix2(0, 1)        # ?????
        elif sy2 != y2:                   # ?????
            pen2.set_left(sx2, sy2)
        if font.k_use_curve:
            pts = [                       # by curve path
                (0, -k_min_width_t2, 0),
                (k_min_width_t2 * 0.9, -k_min_width_t2 * 0.9, 1),
                (k_min_width_t2, 0, 0),
                (k_min_width_t2 * 0.9, k_min_width_t2 * 0.9, 1),
                (0, k_min_width_t2, 0),
            ]
        else:                             # by polygon
            pts = [
                (0, -k_min_width_t2, 0),
                (k_min_width_t2 * 0.7, -k_min_width_t2 * 0.7, 0),
                (k_min_width_t2, 0, 0),
                (k_min_width_t2 * 0.7, k_min_width_t2 * 0.7, 0),
                (0, k_min_width_t2, 0),
            ]
        poly = pen2.get_polygon(pts)
        if sx2 == x2:
            poly.reverse()
        push_polygon(outline, poly)

        if a2 == 15:                      # jump up ... it can change 15->5
            # anytime same degree
            pen2_r = _Pen(x2, y2)
            if is_bottom_to_up:
                pen2_r.set_matrix2(-1, 0)
            push_polygon(outline, pen2_r.get_polygon([
                (0, -k_min_width_t + 1, 0),
                (2, -k_min_width_t - p.k_width * 5, 0),
                (0, -k_min_width_t - p.k_width * 5, 0),
                (-k_min_width_t, -k_min_width_t + 1, 0),
            ]))
    elif a2 == 9 or (a2 == 0 and (a1 == 7 or a1 == 27)):
        # Math.sinnyu & L2RD Harai ... no need for a2=9
        type_ = math.atan2(abs(y2 - sy2), abs(x2 - sx2)) / math.pi * 2 - 0.6
        if type_ > 0:
            type_ *= 8
        else:
            type_ *= 3
        pm = -1 if type_ < 0 else 1
        pen2 = _Pen(x2, y2)
        if sy2 == y2:
            pen2.set_matrix2(1, 0)        # ?????
        elif sx2 == x2:
            pen2.set_matrix2(0, -1 if y2 > sy2 else 1)   # for backward compatibility...
        else:
            pen2.set_left(sx2, sy2)
        push_polygon(outline, pen2.get_polygon([
            (0, k_min_width_t * p.k_l2r_dfatten, 0),
            (0, -k_min_width_t * p.k_l2r_dfatten, 0),
            (abs(type_) * k_min_width_t * p.k_l2r_dfatten,
             pm * k_min_width_t * p.k_l2r_dfatten, 0),
        ]))
    elif a2 == 14:
        # jump to left, allways go left
        jump_factor = 6.0 / k_min_width_t if k_min_width_t > 6 else 1.0
        hane_length = p.k_width * 4 \
            * min(1 - hane_adjustment / 10, (k_min_width_t / p.k_min_width_t) ** 3) \
            * jump_factor
        push_polygon(outline, _Pen(x2, y2).get_polygon([
            (0, 0, 0),
            (0, -k_min_width_t, 0),
            (-hane_length, -k_min_width_t, 0),
            (-hane_length, -k_min_width_t * 0.5, 0),
        ]))
        # poly.reverse();


# ── K/font/mincho/cd.ts:494-509 导出薄壳 ────────────────────────
def cd_draw_bezier(font, outline,
                   x1, y1, x2, y2, x3, y3, x4, y4,
                   a1, a2,
                   opt1, hane_adjustment, opt3, opt4) -> None:
    cd_draw_curve_u(font, outline, x1, y1, x2, y2, x3, y3, x4, y4,
                    a1, a2, opt1, hane_adjustment, opt3, opt4)


def cd_draw_curve(font, outline,
                  x1, y1, x2, y2, x3, y3,
                  a1, a2,
                  opt1, hane_adjustment, opt3, opt4) -> None:
    cd_draw_curve_u(font, outline, x1, y1, x2, y2, x2, y2, x3, y3,
                    a1, a2, opt1, hane_adjustment, opt3, opt4)


# ── K/font/mincho/cd.ts:511-847 cdDrawLine ──────────────────────
def cd_draw_line(font, outline,
                 tx1, ty1, tx2, ty2,
                 ta1, ta2, opt1, uroko_adjustment, kakato_adjustment) -> None:
    x1 = tx1
    y1 = ty1
    x2 = tx2
    y2 = ty2
    a1 = ta1
    a2 = ta2
    p = font.params

    k_min_width_t = p.k_min_width_t - opt1 / 2

    if x1 == x2 or (y1 != y2 and (x1 > x2 or abs(y2 - y1) >= abs(x2 - x1)
                                  or a1 == 6 or a2 == 6)):
        # if TATE stroke, use y-axis
        # for others, use x-axis
        # KAKUDO GA FUKAI or KAGI NO YOKO BOU
        if x1 == x2:
            cosrad, sinrad = 0, 1          # ?????
        else:
            cosrad, sinrad = normalize(x2 - x1, y2 - y1)

        pen1 = _Pen(x1, y1)
        pen2 = _Pen(x2, y2)
        # if (x1 !== x2) { pen1.setDown(x2, y2); pen2.setUp(x1, y1); }
        pen1.set_matrix2(sinrad, -cosrad)
        pen2.set_matrix2(sinrad, -cosrad)

        poly0 = [(0.0, 0.0, 0)] * 4        # new Polygon(4)
        # switch (a1)
        if a1 == 0:
            poly0[0] = pen1.get_point(k_min_width_t, p.k_min_width_y / 2)
            poly0[3] = pen1.get_point(-k_min_width_t, -p.k_min_width_y / 2)
        elif a1 in (1, 6):                 # ... no need
            poly0[0] = pen1.get_point(k_min_width_t, 0)
            poly0[3] = pen1.get_point(-k_min_width_t, 0)
        elif a1 == 12:
            poly0[0] = pen1.get_point(k_min_width_t, -p.k_min_width_y)
            poly0[3] = pen1.get_point(-k_min_width_t, -p.k_min_width_y - k_min_width_t)
        elif a1 == 22:
            if x1 == x2:
                poly0[0] = (x1 + k_min_width_t, y1, 0)
                poly0[3] = (x1 - k_min_width_t, y1, 0)
            else:
                v = -1 if x1 > x2 else 1
                # TODO: why " + v", " + 1" ???
                poly0[0] = (x1 + (k_min_width_t + v) / sinrad, y1 + 1, 0)
                poly0[3] = (x1 - k_min_width_t / sinrad, y1, 0)
        elif a1 == 32:
            if x1 == x2:
                poly0[0] = (x1 + k_min_width_t, y1 - p.k_min_width_y, 0)
                poly0[3] = (x1 - k_min_width_t, y1 - p.k_min_width_y, 0)
            else:
                poly0[0] = (x1 + k_min_width_t / sinrad, y1, 0)
                poly0[3] = (x1 - k_min_width_t / sinrad, y1, 0)

        # switch (a2)
        if a2 == 0:
            if a1 == 6:                    # KAGI's tail ... no need
                poly0[1] = pen2.get_point(k_min_width_t, 0)
                poly0[2] = pen2.get_point(-k_min_width_t, 0)
            else:
                poly0[1] = pen2.get_point(k_min_width_t, -k_min_width_t / 2)
                poly0[2] = pen2.get_point(-k_min_width_t, k_min_width_t / 2)
        elif a2 == 5 and x1 != x2 or a2 == 1:      # case 5 fall-through / is needed?
            poly0[1] = pen2.get_point(k_min_width_t, 0)
            poly0[2] = pen2.get_point(-k_min_width_t, 0)
        elif a2 == 13:
            poly0[1] = pen2.get_point(k_min_width_t, _js_index(p.k_adjust_kakato_l, kakato_adjustment))
            poly0[2] = pen2.get_point(-k_min_width_t, _js_index(p.k_adjust_kakato_l, kakato_adjustment) + k_min_width_t)
        elif a2 == 23:
            poly0[1] = pen2.get_point(k_min_width_t, _js_index(p.k_adjust_kakato_r, kakato_adjustment))
            poly0[2] = pen2.get_point(-k_min_width_t, _js_index(p.k_adjust_kakato_r, kakato_adjustment) + k_min_width_t)
        elif a2 in (24, 32):               # for T/H design
            if x1 == x2:
                poly0[1] = (x2 + k_min_width_t, y2 + p.k_min_width_y, 0)
                poly0[2] = (x2 - k_min_width_t, y2 + p.k_min_width_y, 0)
            else:
                poly0[1] = (x2 + k_min_width_t / sinrad, y2, 0)
                poly0[2] = (x2 - k_min_width_t / sinrad, y2, 0)

        push_polygon(outline, poly0)

        if a2 == 24:                       # for T design
            push_polygon(outline, _Pen(x2, y2).get_polygon([
                (0, p.k_min_width_y, 0),
                *([(k_min_width_t, -p.k_min_width_y * 3, 0)] if x1 == x2   # ?????
                  else [(k_min_width_t * 0.5, -p.k_min_width_y * 4, 0)]),
                (k_min_width_t * 2, -p.k_min_width_y, 0),
                (k_min_width_t * 2, p.k_min_width_y, 0),
            ]))
        elif a2 == 13 and kakato_adjustment == 4:
            # for new GTH box's left bottom corner
            if x1 == x2:
                push_polygon(outline, _Pen(x2, y2).get_polygon([
                    (-k_min_width_t, -p.k_min_width_y * 3, 0),
                    (-k_min_width_t * 2, 0, 0),
                    (-p.k_min_width_y, p.k_min_width_y * 5, 0),
                    (k_min_width_t, p.k_min_width_y, 0),
                ]))
            else:                          # MUKI KANKEINASHI
                m = math.floor((x1 - x2) / (y2 - y1) * 3) \
                    if (x1 > x2 and y1 != y2) else 0
                push_polygon(outline, _Pen(x2 + m, y2).get_polygon([
                    (0, -p.k_min_width_y * 5, 0),
                    (-k_min_width_t * 2, 0, 0),
                    (-p.k_min_width_y, p.k_min_width_y * 5, 0),
                    (k_min_width_t, p.k_min_width_y, 0),
                    (0, 0, 0),
                ]))

        if a1 in (22, 27):
            # box's right top corner
            # SHIKAKU MIGIUE UROKO NANAME DEMO MASSUGU MUKI
            if x1 == x2:
                extra = [(k_min_width_t, k_min_width_t, 0),
                         (-k_min_width_t, 0, 0)]
            elif a1 == 27:
                extra = [(k_min_width_t, k_min_width_t - 1, 0),
                         (0, k_min_width_t + 2, 0),
                         (0, 0, 0)]
            else:
                extra = [(k_min_width_t, k_min_width_t - 1, 0),
                         (-k_min_width_t, k_min_width_t + 4, 0)]
            push_polygon(outline, _Pen(x1, y1).get_polygon(
                [(-k_min_width_t, -p.k_min_width_y, 0),
                 (0, -p.k_min_width_y - p.k_width, 0),
                 (k_min_width_t + p.k_width, p.k_min_width_y, 0)] + extra))
        elif a1 == 0:
            # beginning of the stroke
            poly = pen1.get_polygon([
                (k_min_width_t, p.k_min_width_y * 0.5, 0),
                (k_min_width_t + k_min_width_t * 0.5,
                 p.k_min_width_y * 0.5 + p.k_min_width_y, 0),
                (k_min_width_t - 2,
                 p.k_min_width_y * 0.5 + p.k_min_width_y * 2 + 1, 0),
            ])
            if x1 != x2:                   # ?????
                poly[2] = (
                    x1 + (k_min_width_t - 2) * sinrad
                    + (p.k_min_width_y * 0.5 + p.k_min_width_y * 2) * cosrad,
                    y1 + (k_min_width_t + 1) * -cosrad
                    + (p.k_min_width_y * 0.5 + p.k_min_width_y * 2) * sinrad, 0)   # ?????
            push_polygon(outline, poly)

        if (x1 == x2 and a2 == 1) or (a1 == 6 and (a2 == 0 or (x1 != x2 and a2 == 5))):
            # KAGI NO YOKO BOU NO SAIGO NO MARU ... no need only used at 1st=yoko
            poly: list[tuple[float, float, int]] = []
            if font.k_use_curve:
                poly.append(pen2.get_point(k_min_width_t, 0))
                poly.append((x2 - cosrad * k_min_width_t * 0.9 + -sinrad * -k_min_width_t * 0.9,   # typo? (-cosrad should be +cosrad)
                             y2 + sinrad * k_min_width_t * 0.9 + cosrad * -k_min_width_t * 0.9, 1))
                poly.append(pen2.get_point(0, k_min_width_t))
                poly.append(pen2.get_point(-k_min_width_t * 0.9, k_min_width_t * 0.9, 1))
                poly.append(pen2.get_point(-k_min_width_t, 0))
            else:
                r = 0.6 if (x1 == x2 and ((a1 == 6 and a2 == 0) or a2 == 1)) else 0.8   # ?????
                poly.append(pen2.get_point(k_min_width_t, 0))
                poly.append(pen2.get_point(k_min_width_t * 0.6, k_min_width_t * r))
                poly.append(pen2.get_point(0, k_min_width_t))
                poly.append(pen2.get_point(-k_min_width_t * 0.6, k_min_width_t * r))
                poly.append(pen2.get_point(-k_min_width_t, 0))
            if x1 == x2 and ((a1 == 6 and a2 == 0) or a2 == 1):
                # for backward compatibility
                poly.reverse()
            # poly.reverse(); // for fill-rule
            push_polygon(outline, poly)
            if x1 != x2 and a1 == 6 and a2 == 5:
                # KAGI NO YOKO BOU NO HANE
                hane_length = p.k_width * 5
                rv = 1 if x1 < x2 else -1
                push_polygon(outline, pen2.get_polygon([
                    (rv * (k_min_width_t - 1), 0, 0),
                    (rv * (k_min_width_t + hane_length), 2, 0),
                    (rv * (k_min_width_t + hane_length), 0, 0),
                    (k_min_width_t - 1, -k_min_width_t, 0),   # rv ?????
                ]))
    elif y1 == y2 and a1 == 6:
        # if it is YOKO stroke, use x-axis
        # if it is KAGI's YOKO stroke, get bold
        # x1 !== x2 && y1 === y2 && a1 === 6
        pen1_r = _Pen(x1, y1)
        pen2_r = _Pen(x2, y2)
        push_polygon(outline, [
            pen1_r.get_point(0, -k_min_width_t),
            pen2_r.get_point(0, -k_min_width_t),
            pen2_r.get_point(0, k_min_width_t),
            pen1_r.get_point(0, k_min_width_t),
        ])

        if a2 in (1, 0, 5):                # no need a2=1
            # KAGI NO YOKO BOU NO SAIGO NO MARU
            pen2 = _Pen(x2, y2)
            if x1 > x2:
                pen2.set_matrix2(-1, 0)
            r = 0.6
            if font.k_use_curve:
                pts = [
                    (0, -k_min_width_t, 0),
                    (k_min_width_t * 0.9, -k_min_width_t * 0.9, 1),
                    (k_min_width_t, 0, 0),
                    (k_min_width_t * 0.9, k_min_width_t * 0.9, 1),
                    (0, k_min_width_t, 0),
                ]
            else:
                pts = [
                    (0, -k_min_width_t, 0),
                    (k_min_width_t * r, -k_min_width_t * 0.6, 0),
                    (k_min_width_t, 0, 0),
                    (k_min_width_t * r, k_min_width_t * 0.6, 0),
                    (0, k_min_width_t, 0),
                ]
            poly = pen2.get_polygon(pts)
            if x1 >= x2:
                poly.reverse()
            push_polygon(outline, poly)

            if a2 == 5:
                hane_length = p.k_width * (4 * (1 - opt1 / p.k_adjust_mage_step) + 1)
                # KAGI NO YOKO BOU NO HANE
                rv = 1 if x1 < x2 else -1
                push_polygon(outline, pen2.get_polygon([
                    # (0, rv * (-k_min_width_t + 1), 0),
                    (0, rv * -k_min_width_t, 0),
                    (2, rv * (-k_min_width_t - hane_length), 0),
                    (0, rv * (-k_min_width_t - hane_length), 0),
                    # (-k_min_width_t, rv * (-k_min_width_t + 1), 0),
                    (-k_min_width_t, rv * -k_min_width_t, 0),
                ]))
                # poly2.reverse(); // for fill-rule
    else:
        # for others, use x-axis
        # ASAI KAUDO
        if y1 == y2:
            cosrad, sinrad = 1, 0          # ?????
        else:
            cosrad, sinrad = normalize(x2 - x1, y2 - y1)
        # always same
        pen1 = _Pen(x1, y1)
        pen2 = _Pen(x2, y2)
        # if (y1 !== y2) { pen1.setRight(x2, y2); pen2.setLeft(x1, y1); }
        pen1.set_matrix2(cosrad, sinrad)
        pen2.set_matrix2(cosrad, sinrad)
        push_polygon(outline, [
            pen1.get_point(0, -p.k_min_width_y),
            pen2.get_point(0, -p.k_min_width_y),
            pen2.get_point(0, p.k_min_width_y),
            pen1.get_point(0, p.k_min_width_y),
        ])

        if a2 == 0:
            # UROKO
            uroko_scale = (p.k_min_width_u / p.k_min_width_y - 1.0) / 4.0 + 1.0
            poly2 = pen2.get_polygon([
                (0, -p.k_min_width_y, 0),
                (-_js_index(p.k_adjust_uroko_x, uroko_adjustment) * uroko_scale, 0, 0),
            ])
            poly2.append((
                x2 - (cosrad - sinrad) * _js_index(p.k_adjust_uroko_x, uroko_adjustment) * uroko_scale / 2,
                y2 - (sinrad + cosrad) * _js_index(p.k_adjust_uroko_y, uroko_adjustment) * uroko_scale, 0))
            push_polygon(outline, poly2)
