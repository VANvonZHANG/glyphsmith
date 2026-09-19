# src/glyphsmith/pen/graph.py
"""The relational graph (spec §3.2): nodes are strokes, edges are relations.

ARG-style (attributed relational graph): a node carries the stroke's attributes
(type, orientation band, GSF head/tail words, length, bbox, centerline), an edge
carries a topological relation plus the distance that made it. The graph is the
first agent-queryable intermediate product — it is pure data and serialises.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from glyphsmith.legacy_kurgm.geom2d import is_cross
from glyphsmith.pen.centerline import arc_length, classify_orientation, extract

TYPE_NAMES = {1: "line", 2: "quad", 3: "poly", 4: "bend", 6: "cubic", 7: "vcurve"}
HEAD_NAMES = {0: "flat", 2: "join-h", 7: "tip", 12: "corner-ul", 22: "corner-ur",
              32: "join-v"}
TAIL_NAMES = {0: "flat", 2: "join-h", 4: "hook", 7: "tip", 13: "heel-ll",
              23: "heel-lr", 24: "cap-t", 32: "join-v", 313: "heel-ll-old",
              413: "heel-ll-new"}


@dataclass(frozen=True)
class Node:
    id: int
    a1_100: int
    a1_opt: int
    a3_opt: int                       # floor(a3/100); see the tail lookup in build()
    type: object                     # word, or the raw int when out of table
    orientation: str
    head: object                     # word, or the raw int when out of table
    tail: object
    length: float
    bbox: tuple[float, float, float, float]
    centerline: tuple[tuple[float, float], ...]
    pure_geometry: bool


@dataclass(frozen=True)
class Edge:
    kind: str                        # meets | crosses | tee | parallel
    a_id: int
    a_end: str                       # head | tail | mid
    b_id: int
    b_end: str
    distance: float


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _point_seg_distance(p, a, b):
    """Distance from p to segment ab, plus the projection parameter t."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n2 = dx * dx + dy * dy
    if n2 == 0.0:
        return math.hypot(p[0] - a[0], p[1] - a[1]), 0.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n2
    tc = min(1.0, max(0.0, t))
    return math.hypot(p[0] - (a[0] + tc * dx), p[1] - (a[1] + tc * dy)), t


def _end_point(node, end):
    return node.centerline[0] if end == "head" else node.centerline[-1]


class StrokeGraph:
    def __init__(self, nodes, edges):
        self.nodes = list(nodes)
        self.edges = list(edges)
        self._by_id = {n.id: n for n in self.nodes}

    def node(self, node_id):
        return self._by_id[node_id]

    def to_dict(self) -> dict:
        return {
            "nodes": [{"id": n.id, "type": n.type, "orientation": n.orientation,
                       "head": n.head, "tail": n.tail, "a3_opt": n.a3_opt,
                       "length": round(n.length, 4),
                       "bbox": n.bbox, "pure_geometry": n.pure_geometry,
                       "centerline": [list(p) for p in n.centerline]} for n in self.nodes],
            "edges": [{"kind": e.kind, "a_id": e.a_id, "a_end": e.a_end,
                       "b_id": e.b_id, "b_end": e.b_end,
                       "distance": round(e.distance, 4)} for e in self.edges],
        }

    def nearest(self, subject_id, at="tail", want=None, side=None):
        """Closest other stroke matching `want` on the given `side` of the
        subject's `at` end. Returns (node, distance, end_of_that_node) or None.

        This is the metric query the hook-length rule needs (spec §4.2.4):
        `side` is judged from the candidate's bbox relative to the anchor, so a
        vertical whose bbox lies entirely left of the anchor counts as "left".
        """
        subject = self._by_id[subject_id]
        anchor = _end_point(subject, at)
        best = None
        for other in self.nodes:
            if other.id == subject_id:
                continue
            if want is not None and other.orientation != want:
                continue
            if side is not None and not _on_side(other.bbox, anchor, side):
                continue
            for end in ("head", "tail", "mid"):
                pts = ([other.centerline[0]] if end == "head" else
                       [other.centerline[-1]] if end == "tail" else [])
                if end == "mid":
                    d = min(_point_seg_distance(anchor, other.centerline[i],
                                                other.centerline[i + 1])[0]
                            for i in range(len(other.centerline) - 1))
                else:
                    d = math.hypot(pts[0][0] - anchor[0], pts[0][1] - anchor[1])
                if best is None or d < best[1]:
                    best = (other, d, end)
        return best


def _on_side(bbox, anchor, side) -> bool:
    x0, y0, x1, y1 = bbox
    ax, ay = anchor
    if side == "left":
        return x1 <= ax
    if side == "right":
        return x0 >= ax
    if side == "above":
        return y1 <= ay
    if side == "below":
        return y0 >= ay
    return True


def build(strokes, *, meets_tol=1.0, parallel_tol=12.0) -> StrokeGraph:
    """Build the graph from expanded strokes (TransformOp items are filtered by
    the caller — they are not strokes, they are outline-level transforms)."""
    nodes = []
    for i, st in enumerate(strokes):
        pts = extract(st)
        a1 = st.a1_100 if st.a1_opt == 0 else 1
        # RStroke splits a3 into a3_opt = floor(a3/100) and a3_100 = a3 mod 100,
        # so the original code is a3_opt * 100 + a3_100. TAIL_NAMES holds 313 and
        # 413 ("heel-ll-old"/"heel-ll-new") under that reconstruction only —
        # keyed on a3_100 alone they are unreachable, and the two codes then
        # silently collapse to "heel-ll". Reconstruct first, and fall back to the
        # remainder lookup when the reconstruction names nothing, so an odd
        # negative or out-of-table code keeps today's raw-int naming.
        raw_tail = st.a3_opt * 100 + st.a3_100
        tail = TAIL_NAMES.get(raw_tail, TAIL_NAMES.get(st.a3_100, st.a3_100))
        # The head needs no such reconstruction: every HEAD_NAMES key (0, 2, 7,
        # 12, 22, 32) is < 100, so no a2_opt * 100 + a2_100 can ever name one.
        nodes.append(Node(
            id=i, a1_100=st.a1_100, a1_opt=st.a1_opt, a3_opt=st.a3_opt,
            type=TYPE_NAMES.get(a1, a1),
            orientation=classify_orientation(pts),
            head=HEAD_NAMES.get(st.a2_100, st.a2_100),
            tail=tail,
            length=arc_length(pts), bbox=_bbox(pts), centerline=tuple(pts),
            pure_geometry=st.a1_opt != 0))
    edges = []
    for a in nodes:
        for b in nodes:
            if b.id <= a.id:
                continue
            edges.extend(_pair_edges(a, b, meets_tol, parallel_tol))
    return StrokeGraph(nodes, edges)


def _pair_edges(a: Node, b: Node, meets_tol: float, parallel_tol: float) -> list:
    """All relations between one unordered pair.

    Junction first, crossing second: legacy_kurgm.geom2d.is_cross uses `<= 0`,
    so two segments that merely *touch* at an endpoint count as crossing. A
    T-junction would therefore be reported twice (as `tee` and as `crosses`) —
    so once the pair has any endpoint junction, the crossing test is skipped.
    """
    out = []
    # meets: endpoint-to-endpoint
    for ea in ("head", "tail"):
        pa = _end_point(a, ea)
        for eb in ("head", "tail"):
            pb = _end_point(b, eb)
            d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
            if d <= meets_tol:
                out.append(Edge("meets", a.id, ea, b.id, eb, d))
    # tee: one endpoint lands strictly inside the other
    for ea in ("head", "tail"):
        pa = _end_point(a, ea)
        d, _t = _min_over_segments(pa, b)
        if d <= meets_tol and _strictly_inside(pa, b, meets_tol):
            out.append(Edge("tee", a.id, ea, b.id, "mid", d))
    for eb in ("head", "tail"):
        pb = _end_point(b, eb)
        d, _t = _min_over_segments(pb, a)
        if d <= meets_tol and _strictly_inside(pb, a, meets_tol):
            out.append(Edge("tee", b.id, eb, a.id, "mid", d))
    # crosses: a genuine transversal crossing of two interiors
    if not out:                                     # no junction on this pair
        for i in range(len(a.centerline) - 1):
            hit = False
            for j in range(len(b.centerline) - 1):
                if is_cross(a.centerline[i][0], a.centerline[i][1],
                            a.centerline[i + 1][0], a.centerline[i + 1][1],
                            b.centerline[j][0], b.centerline[j][1],
                            b.centerline[j + 1][0], b.centerline[j + 1][1]):
                    out.append(Edge("crosses", a.id, "mid", b.id, "mid", 0.0))
                    hit = True
                    break
            if hit:
                break
    # parallel: same band, close by, not already a crossing of the same pair
    if a.orientation == b.orientation:
        d = min(_point_seg_distance(a.centerline[i], b.centerline[j],
                                    b.centerline[j + 1])[0]
                for i in range(len(a.centerline))
                for j in range(len(b.centerline) - 1))
        if d <= parallel_tol:
            out.append(Edge("parallel", a.id, "mid", b.id, "mid", d))
    return out


def _min_over_segments(p, node):
    best = (math.inf, 0.0)
    for i in range(len(node.centerline) - 1):
        d, t = _point_seg_distance(p, node.centerline[i], node.centerline[i + 1])
        if d < best[0]:
            best = (d, t)
    return best


def _strictly_inside(p, node, meets_tol: float) -> bool:
    """True when p falls on node's interior, away from node's own ends (landing
    on a first/last point would be a `meets`, not a `tee`).

    Two shapes count. First, a node's *interior vertex* — a turn point of a
    poly/bend/vcurve, i.e. centerline[1:-1]; without this, a junction onto the
    corner of 力/刀/乃 matched no segment interior (t is 0.0 or 1.0 there), no
    junction was recorded, and is_cross() then reported the touch as a `crosses`.
    Second, a projection into a single segment's interior, away from both of its
    ends."""
    for v in node.centerline[1:-1]:
        if math.hypot(p[0] - v[0], p[1] - v[1]) <= meets_tol:
            return True
    for i in range(len(node.centerline) - 1):
        a, b = node.centerline[i], node.centerline[i + 1]
        d, t = _point_seg_distance(p, a, b)
        if d > meets_tol or not 0.0 < t < 1.0:
            continue
        q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        if math.hypot(p[0] - q[0], p[1] - q[1]) > meets_tol:
            continue
        if math.hypot(p[0] - a[0], p[1] - a[1]) <= meets_tol:
            continue
        if math.hypot(p[0] - b[0], p[1] - b[1]) <= meets_tol:
            continue
        return True
    return False
