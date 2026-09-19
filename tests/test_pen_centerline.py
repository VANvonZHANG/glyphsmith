# tests/test_pen_centerline.py
import math

import pytest

from glyphsmith.legacy_kurgm.rstroke import RStroke
from glyphsmith.pen.centerline import FLATTEN_TOL, arc_length, extract


def _rs(*rows):
    """Build an RStroke directly: (a1_100, a2_100, a3_100, x1,y1,x2,y2,x3,y3,x4,y4)."""
    return RStroke(*rows)


def test_line_is_two_points():
    pts = extract(_rs(1, 0, 0, 20, 50, 180, 50, 0, 0, 0, 0))
    assert pts == [(20.0, 50.0), (180.0, 50.0)]
    assert arc_length(pts) == pytest.approx(160.0)


def test_poly_uses_all_three_points():
    pts = extract(_rs(3, 0, 0, 20, 20, 180, 20, 100, 120, 0, 0))
    assert pts == [(20.0, 20.0), (180.0, 20.0), (100.0, 120.0)]


def test_vcurve_uses_all_four_points():
    pts = extract(_rs(7, 0, 0, 10, 10, 20, 20, 30, 30, 40, 40))
    assert pts == [(10.0, 10.0), (20.0, 20.0), (30.0, 30.0), (40.0, 40.0)]


def test_quad_is_a_true_curve_not_the_control_polygon():
    # 寸's dot: (53,88) via(77,105) (84,129). The curve at t=0.5 is the de
    # Casteljau midpoint (0.25*53+0.5*77+0.25*84, 0.25*88+0.5*105+0.25*129)
    # = (72.75, 106.75); the control polygon's middle vertex is (77,105).
    pts = extract(_rs(2, 7, 8, 53, 88, 77, 105, 84, 129, 0, 0))
    assert pts[0] == (53.0, 88.0) and pts[-1] == (84.0, 129.0)
    assert len(pts) > 3, "a true curve needs more than the two chords"
    assert (77.0, 105.0) not in pts, "the control point is not on the curve"
    mids = [p for p in pts if math.isclose(p[0], 72.75, abs_tol=1e-6)]
    assert mids and math.isclose(mids[0][1], 106.75, abs_tol=1e-6)


def test_cubic_is_a_true_curve():
    # symmetric cubic: (20,100) c1(60,20) c2(140,180) (180,100); at t=0.5 the
    # point is the average of the 8 de Casteljau weights → (100, 100)
    pts = extract(_rs(6, 0, 0, 20, 100, 60, 20, 140, 180, 180, 100))
    assert pts[0] == (20.0, 100.0) and pts[-1] == (180.0, 100.0)
    assert any(math.isclose(x, 100.0, abs_tol=1e-6) and math.isclose(y, 100.0, abs_tol=1e-6)
               for x, y in pts)


def test_no_segment_types_are_empty():
    for a1 in (0, 8, 9):
        assert extract(_rs(a1, 0, 0, 0, 0, 100, 0, 0, 0, 0, 0)) == []


def test_a1_option_bit_falls_back_to_a_plain_line():
    # a1_opt != 0 → get_control_segments treats it as type 1 (x1x2 only)
    pts = extract(_rs(101, 0, 0, 0, 0, 100, 0, 50, 50, 0, 0))
    assert pts == [(0.0, 0.0), (100.0, 0.0)]


def test_nonfinite_input_does_not_hang():
    pts = extract(_rs(2, 7, 8, float("nan"), 0, 50, 50, 100, 0, 0, 0))
    assert len(pts) == 3, "non-finite input returns the raw control polygon"
    assert math.isnan(pts[0][0])


def test_collinear_curve_collapses_to_one_segment():
    # control point exactly on the chord → flatness test stops immediately
    pts = extract(_rs(2, 0, 0, 0, 0, 50, 0, 100, 0, 0, 0))
    assert len(pts) == 2


def test_flatten_tol_is_the_documented_value():
    assert FLATTEN_TOL == 0.25
