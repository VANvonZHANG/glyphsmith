# src/glyphsmith/pen/__init__.py
"""The pen backend package (v2): relational graph + declarative styles + nib.

Modules: centerline (stroke -> polyline), graph, style, nib, backend.
Design: docs/pen-backend-design.md (v1 freeze) and the v2 spec.
"""
import glyphsmith.pen.backend  # noqa: F401  registers the `pen` backend; a backend
# that is not imported at package import time is a cold `import glyphsmith` ValueError.
