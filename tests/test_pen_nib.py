# tests/test_pen_nib.py
import math

import pytest

from glyphsmith.pen.nib import PenPlan, body_contour, shoelace


def plan(pts, width=10.0, **kw):
    n = len(pts)
    return PenPlan(centerline=list(pts), widths=[width] * n, **kw)


def test_single_segment_butt_is_a_rectangle():
    # (20,50)->(180,50), full width 10 → a 160 x 10 rectangle
    c = body_contour(plan([(20.0, 50.0), (180.0, 50.0)]))
    assert len(c) == 4
    assert shoelace(c) == pytest.approx(1600.0)


def test_contour_is_closed_ccw_without_repeating_the_first_point():
    c = body_contour(plan([(20.0, 50.0), (180.0, 50.0)]))
    assert c[0] != c[-1], "the closing edge is implicit"
    assert shoelace(c) > 0, "CCW: positive signed area"


def test_area_scales_with_width_and_length():
    for w in (4.0, 10.0, 23.5):
        c = body_contour(plan([(0.0, 0.0), (140.0, 0.0)], width=w))
        assert shoelace(c) == pytest.approx(140.0 * w)


def test_vertical_and_diagonal_keep_their_area():
    c = body_contour(plan([(50.0, 20.0), (50.0, 120.0)], width=8.0))
    assert shoelace(c) == pytest.approx(800.0)
    # a 3-4-5 diagonal of length 100
    c = body_contour(plan([(0.0, 0.0), (60.0, 80.0)], width=6.0))
    assert shoelace(c) == pytest.approx(600.0)


def test_two_segments_bevel_join_area():
    # 90-degree bend, equal width, bevel join. Two 100x10 rectangles, overlap
    # 10x10, plus the outer bevel triangle of area w^2/8 = 12.5:
    #   1000 + 1000 - 100 + 12.5 = 1987.5
    # This is THE test that catches a missing concave-corner trim: without it
    # the inner corner self-intersects and the shoelace area is 2000 — which is
    # exactly the miter answer, so a miter-only suite would not notice.
    c = body_contour(plan([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], width=10.0))
    assert shoelace(c) == pytest.approx(1987.5)
    assert len(c) == 7, "outer bevel keeps both points; inner corner trims to 1"


def test_concave_corner_is_trimmed_to_the_offset_intersection():
    # the inner offset vertex must be exactly (95,5): the crossing of the two
    # offset lines, not either segment's own offset endpoint
    c = body_contour(plan([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], width=10.0))
    assert (95.0, 5.0) in c
    assert (100.0, 5.0) not in c, "the un-trimmed endpoint must be gone"
    assert (95.0, 0.0) not in c


def test_collinear_join_adds_nothing():
    # The mid vertex stays in the output (a collinear vertex is harmless under
    # nonzero fill and does not change the shoelace area) — what must not happen
    # is a duplicated point at the join.
    c = body_contour(plan([(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)], width=10.0))
    assert shoelace(c) == pytest.approx(1000.0)
    assert len(c) == 6


def test_no_duplicate_consecutive_points():
    # duplicated vertices are silent geometry bugs: they break the arc/join maths
    # downstream and inflate any vertex-count assertion
    for pts in ([(0.0, 0.0), (100.0, 0.0)],
                [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)],
                [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]):
        c = body_contour(plan(pts, width=10.0))
        n = len(c)
        for i in range(n):
            assert c[i] != c[(i + 1) % n], f"duplicate point at {i} in {pts}"
