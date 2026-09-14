# src/gsrender/__init__.py
"""gsrender：GSF 字形渲染器。"""
import gsrender.pen_minimal  # noqa: F401  注册 pen-minimal 后端（不 import 则 get_backend 抛 ValueError，T8 审查教训；legacy-kurgm 由 cli.py 显式 import 注册）
from gsrender.compare import compare
from gsrender.corpus import Corpus
from gsrender.protocol import RenderOptions, Renderer

__version__ = "0.1.0"

__all__ = ["Corpus", "Renderer", "RenderOptions", "compare", "__version__"]
