# src/gsrender/legacy_kurgm/font/__init__.py
"""字体层：Shotai 选择、FontParams 参数基座、drawers 管线、dfTransform。

← K/font/index.ts（FontInterface/select）、K/font/shotai.ts（KShotai）、
K/font/mincho/index.ts、K/font/gothic/index.ts。
"""
from .base import Drawer, Font, FontParams, Shotai, _StubFont, select_font
from .transform import df_transform

__all__ = ["Drawer", "Font", "FontParams", "Shotai", "df_transform",
           "select_font", "_StubFont"]
