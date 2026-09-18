# src/glyphsmith/legacy_kurgm/font/__init__.py
"""Font layer: Shotai selection, the FontParams parameter base, the drawers
pipeline, dfTransform.

← K/font/index.ts (FontInterface/select), K/font/shotai.ts (KShotai),
K/font/mincho/index.ts, K/font/gothic/index.ts.
"""
from . import base as _base
from .base import Drawer, Font, FontParams, Shotai, _StubFont, select_font
from .gothic import GothicFont
from .mincho import MinchoAdjustedStroke, MinchoFont
from .transform import df_transform

# T8-T10: register the real GothicFont (T8) and the real MinchoFont (T9's
# seven-stage adjust pipeline + T10's mincho cd tables, with the golden m:
# subset all green). The registry itself stays in base (avoiding a
# base ↔ subclass import cycle) and is populated here at package init — any
# submodule import of this package runs this file first, so registration
# precedes every select_font call.
_base._FONTS[Shotai.K_GOTHIC] = GothicFont
_base._FONTS[Shotai.K_MINCHO] = MinchoFont

__all__ = ["Drawer", "Font", "FontParams", "Shotai", "GothicFont",
           "MinchoFont", "MinchoAdjustedStroke",
           "df_transform", "select_font", "_StubFont"]
