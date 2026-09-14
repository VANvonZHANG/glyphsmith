# src/gsrender/__init__.py
"""gsrender：GSF 字形渲染器。"""
from gsrender.compare import compare
from gsrender.corpus import Corpus
from gsrender.protocol import RenderOptions, Renderer

__version__ = "0.1.0"

__all__ = ["Corpus", "Renderer", "RenderOptions", "compare", "__version__"]
