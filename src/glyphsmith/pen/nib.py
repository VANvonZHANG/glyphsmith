# src/glyphsmith/pen/nib.py
"""The pen model: a stroke plan -> filled outline.

Weak correctness (spec D5): one closed contour per stroke body, decorations as
separate stacked contours, everything emitted CCW. Curvature radius below the
half-width is *detected* and degrades that stroke to per-segment quads — the
evolute is explicitly out of scope.

Geometry vocabulary follows Levien & Uguray 2024: parallel curve + join
(bevel/miter/round) + cap (butt/square/round).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

ARC_TOL = 0.25          # arc flattening tolerance, KAGE units


@dataclass
class PenPlan:
    """The minimum nib needs (T10 replaces this with style.StrokePlan)."""
    centerline: list[tuple[float, float]]
    widths: list[float]                      # full width per vertex
    cap_head: str = "butt"
    cap_tail: str = "butt"
    joins: list[str] = field(default_factory=list)      # per interior vertex
    miter_limit: float = 3.0


def shoelace(pts) -> float:
    """Signed area of the closed polygon through pts; positive == CCW."""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def left_normal(d) -> tuple[float, float]:
    """Unit normal 90 degrees from d (y-down: (dx,dy) -> (-dy,dx))."""
    n = math.hypot(d[0], d[1])
    return (0.0, 0.0) if n == 0.0 else (-d[1] / n, d[0] / n)


def _norm(d):
    n = math.hypot(d[0], d[1])
    return (0.0, 0.0) if n == 0.0 else (d[0] / n, d[1] / n)


def segment_dirs(pts):
    """Unit direction per segment (NOT per vertex: the vertex tangents of a bent
    stroke would tilt the join maths — caps use the first/last segment instead)."""
    return [_norm((pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
            for i in range(len(pts) - 1)]


def _close(a, b, eps=1e-9) -> bool:
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def _cross(a, b) -> float:
    """2D cross product; its sign is the turn direction (y-down coordinates)."""
    return a[0] * b[1] - a[1] * b[0]


def _line_intersection(p, d, q, e):
    """Intersection of {p + s*d} and {q + u*e}; None when parallel."""
    den = _cross(d, e)
    if abs(den) < 1e-12:
        return None
    s = _cross((q[0] - p[0], q[1] - p[1]), e) / den
    return (p[0] + s * d[0], p[1] + s * d[1])


def _join_replace(prev, nxt, vertex, d_prev, d_next, half, kind, miter_limit, sign):
    """Replace the offset pair (prev, nxt) around one interior vertex.

    Concave (inner) corners are always trimmed to the offset-line intersection:
    without that the two offset segments overlap, the contour self-intersects,
    and the shoelace area overcounts the covered region (measured: a 90-degree
    bend gives 2000 instead of the correct 1987.5 — and 2000 happens to be the
    miter answer, so only a bevel/round test catches it).

    Convex (outer) corners follow the join style. T5 adds miter and round.
    """
    cross = _cross(d_prev, d_next)
    if abs(cross) < 1e-12:                      # collinear: the pair coincides
        return [nxt] if _close(prev, nxt) else [prev, nxt]
    if sign * cross > 0.0:                      # concave side: trim
        x = _line_intersection(prev, d_prev, nxt, d_next)
        if x is not None:
            return [x]
    return [prev, nxt]                          # bevel


def walk_side(pts, dirs, half, sign, joins, miter_limit):
    """One side's offset polyline, head end to tail end, joins applied."""
    n = len(pts)
    a_off, b_off = [], []
    for i in range(n - 1):
        mx, my = left_normal(dirs[i])
        mx, my = sign * mx, sign * my
        a_off.append((pts[i][0] + mx * half[i], pts[i][1] + my * half[i]))
        b_off.append((pts[i + 1][0] + mx * half[i + 1], pts[i + 1][1] + my * half[i + 1]))
    out = [a_off[0], b_off[0]]
    for j in range(1, n - 1):
        prev = out.pop()                    # == b_off[j-1], not yet committed
        out += _join_replace(prev, a_off[j], pts[j], dirs[j - 1], dirs[j],
                             half[j], joins[j], miter_limit, sign)
        out.append(b_off[j])
    return out


def _cap_points(p_end, out_dir, half, style, start, stop):
    """Cap interior points walking from `start` to `stop` (both excluded)."""
    return []                   # T4 adds square/round


def body_contour(plan: PenPlan) -> list[tuple[float, float]]:
    """The stroke body as one closed CCW contour (spec §4.3.2)."""
    pts = plan.centerline
    half = [w / 2.0 for w in plan.widths]
    dirs = segment_dirs(pts)
    joins = list(plan.joins) + [""] * max(0, len(pts) - 1 - len(plan.joins))
    right = walk_side(pts, dirs, half, -1.0, joins, plan.miter_limit)
    left = walk_side(pts, dirs, half, +1.0, joins, plan.miter_limit)
    head = _cap_points(pts[0], dirs[0], half[0], plan.cap_head, right[-1], left[0])
    tail = _cap_points(pts[-1], dirs[-1], half[-1], plan.cap_tail, left[-1], right[0])
    contour = list(reversed(right)) + head + left + tail
    return contour if shoelace(contour) > 0 else list(reversed(contour))
