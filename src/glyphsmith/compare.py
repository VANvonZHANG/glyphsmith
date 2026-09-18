# src/glyphsmith/compare.py
"""The comparison end of the authoring loop: raster IoU + per-stroke structural metrics."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

from glyphsmith.outline import Outline


def rasterize(outline: Outline, size: int = 256) -> Image.Image:
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    for contour in outline.contours:
        pts = [(x * size / 200.0, y * size / 200.0) for x, y, _ in contour]
        if len(pts) >= 3:
            draw.polygon(pts, fill=255)
    return img


def _mask(outline: Outline, size: int) -> np.ndarray:
    return np.asarray(rasterize(outline, size), dtype=bool)


@dataclass
class StrokeMetric:
    bbox_iou: float
    vertex_count_a: int
    vertex_count_b: int
    hausdorff: float


@dataclass
class CompareResult:
    iou: float
    per_stroke: list[StrokeMetric] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"iou": self.iou,
                "per_stroke": [{"bbox_iou": m.bbox_iou,
                                "vertex_count": [m.vertex_count_a, m.vertex_count_b],
                                "hausdorff": m.hausdorff} for m in self.per_stroke]}


def compare(a: Outline, b: Outline, *, size: int = 256) -> CompareResult:
    ma, mb = _mask(a, size), _mask(b, size)
    union = int((ma | mb).sum())
    iou = float((ma & mb).sum() / union) if union else 1.0
    return CompareResult(iou=iou)


def compare_separated(as_: list[Outline], bs: list[Outline]) -> list[StrokeMetric]:
    out = []
    for a, b in zip(as_, bs):
        out.append(StrokeMetric(
            _bbox_iou(_bbox(a), _bbox(b)),
            sum(len(c) for c in a.contours),
            sum(len(c) for c in b.contours),
            _hausdorff(a, b)))
    return out


def _bbox(o: Outline):
    xs = [x for c in o.contours for x, _, _ in c]
    ys = [y for c in o.contours for y, _, _ in c]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)


def _bbox_iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 1.0


def _hausdorff(a: Outline, b: Outline) -> float:
    pa = np.array([(x, y) for c in a.contours for x, y, _ in c] or [(0.0, 0.0)])
    pb = np.array([(x, y) for c in b.contours for x, y, _ in c] or [(0.0, 0.0)])
    d = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2)
    return float(max(d.min(axis=1).max(), d.min(axis=0).max()))
