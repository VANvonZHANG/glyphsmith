# tests/test_compare.py
import json

import pytest

from glyphsmith.compare import compare, compare_separated, rasterize
from glyphsmith.outline import Outline


def _square(x0=20, y0=20, x1=180, y1=180):
    return Outline.from_contours(
        [[(float(x0), float(y0), 0), (float(x1), float(y0), 0),
          (float(x1), float(y1), 0), (float(x0), float(y1), 0)]])


def test_identical_squares_iou_1():
    assert compare(_square(), _square()).iou == 1.0


def test_shifted_squares_lower_iou():
    assert 0.5 < compare(_square(), _square(x0=40, x1=200)).iou < 1.0


def test_disjoint_zero():
    r = compare(_square(), _square(x0=400, y0=400, x1=500, y1=500))
    assert r.iou == 0.0


def test_rasterize_size():
    assert rasterize(_square(), size=256).size == (256, 256)


def test_to_dict_serializable():
    json.dumps(compare(_square(), _square()).to_dict())


def test_perturbation_detected():   # 判别力负测试（防盲比对复发）
    b = _square()
    b.contours[0][1] = (180.0, 60.0, 0)      # 挪一个顶点
    assert compare(_square(), b).iou < 1.0


def test_separated_metrics():
    s1 = [_square(), _square()]
    s2 = [_square(), _square(x0=60)]
    ms = compare_separated(s1, s2)
    assert len(ms) == 2
    assert ms[0].bbox_iou == 1.0 and ms[1].bbox_iou < 1.0
    assert ms[1].hausdorff > 0
