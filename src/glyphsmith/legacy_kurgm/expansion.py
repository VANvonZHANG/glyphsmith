# src/glyphsmith/legacy_kurgm/expansion.py
"""ref recursive expansion: affine scaling + stretch + cycle detection + TransformOp. ← K/kage.ts"""
from __future__ import annotations

from typing import NamedTuple

from gsf.model import Glyph, RawOp, Ref, Stroke

from .rstroke import RStroke


class CycleError(Exception):
    def __init__(self, path: list[str]):
        super().__init__("cycle: " + " -> ".join(path))
        self.path = path


class TransformOp(NamedTuple):
    """The 97/98/99 special rows of type-0 (dfcd adjustment operations): passed
    through to the font layer, not involved in geometry.

    a3 = the raw row's cols[2] (kurgm Stroke.a3_100): the rotation level for
    kind=99 (1/2/3 → clockwise 90/180/270 degrees), on which the font layer
    calls df_transform(a3=...); it is 0 for kind=97/98 (flips) and carries no
    semantics there.
    """

    kind: int
    a3: int
    x1: int
    y1: int
    x2: int
    y2: int


def ref_names(glyph: Glyph) -> list[str]:
    return [op.name for op in glyph.ops if isinstance(op, Ref)]


def expand(glyph: Glyph, parts: dict[str, Glyph],
           warnings: list[str] | None = None) -> list:
    # NB: `warnings or []` must not be used here: an empty list passed in by the
    # caller is falsy and would be discarded, so the warnings would go into a
    # temporary list the caller never sees (the brief's reference code had
    # exactly this trap; fixed).
    return _expand(glyph, parts, [] if warnings is None else warnings, depth=0)


def _expand(glyph: Glyph, parts: dict[str, Glyph],
            warnings: list[str], depth: int) -> list:
    if depth > 30:                      # simplified version of kage-cpp's CheckGlyph idea
        raise CycleError([glyph.name])
    items: list = []
    for op in glyph.ops:
        if isinstance(op, Stroke):
            items.append(RStroke.from_gsf(op))
        elif isinstance(op, Ref):
            part = parts.get(op.name)
            if part is None:            # @version fallback: a ref name with @N falls back to base
                base = op.name.partition("@")[0]
                # a self-referential historical snapshot self@N does not get the
                # fallback (T16 full-dump smoke: all 94 CycleError cases in the
                # dump are X referencing X@N — a newest-only corpus has no X@N
                # row, so falling back to itself would be a false cycle; kurgm's
                # exact match finds nothing → the ref is skipped)
                if base != glyph.name:
                    part = parts.get(base)
            if part is None:
                warnings.append(f"missing part: {op.name}")
                continue
            sub = _expand(part, parts, warnings, depth + 1)
            box = _box(sub)
            sx, sy, sx2, sy2 = op.sx, op.sy, op.sx2, op.sy2
            if sx != 0 or sy != 0:                 # K/kage.ts:242-249
                if sx > 100:
                    sx -= 200
                else:
                    sx2 = sy2 = 0
            for st in sub:                          # K/kage.ts:251-263
                if isinstance(st, RStroke):
                    if sx != 0 or sy != 0:
                        st.apply_stretch(sx, sx2, sy, sy2,
                                         box["minX"], box["maxX"],
                                         box["minY"], box["maxY"])
                    st.x1 = op.x1 + st.x1 * (op.x2 - op.x1) / 200
                    st.y1 = op.y1 + st.y1 * (op.y2 - op.y1) / 200
                    st.x2 = op.x1 + st.x2 * (op.x2 - op.x1) / 200
                    st.y2 = op.y1 + st.y2 * (op.y2 - op.y1) / 200
                    st.x3 = op.x1 + st.x3 * (op.x2 - op.x1) / 200
                    st.y3 = op.y1 + st.y3 * (op.y2 - op.y1) / 200
                    st.x4 = op.x1 + st.x4 * (op.x2 - op.x1) / 200
                    st.y4 = op.y1 + st.y4 * (op.y2 - op.y1) / 200
            items.extend(sub)
        elif isinstance(op, RawOp):
            cols = op.cols
            if len(cols) >= 7 and cols[0] == "0" and cols[1] in ("97", "98", "99"):
                items.append(TransformOp(int(cols[1]), int(cols[2]), int(cols[3]),
                                         int(cols[4]), int(cols[5]), int(cols[6])))
            else:
                warnings.append(f"raw op skipped: {':'.join(cols[:4])}")
    return items


def _box(items) -> dict:
    """K/kage.ts:266-285: start from [0,200] and take the extremes of each
    RStroke.get_box().

    Aggregation uses JS Math.min/max semantics (NaN contagion): when a part's
    stroke box carries NaN (caused by a degenerate stretch) the whole box
    becomes NaN → the outer stretch is all NaN → the polygon is dropped (the
    T16 closure smoke found 84 glyphs where Python's min silently dropped the
    NaN and drew extra)."""
    from .geom2d import js_max, js_min
    min_x = min_y = 200
    max_x = max_y = 0
    for it in items:
        if isinstance(it, RStroke):
            b = it.get_box()
            min_x = js_min(min_x, b["minX"]); max_x = js_max(max_x, b["maxX"])
            min_y = js_min(min_y, b["minY"]); max_y = js_max(max_y, b["maxY"])
    return {"minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y}
