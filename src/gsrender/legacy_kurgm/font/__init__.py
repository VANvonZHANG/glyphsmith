# src/gsrender/legacy_kurgm/font/__init__.py
"""字体层：Shotai 选择、FontParams 参数基座、drawers 管线、dfTransform。

← K/font/index.ts（FontInterface/select）、K/font/shotai.ts（KShotai）、
K/font/mincho/index.ts、K/font/gothic/index.ts。
"""
from . import base as _base
from .base import Drawer, Font, FontParams, Shotai, _StubFont, select_font
from .gothic import GothicFont
from .transform import df_transform

# T8：K_GOTHIC 注册真 GothicFont（笔画真画）。注册表本体留在 base（避免
# base ↔ gothic 循环导入），在包初始化处完成注入——import 本包任何子模块
# 都会先跑本文件，注册先于一切 select_font 调用。K_MINCHO 待 T10。
_base._FONTS[Shotai.K_GOTHIC] = GothicFont

__all__ = ["Drawer", "Font", "FontParams", "Shotai", "GothicFont",
           "df_transform", "select_font", "_StubFont"]
