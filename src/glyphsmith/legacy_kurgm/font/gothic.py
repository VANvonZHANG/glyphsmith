# src/glyphsmith/legacy_kurgm/font/gothic.py
"""GothicFont: a direct translation of K/font/gothic/index.ts (dfDrawFont +
the Gothic class).

adjustStrokes finding (confirmed by reading the source, gothic/index.ts:168
vs mincho/index.ts:356): Mincho.getDrawers first runs
this.adjustStrokes(strokesArray).map(...) (the mincho-only seven-stage stroke
parameter adjust pipeline), whereas Gothic's overriding getDrawers calls
strokesArray.map(stroke => dfDrawFont(this, polygons, stroke)) directly —
**Gothic skips mincho's adjustStrokes entirely**, and the raw Stroke reaches
dfDrawFont untouched.
Also Gothic extends Mincho (K:165): the parameter table/setSize are wholly
inherited and only shotai and getDrawers are overridden; this repo's base Font
already carries the shared pipeline, so GothicFont only has to override stroke
dispatch (_stroke_drawer → df_draw_font), while the TransformOp channel
(lines 0:97/98/99 of case 0) uses T7's base-class dispatch.
"""
from __future__ import annotations

import math

from glyphsmith.outline import Outline

from .base import Drawer, Font, Shotai
from .gothic_cd import (_hypot, cd_draw_bezier, cd_draw_curve, cd_draw_line,
                        normalize)
from .transform import df_transform


def df_draw_font(font: Font, outline: Outline, stroke) -> None:
    """Case-by-case direct translation of gothic/index.ts:10-162 dfDrawFont.

    stroke fields = RStroke (the decomposition fields produced by kurgm's
    Stroke constructor). The width/curvature formulas are copied term by term
    (kMage/kWidth etc. come from font.params); Math.floor is kept in place.
    """
    a1_100 = stroke.a1_100
    a2_100 = stroke.a2_100
    a2_opt = stroke.a2_opt
    a3_100 = stroke.a3_100
    a3_opt = stroke.a3_opt
    a3_opt_1 = stroke.a3_opt_1
    x1, y1, x2, y2 = stroke.x1, stroke.y1, stroke.x2, stroke.y2
    x3, y3, x4, y4 = stroke.x3, stroke.y3, stroke.x4, stroke.y4

    if a1_100 == 0:
        df_transform(outline, a2_100, x1, y1, x2, y2,
                     a3=a3_100, a2_opt=a2_opt, a3_opt=a3_opt)
    elif a1_100 == 1:
        if a3_100 == 4:
            if x1 == x2 and y1 == y2:
                dx1, dy1 = 0, font.params.k_mage          # ?????
            else:
                dx1, dy1 = normalize(x1 - x2, y1 - y2, font.params.k_mage)
            tx1 = x2 + dx1
            ty1 = y2 + dy1
            cd_draw_line(font, outline, x1, y1, tx1, ty1, a2_100, 1)
            cd_draw_curve(font, outline, tx1, ty1, x2, y2,
                          x2 - font.params.k_mage * 2,
                          y2 - font.params.k_mage * 0.5, 1, 0)
        else:
            cd_draw_line(font, outline, x1, y1, x2, y2, a2_100, a3_100)
    elif a1_100 in (2, 12):
        if a3_100 == 4:
            if x2 == x3:
                dx1, dy1 = 0, -font.params.k_mage                  # ?????
            elif y2 == y3:
                dx1, dy1 = -font.params.k_mage, 0                  # ?????
            else:
                dx1, dy1 = normalize(x2 - x3, y2 - y3, font.params.k_mage)
            tx1 = x3 + dx1
            ty1 = y3 + dy1
            cd_draw_curve(font, outline, x1, y1, x2, y2, tx1, ty1, a2_100, 1)
            cd_draw_curve(font, outline, tx1, ty1, x3, y3,
                          x3 - font.params.k_mage * 2,
                          y3 - font.params.k_mage * 0.5, 1, 0)
        elif a3_100 == 5 and a3_opt == 0:
            tx1 = x3 + font.params.k_mage
            ty1 = y3
            tx2 = tx1 + font.params.k_mage * 0.5
            ty2 = y3 - font.params.k_mage * 2
            cd_draw_curve(font, outline, x1, y1, x2, y2, x3, y3, a2_100, 1)
            cd_draw_curve(font, outline, x3, y3, tx1, ty1, tx2, ty2, 1, 0)
        else:
            cd_draw_curve(font, outline, x1, y1, x2, y2, x3, y3, a2_100, a3_100)
    elif a1_100 == 3:
        if x1 == x2 and y1 == y2:
            dx1, dy1 = 0, font.params.k_mage                          # ?????
        else:
            dx1, dy1 = normalize(x1 - x2, y1 - y2, font.params.k_mage)
        tx1 = x2 + dx1
        ty1 = y2 + dy1
        if x2 == x3 and y2 == y3:
            dx2, dy2 = 0, -font.params.k_mage                         # ?????
        else:
            dx2, dy2 = normalize(x3 - x2, y3 - y2, font.params.k_mage)
        tx2 = x2 + dx2
        ty2 = y2 + dy2

        cd_draw_line(font, outline, x1, y1, tx1, ty1, a2_100, 1)
        cd_draw_curve(font, outline, tx1, ty1, x2, y2, tx2, ty2, 1, 1)

        if a3_100 == 5 and a3_opt_1 == 0:
            tx3 = x3 - font.params.k_mage
            ty3 = y3
            tx4 = x3 + font.params.k_mage * 0.5
            ty4 = y3 - font.params.k_mage * 2

            cd_draw_line(font, outline, tx2, ty2, tx3, ty3, 1, 1)
            cd_draw_curve(font, outline, tx3, ty3, x3, y3, tx4, ty4, 1, 0)
        else:
            cd_draw_line(font, outline, tx2, ty2, x3, y3, 1, a3_100)
    elif a1_100 == 4:
        rate = _hypot(x3 - x2, y3 - y2) / 120 * 6
        if rate > 6:
            rate = 6
        if x1 == x2 and y1 == y2:
            dx1, dy1 = 0, font.params.k_mage * rate                # ?????
        else:
            dx1, dy1 = normalize(x1 - x2, y1 - y2, font.params.k_mage * rate)
        tx1 = x2 + dx1
        ty1 = y2 + dy1
        if x2 == x3 and y2 == y3:
            dx2, dy2 = 0, -font.params.k_mage * rate               # ?????
        else:
            dx2, dy2 = normalize(x3 - x2, y3 - y2, font.params.k_mage * rate)
        tx2 = x2 + dx2
        ty2 = y2 + dy2

        cd_draw_line(font, outline, x1, y1, tx1, ty1, a2_100, 1)
        cd_draw_curve(font, outline, tx1, ty1, x2, y2, tx2, ty2, 1, 1)
        if a3_100 == 5 and a3_opt == 0:
            tx3 = x3 - font.params.k_mage
            ty3 = y3
            tx4 = x3 + font.params.k_mage * 0.5
            ty4 = y3 - font.params.k_mage * 2

            cd_draw_line(font, outline, tx2, ty2, tx3, ty3, 1, 1)
            cd_draw_curve(font, outline, tx3, ty3, x3, y3, tx4, ty4, 1, 0)
        else:
            cd_draw_line(font, outline, tx2, ty2, x3, y3, 1, a3_100)
    elif a1_100 == 6:
        if a3_100 == 4:
            if x3 == x4:
                dx1, dy1 = 0, -font.params.k_mage                  # ?????
            elif y3 == y4:
                dx1, dy1 = -font.params.k_mage, 0                  # ?????
            else:
                dx1, dy1 = normalize(x3 - x4, y3 - y4, font.params.k_mage)
            tx1 = x4 + dx1
            ty1 = y4 + dy1
            cd_draw_bezier(font, outline, x1, y1, x2, y2, x3, y3, tx1, ty1, a2_100, 1)
            cd_draw_curve(font, outline, tx1, ty1, x4, y4,
                          x4 - font.params.k_mage * 2,
                          y4 - font.params.k_mage * 0.5, 1, 0)
        elif a3_100 == 5 and a3_opt == 0:
            tx1 = x4 - font.params.k_mage
            ty1 = y4
            tx2 = x4 + font.params.k_mage * 0.5
            ty2 = y4 - font.params.k_mage * 2
            # the source keeps a commented-out old implementation here that
            # split this into two cdDrawCurve calls at the midpoint; current
            # behaviour copied as-is
            cd_draw_bezier(font, outline, x1, y1, x2, y2, x3, y3, tx1, ty1, a2_100, 1)
            cd_draw_curve(font, outline, tx1, ty1, x4, y4, tx2, ty2, 1, 0)
        else:
            # the source keeps a commented-out old implementation here that
            # split this into two cdDrawCurve calls at the midpoint; current
            # behaviour copied as-is
            cd_draw_bezier(font, outline, x1, y1, x2, y2, x3, y3, x4, y4, a2_100, a3_100)
    elif a1_100 == 7:
        cd_draw_line(font, outline, x1, y1, x2, y2, a2_100, 1)
        cd_draw_curve(font, outline, x2, y2, x3, y3, x4, y4, 1, a3_100)
    elif a1_100 == 9:
        pass    # may not be exist (source comment; old kageCanvas code commented out)
    # default: break (no operation)


class GothicFont(Font):
    """Gothic. ← K/font/gothic/index.ts:164-173 Gothic.

    Only the shotai and getDrawers semantics are overridden (skipping mincho's
    adjustStrokes, see the module docstring); parameters and setSize are wholly
    inherited from the base (in the source, inherited from Mincho).
    """

    shotai = Shotai.K_GOTHIC

    def _stroke_drawer(self, stroke) -> Drawer:
        def draw(outline: Outline) -> None:
            df_draw_font(self, outline, stroke)
        return draw
