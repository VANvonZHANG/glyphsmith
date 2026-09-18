# src/glyphsmith/__init__.py
"""glyphsmith：GSF 字形渲染器。"""
import glyphsmith.legacy_kurgm  # noqa: F401  注册 legacy-kurgm（默认后端）——终审 C2：
                               # 此前仅由 cli.py 显式 import 注册，库态冷导入
                               # `import glyphsmith; Renderer()` 会抛 ValueError
import glyphsmith.pen_minimal  # noqa: F401  注册 pen-minimal 后端（T8 审查教训：不 import 则 get_backend 抛 ValueError）
from glyphsmith.compare import compare
from glyphsmith.corpus import Corpus
from glyphsmith.protocol import RenderOptions, Renderer

__version__ = "0.1.0"

__all__ = ["Corpus", "Renderer", "RenderOptions", "compare", "__version__"]
