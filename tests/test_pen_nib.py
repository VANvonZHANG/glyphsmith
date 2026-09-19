# tests/test_pen_nib.py
import math

import pytest

from glyphsmith.pen.nib import ARC_TOL, PenPlan, _arc_points, body_contour, shoelace


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


def test_joins_are_indexed_per_interior_vertex():
    # A 4-point centerline has 2 interior vertices; entry i of `joins` belongs to
    # vertex i+1. The unimplemented-join guard makes the mapping observable: with
    # the off-by-one, the single entry landed on no vertex at all and nothing raised.
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (200.0, 100.0)]
    with pytest.raises(NotImplementedError):
        body_contour(plan(pts, width=10.0, joins=["miter"]))
    with pytest.raises(NotImplementedError):
        body_contour(plan(pts, width=10.0, joins=["bevel", "miter"]))
    # a fully implemented join list stays silent and yields a closed CCW contour
    c = body_contour(plan(pts, width=10.0, joins=["bevel", "bevel"]))
    assert shoelace(c) > 0.0
    assert c[0] != c[-1]


def test_unknown_cap_styles_raise():
    # T4 implements the whole cap vocabulary (butt/square/round); anything else
    # is invalid rather than merely unimplemented, and must not silently degrade
    # to a butt cap.
    for style in ("wedge", "squarish", "BUTT", ""):
        with pytest.raises(ValueError):
            body_contour(plan([(0.0, 0.0), (100.0, 0.0)], cap_head=style))
        with pytest.raises(ValueError):
            body_contour(plan([(0.0, 0.0), (100.0, 0.0)], cap_tail=style))


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


def test_square_cap_adds_a_square():
    c = body_contour(plan([(20.0, 50.0), (180.0, 50.0)], width=10.0,
                          cap_head="square", cap_tail="square"))
    assert shoelace(c) == pytest.approx(1700.0)      # 1600 + w^2


def test_cap_styles_are_per_end():
    head_only = body_contour(plan([(20.0, 50.0), (180.0, 50.0)], width=10.0,
                                  cap_head="square", cap_tail="butt"))
    assert shoelace(head_only) == pytest.approx(1650.0)   # 1600 + w^2/2
    tail_only = body_contour(plan([(20.0, 50.0), (180.0, 50.0)], width=10.0,
                                  cap_head="butt", cap_tail="square"))
    assert shoelace(tail_only) == pytest.approx(1650.0)


def test_round_cap_vertices_lie_on_the_circle():
    # The flattened semicircle is inscribed, so its area is strictly below the
    # true L*w + pi*(w/2)^2 = 1678.5398. What must hold exactly is that every cap
    # vertex is at distance r from the end point — that is what makes it round.
    c = body_contour(plan([(20.0, 50.0), (180.0, 50.0)], width=10.0,
                          cap_head="round", cap_tail="round"))
    a = shoelace(c)
    assert 1670.0 <= a <= 1600.0 + math.pi * 25.0 + 1e-6
    for x, y in c:
        if x < 20.0:                     # the head cap's points
            assert math.hypot(x - 20.0, y - 50.0) == pytest.approx(5.0)


def test_round_cap_single_semicircle_area():
    c = body_contour(plan([(20.0, 50.0), (180.0, 50.0)], width=10.0,
                          cap_head="round", cap_tail="butt"))
    a = shoelace(c)
    assert 1600.0 + 36.0 <= a <= 1600.0 + math.pi * 12.5 + 1e-6


def test_arc_points_excludes_endpoints_and_respects_the_through_direction():
    p_from, p_to = (0.0, -5.0), (5.0, 0.0)          # quarter arc around origin
    pts = _arc_points((0.0, 0.0), 5.0, p_from, p_to, (3.54, -3.54))
    assert pts and all(math.hypot(x, y) == pytest.approx(5.0) for x, y in pts)
    assert all(y < 0.0 and x > 0.0 for x, y in pts), "must stay in the quarter"
    # going the other way round also works when `through` says so
    pts2 = _arc_points((0.0, 0.0), 5.0, p_from, p_to, (-3.54, 3.54))
    assert pts2 and all(math.hypot(x, y) == pytest.approx(5.0) for x, y in pts2)


def test_round_cap_arc_is_finer_than_the_tolerance():
    # sagitta of each chord must respect ARC_TOL, i.e. r*(1-cos(step/2)) <= tol
    pts = _arc_points((0.0, 0.0), 20.0, (0.0, -20.0), (0.0, 20.0), (20.0, 0.0))
    angs = sorted(math.atan2(y, x) for x, y in pts)
    steps = [angs[i + 1] - angs[i] for i in range(len(angs) - 1)]
    assert steps and max(steps) <= 2 * math.acos(1 - ARC_TOL / 20.0) + 1e-9
