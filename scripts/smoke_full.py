#!/usr/bin/env python
# scripts/smoke_full.py —— M4 acceptance: full dump, zero crashes + non-empty rate
"""Full smoke: render every glyph in the dump, counting ok/empty/err only, with
nothing written to disk.

Two scopes (both numbers go into the report):
- stroke-only (default): parts contain only the glyph itself and ref rows do not
  go through the closure — a pure-ref glyph is necessarily empty; this measures
  "the renderer does not crash on arbitrary data";
- --closure: corpus.resolve(name), the full closure — this measures "every glyph
  ends up with a non-empty outline".

--limit N   smoke only the first N names (a deterministic subset, handy for a
            quick check);
--style S   pen backend style (builtin name or style file, default serif-song);
            the other backends ignore it. Degeneracy numbers are not this
            script's job: see scripts/pen_audit.py (spec §6 layer 3);
--workers N ≥2 runs the multiprocess version (each worker builds its own Corpus;
            windowed submission keeps memory bounded); the counting logic shares
            _render_chunk with the serial version and the numbers must agree
            (checked against 20000 stroke-only / 5000 closure cases).

Usage (the corpus path is never hard-coded: pick either the GSF_DUMP environment
variable or --corpus; with neither, the script errors out):
    GSF_DUMP=<dump_newest_only.txt> python scripts/smoke_full.py --limit 20000
    python scripts/smoke_full.py --limit 20000 --workers 8 --corpus <dump>
    python scripts/smoke_full.py --limit 5000 --closure --workers 8 --corpus <dump>
    python scripts/smoke_full.py --corpus <dump>          # the full 2.22M (about 2 minutes)
    python scripts/smoke_full.py --closure --workers 16 --corpus <dump>
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from itertools import islice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# default corpus: the environment variable (no hard-coded absolute path)
DUMP = os.environ.get("GSF_DUMP", "").strip()
PROGRESS_EVERY = 200_000        # stderr progress granularity
CHUNK = 500                     # names per worker task
WINDOW_FACTOR = 4               # in-flight window = workers × WINDOW_FACTOR chunks

# filled by the worker initializer (the serial version fills it in the main process)
_STATE: dict = {}


def _init_worker(dump, backend_name, closure, style):
    from importlib import import_module

    from glyphsmith.batch import _BACKEND_MODULES
    from glyphsmith.corpus import Corpus
    from glyphsmith.protocol import get_backend

    mod = _BACKEND_MODULES.get(backend_name)
    if mod is not None:                 # unknown names are left to get_backend's ValueError
        import_module(mod)
    if backend_name == "pen":
        # One load per worker, before the scan: Style.load is memoised per file
        # revision, and an unusable style is one clean exit rather than one error
        # per glyph. Only the pen backend has styles; the others ignore --style.
        from glyphsmith.pen.style import Style
        Style.load(style)
    _STATE["corpus"] = Corpus.from_dump(dump)
    _STATE["backend"] = get_backend(backend_name)
    _STATE["backend_name"] = backend_name
    _STATE["closure"] = closure
    _STATE["style"] = style


def _render_chunk(names):
    """Count one block of names → (ok, empty, err, error samples). Serial/multiprocess shared."""
    from gsf.kage2 import parse_kage2
    from glyphsmith.corpus import ResolveResult
    from glyphsmith.protocol import RenderOptions

    corpus, backend = _STATE["corpus"], _STATE["backend"]
    opts = RenderOptions(backend=_STATE["backend_name"], style=_STATE["style"])
    ok = empty = err = 0
    errors: list[str] = []
    for name in names:
        try:
            if _STATE["closure"]:
                out = backend.render(corpus.resolve(name), opts)
            else:                       # stroke-only scope: parts are only itself
                g = parse_kage2(corpus._data[name], name)
                out = backend.render(ResolveResult(name, g, {name: g}, []), opts)
            if out.contours:
                ok += 1
            else:
                empty += 1
        except Exception as e:          # smoke convention: record, do not abort
            err += 1
            if len(errors) < 3:
                errors.append(f"{name}: {type(e).__name__}: {e}")
    return ok, empty, err, errors


def main() -> None:
    ap = argparse.ArgumentParser(
        description="GSF renderer full smoke (zero crashes + non-empty rate, no writes)")
    ap.add_argument("--corpus", default=DUMP,
                    help="path to dump_newest_only.txt (defaults to the GSF_DUMP env var)")
    ap.add_argument("--backend", default="legacy-kurgm")
    ap.add_argument("--style", default="serif-song",
                    help="pen backend style (builtin name or style file); "
                         "the other backends ignore it")
    ap.add_argument("--closure", action="store_true",
                    help="full-closure scope (default stroke-only)")
    ap.add_argument("--limit", type=int, default=None,
                    help="first N names only (default: all)")
    ap.add_argument("--workers", type=int, default=1,
                    help="≥2 enables the multiprocess version")
    a = ap.parse_args()
    if not a.corpus:
        sys.exit("error: no corpus given\n"
                 "usage: GSF_DUMP=<dump_newest_only.txt> python scripts/smoke_full.py "
                 "[--limit N] [--workers N] [--closure]\n"
                 "   or: python scripts/smoke_full.py --corpus <dump_newest_only.txt>")
    if a.workers < 1:
        sys.exit("--workers must be >= 1")
    if a.limit is not None and a.limit < 0:
        sys.exit("--limit must be >= 0")

    scope = "closure" if a.closure else "stroke-only"
    print(f"smoke scope={scope} backend={a.backend} style={a.style} "
          f"workers={a.workers} limit={a.limit if a.limit is not None else 'all'}",
          file=sys.stderr)

    # Name list: the main process builds its own corpus (workers build their
    # own, one init each). Configuration errors (unknown backend / style,
    # missing file) exit cleanly here, leaving no raw traceback.
    from glyphsmith.pen.style import StyleError
    try:
        _init_worker(a.corpus, a.backend, a.closure, a.style)
    except (ValueError, FileNotFoundError, StyleError) as e:
        sys.exit(f"error: {e}")
    names = list(_STATE["corpus"].iter_names())
    if a.limit is not None:
        names = names[:a.limit]
    total = len(names)
    chunks = [names[i:i + CHUNK] for i in range(0, total, CHUNK)]

    ok = empty = err = done = 0
    samples: list[str] = []
    t0 = time.time()

    def tally(res):
        nonlocal ok, empty, err, done, samples
        c_ok, c_empty, c_err, c_errors = res
        ok += c_ok
        empty += c_empty
        err += c_err
        for e in c_errors:
            if len(samples) < 3:
                samples.append(e)
        done += CHUNK
        if done % PROGRESS_EVERY < CHUNK:
            print(f"{min(done, total)} done, err={err}, {time.time() - t0:.0f}s",
                  file=sys.stderr)

    if a.workers == 1:
        for chunk in chunks:
            tally(_render_chunk(chunk))
    else:
        from concurrent.futures import ProcessPoolExecutor
        it = iter(chunks)
        with ProcessPoolExecutor(max_workers=a.workers,
                                 initializer=_init_worker,
                                 initargs=(a.corpus, a.backend, a.closure,
                                           a.style)) as ex:
            while True:                  # windowed submission: bounded in-flight tasks
                window = list(islice(it, a.workers * WINDOW_FACTOR))
                if not window:
                    break
                for res in ex.map(_render_chunk, window):
                    tally(res)

    dt = time.time() - t0
    for s in samples:
        print(f"error sample: {s}", file=sys.stderr)
    rate = total / dt if dt else float("inf")
    print(f"scope={scope} backend={a.backend} style={a.style} workers={a.workers} "
          f"total={total} ok={ok} empty={empty} err={err} "
          f"elapsed={dt:.1f}s rate={rate:.0f}/s")


if __name__ == "__main__":
    main()
