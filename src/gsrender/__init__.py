# src/gsrender/__init__.py
"""gsrender：GSF 字形渲染器。"""
from gsrender.corpus import Corpus
from gsrender.protocol import RenderOptions, Renderer

__version__ = "0.1.0"

# compare 等 T13 后再补
__all__ = ["Corpus", "Renderer", "RenderOptions", "__version__"]
