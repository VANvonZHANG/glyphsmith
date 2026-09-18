# pen backend design (reserved for v2, interface locked in v1)

> This is the pen backend's standalone design note: it answers three questions
> without depending on any document outside the repository — **what is to be
> built** (three modules and the data flow), **why it is designed this way**
> (the two-backend division of labour and the vocabulary decisions), and
> **which geometric/academic grounds it needs** (parallel curves / weak vs
> strong correctness / relational graphs / parametric precedents).
>
> v1 ships only its interface placeholder `pen-minimal`
> (`src/glyphsmith/pen_minimal.py`: uniform-width stroking + butt caps,
> per-segment quads, whose nonzero union is Levien's "weak correctness" level) —
> it proves the Backend protocol is not shaped for legacy alone. The
> graph/style/nib modules and the style-file engine are all v2 scope.

## 1. Why a second backend

v1's `legacy-kurgm` is a faithful port: it renders what the data says, point for
point identical to the reference implementation (that is the research baseline).
The price is that **style is not parameterizable** — the 宋/黑 distinction comes
from two hard-coded rule tables in kagecd.js/kagedf.js, changing one stroke
ending means changing code, and the rules cover only those two families.

What the research side actually needs is **declarative, comparable style**: one
skeleton, and swapping the style file yields another typeface, with every step of
"skeleton → outline" inspectable and intervenable by an agent. This does not
replace legacy-kurgm; it divides labour with it:

| | `legacy-kurgm` (v1) | `pen` (v2) |
|---|---|---|
| Goal | point-for-point identical to kage-engine | style parameterization, explicable, iterable |
| Rule source | hard-coded kagecd/kagedf tables | YAML style files (declarative) |
| Width | determined by the rule tables and the ending code | skeleton × w(t) width profile × caps/decorations |
| Typefaces covered | 宋 mincho / 黑 gothic | target: the serif/sans/round recipe families |
| Role | regression baseline, cross-validation oracle | the research mainline |

## 2. The interface v1 has locked (v2's construction surface)

1. **The `Backend` protocol** (`src/glyphsmith/protocol.py`): the two methods
   `render(result)` and `render_separated(result)`, with `Backend.register` to
   register and `get_backend` to look up. The protocol only requires
   "`ResolveResult` in, `Outline` out" and imposes nothing on the internals.
2. **The shared `Outline` structure** (`src/glyphsmith/outline.py`): a contour
   table of `[(x, y, off), …]`, where off=1 means off-curve (the TrueType
   convention), responsible for `to_path_d()` / `to_svg()` and wrap-around
   normalization. Both backends emit the same structure, so `compare` /
   `scripts/smoke_full.py` / `batch` work with a new backend out of the box.
3. **`--backend` end to end**: the CLI's
   `--backend legacy-kurgm|pen-minimal|both`, `Renderer(backend=…)` and
   `batch --backend` are all in place; a new backend only has to register.
4. **What `pen-minimal` proves**: ref expansion reuses legacy's `expand` (the
   first evidence that the protocol generalizes), and it writes back the same
   `result.warnings` as legacy (missing part / raw op do not go silent just
   because the backend changed).

All of v2's new work falls inside the three `pen/` modules and needs no change
to the protocol layer — if a change is needed, the protocol is misdesigned and
should be fixed first.

## 3. The three v2 modules

```
pen/
  graph.py   Relational graph (ARG style): nodes = strokes,
             edges = meets/crosses/tee/parallel + geometric attributes
             → an agent-queryable intermediate product
  style.py   Style-file loading (YAML)
  nib.py     Pen model: skeleton × w(t) width profile × caps/decorations
             → variable-width offset → Outline
```

Data flow (every step is a queryable intermediate product — this is where
"agent-native" lands):

```
GSF skeleton ──expand──> stroke sequence ──graph──> relational graph ──style──> rule evaluation
                                                                                   │
                                    Outline <──nib (offset + caps + decorations) ──┘
```

- **graph**: makes "two strokes meet / cross / form a T / run parallel" explicit.
  The input to composition rules is relations, not pixels — conditions like
  `when: {rel: meets, from: horizontal, to: vertical, at: head}` can only be
  written on a graph. It follows the ARG (attributed relational graph) tradition
  in online Chinese character recognition and StrokeStrip's stroke-grouping and
  tangency criteria.
- **style**: the style file is **data**, not code. The same relational graph fed
  to different style files yields different typefaces; a style-file diff can be
  reviewed and regression-tested.
- **nib**: skeleton + width profile + caps/decorations → outline. Uniform width
  is the degenerate case w(t)=const (which is what pen-minimal does); variable
  width goes through parallel-curve offsetting.

## 4. Style-file syntax draft (direction frozen, to prevent v2 drift)

```yaml
# styles/serif-song.yaml
name: serif-song            # genre: serif; regional recipe suffix: song/ming/mincho
width_profile:
  horizontal: {w0: 6,  w1: 6}
  vertical:   {w0: 14, w1: 12}
caps:
  horizontal-head: wedge    # uroko (鱗) = wedge serif
decorations:
  wedge: {shape: triangle, size: 1.4}
rules:                      # declarative composition rules (over the relational graph)
  - when: {rel: meets, from: horizontal, to: vertical, at: head}
    then: {suppress: wedge}
```

Three design intentions v2 should not deviate from:

1. `width_profile` is banded by **stroke orientation** (one pair of end widths
   for horizontals, one for verticals), which matches calligraphic reality
   (horizontals thin, verticals thick) and avoids per-stroke tuning;
2. `caps`/`decorations` use **words from the vocabulary** (`wedge`, `hook`,
   `heel`, …), not numeric codes — the reader of a style file is a human;
3. `rules` operate on the relational graph, where the `when` condition is
   relation + orientation + ending position, and `then` may only suppress,
   replace or scale existing decorations (v2 explicitly does not support
   arbitrary scripts).

## 5. Vocabulary decisions

### 5.1 Three naming layers

| Layer | Wording | Examples |
|---|---|---|
| genre (the broad typeface class) | international standard words | `serif` / `sans` / `round` |
| regional recipe (suffix) | place name + traditional name | `serif-song` (宋), `serif-mincho` (明朝), `sans-hei` (黑) |
| detail (ending / decoration / cap / join) | English descriptive words | `wedge` / `hook` / `heel` / `bend` / `cut` / `butt` / `miter` |

The detail words are aligned with, and reuse, GSF v1's stroke-ending enum
(`hook`, `heel-ll`, …): one physical thing gets one word at the data layer (GSF)
and at the style layer (pen), so no second set of translations appears.

### 5.2 Terminology table (Japanese → Chinese → English)

KAGE is a Japanese project and its rule-table terminology is entirely Japanese
type-engineering jargon. The table below is where v2's vocabulary comes from;
the Japanese source word is glossed only at a term's first appearance in the
documentation, and code and configuration always use the English descriptive
words.

| Japanese jargon | Chinese | English (this project) | Note |
|---|---|---|---|
| うろこ uroko（鱗） | 三角衬线 | `wedge` | an existing Latin-typography word (wedge serif); the meaning matches |
| 跳ね hane | 钩 | `hook` | already fixed by GSF v1 |
| 踵 kakato | 踵（底角出头） | `heel` | already fixed by GSF v1 |
| はらい harai | 撇捺出尖 | `tip` | already fixed by GSF v1 |
| 曲がり mage | 弯 | `bend` | descriptive |
| 切り口 kirikuchi | 切头 | `cut` | descriptive |
| とめ tome | 平收 | `flat` | already fixed by GSF v1 |
| 端帽族 (caps) | — | `butt` / `square` / `round` | SVG `stroke-linecap` + Levien 2024 |
| 连接族 (joins) | — | `bevel` / `miter` / `round` | SVG `stroke-linejoin` + Levien 2024 |

The broad typeface classes have a mapping too (`明朝体` = Chinese 「宋体/明體」 =
genre `serif`; `ゴシック体` = 「黑体」 = genre `sans`); inside the software the
genre layer is always merged into the international standard words, and the
宋/明/黑/圆 distinctions are left to the recipe-parameter layer.

### 5.3 False friends and traps

1. **Gothic**: Japanese `ゴシック体` = sans-serif; in English typography Gothic =
   blackletter. Inside the software the genre is always written `sans`, with
   `gothic` entering the registry only as an alias.
2. **明朝/宋/明體**: sibling names from three regions, not three typefaces; the
   differences (character-face ratio, kana pairing, …) belong to the recipe
   layer.
3. **The ambiguity of serif**: in a CJK context serif means the "宋-family"
   whole, in a Latin context it means the stroke foot. When a specific triangular
   serif is meant, use `wedge`, not the generic word.
4. **Long-vowel spelling**: `minchō` is often written `mincho` in ASCII
   environments — the alias registry accepts both.

The alias registry takes Japanese romanization (including long/short vowel
variants) and Chinese pinyin, for searching and for cross-reading the
literature; code and configuration never contain aliases.

## 6. Geometric and academic grounds

**(a) Stroke → filled outline: Levien & Uguray, "GPU-friendly Stroke Expansion"
(SIGGRAPH Asia 2024, arXiv:2405.00127 <https://arxiv.org/abs/2405.00127>)**
organizes "stroke → fill" into the clean vocabulary of **parallel curve + join
(bevel/miter/round) + cap (butt/square/round)**, and distinguishes:

- **weak correctness**: parallel curve + caps + outer joins; good enough
  engineering. `pen-minimal` sits at this level (uniform width, butt caps,
  per-segment quads, no boolean union);
- **strong correctness**: handles the evolute as well, needed only where the
  radius of curvature is smaller than the half-width. v2's nib layer must handle
  variable width and therefore **must** state its strong/weak correctness
  trade-off explicitly and say in the documentation which level it is at.

**(b) The formal geometry of variable width w(t)**: a cubic Bézier approximation
of the variable-radius offset curve (subdivision + normal offset + error
control) is a workable engineering route; `nib`'s width profile approximates
w(t) with piecewise-constant/linear functions.

**(c) A direct precedent for parametric Chinese characters**: John Hobby,
"A Chinese Meta-Font" (TUGboat, 1984,
<https://tug.org/TUGboat/tb05-2/tb10hobby.pdf>) used a Metafont pen model plus
parametric stroke routines to make Chinese characters, with different stroke
routines taking different font parameters — the pipeline in this section was
validated once already, 42 years ago. The lineage: Knuth, "The Concept of a
Meta-Font" (1980) → Hobby (1984) → variable fonts' "style = parameter vector" →
CSS `stroke-linecap`/`stroke-linejoin` (the standardization of cap/join
vocabulary).

**(d) The history and practice of relational graphs**: ARG (attributed
relational graph) online Chinese character recognition (IET 1996) and
hierarchical attributed graphs (Pattern Recognition 1991) are the classic use of
"strokes = nodes, relations = edges"; StrokeStrip (2022,
<https://www.davepagurek.com/programming/strokestrip/>) gives a modern
implementation of stroke grouping and tangency/join criteria; Berio et al.,
"StrokeStyles" (ACM TOG 2022, <https://doi.org/10.1145/3505246>) shows that
bidirectional "outline ↔ stroke" conversion plus restyling is an active
direction. v2's graph module takes the former's relational vocabulary and the
latter's grouping criteria.

## 7. Explicitly not doing (v2 non-goals)

- **Composition rules for arbitrary scripts**: `rules.then` may only suppress,
  replace or scale existing decorations;
- **automatic style fitting** (inferring a style file from an outline) — that
  belongs to the long-range "reverse glyph generation", not v2;
- **replacing legacy-kurgm**: the pen backend does not join the golden
  differential baseline; the two divide labour rather than substitute for each
  other;
- the data layer, the IDS layout layer, SFD/OTF export and other items v1
  explicitly places outside the repository are likewise outside the first
  version of v2.

## 8. v2 acceptance draft (written down, so we cannot "finish without being able to say what we did")

1. `styles/` holds at least one serif and one sans style file, each rendering
   the same corpus;
2. with the same skeleton, swapping the style file changes `compare`'s IoU
   markedly, and in the direction the style parameters imply (e.g. thickening
   verticals → lower IoU against the baseline but a larger stroke-covered area);
3. `graph`'s intermediate products can be exported as JSON by the CLI
   (agent-queryable);
4. the variable-width offset states its strong/weak correctness trade-off in
   writing, and produces no NaN for degenerate input (zero-length strokes,
   collinear control points, radius of curvature < half-width) — reusing v1's
   smoke criterion of err=0.
