# src/glyphsmith/legacy_kurgm/__init__.py
"""legacy-kurgm backend: a faithful Python port of kurgm/kage-engine.

Porting lineage: kurgm/kage-engine (TypeScript, the porting baseline) ←
kamichikoichi/kage-engine (the original, source of the kagecd.js/kagedf.js rule
tables); the Python port took HowardZorn/kage-engine as a reference; the cycle
detection idea was back-ported from takushun-wu/kage-cpp. GPLv3.
"""
from __future__ import annotations

from glyphsmith.outline import Outline
from glyphsmith.protocol import Backend, RenderOptions


class LegacyKurgmBackend(Backend):
    """The kurgm pipeline's public wrapper: resolve result → expand → font
    drawers → Outline.

    Two places where the brief's skeleton was adapted to reality (public
    behaviour unchanged):
    - kUseCurve goes through the Font.k_use_curve property (T7 delegates to the
      snake_case params.k_use_curve field; writing font.params.kUseCurve
      directly would silently create an unrelated attribute);
    - select_font(Shotai.K_GOTHIC) has returned a real GothicFont since T8 (not
      _StubFont); mincho was still a placeholder (drawing no strokes) before
      T10.
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
