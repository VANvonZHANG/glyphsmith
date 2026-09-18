# src/glyphsmith/__init__.py
"""glyphsmith: a GSF glyph renderer."""
import glyphsmith.legacy_kurgm  # noqa: F401  register legacy-kurgm (the default backend)
# Final review C2: previously only cli.py's explicit import registered it, so a
# cold library import `import glyphsmith; Renderer()` raised ValueError.
import glyphsmith.pen_minimal  # noqa: F401  register the pen-minimal backend
# T8 review lesson: without this import, get_backend raises ValueError.
from glyphsmith.compare import compare
from glyphsmith.corpus import Corpus
from glyphsmith.protocol import RenderOptions, Renderer

__version__ = "0.1.0"

__all__ = ["Corpus", "Renderer", "RenderOptions", "compare", "__version__"]
