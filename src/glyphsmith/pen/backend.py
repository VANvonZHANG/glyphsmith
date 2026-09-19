# src/glyphsmith/pen/backend.py
"""The pen backend: the pipeline that turns a ResolveResult into an Outline.

Stream order matters (spec §3.4): a TransformOp row transforms the contours
accumulated *so far*, so the item stream is walked in order and RStrokes are
drawn individually while TransformOps are applied to the outline in place.
The graph, by contrast, is built once over all strokes: kinds 97/98/99 are
isometries, so relations and distances are invariant under them.
"""
from __future__ import annotations

from glyphsmith.legacy_kurgm.expansion import expand
from glyphsmith.legacy_kurgm.font.transform import df_transform
from glyphsmith.outline import Outline
from glyphsmith.pen import graph as graph_mod
from glyphsmith.pen import nib, style as style_mod
from glyphsmith.protocol import Backend, RenderOptions


def expand_to_graph(result, style_name: str):
    """expand() -> (graph, plans, items, warnings, counts). Shared by the CLI's
    `graph` command and render_stream(), so both see exactly the same pipeline.

    `counts` is what the full-corpus smoke reports per style: a run that
    degrades nothing and skips nothing is the acceptance bar (spec §6 layer 3),
    and a bare err=0 would hide both.

    Degeneracy is counted by calling `nib.should_degrade(plan)` and never by a
    non-empty `plan.warnings`: `style.plan_for` also writes data-quality notices
    there (`unmapped ending code 8 at tail`, ~12% of real strokes), so counting
    on warnings would report a huge false degeneracy rate.
    """
    warnings = list(result.warnings)
    items = expand(result.glyph, result.parts, warnings)
    strokes = [it for it in items if not isinstance(it, tuple)]
    g = graph_mod.build(strokes)
    st = style_mod.Style.load(style_name)
    plans = st.apply(g)
    counts = {"strokes": len(strokes), "degenerate": 0, "empty": 0}
    for plan in plans.values():
        if nib.should_degrade(plan):
            counts["degenerate"] += 1
        elif not nib.decoration_contours(plan) and not plan.centerline:
            counts["empty"] += 1
        for w in plan.warnings:
            if w not in warnings:
                warnings.append(w)
    return g, plans, items, warnings, counts


def plan_to_dict(plan) -> dict:
    return {"stroke_id": plan.stroke_id, "centerline": [list(p) for p in plan.centerline],
            "widths": list(plan.widths), "cap_head": plan.cap_head,
            "cap_tail": plan.cap_tail, "joins": list(plan.joins),
            "miter_limit": plan.miter_limit,
            "decorations": [{"kind": d.kind, "at": d.at, "length": d.length,
                             "size": d.size, "width": d.width} for d in plan.decorations]}


def render_stream(result, style_name: str):
    """-> (Outline, list[Outline] per stroke, warnings).

    Per-stroke outlines are captured *as drawn*: for a glyph with a mid-stream
    TransformOp they hold pre-transform geometry, while `render`'s composite is
    post-transform (df_transform mutates only the accumulated outline).
    """
    _g, plans, items, warnings, _counts = expand_to_graph(result, style_name)
    outline, per_stroke, idx = Outline(), [], 0
    for it in items:
        if isinstance(it, tuple):            # TransformOp: mutates what is drawn so far
            df_transform(outline, it.kind, it.x1, it.y1, it.x2, it.y2, a3=it.a3)
            continue
        o = nib.stroke(plans[idx])
        outline.contours.extend(list(c) for c in o.contours)
        per_stroke.append(o)
        idx += 1
    return outline, per_stroke, warnings


class PenBackend(Backend):
    """The v2 research backend: style files instead of rule tables.

    Weak correctness (spec §4.3.3): one CCW contour per stroke body, decorations
    stacked as separate contours; degenerate strokes fall back to per-segment
    quads and say so in result.warnings.
    """

    name = "pen"

    def render(self, result, opts=None) -> Outline:
        outline, _per_stroke, warnings = render_stream(
            result, _style_of(opts))
        result.warnings[:] = warnings          # v1 final-review I2: never lose warnings
        return outline

    def render_separated(self, result, opts=None) -> list:
        _outline, per_stroke, warnings = render_stream(result, _style_of(opts))
        result.warnings[:] = warnings
        return per_stroke


def _style_of(opts) -> str:
    # The fallback is RenderOptions().style, not a second "serif-song" literal:
    # one source of truth, so the dataclass default and this fallback cannot diverge.
    return getattr(opts, "style", None) or RenderOptions().style


Backend.register(PenBackend)
