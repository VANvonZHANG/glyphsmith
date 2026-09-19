# tests/test_pen_nib.py
import math

import pytest

from glyphsmith.pen.nib import ARC_TOL, StrokePlan, _arc_points, body_contour, shoelace


def plan(pts, width=10.0, **kw):
    n = len(pts)
    return StrokePlan(centerline=list(pts), widths=[width] * n, **kw)


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
    # vertex i+1. The unknown-join guard makes the mapping observable: with the
    # off-by-one, the single entry landed on no vertex at all and nothing raised.
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (200.0, 100.0)]
    with pytest.raises(ValueError):
        body_contour(plan(pts, width=10.0, joins=["wedge"]))
    with pytest.raises(ValueError):
        body_contour(plan(pts, width=10.0, joins=["bevel", "wedge"]))
    # a fully valid join list stays silent and yields a closed CCW contour
    c = body_contour(plan(pts, width=10.0, joins=["bevel", "bevel"]))
    assert shoelace(c) > 0.0
    assert c[0] != c[-1]


def test_unknown_join_kinds_raise():
    # T5 implements the whole join vocabulary (bevel/miter/round, "" = default);
    # anything else is invalid rather than merely unimplemented, and must not
    # silently degrade to a bevel.
    for kind in ("wedge", "MITER", "rounds"):
        with pytest.raises(ValueError):
            body_contour(plan(BEND, width=10.0, joins=[kind]))


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


BEND = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]


def test_miter_join_area_is_exactly_sum_of_segments():
    # for a right angle with equal widths the miter join makes the area exactly
    # sum(L_i * w) — the corner square w^2/4 added, the overlap w^2/4 removed
    c = body_contour(plan(BEND, width=10.0, joins=["miter"]))
    assert shoelace(c) == pytest.approx(2000.0)
    assert (105.0, -5.0) in c, "the miter point is the outer offset intersection"
    assert (100.0, -5.0) not in c and (105.0, 0.0) not in c


def test_miter_falls_back_to_bevel_past_the_limit():
    c = body_contour(plan(BEND, width=10.0, joins=["miter"], miter_limit=1.0))
    # |X - vertex| = 5*sqrt(2) = 7.07 > 1.0 * 5 → bevel
    assert shoelace(c) == pytest.approx(1987.5)


def test_bevel_join_area():
    c = body_contour(plan(BEND, width=10.0, joins=["bevel"]))
    assert shoelace(c) == pytest.approx(1987.5)
    assert (100.0, -5.0) in c and (105.0, 0.0) in c


def test_round_join_arc_lies_on_the_vertex_circle():
    c = body_contour(plan(BEND, width=10.0, joins=["round"]))
    a = shoelace(c)
    # true area = union(1975) + quarter disc(pi*25/4) = 1994.6349; the inscribed
    # polygon under-counts by 0.5*r^2*(theta - k*sin(theta/k)) ≈ 0.885
    assert 1993.5 <= a <= 2000.0
    arc = [(x, y) for x, y in c if x > 100.0 and y < 0.0]
    assert arc, "the round join must bulge outside the corner"
    for x, y in arc:
        assert math.hypot(x - 100.0, y) == pytest.approx(5.0, abs=1e-9)


def test_concave_corner_stays_trimmed_for_every_join_style():
    for kind in ("miter", "bevel", "round"):
        c = body_contour(plan(BEND, width=10.0, joins=[kind]))
        assert (95.0, 5.0) in c, f"{kind}: the inner corner must still be trimmed"
        assert (100.0, 5.0) not in c and (95.0, 0.0) not in c


def test_join_style_applies_per_vertex():
    # two bends, different joins, and the areas are the sum of the two corners'
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (200.0, 100.0)]
    c = body_contour(plan(pts, width=10.0, joins=["miter", "bevel"]))
    assert shoelace(c) == pytest.approx(3000.0 - 12.5)


from glyphsmith.pen.nib import curvature_radius, quad_fallback, should_degrade


def test_curvature_radius_of_a_straight_run_is_none():
    assert curvature_radius([(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]) == [None]


def test_curvature_radius_of_a_quarter_circle():
    # three points on a radius-50 circle → R = 50
    pts = [(50.0, 0.0), (35.355339, 35.355339), (0.0, 50.0)]
    r = curvature_radius(pts)[0]
    assert r == pytest.approx(50.0, rel=1e-5)


def test_should_degrade_when_radius_is_below_half_width():
    pts = [(50.0, 0.0), (35.355339, 35.355339), (0.0, 50.0)]      # R = 50
    assert not should_degrade(plan(pts, width=10.0))              # half = 5 < 50
    assert should_degrade(plan(pts, width=120.0))                 # half = 60 > 50


def test_quad_fallback_covers_each_segment_and_keeps_the_area():
    p = plan(BEND, width=10.0)
    quads = quad_fallback(p)
    assert len(quads) == 2
    # each quad is a w x L rectangle; their union area is not additive (they
    # overlap) but each individual quad has the exact segment area
    assert shoelace(quads[0]) == pytest.approx(1000.0)
    assert shoelace(quads[1]) == pytest.approx(1000.0)


def test_degenerate_inputs_are_reported_not_raised():
    zero_len = plan([(5.0, 5.0), (5.0, 5.0)], width=10.0)
    assert should_degrade(zero_len)
    assert any("zero-length" in w for w in zero_len.warnings)

    nan = plan([(float("nan"), 0.0), (100.0, 0.0)], width=10.0)
    assert should_degrade(nan)
    assert any("non-finite" in w for w in nan.warnings)

    zero_w = plan([(0.0, 0.0), (100.0, 0.0)], width=0.0)
    assert should_degrade(zero_w)
    assert any("non-positive width" in w for w in zero_w.warnings)


def test_degraded_strokes_still_produce_something():
    # A degraded stroke must still draw (spec §4.3.4 wants a fallback, not a hole).
    # Input calibrated so the degradation REALLY fires: BEND's corner has
    # circumradius 100*100*141.42/(2*10000) = 70.71, so width 160 (half 80) is
    # above it while width 120 (half 60) is not — the earlier draft used 120 and
    # the assertion passed vacuously on its first disjunct.
    p = plan(BEND, width=160.0)
    assert should_degrade(p) is True
    quads = quad_fallback(p)
    assert len(quads) == 2, "the fallback tiles the stroke segment by segment"
    for q in quads:
        assert shoelace(q) == pytest.approx(100.0 * 160.0)
    p2 = plan([(5.0, 5.0), (5.0, 5.0)], width=10.0)
    assert quad_fallback(p2) == [], "a zero-length stroke has no quad to draw"


def test_a_width_count_mismatch_is_named_not_an_index_error():
    # One full width per centerline vertex is the nib's indexing contract: a
    # short list used to escape as an IndexError from deep inside the geometry,
    # and a long one was silently ignored (the stroke then drew its tail with
    # whichever width happened to sit at that index).
    with pytest.raises(ValueError) as e:
        StrokePlan(centerline=[(0.0, 0.0), (100.0, 0.0)], widths=[10.0])
    assert "1" in str(e.value) and "2" in str(e.value), \
        f"the message must name both lengths: {e.value}"
    with pytest.raises(ValueError) as e:
        StrokePlan(centerline=[(0.0, 0.0)], widths=[10.0, 10.0, 10.0])
    assert "3" in str(e.value) and "1" in str(e.value), \
        f"the message must name both lengths: {e.value}"
