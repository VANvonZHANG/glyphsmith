# glyphsmith

**A renderer for [GSF](https://github.com/VANvonZHANG/gsftool) glyph skeletons** — it turns the KAGE/2
stroke-skeleton data behind [GlyphWiki](https://glyphwiki.org) into outlines and SVG, through an
agent-friendly CLI and a Python library.

[![CI](https://github.com/VANvonZHANG/glyphsmith/actions/workflows/ci.yml/badge.svg)](https://github.com/VANvonZHANG/glyphsmith/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)
[中文说明（Chinese）](README.zh.md)

Three backends share one outline structure and one CLI:

| Backend | What it is |
|---|---|
| `legacy-kurgm` | A line-by-line Python port of the [kage-engine](https://github.com/kurgm/kage-engine) TypeScript renderer. Point-for-point identical to the reference implementation (see [validation](#validation)) — the regression baseline. |
| `pen` | The v2 style engine: a relational graph over the strokes plus declarative style files (`--style serif-song\|sans-hei\|sans-round\|<path>`). Variable-width nib; endpoints come from the data, ornaments from the style. User guide: [`docs/pen-backend.md`](docs/pen-backend.md). |
| `pen-minimal` | A uniform-width stroke preview (butt caps, per-segment quads; Levien's *weak correctness* level). Preview-grade; it is the v1 interface placeholder, kept as the equivalence anchor. |

`--backend both` renders `legacy-kurgm` and `pen` side by side — the useful contrast is now
faithful-vs-pen, not faithful-vs-preview.

## Why this exists

GlyphWiki glyphs are stored as skeletons. `gsftool` converts them to GSF losslessly; `glyphsmith`
renders them. Three properties are the reason it was written.

**1. Faithful rendering, measured rather than claimed.** `legacy-kurgm` is a faithful port of
kurgm/kage-engine — including its quirks. Faithfulness is checked by fingerprint (contour count +
vertex count + sha1 of every coordinate, ε = 0), not by eyeballing: 7,614/7,614 on kage-engine's own
golden matrix, and 1,000/1,000 on randomly sampled real dump glyphs against the original running
under Node. See [validation](#validation).

**2. It renders what you wrote — it does not quietly "correct" you.** Learned font generators have a
documented bias: when a glyph differs from the training distribution by a subtle variation, "the bias
is prone to either correcting or ignoring these subtle variations"
([SFGN, arXiv:2501.08062](https://arxiv.org/abs/2501.08062)). That is fatal for research on variant
forms — 俗字 popular forms, chữ Nôm — where the object of study is often a standard glyph *plus one
extra dot*. A rule engine draws what the data says, which is the whole point here.

**3. Agent-native by construction.** The library and the CLI cover the whole loop in one process:
resolve the reference closure → render → compare against a target → change a parameter → render
again. `compare` returns raster IoU plus per-stroke structural metrics (bbox IoU, vertex counts,
Hausdorff distance); the CLI emits one line of JSON on stdout, uses meaningful exit codes, and puts
the next command to run in `hints` when it fails.

## Installation

`glyphsmith` needs Python ≥ 3.11, `numpy` and `pillow`, and **gsftool** (the GSF parser/writer, which
is not on PyPI):

```sh
pip install git+https://github.com/VANvonZHANG/gsftool
pip install git+https://github.com/VANvonZHANG/glyphsmith
glyphsmith --help
```

Or work from clones, with the two repositories side by side:

```sh
git clone https://github.com/VANvonZHANG/gsftool
git clone https://github.com/VANvonZHANG/glyphsmith
pip install -e gsftool -e "glyphsmith[dev]"    # [dev] adds pytest
cd glyphsmith && pytest -q
```

`python -m glyphsmith.cli …` is equivalent to `glyphsmith …` when the console script is not on
`PATH`. The full corpus is not bundled: point `--corpus` at a GSF file or at GlyphWiki's
`dump_newest_only.txt`. The one exception is the 8-glyph
[`examples/showcase.gsf`](examples/showcase.gsf) (see [License](#license-and-provenance)), which is
what every example below uses — **those examples assume you are working in a clone of this
repository**, since `pip install` does not ship the `examples/` directory.

## Quick start

### Render a glyph

```sh
$ glyphsmith render u4e00-j --corpus examples/showcase.gsf
{"status": "ok", "data": {"name": "u4e00-j", "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 200 200\" width=\"200\" height=\"200\"><path d=\"M 14,99 L 186,99 L 186,103 L 14,103 Z M 186,99 L 162,101 L 174,89 Z\" fill=\"black\" fill-rule=\"nonzero\"/></svg>"}, "warnings": [], "hints": []}

$ glyphsmith render u6f22-j --out png --corpus examples/showcase.gsf
{"status": "ok", "data": {"name": "u6f22-j", "path": "u6f22-j.png"}, "warnings": [], "hints": []}
```

`--out` is `svg` (default, returned inline, nothing written), `png` (written to
`<name>.png` in the current directory), or `outline.json`. `--backend` is `legacy-kurgm`
(default), `pen`, `pen-minimal`, or `both` — legacy-kurgm and pen side by side, as `svg_legacy`
and `svg_pen`. `--font` takes `serif`/`mincho` or `sans`/`gothic` and belongs to `legacy-kurgm`;
the pen backend ignores it and takes `--style <name|path>` instead — the three built-ins are
listed by `glyphsmith styles`:

```sh
$ glyphsmith render u4e00-j --corpus examples/showcase.gsf --backend pen --style sans-hei
$ glyphsmith styles
{"status": "ok", "data": {"styles": [{"name": "sans-hei", "genre": "sans", "path": "…/styles/sans-hei.yaml", "description": "sans style with 0 decoration(s) and 0 rule(s)"}, …]}, "warnings": [], "hints": []}
```

With `--backend pen`, a `--style` that is empty, unknown, or a file that cannot be read is a
usage error (exit 2, message in `data.error`) rather than a silent fall back to the default. The
other backends never open the style file, so `render --style nope` with them exits 0 by design:
the value is validated only where it would be read (`cli.py`; an empty `--style` is a usage error
everywhere, because nobody means it).

### Resolve the reference closure

GlyphWiki glyphs are assembled from parts by reference, so rendering one glyph means resolving its
closure first:

```sh
$ glyphsmith resolve u6f22 --corpus examples/showcase.gsf
{"status": "ok", "data": {"name": "u6f22", "closure": ["u26c29-02", "u6c35-01", "u6f22", "u6f22-j"], "dangling": [], "depth": 3}, "warnings": [], "hints": []}
```

`closure` is every glyph that participates, `depth` is the deepest reference chain, and `dangling`
lists references whose target is not in the corpus. Reference cycles are detected during resolution
and terminate the command with exit code 4 and the cycle path in `data.error` — the renderer never
recurses forever.

### Compare two glyphs

```sh
$ glyphsmith compare u6f22-j u6f22-v --corpus examples/showcase.gsf
{"status": "ok", "data": {"iou": 0.5289900575614861, "per_stroke": []}, "warnings": ["stroke count mismatch: 15 vs 16; per_stroke skipped"], "hints": []}
```

`u6f22-j` and `u6f22-v` are two real variants of 漢 with different component cuts: the rasterized
IoU is 0.53. Per-stroke metrics are skipped here because the two have different stroke counts, and
the CLI says so in `warnings` rather than returning a silently meaningless list.

### Use the library

```python
from glyphsmith import Corpus, Renderer, compare

corpus = Corpus.from_gsf("examples/showcase.gsf")     # or Corpus.from_dump("dump_newest_only.txt")
han = corpus.resolve("u6f22-j")                       # ref closure, cycle-checked

serif = Renderer(backend="legacy-kurgm", font="mincho").render(han)
gothic = Renderer(backend="legacy-kurgm", font="gothic").render(han)     # same skeleton, other genre
pen = Renderer(backend="pen", style="serif-song").render(han)            # the v2 style engine
preview = Renderer(backend="pen-minimal").render(han)

print("contours:", len(serif.contours))               # contours: 28
print("mincho vs gothic  IoU:", round(compare(serif, gothic).iou, 3))    # 0.635
print("mincho vs preview IoU:", round(compare(serif, preview).iou, 3))   # 0.548
svg = serif.to_svg()                                  # Outline -> SVG, or to_path_d() for a path
```

`Renderer.render()` returns an `Outline`: a list of contours of `(x, y, off)` points on GlyphWiki's
200×200 grid, y down, `off=1` marking off-curve (TrueType convention) points.

## Architecture

| Module | Role |
|---|---|
| `glyphsmith.protocol` | The `Backend` ABC + registry, `Renderer` (public API), `RenderOptions` |
| `glyphsmith.corpus` | `Corpus`: loads a GSF file or a GlyphWiki dump, caches parses, resolves reference closures, detects cycles, reports dangling references |
| `glyphsmith.legacy_kurgm` | The faithful port: mincho/gothic rule tables (straight and curve variants), stroke geometry, transforms, fingerprinting |
| `glyphsmith.pen` | The v2 backend: relational graph, declarative style files, variable-width nib (`style.py`, `graph.py`, `nib.py`, `backend.py`) |
| `glyphsmith.pen_minimal` | Preview backend: uniform-width outline of every control segment |
| `glyphsmith.outline` | The shared `Outline` structure both backends produce (`to_svg`, `to_path_d`) |
| `glyphsmith.compare` | Raster IoU and per-stroke metrics |
| `glyphsmith.batch` | Multiprocess whole-corpus rendering to `outdir/<name>.svg` |
| `glyphsmith.cli` | The JSON-contract CLI |

The data flow is deliberately narrow: `Corpus.resolve(name)` → `ResolveResult` (the glyph plus its
parts plus warnings) → `Backend.render(result)` → `Outline`. Everything downstream — SVG, PNG,
`compare`, `batch`, the smoke harness — consumes `Outline` and is therefore backend-agnostic.

Adding a backend is a `Backend.register` call in a module that gets imported (that is how
`glyphsmith/__init__.py` wires up the two shipped backends). The CLI, `compare` and the library then
accept it by name. Two places are **not** automatic, and are worth knowing before you write one:
`batch` runs its workers in separate processes, so a new backend must also be added to
`glyphsmith.batch._BACKEND_MODULES` (a name→module map imported inside each worker; otherwise the
workers fail with an unknown-backend error counted per glyph), and `scripts/smoke_full.py` reuses
that same map.

## CLI contract

`glyphsmith` writes exactly one line of JSON to stdout, always with the same envelope:

```json
{"status": "ok|error", "data": {…}, "warnings": ["…"], "hints": [{"action": "…", "reason": "…"}]}
```

| Exit code | Meaning |
|---|---|
| 0 | success — payload in `data` |
| 2 | usage error: bad arguments, unknown backend/font, corpus not openable, write failure |
| 3 | unknown glyph — `hints` contains a `glyphsmith list --like '<prefix>*'` suggestion |
| 4 | reference cycle — `data.error` carries the cycle path |

Diagnostics never go to stdout, so `glyphsmith … | jq .data.svg` works. Warnings are data, not
failure: dangling references, version fallbacks and similar conditions are reported in `warnings`
while the command still exits 0.

## Validation

Every number below is reproducible from this repository; the harnesses skip (never fail) when their
external inputs are missing.

| Tier | What it checks | Result |
|---|---|---|
| Golden matrix | kage-engine's own 7,614 cases, per-character fingerprint | **7,614/7,614** |
| Cross-engine | 1,000 randomly sampled real dump glyphs, fingerprints against kage-engine under Node | **1,000/1,000** |
| Full-dump smoke | every glyph in `dump_newest_only.txt` (2,221,895), rendered, counted, never written | **2,221,895 glyphs, err=0** |
| Test suite | `pytest` | **8,019 passed** |

The golden fixture is kage-engine's own `test/strokes.js` snapshot
(`tests/fixtures/kurgm-strokes-golden.tsv`) — the reference implementation's expectations, not
ours.

```sh
pytest -q                                                   # 8,011 passed, 8 skipped (no external data)
pytest -m golden -q                                         # 7,614 passed — the golden matrix
GSF_DUMP=<dump>/dump_newest_only.txt \
  KAGE_ENGINE=<kage-engine>/lib/esm/index.js pytest -q      # 8,019 passed — nothing skipped
```

The 8 tests that skip without external resources are the ones that need the 318 MB dump, Node.js, or
a kage-engine checkout. They are enabled by environment variables, never by editing test code:

| Variable | Used by | Meaning |
|---|---|---|
| `GSF_DUMP` | `pytest`, `scripts/smoke_full.py` | Path to `dump_newest_only.txt`. Unset ⇒ dump-backed tests skip. |
| `KAGE_ENGINE` | `pytest`, `scripts/render_bridge.mjs` | Path to kage-engine's ESM entry (`<kage-engine>/lib/esm/index.js`, or `node_modules/@kurgm/kage-engine/lib/esm/index.js` after `npm install @kurgm/kage-engine`). Unset ⇒ cross-engine tests skip and `render_bridge.mjs` exits 2 with a JSON error on stderr. |

Full-dump smoke, both scopes (`scripts/smoke_full.py`, 16 workers, `legacy-kurgm`/mincho):

| Scope | Total | ok | empty | err | Wall clock |
|---|---:|---:|---:|---:|---:|
| stroke-only (parts = the glyph itself) | 2,221,895 | 166,755 | 2,055,140 | **0** | 82 s serial / 17 s at 8 workers |
| closure (`Corpus.resolve` per glyph) | 2,221,895 | 2,221,576 | 319 | **0** | 213 s at 16 workers |

The two scopes measure different things: stroke-only asks "does the renderer survive arbitrary
data" (a pure-reference glyph is *expected* to be empty, since its parts are not resolved), while
closure asks "does every glyph end up with a non-empty outline". Wall-clock is machine-dependent;
the counters are not — the repo's test suite pins serial and parallel runs to identical counts.
A quick subset check:

```sh
$ GSF_DUMP=<dump> python scripts/smoke_full.py --limit 20000 --workers 8
scope=stroke-only backend=legacy-kurgm style=serif-song workers=8 total=20000 ok=165 empty=19835 err=0 elapsed=2.0s rate=10067/s
```

## Known limitations

- **`legacy-kurgm` renders 宋 and 黑 only** (`--font serif|sans` → mincho/gothic), inherited from
  kage-engine's two rule tables (`kagecd.js`/`kagedf.js`). Other genres — 楷, 圆, 隶 — are not
  covered; they are the motivation for the v2 pen backend.
- **`pen-minimal` is preview-grade.** Uniform `WIDTH = 8.0`, butt caps only, per-segment quads with
  no boolean union, transforms skipped. It exists to prove the `Backend` protocol is not
  legacy-shaped, and it is a fast preview tool. The v2 engine it stood in for now ships as
  `--backend pen` (relational graph + style files + variable-width nib; design and equations in
  [`docs/pen-backend-design.md`](docs/pen-backend-design.md)).
- **`batch` does not resolve references.** Like the smoke harness it renders each glyph with its own
  parts only (a throughput decision at dump scale), so reference-only glyphs come out as empty SVGs.
  Use `render` when you need closure-resolved output. `empty` is reported in the batch stats.
- **No SFD/OTF export.** Output is SVG, PNG and `outline.json`. There is no font-file writer.
- **No IDS layout layer.** Composition is by explicit `ref` + box, exactly as GlyphWiki stores it;
  there is no automatic 左右/上下 structure inference.
- **One known residual glyph.** `hkcs_m730b-p01-s00` contains `116p` where a number belongs — a
  typo in the source data. kage-engine lets `NaN` flow through the stroke maths; we skip the
  malformed row and draw the rest. Zero rendering impact on the other 2,221,894 glyphs; with the
  typo corrected the two sides agree exactly. Residual malformed rows are listed in
  `scripts/audit_gap_glyphs.py::KNOWN_RESIDUAL_GLYPHS`.
- **Version-fallback semantics differ from kage-engine by design.** When `X@N` is referenced but
  that version is absent from a newest-only dump, glyphsmith falls back to rendering newest `X` and
  emits a `version ref fallback` warning; kage-engine looks the part up exactly and silently draws
  nothing. This is a long-standing, disclosed difference in the corpus layer, not in the renderer.
- **The pen backend is not part of the golden differential baseline.** It shares the skeleton with
  `legacy-kurgm` (expansion, stroke order) but deliberately not the geometry — decorations are
  calibrated rather than ported, curves follow the true curve instead of the control polygon, the two
  rules are declarative rewrites rather than ports, and `meets_tol = 1.0` replaces exact coordinate
  equality. The IoU between the two engines is therefore a **reference number, not a pass/fail
  gate**: 0.7409 at n = 200 (0.7412 at n = 2000) from `scripts/pen_style_diff.py --closure` — the
  flag matters, because the stroke-only default compares mostly blank masks. Full list and the
  five-layer validation story: [`docs/pen-backend.md`](docs/pen-backend.md).

> **Nothing here can tell you whether the pen output *looks like* Song/Ming.** That is an
> aesthetic judgement about a typeface, and the pen backend does not pretend to score it: the
> validation layers constrain the geometry and the wiring, and the self-golden fixture only
> freezes what they produced. The full statement — what each of the five layers can and cannot
> prove — is in the [pen backend guide](docs/pen-backend.md#validation-five-layers-and-what-each-cannot-tell-you).

## License and provenance

`glyphsmith` is free software under the **GNU General Public License v3.0 or later**
(GPL-3.0-or-later) — see [`LICENSE`](LICENSE). Copyright (C) 2026 Fan Zhang.

The `legacy-kurgm` backend is a port, and the lineage is specific:

- **[kurgm/kage-engine](https://github.com/kurgm/kage-engine)** (TypeScript, npm
  `@kurgm/kage-engine`) — the porting baseline; glyphsmith matches its behaviour point for point.
- **[kamichikoichi/kage-engine](https://github.com/kamichikoichi/kage-engine)** — the original
  engine, and the ultimate source of the stroke rule tables `kagecd.js` (宋) and `kagedf.js` (黑).
- **[HowardZorn/kage-engine](https://github.com/HowardZorn/kage-engine)** — a prior Python port,
  used as a reference.
- **[takushun-wu/kage-cpp](https://github.com/takushun-wu/kage-cpp)** — the cycle-detection
  (`CheckGlyph`) approach was back-ported from here.

Glyph data rendered by this software is **not** placed under the GPL by rendering it: GlyphWiki's
data files are a separate work distributed by the [GlyphWiki Project](https://glyphwiki.org) under
its own free license ("These data files are free software. Unlimited permission is hereby granted to
use, copy, and distribute these files, with or without modification, either commercially or
non-commercially." — Copyright 2009 GlyphWiki Project). The corpus itself is not part of this
repository — but neither is the repository data-free: the only glyph data bundled here is
[`examples/showcase.gsf`](examples/showcase.gsf), the 8 glyphs used by the examples above,
redistributed under that same GlyphWiki license. Its file header records the source and the
license. Everything else you must point `--corpus` at yourself.

## Related projects

- **[gsftool](https://github.com/VANvonZHANG/gsftool)** — KAGE/2 ⇄ GSF converter and roundtrip
  verifier; the upstream of every corpus glyphsmith reads. *Bones, not flesh* (存骨不存肉): gsftool
  keeps the skeleton, glyphsmith draws the flesh.
- **[GlyphWiki](https://glyphwiki.org)** — the community glyph database this works on, and the
  source of the test corpus.
- **[kage-engine](https://github.com/kurgm/kage-engine)** — the reference renderer, used here as the
  golden and cross-engine oracle.
