#!/usr/bin/env python
"""Style-difference report (spec §6 layer 4): does a parameter actually move the
output, in the direction the style file implies?

Layer 4 asks a *difference*, not an absolute: one glyph rendered under two
styles — or under one style and the peer engine — compared by raster IoU and by
ink area, reported as the pair of numbers a human reads as a sign. Nothing here
is gated on a threshold on purpose. A threshold would turn "this parameter does
something" into a calibration gate, and the pen styles are supposed to become
their own typefaces, not to track legacy's tables; the pen-vs-legacy line is
*recorded* (spec §6) so that drift is a number someone can look at.

Both sides take either a pen style (a builtin name like `serif-song`, or a path
to a .yaml) or a backend name: `legacy-kurgm` renders the peer engine at its
default font (mincho — the genre `serif-song` belongs to). A style that cannot
be loaded is a clean exit here, not one error per glyph out of N.

Scope: stroke-only by default (parts hold only the glyph itself, as in
`smoke_full.py`); `--closure` resolves the ref closure. The scope matters for a
sample taken off the dump's head: the first names are user sandboxes
(`a77uyh_*`) built entirely from `99:` refs, so in stroke-only scope they render
nothing and *both* sides come out empty — `compare` calls two empty masks an
IoU of 1.0, and a mean over such pairs reads as "the styles agree" when in fact
nothing was drawn. `empty=` counts exactly those pairs (and `err=` the glyphs
that raised, excluded from the mean with samples on stderr), so a differential
is never published over a sample that was silently blank or truncated.

Usage (the corpus path is never hard-coded: pick either GSF_DUMP or --corpus):
    python scripts/pen_style_diff.py --corpus ../data/dump_newest_only.txt \
        --a serif-song --b sans-hei --n 200 --closure
    python scripts/pen_style_diff.py --corpus <dump> --a serif-song \
        --b legacy-kurgm --n 200 --closure
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# default corpus: the environment variable (no hard-coded absolute path)
DUMP = os.environ.get("GSF_DUMP", "").strip()
MAX_ERROR_SAMPLES = 5           # per report; the count is exact, the list is a sample


def _renderer(spec: str):
    """One side as `ResolveResult -> Outline`, validated before the scan starts.

    `spec` names a pen style (builtin name or YAML path) or a backend. The order
    of the test is what makes `--b legacy-kurgm` work: a real file is a style,
    then a backend name is a backend, and anything else is a style name that
    `Style.load` either resolves or rejects by name. `legacy-kurgm` keeps
    `RenderOptions`' defaults (`font="mincho"`, `use_curve=False`), which is the
    peer `serif-song` has a genre in common with.
    """
    from glyphsmith.pen.style import Style
    from glyphsmith.protocol import Backend, RenderOptions, get_backend

    if not Path(spec).is_file() and spec in Backend.available():
        backend = get_backend(spec)
        opts = RenderOptions(backend=spec)
    else:
        Style.load(spec)                # unknown style / malformed file exits here
        backend = get_backend("pen")
        opts = RenderOptions(backend="pen", style=spec)
    return lambda result: backend.render(result, opts)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="cross-style differential report (spec §6 layer 4)")
    ap.add_argument("--corpus", default=DUMP,
                    help="path to dump_newest_only.txt (defaults to the GSF_DUMP env var)")
    ap.add_argument("--a", default="serif-song",
                    help="first side: a pen style (name or .yaml path) or a backend name")
    ap.add_argument("--b", default="sans-hei",
                    help="second side, same vocabulary as --a")
    ap.add_argument("--n", type=int, default=200, help="first N corpus names (default 200)")
    ap.add_argument("--size", type=int, default=256,
                    help="raster size for IoU and ink (default 256)")
    ap.add_argument("--closure", action="store_true",
                    help="resolve the ref closure (default stroke-only, as in smoke_full)")
    a = ap.parse_args()
    if not a.corpus:
        sys.exit("error: no corpus given\n"
                 "usage: GSF_DUMP=<dump_newest_only.txt> python scripts/pen_style_diff.py "
                 "--a <style> --b <style> [--n N] [--closure]\n"
                 "   or: python scripts/pen_style_diff.py --corpus <dump_newest_only.txt> ...")
    if a.n < 1 or a.size < 1:
        sys.exit("--n and --size must be >= 1")

    import numpy as np

    from glyphsmith.compare import compare, rasterize
    from glyphsmith.corpus import Corpus, ResolveResult
    from glyphsmith.pen.style import StyleError

    try:
        render_a, render_b = _renderer(a.a), _renderer(a.b)
        corpus = Corpus.from_dump(a.corpus)
    except (StyleError, OSError) as e:      # unknown style / unreadable corpus
        sys.exit(f"error: {e}")

    names = list(corpus.iter_names())[:a.n]
    scope = "closure" if a.closure else "stroke-only"
    ious: list[float] = []
    ink_a = ink_b = empty = err = 0
    errors: list[str] = []
    t0 = time.time()
    for name in names:
        try:
            if a.closure:
                result = corpus.resolve(name)
            else:                           # stroke-only: parts are only the glyph itself
                glyph = corpus.glyph_of(name)
                result = ResolveResult(name, glyph, {name: glyph}, [])
            oa, ob = render_a(result), render_b(result)
        except Exception as e:              # smoke convention: record, do not abort
            err += 1
            if len(errors) < MAX_ERROR_SAMPLES:
                errors.append(f"{name}: {type(e).__name__}: {e}")
            continue
        ma = np.asarray(rasterize(oa, a.size), dtype=bool)
        mb = np.asarray(rasterize(ob, a.size), dtype=bool)
        if not ma.any() and not mb.any():
            empty += 1                      # IoU 1.0 by convention: not a measurement
        ious.append(compare(oa, ob, size=a.size).iou)
        ink_a += int(ma.sum())
        ink_b += int(mb.sum())
    dt = time.time() - t0
    for s in errors:
        print(f"error sample: {s}", file=sys.stderr)
    mean = sum(ious) / len(ious) if ious else float("nan")
    print(f"a={a.a} b={a.b} scope={scope} n={len(ious)} empty={empty} err={err} "
          f"mean_iou={mean:.4f} ink_a={ink_a} ink_b={ink_b} elapsed={dt:.1f}s")


if __name__ == "__main__":
    main()
