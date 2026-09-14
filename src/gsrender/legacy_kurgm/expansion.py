# src/gsrender/legacy_kurgm/expansion.py
"""ref 递归展开：affine 缩放 + stretch + 环检测 + TransformOp。← K/kage.ts"""
from __future__ import annotations

from typing import NamedTuple

from gsf.model import Glyph, RawOp, Ref, Stroke

from .rstroke import RStroke


class CycleError(Exception):
    def __init__(self, path: list[str]):
        super().__init__("cycle: " + " -> ".join(path))
        self.path = path


class TransformOp(NamedTuple):
    """type-0 的 97/98/99 特殊行（dfcd 调整操作）：透传给字体层，不参与几何。"""

    kind: int
    x1: int
    y1: int
    x2: int
    y2: int


def ref_names(glyph: Glyph) -> list[str]:
    return [op.name for op in glyph.ops if isinstance(op, Ref)]


def expand(glyph: Glyph, parts: dict[str, Glyph],
           warnings: list[str] | None = None) -> list:
    # 注意不能用 `warnings or []`：调用方传入的空列表是 falsy，会被丢弃，
    # 警告写进临时列表而调用方收不到（简报参考代码即此坑，已修正）。
    return _expand(glyph, parts, [] if warnings is None else warnings, depth=0)


def _expand(glyph: Glyph, parts: dict[str, Glyph],
            warnings: list[str], depth: int) -> list:
    if depth > 30:                      # kage-cpp CheckGlyph 思路的简化版
        raise CycleError([glyph.name])
    items: list = []
    for op in glyph.ops:
        if isinstance(op, Stroke):
            items.append(RStroke.from_gsf(op))
        elif isinstance(op, Ref):
            part = parts.get(op.name)
            if part is None:            # @版本兜底：ref 名带 @N 时回退基名
                part = parts.get(op.name.partition("@")[0])
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
                items.append(TransformOp(int(cols[1]), int(cols[3]), int(cols[4]),
                                         int(cols[5]), int(cols[6])))
            else:
                warnings.append(f"raw op skipped: {':'.join(cols[:4])}")
    return items


def _box(items) -> dict:
    """K/kage.ts:266-285：初始 [0,200]，取各 RStroke.get_box() 极值。"""
    min_x = min_y = 200
    max_x = max_y = 0
    for it in items:
        if isinstance(it, RStroke):
            b = it.get_box()
            min_x = min(min_x, b["minX"]); max_x = max(max_x, b["maxX"])
            min_y = min(min_y, b["minY"]); max_y = max(max_y, b["maxY"])
    return {"minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y}
