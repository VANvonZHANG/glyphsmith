# tests/test_pen_equivalence.py
"""Spec §6 layer 2: the pen body against pen-minimal, the internal oracle.

pen-minimal is the v1 preview backend and the pen work's only independently
verified drawing routine (uniform width, butt caps, no join handling, no
decorations, no endings). The probe style (`pen-minimal-probe`) reproduces
exactly what it draws, so on a restricted subset the v2 body must cover the
same region — an independent check on the new geometry, since both engines
share only the expansion layer.

Coverage equality is judged as IoU > 0.99 plus a mask-count difference of at
most 1%, NOT exact pixel equality: the two engines genuinely differ at corners
(pen-minimal stacks one quad per segment, so consecutive quads overlap; the pen
body trims the concave corner to the offset intersection and cuts the convex
one with the join style).
"""
import numpy as np
import pytest
from gsf.kage2 import parse_kage2

from glyphsmith.compare import rasterize
from glyphsmith.legacy_kurgm.expansion import expand
from glyphsmith.outline import Outline
from glyphsmith.pen.backend import expand_to_graph
from glyphsmith.pen.nib import stroke
from glyphsmith.pen_minimal import WIDTH as W          # the width the probe must copy
from glyphsmith.protocol import RenderOptions, get_backend

# ── the restricted subset both conditions of the plan's correction 1 ────────
#
#   (a) no TransformOp in the expansion: a TransformOp acts on the outline
#       accumulated so far, in stream order (backend.render_stream), while
#       pen-minimal drops it entirely — the two engines would differ on any
#       glyph that carries one, mid-glyph or not;
#   (b) polyline stroke types only, `line`/`poly`/`bend`/`vcurve`: `quad` and
#       `cubic` are excluded because the pen centerline follows the true curve
#       while pen-minimal walks the control polygon.
#
# `_subset_violation` is the executable form of that filter, the samples below
# are what it accepts, and the comparison test re-checks the filter rather than
# trusting the list. A sample that leaves the subset is reported, never quietly
# dropped.
_CURVE_TYPES = {2: "quad", 6: "cubic"}


class R:
    """The slice of ResolveResult the expansion and the backends read."""

    def __init__(self, g):
        self.name, self.glyph, self.parts, self.warnings = g.name, g, {g.name: g}, []


def _subset_violation(rows) -> str | None:
    """Why `rows` is outside the restricted subset, or None when it is inside.

    The reason is returned as a name, not a bool, so a caller that skips a
    sample has to say what it skipped.
    """
    g = parse_kage2(rows, "t")
    items = expand(g, {g.name: g}, [])
    for it in items:
        if isinstance(it, tuple):                 # TransformOp
            return "TransformOp"
    for it in items:
        a1 = it.a1_100 if it.a1_opt == 0 else 1   # centerline.extract's dispatch
        if a1 in _CURVE_TYPES:
            return _CURVE_TYPES[a1]
    return None


def _pen_body(rows, name="t"):
    """The pen backend's *bodies only*, via the probe style."""
    g = parse_kage2(rows, name)
    _graph, plans, items, _w, _counts = expand_to_graph(R(g), "pen-minimal-probe")
    assert all(not isinstance(it, tuple) for it in items), "restricted subset"
    out_contours = []
    for pid in sorted(plans):
        out_contours.extend(c for c in stroke(plans[pid]).contours)
    return Outline.from_contours([list(c) for c in out_contours])


def _mask(o, size=512):
    return np.asarray(rasterize(o, size), dtype=bool)


POLYLINE_ONLY = [
    "1:0:0:20:50:180:50",                                   # line
    "1:12:13:40:40:40:160",                                 # line
    "3:0:0:20:20:180:20:100:120",                           # poly (bend)
    "4:0:0:20:20:180:20:100:120",                           # bend
    "7:0:0:10:10:20:20:30:30:40:40",                        # vcurve
    "1:0:0:20:50:180:50$1:0:0:100:17:100:185",              # cross
    "4:0:0:20:20:180:20:100:120$1:0:0:40:160:160:160",      # bend + line
]


@pytest.mark.parametrize("rows", POLYLINE_ONLY)
def test_pen_body_covers_the_same_region_as_pen_minimal(rows):
    # Criterion fixed by the controller before execution (2026-09-19): coverage
    # equality is judged as IoU > 0.99 plus a mask-count difference of at most 1%,
    # NOT exact pixel equality. The two engines genuinely differ at corners —
    # pen-minimal stacks one quad per segment (they overlap), the pen body trims
    # the concave corner to the offset intersection. If IoU > 0.99 cannot be met
    # on these inputs, STOP AND REPORT: that is exactly the deviation this layer
    # exists to surface. Do not relax the assertion to make it pass.
    assert _subset_violation(rows) is None, "sample outside the restricted subset"
    g = parse_kage2(rows, "t")
    mini = get_backend("pen-minimal").render(R(g), RenderOptions(backend="pen-minimal"))
    body = _pen_body(rows)
    ma, mb = _mask(body), _mask(mini)
    iou = (ma & mb).sum() / max(1, (ma | mb).sum())
    assert iou > 0.99, f"IoU {iou:.4f} — stop and report, do not relax"
    assert abs(ma.sum() - mb.sum()) <= 0.01 * max(ma.sum(), mb.sum())


def test_a_mid_glyph_transform_op_is_excluded_by_the_subset_filter():
    # The graph is built over all strokes, but a TransformOp acts on the outline
    # drawn so far (stream order) and pen-minimal drops it outright. Comparing
    # such a glyph would measure the transform difference, not the nib — so the
    # filter excludes it, and this pins that exclusion down instead of letting
    # the sample list hide it.
    rows = ("1:0:0:20:50:180:50"
            "$0:99:0:0:0:200:200:rot:0:0"          # mid-glyph TransformOp
            "$1:0:0:20:150:180:150")
    assert _subset_violation(rows) == "TransformOp"
    with pytest.raises(AssertionError, match="restricted subset"):
        _pen_body(rows)


@pytest.mark.parametrize("rows,violation", [
    ("2:0:0:20:20:180:20:100:120", "quad"),        # pen follows the true curve
    ("6:0:0:20:20:180:20:100:120", "cubic"),       # pen-minimal the control polygon
    ("1:0:0:20:50:180:50", None),                  # control: a line is accepted
])
def test_curve_strokes_are_excluded_by_the_subset_filter(rows, violation):
    assert _subset_violation(rows) == violation


def test_probe_style_is_uniform_and_decoration_free():
    from glyphsmith.pen.style import Style
    s = Style.load("pen-minimal-probe")
    assert {tuple(map(tuple, v)) for v in s.width_profile.values()} == \
        {((0.0, W), (1.0, W))}
    assert s.decorations == {} and s.rules == []
    assert s.endings_source == "style", \
        "the data's endings must be ignored: pen-minimal draws no endings at all"


def test_the_probe_is_exempt_from_the_ending_table():
    # endings_source: style ignores the data words, but the table still has to be
    # complete (T7's rule) — this test pins that reading down
    from glyphsmith.pen.style import ENDING_WORDS, Style
    assert set(Style.load("pen-minimal-probe").endings) == set(ENDING_WORDS)
