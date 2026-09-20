# tests/test_pen_decorations.py
import math

import pytest

from glyphsmith.pen.nib import decoration_contours, frame_at, shoelace, stroke
from glyphsmith.pen.style import Decoration, StrokePlan


def plan(pts, widths, decos=(), **kw):
    return StrokePlan(centerline=list(pts), widths=list(widths),
                      decorations=list(decos), **kw)


def test_frame_is_outward_at_both_ends():
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0])
    o_head, t_head, n_head, h_head = frame_at(p, "head")
    o_tail, t_tail, n_tail, h_tail = frame_at(p, "tail")
    assert o_head == (20.0, 50.0) and o_tail == (180.0, 50.0)
    assert t_head == (-1.0, 0.0) and t_tail == (1.0, 0.0), "outward, not forward"
    assert n_tail == (0.0, 1.0) and h_tail == 2.0


def test_wedge_vertices_match_the_measured_shape():
    # 1:0:0:20:50:180:50 with legacy mincho gives the triangle
    # (180,48) (156,50) (168,38) → local (0,-2) (-24,0) (-12,-12), w = 4
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("wedge", "tail", size=3.0)])
    c = decoration_contours(p)[0]
    assert {(round(x - 180.0, 6), round(y - 50.0, 6)) for x, y in c} == \
        {(0.0, -2.0), (-24.0, 0.0), (-12.0, -12.0)}


def test_wedge_area_grows_with_size():
    # The first vertex is the stroke end's corner (0, -w/2) at EVERY size — that
    # is what the legacy engine draws — so the triangle is not homothetic in
    # `size` and the area law carries a linear term: w^2 * (size^2 - size/4).
    # A "scales with size squared" assertion would require the corner to move
    # with `size`, which contradicts the measured vertices above.
    areas = []
    for size in (1.0, 2.0, 4.0):
        p = plan([(0.0, 0.0), (100.0, 0.0)], [8.0, 8.0],
                 [Decoration("wedge", "tail", size=size)])
        areas.append(shoelace(decoration_contours(p)[0]))
    assert areas == pytest.approx([64.0 * (s * s - s / 4.0)
                                   for s in (1.0, 2.0, 4.0)])   # 48, 224, 960
    assert areas[1] > areas[0] and areas[2] > areas[1], "bigger size, bigger wedge"


def test_zero_size_produces_no_contour():
    p = plan([(0.0, 0.0), (100.0, 0.0)], [8.0, 8.0],
             [Decoration("wedge", "tail", size=0.0)])
    assert decoration_contours(p) == []


def test_hook_points_along_the_left_normal():
    # a vertical stroke, hook at the tail → the tip must go left (like 寸)
    p = plan([(100.0, 20.0), (100.0, 180.0)], [12.0, 12.0],
             [Decoration("hook", "tail", length=2.5, width=1.0)])
    c = decoration_contours(p)[0]
    tip = min(c, key=lambda q: q[0])
    assert tip[0] == pytest.approx(100.0 - 2.5 * 12.0)
    assert tip[1] == pytest.approx(180.0 - 0.17 * 2.5 * 12.0)


def test_hook_base_follows_the_width_multiple():
    p1 = plan([(0.0, 0.0), (0.0, 100.0)], [10.0, 10.0],
              [Decoration("hook", "tail", length=2.0, width=1.0)])
    p2 = plan([(0.0, 0.0), (0.0, 100.0)], [10.0, 10.0],
              [Decoration("hook", "tail", length=2.0, width=0.5)])
    # the base is the stroke's END FACE: both its corners sit at the end's y,
    # +/- w/2*k off the centreline. (Filtering on x == 0 selects nothing here:
    # the tip is the only point off the end face, and it is 2*length*w away.)
    b1 = {(x, y) for x, y in decoration_contours(p1)[0]
          if y == pytest.approx(100.0)}
    b2 = {(x, y) for x, y in decoration_contours(p2)[0]
          if y == pytest.approx(100.0)}
    assert len(b1) == 2 and len(b2) == 2
    assert shoelace(decoration_contours(p2)[0]) < shoelace(decoration_contours(p1)[0])


def test_stroke_returns_body_plus_decorations_all_ccw():
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("wedge", "tail", size=3.0)])
    o = stroke(p)
    assert len(o.contours) == 2
    # Outline contours are (x, y, off) triples; shoelace takes plain points
    assert all(shoelace([(x, y) for x, y, _ in c]) > 0 for c in o.contours), \
        "every contour is CCW"


def test_stroke_of_a_degenerate_plan_is_empty_but_warns():
    p = plan([(5.0, 5.0), (5.0, 5.0)], [8.0, 8.0])
    o = stroke(p)
    assert o.contours == []
    assert any("zero-length" in w for w in p.warnings)


def test_unknown_kind_draws_nothing_and_warns_once():
    # The style validator would reject "sparkle", but `decorations` is plain data
    # on a public entry point: the skip must be reported, not silent.
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("sparkle", "tail", size=3.0)])
    assert decoration_contours(p) == []
    assert p.warnings == ["decoration kind 'sparkle' ignored"]


def test_repeated_unknown_kind_warns_only_once():
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("sparkle", "tail", size=3.0)] * 5)
    assert decoration_contours(p) == []
    assert p.warnings == ["decoration kind 'sparkle' ignored"]


def test_stroke_keeps_the_body_when_a_decoration_is_unknown():
    # visible, not fatal: the odd decoration is skipped, the stroke still draws.
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("sparkle", "tail", size=3.0)])
    o = stroke(p)
    assert len(o.contours) == 1
    assert p.warnings == ["decoration kind 'sparkle' ignored"]


def test_unknown_end_draws_nothing_and_warns_once():
    # An end that is not "head"/"tail" must not be reinterpreted as the tail.
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("hook", "middle", length=2.0, width=1.0)])
    assert decoration_contours(p) == []
    assert p.warnings == ["decoration at 'middle' ignored"]


def test_unknown_kind_and_end_each_warn_once_across_repeats():
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("sparkle", "tail", size=1.0),
              Decoration("sparkle", "tail", size=1.0),
              Decoration("hook", "middle", length=1.0, width=1.0),
              Decoration("hook", "middle", length=1.0, width=1.0)])
    assert decoration_contours(p) == []
    assert p.warnings == ["decoration kind 'sparkle' ignored",
                          "decoration at 'middle' ignored"]


def test_known_decorations_do_not_warn():
    # "heel-ll" exercises the "-" suffix dispatch (heel shape, non-wedge args).
    p = plan([(20.0, 50.0), (180.0, 50.0)], [4.0, 4.0],
             [Decoration("wedge", "tail", size=3.0),
              Decoration("hook", "head", length=2.5, width=1.0),
              Decoration("heel-ll", "tail", length=2.0, width=1.0)])
    assert len(decoration_contours(p)) == 3
    assert p.warnings == []
