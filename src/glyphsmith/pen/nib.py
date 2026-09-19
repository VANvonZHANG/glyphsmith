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
class StrokePlan:
    """What the nib needs for one stroke (spec §3.3). Built by style.apply."""
    centerline: list[tuple[float, float]]
    widths: list[float]                      # full width per vertex
    cap_head: str = "butt"
    cap_tail: str = "butt"
    # One entry per interior vertex: len(centerline) - 2 entries, where entry i
    # applies to centerline vertex i + 1.
    joins: list[str] = field(default_factory=list)
    miter_limit: float = 3.0
    # Ornaments stacked on top of the body ([style.Decoration], spec §4.3.5).
    # The nib itself never reads them: the decoration geometry is T11's job.
    decorations: list = field(default_factory=list)
    # Why this stroke could not be stroked normally (spec §4.3.4); should_degrade
    # records its reasons here instead of dropping geometry silently.
    warnings: list[str] = field(default_factory=list)
    # The graph node this plan came from: `Style.apply_rules` walks graph.nodes
    # by plan, so the plan has to carry the id back to the relational layer.
    stroke_id: int = -1

    def __post_init__(self) -> None:
        # One full width per centerline vertex is the nib's indexing contract.
        # Too few entries surface as an opaque IndexError deep inside the
        # geometry; too many are silently ignored, so the stroke quietly draws
        # with the wrong width at its tail. Name both lengths instead.
        if len(self.widths) != len(self.centerline):
            raise ValueError(
                f"widths has {len(self.widths)} entries but centerline has "
                f"{len(self.centerline)} vertices: one full width per vertex "
                f"is required")


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
    without that the offset segments overlap, the contour self-intersects, and
    the shoelace area overcounts the covered region (measured: a 90-degree bend
    gives 2000 instead of the correct 1987.5 — and 2000 happens to be the miter
    answer, so only a bevel/round test catches it).

    Convex (outer) corners follow the join style. `miter_limit` is the CSS
    ratio |X - vertex| / half-width, i.e. 1/sin(theta/2).
    """
    if kind not in ("", "bevel", "miter", "round"):
        raise ValueError(
            f"unknown join kind {kind!r} (allowed: '', bevel, miter, round)")
    cross = _cross(d_prev, d_next)
    if abs(cross) < 1e-12:                      # collinear: the pair coincides
        return [nxt] if _close(prev, nxt) else [prev, nxt]
    x = _line_intersection(prev, d_prev, nxt, d_next)
    if x is None:
        return [prev, nxt]
    if sign * cross > 0.0:                      # concave side: trim
        return [x]
    if kind == "miter" and math.hypot(x[0] - vertex[0],
                                      x[1] - vertex[1]) <= miter_limit * half:
        return [x]
    if kind == "round":
        m0, m1 = left_normal(d_prev), left_normal(d_next)
        mx, my = m0[0] + m1[0], m0[1] + m1[1]
        n = math.hypot(mx, my)
        mx, my = (m0 if n == 0.0 else (mx / n, my / n))
        through = (vertex[0] + sign * mx * half, vertex[1] + sign * my * half)
        return [prev] + _arc_points(vertex, half, prev, nxt, through) + [nxt]
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
                             half[j], joins[j - 1], miter_limit, sign)
        out.append(b_off[j])
    return out


def _arc_points(center, r, p_from, p_to, through):
    """Flattened circular arc from p_from to p_to around `center`, in the sweep
    direction that passes through the direction of `through`. Both endpoints are
    excluded (the caller already has them).

    The chord count comes from the sagitta bound: a chord subtending `step`
    dips r*(1-cos(step/2)) below the arc, so requiring that to be <= ARC_TOL
    gives step = 2*acos(1 - ARC_TOL/r).
    """
    if r <= 0.0:
        return []
    a0 = math.atan2(p_from[1] - center[1], p_from[0] - center[0])
    a1 = math.atan2(p_to[1] - center[1], p_to[0] - center[0])
    at = math.atan2(through[1] - center[1], through[0] - center[0])
    two_pi = 2.0 * math.pi
    sweep = (a1 - a0) % two_pi
    if ((at - a0) % two_pi) > sweep:
        sweep -= two_pi                  # go the other way round
    if abs(sweep) < 1e-12:
        return []
    step = math.pi / 2.0 if ARC_TOL >= r else 2.0 * math.acos(1.0 - ARC_TOL / r)
    k = max(2, math.ceil(abs(sweep) / step))
    return [(center[0] + r * math.cos(a0 + sweep * i / k),
             center[1] + r * math.sin(a0 + sweep * i / k)) for i in range(1, k)]


def _cap_points(p_end, out_dir, half, style, start, stop):
    """Cap interior points walking from `start` to `stop` (both excluded).

    `out_dir` points away from the stroke: the head cap is called with -dirs[0]
    and the tail cap with +dirs[-1] (body_contour does that). `start` and `stop`
    are the cap's actual neighbours on the contour: the offset endpoints at that
    end of the stroke.
    """
    if style not in ("butt", "square", "round"):
        raise ValueError(
            f"unknown cap style {style!r} (allowed: butt, square, round)")
    if style == "butt" or half <= 0.0:
        return []
    if style == "square":
        return [(start[0] + out_dir[0] * half, start[1] + out_dir[1] * half),
                (stop[0] + out_dir[0] * half, stop[1] + out_dir[1] * half)]
    through = (p_end[0] + out_dir[0] * half, p_end[1] + out_dir[1] * half)
    return _arc_points(p_end, half, start, stop, through)


def body_contour(plan: StrokePlan) -> list[tuple[float, float]]:
    """The stroke body as one closed CCW contour (spec §4.3.2)."""
    pts = plan.centerline
    half = [w / 2.0 for w in plan.widths]
    dirs = segment_dirs(pts)
    joins = list(plan.joins) + [""] * max(0, len(pts) - 2 - len(plan.joins))
    right = walk_side(pts, dirs, half, -1.0, joins, plan.miter_limit)
    left = walk_side(pts, dirs, half, +1.0, joins, plan.miter_limit)
    # The contour reads reversed(right) + head + left + tail, so the head cap
    # bridges right[0] to left[0] and the tail cap bridges left[-1] to right[-1].
    head = _cap_points(pts[0], (-dirs[0][0], -dirs[0][1]), half[0],
                       plan.cap_head, right[0], left[0])
    tail = _cap_points(pts[-1], dirs[-1], half[-1],
                       plan.cap_tail, left[-1], right[-1])
    contour = list(reversed(right)) + head + left + tail
    return contour if shoelace(contour) > 0 else list(reversed(contour))


def curvature_radius(pts):
    """Local curvature radius at each interior vertex (circumradius of the
    triangle formed with its neighbours); None where the three points are
    collinear (infinite radius = no curvature).

    A radius below the local half-width is exactly the case where the offset
    curve meets the evolute — the trade-off spec §4.3.4 pins down as "detect
    and degrade", never "compute the evolute".
    """
    out = []
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        ab = math.hypot(b[0] - a[0], b[1] - a[1])
        bc = math.hypot(c[0] - b[0], c[1] - b[1])
        ca = math.hypot(c[0] - a[0], c[1] - a[1])
        area2 = abs(_cross((b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1])))
        if area2 <= 1e-12 or ab == 0.0 or bc == 0.0 or ca == 0.0:
            out.append(None)
        else:
            out.append(ab * bc * ca / (2.0 * area2))
    return out


def _degeneracy_reasons(plan: StrokePlan) -> list[str]:
    """Every reason this stroke cannot be stroked normally (spec §4.3.4)."""
    pts = plan.centerline
    reasons = []
    if len(pts) < 2:
        reasons.append("zero-length centerline")
        return reasons
    if not all(math.isfinite(v) for p in pts for v in p):
        reasons.append("non-finite centerline coordinate")
        return reasons
    if all(abs(p[0] - pts[0][0]) <= 1e-12 and abs(p[1] - pts[0][1]) <= 1e-12
           for p in pts):
        reasons.append("zero-length centerline")
        return reasons
    if not any(w > 0.0 for w in plan.widths):
        reasons.append("non-positive width profile")
        return reasons
    radii = curvature_radius(pts)
    for i, r in enumerate(radii):
        if r is not None and r < plan.widths[i + 1] / 2.0:
            reasons.append(f"degraded: curvature radius {r:.2f} < half-width "
                           f"{plan.widths[i + 1] / 2.0:.2f} at vertex {i + 1}")
            break
    return reasons


def _warn_once(plan: StrokePlan, msg: str) -> None:
    """Record `msg` in plan.warnings at most once — the dedupe idiom
    should_degrade established: a pathological plan repeating the same notice
    tells the caller nothing new."""
    if msg not in plan.warnings:
        plan.warnings.append(msg)


def should_degrade(plan: StrokePlan) -> bool:
    """True when the stroke cannot be stroked as a single contour; records why
    in plan.warnings (never raises — warnings are the contract)."""
    reasons = _degeneracy_reasons(plan)
    for r in reasons:
        _warn_once(plan, r)
    return bool(reasons)


def quad_fallback(plan: StrokePlan) -> list[list[tuple[float, float]]]:
    """Per-segment quads (pen-minimal's shape) for a stroke that must degrade.

    Returns [] for a zero-length or non-finite stroke: there is nothing to draw,
    and the caller has already been told why via plan.warnings.
    """
    pts = plan.centerline
    if len(pts) < 2 or not all(math.isfinite(v) for p in pts for v in p):
        return []
    quads = []
    for i in range(len(pts) - 1):
        d = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        n = math.hypot(d[0], d[1])
        if n == 0.0:
            continue
        mx, my = -d[1] / n * plan.widths[i] / 2.0, d[0] / n * plan.widths[i] / 2.0
        quad = [(pts[i][0] + mx, pts[i][1] + my), (pts[i + 1][0] + mx, pts[i + 1][1] + my),
                (pts[i + 1][0] - mx, pts[i + 1][1] - my), (pts[i][0] - mx, pts[i][1] - my)]
        quads.append(quad if shoelace(quad) > 0 else list(reversed(quad)))
    return quads


def frame_at(plan: StrokePlan, at: str):
    """Local frame at one end: origin = the end point, `tangent` points OUTWARD
    (away from the stroke), `normal` is its left normal, `half` the half-width.

    Decorations are defined once in this frame, so the same recipe works at
    either end and rotates/scales with the stroke (spec §4.3.5).

    `at` is "head" or "tail" (style.DECORATION_AT). The vocabulary check is the
    caller's: decoration_contours validates the end and reports an unknown one
    before it gets here, so the tail branch below is only ever the real tail.
    """
    pts = plan.centerline
    dirs = segment_dirs(pts)
    idx = 0 if at == "head" else len(pts) - 1
    origin = tuple(pts[idx])
    if at == "head":
        d = next((x for x in dirs if x != (0.0, 0.0)), (1.0, 0.0))
        tangent = (-d[0], -d[1])
    else:
        d = next((x for x in reversed(dirs) if x != (0.0, 0.0)), (1.0, 0.0))
        tangent = d
    normal = left_normal(tangent)
    return origin, tangent, normal, plan.widths[idx] / 2.0


def _off(origin, tangent, normal, x, y):
    return (origin[0] + tangent[0] * x + normal[0] * y,
            origin[1] + tangent[1] * x + normal[1] * y)


def _wedge(origin, tangent, normal, w, size):
    """The measured うろこ: base on the centreline 2*size*w back, apex size*w up
    (legacy's (0,-h) (-24,0) (-12,-12) at w=4, size=3)."""
    if size <= 0.0:
        return []
    return [_off(origin, tangent, normal, 0.0, -w / 2.0),
            _off(origin, tangent, normal, -2.0 * size * w, 0.0),
            _off(origin, tangent, normal, -size * w, -size * w)]


def _hook(origin, tangent, normal, w, length, width):
    """Up-turned tail (跳ね): base across the end, tip along the left normal
    (for a downward stroke that is leftward, as 寸's vertical hook)."""
    if length <= 0.0:
        return []
    k = width if width > 0.0 else 1.0
    ell = length * w
    return [_off(origin, tangent, normal, 0.0, -w / 2.0 * k),
            _off(origin, tangent, normal, 0.0, w / 2.0 * k),
            _off(origin, tangent, normal, -0.17 * ell, ell)]


def _heel(origin, tangent, normal, w, length, width):
    """Bottom-corner widening (踵): a trapezoid narrowing away from the end."""
    if length <= 0.0:
        return []
    k = width if width > 0.0 else 1.0
    ell = length * w
    return [_off(origin, tangent, normal, 0.0, -w / 2.0 * k),
            _off(origin, tangent, normal, 0.0, w / 2.0 * k),
            _off(origin, tangent, normal, -ell, w / 4.0 * k),
            _off(origin, tangent, normal, -ell, -w / 4.0 * k)]


_SHAPES = {"wedge": _wedge, "hook": _hook, "heel": _heel}
# The ends a decoration may sit at, mirroring style.DECORATION_AT. The style
# validator closes this vocabulary today, but `decorations` is plain data and
# stroke() is a public entry point, so decoration_contours re-checks it.
_ENDS = ("head", "tail")


def decoration_contours(plan: StrokePlan) -> list:
    """One CCW contour per decoration (spec §4.3.5). A zero size/length means
    'this style does not draw it' — no contour, no warning.

    A decoration whose `kind` or `at` the nib does not know is skipped *and*
    reported once in plan.warnings. It is deliberately not raised: stroke() runs
    once per stroke across a 2.2M-glyph corpus, where a hard failure on one odd
    plan is worse than a reported skip — the point is that the drop is visible,
    not fatal (a dropped datum must never read as "nothing wrong").
    """
    out = []
    for d in plan.decorations:
        key = d.kind.split("-")[0]      # "heel-ll" -> "heel"; also picks the args
        shape = _SHAPES.get(key)
        if shape is None:
            _warn_once(plan, f"decoration kind {d.kind!r} ignored")
            continue
        if d.at not in _ENDS:
            _warn_once(plan, f"decoration at {d.at!r} ignored")
            continue
        origin, tangent, normal, half = frame_at(plan, d.at)
        w = 2.0 * half                  # frame_at resolved the end's full width
        if key == "wedge":
            pts = shape(origin, tangent, normal, w, d.size)
        else:
            pts = shape(origin, tangent, normal, w, d.length, d.width)
        if len(pts) < 3:
            continue
        out.append(pts if shoelace(pts) > 0 else list(reversed(pts)))
    return out


def stroke(plan: StrokePlan) -> "Outline":
    """A stroke's full drawing: the body plus its decorations (spec §4.3.2/5)."""
    from glyphsmith.outline import Outline

    o = Outline()
    if should_degrade(plan):
        for quad in quad_fallback(plan):
            o.contours.append([(x, y, 0) for x, y in quad])
        for c in decoration_contours(plan):
            o.contours.append([(x, y, 0) for x, y in c])
        return o
    o.contours.append([(x, y, 0) for x, y in body_contour(plan)])
    for c in decoration_contours(plan):
        o.contours.append([(x, y, 0) for x, y in c])
    return o
