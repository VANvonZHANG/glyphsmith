# The pen backend (v2)

`--backend pen` renders a KAGE/2 skeleton through **style files instead of rule
tables**: one stroke model, N typefaces. The skeleton — expansion, stroke order,
the data's own endings — is shared with `legacy-kurgm`; the geometry
deliberately is not. Swapping `--style` changes the typeface and nothing else.

- [`pen-backend-design.md`](pen-backend-design.md) — the design note: vocabulary,
  the three modules, the academic grounds, the non-goals.
- This file — how to drive the backend, what it guarantees, and what it cannot
  tell you.

## Driving it

```sh
glyphsmith render u4e00-j --corpus examples/showcase.gsf --backend pen --style sans-hei
glyphsmith render u4e00-j --corpus examples/showcase.gsf --backend pen --style ./my-style.yaml
glyphsmith graph  u6f22-j --corpus examples/showcase.gsf --style serif-song --plans
glyphsmith styles                       # the built-in style files on disk
```

| Argument | Meaning |
|---|---|
| `--backend pen` | select the style engine |
| `--style <name\|path>` | a built-in name or a path to a style `.yaml`; default `serif-song` |
| `--backend both` | `legacy-kurgm` and `pen` side by side (`svg_legacy` / `svg_pen`); the useful contrast is now faithful-vs-pen |
| `--font` | meaningless here: the genre comes from the style file, not from a font family |

`glyphsmith styles` lists what can be loaded, not what is meant to be used:

| name | what it is |
|---|---|
| `serif-song` | a Song/Ming typeface recipe |
| `sans-hei` | a Hei (gothic) typeface recipe |
| `sans-round` | the same recipe as `sans-hei` with round caps and round joins |
| `pen-minimal-probe` | **not a typeface** — the layer-② validation probe (see below) |

**`pen-minimal-probe` is a probe, not a fourth style.** It is uniform width,
butt caps, bevel joins, data endings ignored — deliberately, so that it
reproduces exactly what the v1 `pen-minimal` preview backend draws. The new nib
is validated against that independently verified routine on a restricted subset
(layer ② below); the probe exists to be that oracle, and it appears in
`glyphsmith styles` only because that command lists every loadable style file.

## The pipeline (every step is queryable data)

```
ResolveResult                          glyphsmith resolve <name>
  ↓ legacy_kurgm.expansion.expand()    shared with legacy-kurgm, not re-implemented
items: [RStroke | TransformOp]         stream order = the data's order
  ↓ pen.graph.build()                  pure geometry; knows nothing about styles
StrokeGraph                            glyphsmith graph <name>            → JSON
  ↓ pen.style.Style.apply(graph)       Style ← YAML
{stroke_id: StrokePlan}                glyphsmith graph <name> --plans    → JSON
  ↓ pen.nib.stroke(plan)               pure geometry; knows nothing about relations
Outline                                glyphsmith render … --out outline.json
```

Nothing in the middle is hidden state. The relational graph and the per-stroke
drawing plans are the CLI's `graph` output (`--plans` adds the plans), the
outline is `render --out outline.json`, and each module is unit-tested on its own
inputs — `graph.py` does not know about width or style, `style.py` does not draw,
`nib.py` does not know about relations or YAML. A `TransformOp` (`0:97/98/99`) is
applied to the outline accumulated *so far*, in stream order, which is what the
legacy drawer does.

### The graph on real glyphs: relation coverage (spec §9-3)

The graph is exported by the CLI (`glyphsmith graph <name> --corpus <dump>`:
`nodes` are strokes with their type, orientation, endings and centerline,
`edges` carry the relation `kind`, the two ends and the distance). The relation
vocabulary — `meets` / `crosses` / `tee` / `parallel` — is exercised on real
glyphs, not only on the hand-built skeletons of the graph tests. Recorded
2026-09-19, and reproducible with:

```sh
$ python scripts/pen_graph_coverage.py --corpus <dump>
scope=own-strokes slice=200000:220000 names=20000 glyphs=639 meets=333 tee=432 crosses=227 parallel=146 edges=3615
first examples (glyphs carrying a tee): gt-59024, gt-66774, gt-66845
coverage: tee, crosses and parallel all occur
```

The scope is what makes those numbers comparable, so the script prints it: the
20,000 dump lines at raw line index 200,000–220,000, and per glyph **its own
strokes** (a pure `99:` reference has no strokes of its own and contributes to
neither column — its parts are counted where they are defined), built by
`pen.graph.build` exactly as `glyphsmith graph` builds them. 639 of the 20,000
names carry their own strokes; the four counts are **the number of those glyphs
in which the relation occurs at least once** (a glyph can carry several edges of
one kind — 3,615 edges in total). The script exits non-zero when `tee`,
`crosses` or `parallel` never occurs, so a slice that fails the acceptance bar
cannot be read as a pass.

## Strong vs weak correctness — which level this is

Following Levien & Uguray, *GPU-friendly Stroke Expansion* (SIGGRAPH Asia 2024,
[arXiv:2405.00127](https://arxiv.org/abs/2405.00127)), this backend implements
**weak correctness**: a parallel curve plus joins (bevel / miter / round) plus
caps (butt / square / round), one closed contour per stroke body, with
decorations stacked as separate contours and resolved under the nonzero winding
rule.

It does **not** handle the evolute. Where a stroke's radius of curvature falls
below its half-width the offset curve would fold through itself; such a stroke is
**detected, degraded to per-segment quads, and reported** — `warnings` carries
`degraded: curvature radius <r> < half-width <w>`, and nothing is dropped
silently (a zero-length centerline, a non-finite coordinate and a non-positive
width take the same explicit path and name themselves). An empty centerline is
degraded first, so it can never slip through the other branches.

**Strong correctness — evolute handling and boolean union — is explicitly out of
scope.** The trade-off is the reason the analytic layer below can be exact: the
per-stroke outline is a simple closed polygon whose shoelace area is the
intended area, with no boolean post-pass to undo it.

## Validation: five layers, and what each cannot tell you

The pen backend has **no external anchor**: no other program renders our style
files, so there is no reference implementation to diff against the way
kage-engine anchors `legacy-kurgm`. Validation is layered instead, and each
layer states what it can and cannot prove.

| # | Layer | Where | Can prove | Cannot prove |
|---|---|---|---|---|
| ① | analytic cases | `tests/test_pen_nib.py` | closed-form areas on synthetic skeletons (butt `L·w`, square `L·w + w²`, linear taper `L·(w0+w1)/2`, 90° bends per join style) match the shoelace area to a relative error < 1e-6 — the **polygonal** cases; the two arc cases are inscribed polygons and are bracketed instead (see the note below) | whether the result looks like Song |
| ② | region equivalence | `tests/test_pen_equivalence.py` + `src/glyphsmith/styles/pen-minimal-probe.yaml` | on polyline-only, TransformOp-free glyphs the body covers the same region as `pen-minimal`: raster IoU > 0.99 **and** mask difference ≤ 1% (worst measured 0.99344 / 0.134%, 7 samples at 512²; off the corners the two agree exactly) | curve strokes (pen follows the true curve, `pen-minimal` the control polygon), decorations, rules, TransformOps |
| ③ | full-corpus smoke | `scripts/smoke_full.py --backend pen --style X`, `scripts/pen_audit.py --style X` | all 2,221,895 glyphs render with `err=0` for all three styles, and every degradation is counted **per reason** | whether it looks like Song |
| ④ | style differentials | `tests/test_pen_style_diff.py`, `scripts/pen_style_diff.py` | a style parameter moves the output **in the direction it implies** (thicker verticals ⇒ more ink and a visibly different render; round caps ⇒ more ink at a high IoU; suppressing the wedge rule ⇒ exactly the wedges disappear) | how large the effect *should* be — magnitude is the style author's judgement, and gating it would fit the styles to legacy |
| ⑤ | self-golden | `tests/test_pen_golden.py` + `tests/fixtures/pen-golden.tsv` | that a refactor does not silently change today's output (3 styles × 3 sample glyphs) | **anything about correctness** — the values come from our own code |

The arc carve-out in layer ①: a round cap and a round join are **flattened
arcs, and the flattener inscribes the circle** (`nib._arc_points` places the
chords inside it), so their areas are strictly *below* the closed form and
cannot meet a two-sided `< 1e-6` bar. What the tests assert there is what is
exactly true — an interval between the flattened value and the closed form
(`1670.0 <= a <= 1678.5398` against `L·w + π(w/2)²` = 1678.5398 for the round
cap; `1993.5 <= a <= 2000.0` against 1994.6349 for the round join, both in
`tests/test_pen_nib.py`) — plus that every arc vertex lies on the circle.
Measured relative errors: **3.02e-03** (round cap) and **4.44e-04** (round
join), i.e. 3,000× and 440× the bound the polygons meet. One published bound for
both would be false: the plan's own gate wording carved the arcs out (in
paraphrase, "arcs are asserted as the inscribed value / the true-value
interval"), and this table dropped the carve-out.

Layer ⑤ is a **drift guard, not evidence**. `scripts/pen_golden_regen.py`
regenerates the fixture; a changed line is a change to what users see, and
reviewing the diff is the point. The same warning is in the test module, the
fixture header and the script, because this is exactly the layer that is easiest
to mistake for a correctness test.

> **No layer can tell you whether the output looks like Song/Ming.** That is an
> aesthetic judgement about a typeface, and this backend does not pretend to
> score it. Layers ①–④ constrain the geometry and the wiring; layer ⑤ only
> freezes what they produced. Whether the result reads as 宋体 is a question for
> a person looking at the glyphs.

### Layer ③ measured: the full corpus

`scripts/pen_audit.py --corpus <dump_newest_only.txt> --style <style>
--workers 16`, stroke-only scope, full corpus, one run per style (2026-09-19,
recorded in the task report):

| style | glyphs | strokes | degenerate | reasons: zero-length / non-finite / non-positive width / curvature | err |
|---|---:|---:|---:|---|---:|
| `serif-song` | 2,221,895 | 1,152,821 | 1,931 (0.168% of strokes) | 326 / 0 / 0 / 1,605 | **0** |
| `sans-hei` | 2,221,895 | 1,152,821 | 3,302 (0.286%) | 326 / 0 / 0 / 2,976 | **0** |
| `sans-round` | 2,221,895 | 1,152,821 | 3,302 (0.286%) | 326 / 0 / 0 / 2,976 | **0** |

The reason counts sum to the totals exactly (326 + 1,605 = 1,931;
326 + 2,976 = 3,302), and every non-zero reason is attributable:

- **`zero-length centerline`** — 326 strokes, identical for all three styles
  (it is a property of the data, not of the style): 137 glyphs, dominated by the
  Greek and halfwidth blocks plus a scatter of test glyphs. `alfa_akarasamani`
  tapers a stroke to a point, so both ends land on the same coordinate.
- **`degraded: curvature radius`** — 1,605 strokes (serif) / 2,976 (sans) on
  ordinary glyphs: e.g. `aisxh999_test100` has a horizontal whose circumradius
  4.08 is below the local half-width 5.53, i.e. the evolute case above. The sans
  styles are thicker, hence the larger count.
- **`non-finite centerline coordinate`** and **`non-positive width profile`** —
  0 in the full corpus (the ref-dense head of the dump does contain them: 3 in a
  200,000-glyph closure sample).
- **`empty`** — 317 of the degenerate strokes render no contour at all (the 326
  zero-length strokes minus 9 that still draw: the nib stacks a data-sourced
  heel ornament on a zero-length frame). The audit counts strokes that draw
  nothing separately from degeneracy for exactly this reason.

The rendering harness of the same layer,
`scripts/smoke_full.py --corpus <dump> --backend pen --style serif-song`, ran the
full corpus as well: `total=2,221,895 ok=166,747 empty=2,055,148 err=0`
(stroke-only scope, in which a pure-reference glyph has nothing to draw — 97% of
this dump's glyphs carry a ref). The other two styles were run to completion too,
each with `err=0`. Reproduce any of it with, for example:

```sh
python scripts/pen_audit.py  --corpus <dump> --style sans-hei --workers 16
python scripts/smoke_full.py --corpus <dump> --backend pen --style sans-hei --workers 16
```

### `pen` vs `legacy-kurgm`: a recorded reference, not a bar

```sh
$ python scripts/pen_style_diff.py --corpus <dump> --a serif-song --b legacy-kurgm \
      --n 200 --closure
a=serif-song b=legacy-kurgm scope=closure n=200 empty=0 err=0 mean_iou=0.7409 …
```

**mean IoU 0.7409 at n = 200, 0.7412 at n = 2000**, `serif-song` against
`legacy-kurgm`'s mincho. Scope matters: `--closure` resolves each glyph's
reference closure before rendering. Without it the script measures stroke-only
scope, where the head of this dump is ref-only sandboxes, most pairs are
blank-blank, and `compare` returns IoU 1.0 for two empty masks — the unflagged
headline on this pair (`0.9908` at n = 200, `empty=191`) is dominated by
non-measurements, and the `empty=` counter is what makes that visible.

This number is **recorded, never gated**. The two engines share the skeleton but
deliberately not the geometry (see below), so a value near 1 would mean the pen
styles had been fitted to legacy — the opposite of the redesign's claim. Gating
it would push the styles toward imitating `legacy-kurgm` instead of being
typefaces; the equivalence oracle for the new nib is `pen-minimal` (layer ②),
not kurgm. No test asserts it.

## Known differences from `legacy-kurgm`

The skeleton is shared; the geometry is not. What follows is why an IoU below 1
between the two is expected rather than a defect:

1. **Decoration shapes are calibrated, not ported.** The wedge / hook / heel
   triangles come from `legacy-kurgm`'s `dfDrawFont` visual alignment; the pen
   decorations are not point-for-point identical to legacy's.
2. **The centerline follows the true curve** for `quad` / `cubic` strokes, where
   legacy walks the control polygon.
3. **The two composition rules are declarative rewrites**, using legacy's
   `adjustUroko` / `adjustHane` as their parameter reference rather than being
   ports of them. Legacy's "wall" quirk (the `lpx + 18` right-boundary
   neighbour in `adjustHane`) is not modelled.
4. **`meets_tol = 1.0`** replaces legacy's exact coordinate equality — expansion
   includes scaling, and floating-point noise would make exact equality fail.
5. **`TransformOp` rectangle selection sees pen's contours**, so the contour set
   a `0:97/98/99` row selects may differ from legacy's.
6. **`use_curve` and `--font` are meaningless here**: the curve is always the
   true curve, and the style file replaces the font family.
7. **The pen backend is not part of the golden differential baseline.** It has no
   external anchor, so the pen-vs-legacy IoU above is a reference number, not a
   pass/fail gate.
8. **`pen-minimal` drops TransformOps outright** (its v1 preview behaviour), so
   the layer-② equivalence is restricted to glyphs without one.

## Where things live

| Path | What |
|---|---|
| `src/glyphsmith/pen/graph.py` | the relational graph (nodes = strokes, edges = meets / crosses / tee / parallel) |
| `src/glyphsmith/pen/style.py` | style-file loading, validation, rule evaluation → `StrokePlan`s |
| `src/glyphsmith/pen/nib.py` | plan → contour: offset curve, joins, caps, decorations, degradation |
| `src/glyphsmith/pen/backend.py` | the `Backend` implementation: stream order, transform interleaving, warnings |
| `src/glyphsmith/styles/*.yaml` | the shipped recipes, including the layer-② probe |
| `tests/test_pen_*.py` | the five layers above, per module |
| `scripts/smoke_full.py`, `scripts/pen_audit.py`, `scripts/pen_style_diff.py`, `scripts/pen_golden_regen.py`, `scripts/pen_graph_coverage.py` | the reproduce-the-numbers artifacts |
