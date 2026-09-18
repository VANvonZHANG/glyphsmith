# src/glyphsmith/legacy_kurgm/font/mincho.py
"""MinchoFont：K/font/mincho/index.ts 的 adjustStrokes 七连管（T9）。

明朝体「看邻居笔画」的书法规则核心——渲染前先对全字每笔算六个调整量
（跳ね/曲げ/縦/踵/鱗×2/切り口），再交给 cd 表画。七连管顺序固定不可换
（index.ts:385-391，uroko2 依赖 uroko 的结果做 isTarget 判定）：

  adjustHane → adjustMage → adjustTate → adjustKakato
  → adjustUroko → adjustUroko2 → adjustKirikuchi

移植对应源段（逐行）：Hane :395-440 / Mage :442-481 / Tate :483-511 /
Kakato :513-536 / Uroko :538-564 / Uroko2 :566-609 / Kirikuchi :611-634；
打包初值 :370-383；骨架 :363-393；getDrawers :356-360。参数表（kAdjust*
等）从 T7 FontParams 取（已逐字段抄源 :303-353）。几何判定用 RStroke 的
is_cross/is_cross_box（T4）。dfDrawFont（:88-221 的 switch(a1_100) 分发）
已随 T10 落地：本模块 df_draw_font 直译分发，mincho/cd.ts 的 cdDraw*
表在 mincho_cd.py（golden m: 子集 3240/3240 绿）。

Gothic 对照（T8 结论）：Gothic 覆写 getDrawers 直接画原始 Stroke，
完全跳过 adjustStrokes——七连管是 Mincho 专用。
"""
from __future__ import annotations

import math

from glyphsmith.outline import Outline

from ..expansion import TransformOp
from ..geom2d import _round
from ..rstroke import RStroke
from .base import Drawer, Font, Shotai
from .gothic_cd import _hypot, normalize   # K/util.ts；共享工具留在 gothic_cd（T10 决策）
from .mincho_cd import cd_draw_bezier, cd_draw_curve, cd_draw_line


class MinchoAdjustedStroke(RStroke):
    """index.ts:10-26 MinchoAdjustedStroke 的镜像。

    TS 是含 `readonly stroke: Stroke` 引用的接口（组合）；按 T9 简报做成
    RStroke 子类（继承）：adj.a1_100 等即源的 adjStroke.stroke.a1_100，
    T10 的 df_draw_font 直接在 adj 上取笔画字段与六个调整量。

    六个字段 = 源 :370-383 的 100s/1000s 位打包改写通道（初值来自 a2/a3
    的 option 位分解，各 adjust 函数在其上累加/覆写）：
    - a2 的 100s 位 kirikuchiAdjustment（2:32 时）；1000s 位 tateAdjustment
      （{1,3,7} 竖，opt_2 + opt_3*10 打包）；
    - a3 的 100s 位 haneAdjustment（{1,2,6}::04）/ urokoAdjustment（1::00）/
      kakatoAdjustment（1::{13,23}）；1000s 位 mageAdjustment（3）。
    """

    def __init__(self, stroke: RStroke) -> None:
        # 展开管线产物（可能已被 apply_stretch/affine 改写坐标）整体过户
        self.__dict__.update(stroke.__dict__)
        # index.ts:370-383 打包初值
        self.kirikuchi_adjustment: int = stroke.a2_opt_1
        self.tate_adjustment: int = stroke.a2_opt_2 + stroke.a2_opt_3 * 10
        self.hane_adjustment: int = stroke.a3_opt_1
        self.uroko_adjustment: int = stroke.a3_opt
        self.kakato_adjustment: int = stroke.a3_opt
        self.mage_adjustment: int = stroke.a3_opt_2


def df_draw_font(font: "MinchoFont", outline: Outline,
                 adj_stroke: MinchoAdjustedStroke) -> None:
    """mincho/index.ts:88-221 dfDrawFont——switch(a1_100) 逐案分发到
    mincho/cd.ts（mincho_cd.cd_draw_*）。

    参数传递铁律：cdDrawCurve 的 opt1/opt3 通道 = tateAdjustment 的
    `% 10` 与 `Math.floor(/10)` 拆分（T9 移交要点 1）；六调整量直接取
    MinchoAdjustedStroke 字段。JS `%` → math.fmod（截断余数语义）。
    """
    st = adj_stroke
    p = font.params
    a1_100 = st.a1_100
    a2_100, a2_opt_1, a2_opt_2, a2_opt_3 = \
        st.a2_100, st.a2_opt_1, st.a2_opt_2, st.a2_opt_3
    a3_100, a3_opt, a3_opt_1, a3_opt_2 = \
        st.a3_100, st.a3_opt, st.a3_opt_1, st.a3_opt_2
    x1, y1, x2, y2 = st.x1, st.y1, st.x2, st.y2
    x3, y3, x4, y4 = st.x3, st.y3, st.x4, st.y4
    kirikuchi = st.kirikuchi_adjustment
    tate = st.tate_adjustment
    hane = st.hane_adjustment
    uroko = st.uroko_adjustment
    kakato = st.kakato_adjustment
    mage = st.mage_adjustment

    if a1_100 == 1:
        if a3_100 == 4:
            if x1 == x2 and y1 == y2:
                dx1, dy1 = 0, p.k_mage                            # ?????
            else:
                dx1, dy1 = normalize(x1 - x2, y1 - y2, p.k_mage)
            tx1 = x2 + dx1
            ty1 = y2 + dy1
            cd_draw_line(font, outline, x1, y1, tx1, ty1,
                         a2_100 + a2_opt_1 * 100, 1, tate, 0, 0)
            cd_draw_curve(font, outline,
                          tx1, ty1, x2, y2,
                          x2 - p.k_mage * (((p.k_adjust_tate_step + 4) - tate)
                                           / (p.k_adjust_tate_step + 4)), y2,
                          1, 14, int(math.fmod(tate, 10)), hane,
                          math.floor(tate / 10), a3_opt_2)
        else:
            cd_draw_line(font, outline, x1, y1, x2, y2,
                         a2_100 + a2_opt_1 * 100, a3_100,
                         tate, uroko, kakato)
    elif a1_100 == 2:
        # case 12: // ... no need
        if a3_100 == 4:
            if x2 == x3:
                dx1, dy1 = 0, -p.k_mage                            # ?????
            elif y2 == y3:
                dx1, dy1 = -p.k_mage, 0                            # ?????
            else:
                dx1, dy1 = normalize(x2 - x3, y2 - y3, p.k_mage)
            tx1 = x3 + dx1
            ty1 = y3 + dy1
            cd_draw_curve(font, outline, x1, y1, x2, y2, tx1, ty1,
                          a2_100 + kirikuchi * 100, 0, a2_opt_2, 0, a2_opt_3, 0)
            cd_draw_curve(font, outline, tx1, ty1, x3, y3, x3 - p.k_mage, y3,
                          2, 14, a2_opt_2, hane, 0, a3_opt_2)
        else:
            cd_draw_curve(font, outline, x1, y1, x2, y2, x3, y3,
                          a2_100 + kirikuchi * 100,
                          15 if (a3_100 == 5 and a3_opt == 0) else a3_100,
                          a2_opt_2, a3_opt_1, a2_opt_3, a3_opt_2)
    elif a1_100 == 3:
        if x1 == x2 and y1 == y2:
            dx1, dy1 = 0, p.k_mage                                # ?????
        else:
            dx1, dy1 = normalize(x1 - x2, y1 - y2, p.k_mage)
        tx1 = x2 + dx1
        ty1 = y2 + dy1
        if x2 == x3 and y2 == y3:
            dx2, dy2 = 0, -p.k_mage                               # ?????
        else:
            dx2, dy2 = normalize(x3 - x2, y3 - y2, p.k_mage)
        tx2 = x2 + dx2
        ty2 = y2 + dy2

        cd_draw_line(font, outline, x1, y1, tx1, ty1,
                     a2_100 + a2_opt_1 * 100, 1, tate, 0, 0)
        cd_draw_curve(font, outline, tx1, ty1, x2, y2, tx2, ty2,
                      1, 1, 0, 0, tate, mage)

        if not (a3_100 == 5 and a3_opt_1 == 0
                and not ((x2 < x3 and x3 - tx2 > 0)
                         or (x2 > x3 and tx2 - x3 > 0))):       # for closer position
            opt2 = 0 if (a3_100 == 5 and a3_opt_1 == 0) \
                else a3_opt_1 + mage * 10
            cd_draw_line(font, outline, tx2, ty2, x3, y3,
                         6, a3_100, mage, opt2, opt2)           # bolder by force
    elif a1_100 == 4:
        rate = _hypot(x3 - x2, y3 - y2) / 120 * 6
        if rate > 6:
            rate = 6
        if x1 == x2 and y1 == y2:
            dx1, dy1 = 0, p.k_mage * rate                          # ?????
        else:
            dx1, dy1 = normalize(x1 - x2, y1 - y2, p.k_mage * rate)
        tx1 = x2 + dx1
        ty1 = y2 + dy1
        if x2 == x3 and y2 == y3:
            dx2, dy2 = 0, -p.k_mage * rate                         # ?????
        else:
            dx2, dy2 = normalize(x3 - x2, y3 - y2, p.k_mage * rate)
        tx2 = x2 + dx2
        ty2 = y2 + dy2

        cd_draw_line(font, outline, x1, y1, tx1, ty1,
                     a2_100 + a2_opt_1 * 100, 1, a2_opt_2 + a2_opt_3 * 10, 0, 0)
        cd_draw_curve(font, outline, tx1, ty1, x2, y2, tx2, ty2, 1, 1, 0, 0, 0, 0)

        if not (a3_100 == 5 and a3_opt == 0 and x3 - tx2 <= 0):    # for closer position
            cd_draw_line(font, outline, tx2, ty2, x3, y3,
                         6, a3_100, 0, a3_opt, a3_opt)             # bolder by force
    elif a1_100 == 6:
        if a3_100 == 4:
            if x3 == x4:
                dx1, dy1 = 0, -p.k_mage                            # ?????
            elif y3 == y4:
                dx1, dy1 = -p.k_mage, 0                            # ?????
            else:
                dx1, dy1 = normalize(x3 - x4, y3 - y4, p.k_mage)
            tx1 = x4 + dx1
            ty1 = y4 + dy1
            cd_draw_bezier(font, outline, x1, y1, x2, y2, x3, y3, tx1, ty1,
                           a2_100 + a2_opt_1 * 100, 1, a2_opt_2, 0, a2_opt_3, 0)
            cd_draw_curve(font, outline, tx1, ty1, x4, y4,
                          x4 - p.k_mage, y4, 1, 14, 0, hane, 0, a3_opt_2)
        else:
            cd_draw_bezier(font, outline, x1, y1, x2, y2, x3, y3, x4, y4,
                           a2_100 + a2_opt_1 * 100,
                           15 if (a3_100 == 5 and a3_opt == 0) else a3_100,
                           a2_opt_2, a3_opt_1, a2_opt_3, a3_opt_2)
    elif a1_100 == 7:
        cd_draw_line(font, outline, x1, y1, x2, y2,
                     a2_100 + a2_opt_1 * 100, 1, tate, 0, 0)
        cd_draw_curve(font, outline, x2, y2, x3, y3, x4, y4,
                      1, a3_100, int(math.fmod(tate, 10)), a3_opt_1,
                      math.floor(tate / 10), a3_opt_2)
    elif a1_100 == 9:
        pass    # may not be exist（源注释；kageCanvas 旧代码已注释）
    elif a1_100 == 12:
        cd_draw_curve(font, outline, x1, y1, x2, y2, x3, y3,
                      a2_100 + a2_opt_1 * 100, 1, a2_opt_2, 0, a2_opt_3, 0)
        cd_draw_line(font, outline, x3, y3, x4, y4, 6, a3_100, 0, a3_opt, a3_opt)


class MinchoFont(Font):
    """明朝体。← K/font/mincho/index.ts:224-635 Mincho（参数表/setSize 在
    T7 基座；本类携带 adjust 七连管与 Mincho 版 getDrawers 分发）。"""

    shotai = Shotai.K_MINCHO

    # ── index.ts:356-360 getDrawers ────────────────────────────
    def get_drawers(self, items: list) -> list[Drawer]:
        """Mincho 版：先全字 adjust（邻居感知，须一次性看全部笔画），再逐项
        分发——TransformOp（0:97/98/99 行）沿用基座 df_transform 通道，
        MinchoAdjustedStroke 进 df_draw_font（T10 前为 no-op 占位）。"""
        return [self._transform_drawer(it) if isinstance(it, TransformOp)
                else self._mincho_stroke_drawer(it)
                for it in self.adjust_strokes(items)]

    def _mincho_stroke_drawer(self, adj: MinchoAdjustedStroke) -> Drawer:
        def draw(outline: Outline) -> None:
            df_draw_font(self, outline, adj)
        return draw

    # ── index.ts:363-393 adjustStrokes ─────────────────────────
    def adjust_strokes(self, items: list) -> list:
        """打包初值构造 + 七连管依序执行（顺序不可换，:385-391）。

        items 是 expand() 的产物（RStroke | TransformOp 混合）。源中 0:97/98/99
        行是 a1_100=0 的 Stroke：七函数的目标/邻居条件全不匹配、getControlSegments
        对 a1=0 返回空（isCross/isCrossBox 恒 False），对 adjust 全惰性——本仓库
        该行是 TransformOp（T7 通道），原样透传、不进七函数，行为与源逐点一致。
        """
        adjusted: list = []
        for it in items:
            adjusted.append(MinchoAdjustedStroke(it)
                            if isinstance(it, RStroke) else it)
        strokes = [a for a in adjusted if isinstance(a, MinchoAdjustedStroke)]
        self._adjust_hane(strokes)        # :385
        self._adjust_mage(strokes)        # :386
        self._adjust_tate(strokes)        # :387
        self._adjust_kakato(strokes)      # :388
        self._adjust_uroko(strokes)       # :389
        self._adjust_uroko2(strokes)      # :390
        self._adjust_kirikuchi(strokes)   # :391
        return adjusted

    # ── :395-440 adjustHane（跳ね：笔末钩的大小看左侧近竖）─────
    def _adjust_hane(self, adj_strokes: list[MinchoAdjustedStroke]
                     ) -> list[MinchoAdjustedStroke]:
        vert_segments = []            # {stroke, x, y1, y2}
        for adj in adj_strokes:
            st = adj
            if st.a1_100 == 1 and st.a1_opt == 0 and st.x1 == st.x2:
                vert_segments.append((st, st.x1, st.y1, st.y2))
        for adj in adj_strokes:
            st = adj
            if (st.a1_100 == 1 or st.a1_100 == 2 or st.a1_100 == 6) \
                    and st.a1_opt == 0 and st.a3_100 == 4 and st.a3_opt == 0:
                lpx: float           # lastPointX
                lpy: float           # lastPointY
                if st.a1_100 == 1:
                    lpx, lpy = st.x2, st.y2
                elif st.a1_100 == 2:
                    lpx, lpy = st.x3, st.y3
                else:
                    lpx, lpy = st.x4, st.y4
                mn = math.inf        # mostNear
                if lpx + 18 < 100:
                    mn = lpx + 18    # 怪点：无近竖时以 lpx+18 当虚拟墙（照抄）
                for st2, x, y1, y2 in vert_segments:
                    if st is not st2 \
                            and lpx - x < 100 and x < lpx \
                            and y1 <= lpy and y2 >= lpy:
                        mn = min(mn, lpx - x)
                if mn != math.inf:
                    adj.hane_adjustment += 7 - math.floor(mn / 15)
        return adj_strokes

    # ── :442-481 adjustMage（曲げ：折れ横段近旁有横则后半变细）─
    def _adjust_mage(self, adj_strokes: list[MinchoAdjustedStroke]
                     ) -> list[MinchoAdjustedStroke]:
        hori_segments = []           # {stroke, adjStroke, isTarget, y, x1, x2}
        for adj in adj_strokes:
            st = adj
            if st.a1_100 == 1 and st.a1_opt == 0 and st.y1 == st.y2:
                hori_segments.append((adj, st, False, st.y2, st.x1, st.x2))
            elif st.a1_100 == 3 and st.a1_opt == 0 and st.y2 == st.y3:
                hori_segments.append((adj, st, True, st.y2, st.x2, st.x3))
        for adj, st, is_target, y, x1, x2 in hori_segments:
            if is_target:
                for st2, _adj2, _is_t2, other_y, other_x1, other_x2 in hori_segments:
                    if st is not st2 \
                            and not (x1 + 1 > other_x2 or x2 - 1 < other_x1) \
                            and _round(abs(y - other_y)) \
                            < self.params.k_min_width_t * self.params.k_adjust_mage_step:
                        adj.mage_adjustment += self.params.k_adjust_mage_step \
                            - math.floor(abs(y - other_y) / self.params.k_min_width_t)
                        if adj.mage_adjustment > self.params.k_adjust_mage_step:
                            adj.mage_adjustment = self.params.k_adjust_mage_step
        return adj_strokes

    # ── :483-511 adjustTate（縦：平行近竖互相提示变细档）────────
    def _adjust_tate(self, adj_strokes: list[MinchoAdjustedStroke]
                     ) -> list[MinchoAdjustedStroke]:
        vert_segments = []           # {stroke, adjStroke, x, y1, y2}
        for adj in adj_strokes:
            st = adj
            if (st.a1_100 == 1 or st.a1_100 == 3 or st.a1_100 == 7) \
                    and st.a1_opt == 0 and st.x1 == st.x2:
                vert_segments.append((adj, st, st.x1, st.y1, st.y2))
        for adj, st, x, y1, y2 in vert_segments:
            for st2, _adj2, other_x, other_y1, other_y2 in vert_segments:
                if st is not st2 \
                        and not (y1 + 1 > other_y2 or y2 - 1 < other_y1) \
                        and _round(abs(x - other_x)) \
                        < self.params.k_min_width_t * self.params.k_adjust_tate_step:
                    adj.tate_adjustment += self.params.k_adjust_tate_step \
                        - math.floor(abs(x - other_x) / self.params.k_min_width_t)
                    # JS && 优先于 ||：A > S || (A === S && (opt_1≠0 || a2_100≠0))
                    if adj.tate_adjustment > self.params.k_adjust_tate_step \
                            or (adj.tate_adjustment == self.params.k_adjust_tate_step
                                and (st.a2_opt_1 != 0 or st.a2_100 != 0)):
                        adj.tate_adjustment = self.params.k_adjust_tate_step
        return adj_strokes

    # ── :513-536 adjustKakato（踵：竖脚下有横穿/贴基线则缩短）──
    def _adjust_kakato(self, adj_strokes: list[MinchoAdjustedStroke]
                       ) -> list[MinchoAdjustedStroke]:
        p = self.params
        for adj in adj_strokes:
            st = adj
            if st.a1_100 == 1 and st.a1_opt == 0 \
                    and (st.a3_100 == 13 or st.a3_100 == 23) and st.a3_opt == 0:
                for k in range(p.k_adjust_kakato_step):
                    if (any(st2 is not st and st2.is_cross_box(
                                st.x2 - p.k_adjust_kakato_range_x / 2,
                                st.y2 + p.k_adjust_kakato_range_y[k],
                                st.x2 + p.k_adjust_kakato_range_x / 2,
                                st.y2 + p.k_adjust_kakato_range_y[k + 1])
                            for st2 in adj_strokes)
                            or _round(st.y2 + p.k_adjust_kakato_range_y[k + 1]) > 200
                            # adjust for baseline
                            or _round(st.y2 - st.y1) < p.k_adjust_kakato_range_y[k + 1]):
                            # for thin box
                        adj.kakato_adjustment = 3 - k
                        break
        return adj_strokes

    # ── :538-564 adjustUroko（鱗：末端被穿/笔画短则收缩）────────
    def _adjust_uroko(self, adj_strokes: list[MinchoAdjustedStroke]
                      ) -> list[MinchoAdjustedStroke]:
        p = self.params
        for adj in adj_strokes:
            st = adj
            if st.a1_100 == 1 and st.a1_opt == 0 \
                    and st.a3_100 == 0 and st.a3_opt == 0:  # no operation for TATE
                for k in range(p.k_adjust_uroko_length_step):
                    if st.y1 == st.y2:  # YOKO
                        cosrad, sinrad = 1, 0                # ?????
                    elif (st.x2 - st.x1 < 0):
                        cosrad, sinrad = normalize(st.x1 - st.x2, st.y1 - st.y2)
                        # for backward compatibility...
                    else:
                        cosrad, sinrad = normalize(st.x2 - st.x1, st.y2 - st.y1)
                    tx = st.x2 - p.k_adjust_uroko_line[k] * cosrad - 0.5 * sinrad
                    # typo? (sinrad should be -sinrad ?)
                    ty = st.y2 - p.k_adjust_uroko_line[k] * sinrad - 0.5 * cosrad

                    if st.y1 == st.y2:              # YOKO
                        tlen = st.x2 - st.x1        # should be Math.abs(...)?
                    else:
                        tlen = _hypot(st.y2 - st.y1, st.x2 - st.x1)
                    if _round(tlen) < p.k_adjust_uroko_length[k] \
                            or any(st2 is not st and st2.is_cross(tx, ty, st.x2, st.y2)
                                   for st2 in adj_strokes):
                        adj.uroko_adjustment = p.k_adjust_uroko_length_step - k
                        break
        return adj_strokes

    # ── :566-609 adjustUroko2（鱗其二：按平行横线密度收缩）──────
    def _adjust_uroko2(self, adj_strokes: list[MinchoAdjustedStroke]
                       ) -> list[MinchoAdjustedStroke]:
        p = self.params
        hori_segments = []           # {stroke, adjStroke, isTarget, y, x1, x2}
        for adj in adj_strokes:
            st = adj
            if st.a1_100 == 1 and st.a1_opt == 0 and st.y1 == st.y2:
                hori_segments.append(
                    (adj, st,
                     st.a3_100 == 0 and st.a3_opt == 0
                     and adj.uroko_adjustment == 0,     # 依赖 _adjust_uroko 先跑
                     st.y1, st.x1, st.x2))
            elif st.a1_100 == 3 and st.a1_opt == 0 and st.y2 == st.y3:
                hori_segments.append((adj, st, False, st.y2, st.x2, st.x3))
        for adj, st, is_target, y, x1, x2 in hori_segments:
            if is_target:
                pressure = 0
                for st2, _adj2, _is_t2, other_y, other_x1, other_x2 in hori_segments:
                    if st is not st2 \
                            and not (x1 + 1 > other_x2 or x2 - 1 < other_x1) \
                            and _round(abs(y - other_y)) < p.k_adjust_uroko2_length:
                        pressure += (p.k_adjust_uroko2_length - abs(y - other_y)) ** 1.1
                # 源此处留有被注释掉的 `if (stroke.a3 < result)` 包裹，照抄现行赋值
                adj.uroko_adjustment = min(
                    math.floor(pressure / p.k_adjust_uroko2_length),
                    p.k_adjust_uroko2_step)
        return adj_strokes

    # ── :611-634 adjustKirikuchi（切り口：2:32 起笔落在横上换切角）─
    def _adjust_kirikuchi(self, adj_strokes: list[MinchoAdjustedStroke]
                          ) -> list[MinchoAdjustedStroke]:
        hori_segments = []           # {y, x1, x2}
        for adj in adj_strokes:
            st = adj
            if st.a1_100 == 1 and st.a1_opt == 0 and st.y1 == st.y2:
                hori_segments.append((st.y1, st.x1, st.x2))
        for adj in adj_strokes:
            st = adj
            if (st.a1_100 == 2 and st.a1_opt == 0
                    and st.a2_100 == 32 and st.a2_opt == 0
                    and st.x1 > st.x2 and st.y1 < st.y2
                    and any(x1 < st.x1 and x2 > st.x1 and y == st.y1
                            for (y, x1, x2) in hori_segments)):
                    # no need to skip when i == j
                adj.kirikuchi_adjustment = 1
        return adj_strokes
