# tests/test_pen_graph.py
import pytest

from glyphsmith.legacy_kurgm.rstroke import RStroke
from glyphsmith.pen.graph import build


def strokes(*rows):
    return [RStroke(*r) for r in rows]


def test_node_attributes_come_from_the_data():
    g = build(strokes((1, 0, 0, 14, 92, 186, 92, 0, 0, 0, 0)))
    n = g.nodes[0]
    assert n.type == "line" and n.orientation == "horizontal"
    assert (n.head, n.tail) == ("flat", "flat")
    assert n.length == pytest.approx(172.0)
    assert n.bbox == (14.0, 92.0, 186.0, 92.0)
    assert n.pure_geometry is False


def test_ten_glyph_has_a_crossing_not_a_meet():
    # 十 u5341-j: stroke 1 horizontal, stroke 2 vertical, crossing at (100,92)
    g = build(strokes((1, 0, 0, 14, 92, 186, 92, 0, 0, 0, 0),
                      (1, 0, 0, 100, 17, 100, 185, 0, 0, 0, 0)))
    kinds = {e.kind for e in g.edges}
    assert "crosses" in kinds
    assert "meets" not in kinds


def test_kou_glyph_corner_tails_meet():
    # 口-shaped skeleton: two horizontals and two verticals sharing endpoints
    g = build(strokes((1, 0, 0, 40, 40, 160, 40, 0, 0, 0, 0),
                      (1, 0, 0, 160, 40, 160, 160, 0, 0, 0, 0),
                      (1, 0, 0, 40, 160, 160, 160, 0, 0, 0, 0),
                      (1, 0, 0, 40, 40, 40, 160, 0, 0, 0, 0)))
    meets = [e for e in g.edges if e.kind == "meets"]
    assert len(meets) == 4, "four corners, each an endpoint-to-endpoint touch"
    assert all(e.distance == pytest.approx(0.0) for e in meets)


def test_tee_is_an_endpoint_on_another_strokes_interior():
    # 丁: a vertical whose head lands in the middle of a horizontal
    g = build(strokes((1, 0, 0, 40, 60, 160, 60, 0, 0, 0, 0),
                      (1, 0, 32, 100, 60, 100, 170, 0, 0, 0, 0)))
    tees = [e for e in g.edges if e.kind == "tee"]
    assert len(tees) == 1
    assert tees[0].b_end == "mid" and tees[0].a_end == "head"


def test_junctions_are_not_also_reported_as_crossings():
    # is_cross() counts endpoint touching as crossing (`<= 0` on both products),
    # so without the junction-first rule a T-junction and every 口 corner would
    # come out twice — once as a junction, once as a bogus crossing.
    tee_glyph = build(strokes((1, 0, 0, 40, 60, 160, 60, 0, 0, 0, 0),
                              (1, 0, 32, 100, 60, 100, 170, 0, 0, 0, 0)))
    assert not [e for e in tee_glyph.edges if e.kind == "crosses"]
    kou = build(strokes((1, 0, 0, 40, 40, 160, 40, 0, 0, 0, 0),
                        (1, 0, 0, 160, 40, 160, 160, 0, 0, 0, 0),
                        (1, 0, 0, 40, 160, 160, 160, 0, 0, 0, 0),
                        (1, 0, 0, 40, 40, 40, 160, 0, 0, 0, 0)))
    assert not [e for e in kou.edges if e.kind == "crosses"]


def test_parallel_needs_same_direction_and_proximity():
    near = build(strokes((1, 0, 0, 50, 40, 50, 160, 0, 0, 0, 0),
                         (1, 0, 0, 58, 40, 58, 160, 0, 0, 0, 0)))
    assert any(e.kind == "parallel" for e in near.edges)
    far = build(strokes((1, 0, 0, 50, 40, 50, 160, 0, 0, 0, 0),
                        (1, 0, 0, 90, 40, 90, 160, 0, 0, 0, 0)))
    assert not any(e.kind == "parallel" for e in far.edges)


def test_meets_tolerance_is_a_backend_parameter():
    a = (1, 0, 0, 40, 40, 160, 40, 0, 0, 0, 0)
    # second stroke's head sits 0.5 units away from the first stroke's head
    b = (1, 0, 0, 40.5, 40.0, 40.5, 160.0, 0, 0, 0, 0)
    assert any(e.kind == "meets" for e in build(strokes(a, b)).edges)
    assert not any(e.kind == "meets" for e in build(strokes(a, b), meets_tol=0.1).edges)


def test_pure_geometry_flag_tracks_the_a1_option_bits():
    g = build(strokes((101, 0, 0, 0, 0, 100, 0, 0, 0, 0, 0)))
    assert g.nodes[0].pure_geometry is True
    assert g.nodes[0].type == "line", "a1_opt != 0 is drawn as a plain line"


def test_transform_ops_are_not_nodes():
    # build() receives RStroke only; the caller filters TransformOp out (T14).
    g = build([])
    assert g.nodes == [] and g.edges == []


def test_to_dict_is_json_ready():
    import json
    g = build(strokes((1, 0, 0, 14, 92, 186, 92, 0, 0, 0, 0),
                      (1, 0, 0, 100, 17, 100, 185, 0, 0, 0, 0)))
    d = g.to_dict()
    assert set(d) == {"nodes", "edges"}
    assert d["nodes"][0]["orientation"] == "horizontal"
    assert d["edges"][0]["kind"] == "crosses"
    json.dumps(d)                        # must not raise on the tuple fields


# ── nearest(): the metric query the 钩长 rule consumes ──
def test_nearest_finds_the_closest_vertical_to_the_left():
    # 扌-like: a vertical at x=60, the hook stroke's tail at (104, 91)
    g = build(strokes((1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0),
                      (2, 0, 7, 18, 122, 63, 107, 104, 91, 0, 0)))
    hit = g.nearest(1, at="tail", want="vertical", side="left")
    assert hit is not None
    node, dist, end = hit
    assert node.id == 0
    assert dist == pytest.approx(104.0 - 60.0)
    assert end in ("head", "tail", "mid")


def test_nearest_returns_none_when_the_side_has_nothing():
    g = build(strokes((1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0),
                      (2, 0, 7, 18, 122, 63, 107, 104, 91, 0, 0)))
    assert g.nearest(1, at="tail", want="vertical", side="right") is None


def test_nearest_ignores_the_subject_itself():
    g = build(strokes((1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0)))
    assert g.nearest(0, at="tail", want="vertical", side="left") is None
