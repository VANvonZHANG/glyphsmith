# src/glyphsmith/legacy_kurgm/__init__.py
"""legacy-kurgm 后端：kurgm/kage-engine 的忠实 Python 移植。

移植谱系：kurgm/kage-engine（TypeScript，移植基准）← kamichikoichi/kage-engine
（原版，kagecd.js/kagedf.js 规则表出处）；Python 移植参考 HowardZorn/kage-engine；
环检测思路回移植自 takushun-wu/kage-cpp。GPLv3。
"""
from __future__ import annotations

from glyphsmith.outline import Outline
from glyphsmith.protocol import Backend, RenderOptions


class LegacyKurgmBackend(Backend):
    """kurgm 管线对外封装：resolve 结果 → expand → font drawers → Outline。

    简报骨架的两处现状适配（公开行为不变）：
    - kUseCurve 走 Font.k_use_curve 属性（T7 委托 params.k_use_curve 的
      snake_case 字段；直接写 font.params.kUseCurve 会静默新建无关属性）；
    - select_font(Shotai.K_GOTHIC) 自 T8 起返回真 GothicFont（非 _StubFont），
      mincho 在 T10 前仍是占位（不画笔画）。
    """

    name = "legacy-kurgm"

    def render(self, result, opts=None):
        opts = opts or RenderOptions()
        from .expansion import expand
        from .font import Shotai, select_font
        shotai = Shotai.K_MINCHO if opts.font == "mincho" else Shotai.K_GOTHIC
        font = select_font(shotai)
        font.k_use_curve = opts.use_curve
        if opts.size:
            font.set_size(opts.size)
        warnings = list(result.warnings)
        items = expand(result.glyph, result.parts, warnings)
        result.warnings[:] = warnings
        o = Outline()
        for d in font.get_drawers(items):
            d(o)
        return o

    def render_separated(self, result, opts=None):
        opts = opts or RenderOptions()
        from .expansion import expand
        from .font import Shotai, select_font
        shotai = Shotai.K_MINCHO if opts.font == "mincho" else Shotai.K_GOTHIC
        font = select_font(shotai)
        font.k_use_curve = opts.use_curve
        items = expand(result.glyph, result.parts)
        outs = []
        for d in font.get_drawers(items):
            o = Outline()
            d(o)
            outs.append(o)
        return outs


Backend.register(LegacyKurgmBackend)
