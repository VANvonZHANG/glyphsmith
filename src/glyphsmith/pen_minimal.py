# src/glyphsmith/pen_minimal.py
"""pen-minimal：等宽描边骨架预览后端（Levien 词汇最小子集：parallel+cap）。

v2 pen 后端（关系图+风格文件+变宽 nib）的接口占位实现，
设计见 docs/pen-backend-design.md。
"""
from __future__ import annotations

import math

from glyphsmith.outline import Outline
from glyphsmith.protocol import Backend, RenderOptions

WIDTH = 8.0


class PenMinimalBackend(Backend):
    name = "pen-minimal"

    def render(self, result, opts=None) -> Outline:
        from .legacy_kurgm.expansion import expand
        warnings = list(result.warnings)   # 终审 I2：与 legacy-kurgm.render 同款
        o = Outline()                      # 回写口径——missing part / raw op 类
        for st in expand(result.glyph, result.parts, warnings):
            if isinstance(st, tuple):      # TransformOp：预览级跳过
                continue
            o.contours.extend(self._draw(st).contours)
        result.warnings[:] = warnings      # 警告不因换后端而悬空静默
        return o

    def render_separated(self, result, opts=None) -> list:
        from .legacy_kurgm.expansion import expand
        warnings = list(result.warnings)
        outs = [self._draw(st) for st in expand(result.glyph, result.parts, warnings)
                if not isinstance(st, tuple)]
        result.warnings[:] = warnings
        return outs

    def _draw(self, st) -> Outline:
        o = Outline()
        for x1, y1, x2, y2 in st.get_control_segments():
            dx, dy = x2 - x1, y2 - y1
            n = math.hypot(dx, dy) or 1.0
            ox, oy = -dy / n * WIDTH / 2, dx / n * WIDTH / 2     # 法向偏移
            o.new_contour()
            o.push(x1 + ox, y1 + oy)
            o.push(x2 + ox, y2 + oy)
            o.push(x2 - ox, y2 - oy)
            o.push(x1 - ox, y1 - oy)     # butt 端帽
        return o


Backend.register(PenMinimalBackend)
