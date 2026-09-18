# src/glyphsmith/pen_minimal.py
"""pen-minimal: a uniform-width stroked-skeleton preview backend (the minimal
subset of Levien's vocabulary: parallel + cap).

The interface placeholder for the v2 pen backend (relational graph + style
files + variable-width nib); the design is in docs/pen-backend-design.md.
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
        warnings = list(result.warnings)   # final review I2: as in legacy-kurgm.render
        o = Outline()                      # write-back convention — missing part / raw op
        for st in expand(result.glyph, result.parts, warnings):
            if isinstance(st, tuple):      # TransformOp: skipped at preview grade
                continue
            o.contours.extend(self._draw(st).contours)
        result.warnings[:] = warnings      # warnings must not silently vanish on a backend switch
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
            ox, oy = -dy / n * WIDTH / 2, dx / n * WIDTH / 2     # normal offset
            o.new_contour()
            o.push(x1 + ox, y1 + oy)
            o.push(x2 + ox, y2 + oy)
            o.push(x2 - ox, y2 - oy)
            o.push(x1 - ox, y1 - oy)     # butt cap
        return o


Backend.register(PenMinimalBackend)
