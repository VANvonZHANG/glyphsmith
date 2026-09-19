# src/glyphsmith/batch.py
"""multiprocessing batch rendering: whole corpus → outdir/*.svg + stats.

Where the brief's skeleton was adapted to reality (public signature and stats
semantics unchanged):
- windowed submission: ProcessPoolExecutor.map submits every task at once
  (source `fs = [self.submit(fn, *args) for args in zip(*iterables)]`), so
  2.22M glyphs would mean 2.22M pending work items (each carrying a data
  string), GBs resident; submitting in _WINDOW-sized batches keeps memory
  bounded;
- per-worker backend registration: under the spawn start method a child does
  not inherit the parent's registry, so _BACKEND_MODULES maps a name to the
  module imported inside the worker (harmless under fork too);
- filename sanitising shares the same helper as cli._safe_filename (T14 review
  M2);
- the worker uses a real ResolveResult (the brief skeleton's four-field
  equivalent _R).

Smoke convention: any per-glyph exception returns an err tuple counted by
errors, without aborting the batch.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from importlib import import_module
from itertools import islice
from pathlib import Path

# backend name → module where its registration lives (imported in the worker)
_BACKEND_MODULES = {
    "legacy-kurgm": "glyphsmith.legacy_kurgm",
    "pen-minimal": "glyphsmith.pen_minimal",
    "pen": "glyphsmith.pen.backend",
}
_WINDOW = 4096                       # tasks submitted per batch (in-flight memory ceiling)
_CHUNKSIZE = 64                      # ex.map dispatch granularity (the brief's value)


def _render_one(job):
    """Render one glyph (worker process). Any exception → (name, "", True, err), never raised."""
    name, data, backend_name, style = job
    from gsf.kage2 import parse_kage2
    from glyphsmith.corpus import ResolveResult
    from glyphsmith.protocol import RenderOptions, get_backend

    try:
        mod = _BACKEND_MODULES.get(backend_name)
        if mod is not None:
            import_module(mod)       # unknown names are left to get_backend's ValueError
        g = parse_kage2(data, name)
        out = get_backend(backend_name).render(
            ResolveResult(name, g, {name: g}, []),  # smoke convention: parts are only itself
            RenderOptions(backend=backend_name, style=style))
        return name, out.to_svg(), not out.contours, ""
    except Exception as e:                       # smoke convention: record, do not abort
        return name, "", True, f"{type(e).__name__}: {e}"


def batch_render(corpus_path, outdir, *, backend="legacy-kurgm",
                 workers=4, dump=False, style="serif-song") -> dict:
    """Batch-render a whole corpus → outdir/<safe-name>.svg, returning a stats
    dict.

    stats = {"rendered", "errors", "empty"}: rendered includes glyphs with empty
    contours (empty is a subset of it); a per-glyph render exception and a
    per-file write OSError are both counted in errors without aborting the batch
    (the batch convention; a failed outdir mkdir raises OSError straight out and
    the CLI layer turns it into exit 2, consistent with the M2 per-glyph
    contract).

    `style` is the pen backend's style name or path (ignored by the other
    backends); the CLI validates it before the batch starts, so an unusable one
    is exit 2 rather than one error per glyph.
    """
    from glyphsmith.cli import _safe_filename
    from glyphsmith.corpus import Corpus

    corpus = Corpus.from_dump(corpus_path) if dump else Corpus.from_gsf(corpus_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)    # OSError bubbles up → CLI exit 2
    # raw kage2 data strings go into the workers (parsing happens worker-side;
    # the parent process caches no glyphs). The style travels in the job: a
    # worker process inherits nothing but what is pickled to it.
    jobs = ((n, corpus._data[n], backend, style) for n in corpus.iter_names())
    stats = {"rendered": 0, "errors": 0, "empty": 0}

    def absorb(name, svg, empty, err) -> None:
        if not err:
            try:
                (outdir / f"{_safe_filename(name)}.svg").write_text(
                    svg, encoding="utf-8")
            except OSError as e:                 # single-file write failure: counted, not fatal
                err = f"OSError: {e}"
        if err:
            stats["errors"] += 1
            return
        stats["rendered"] += 1
        if empty:
            stats["empty"] += 1

    if workers <= 1:
        for t in map(_render_one, jobs):
            absorb(*t)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            while True:                          # windowed submission keeps memory bounded
                window = list(islice(jobs, _WINDOW))
                if not window:
                    break
                for t in ex.map(_render_one, window, chunksize=_CHUNKSIZE):
                    absorb(*t)
    return stats
