#!/usr/bin/env python
"""Degeneracy audit for the pen backend (spec §6 layer 3): over a whole corpus,
how many strokes degrade, why, and how many draw nothing at all.

Layer 3 asks the scale question the unit suite cannot answer — the backend has
to survive every glyph of the real corpus and what it does to them has to be
attributable. A bare `err=0` answers only half of it: a stroke that silently
degrades raises nothing, and a stroke that draws nothing raises nothing either.
So this audit reports, per style:

- glyphs / strokes / err (the smoke's own vocabulary);
- degenerate (strokes whose plan `nib.should_degrade` rejects) plus a per-reason
  breakdown aggregated by the stable message prefix nib writes, with example
  glyph names per non-zero reason (a count has to be inspectable, not just
  reportable);
- empty: strokes that render no contour at all (see `pen.backend.expand_to_graph`
  for the definition — a degraded stroke whose quads all vanish and which has no
  decoration left to draw);
- warning_strokes: the counterfactual of counting `if plan.warnings` as
  degeneracy, so the size of that mistake is a measured number in the artifact;
- the plan warnings that are NOT degeneracy, in their own bucket.

That last split is the whole point of not counting `if plan.warnings` as
degeneracy: `style.plan_for` writes data-quality notices there too (`unmapped
ending code 8 at tail` — the GSF tail-name table has no code 5 or 8, about 12%
of real strokes). Merged into one number they read as a ~18% degeneracy rate
where the real one is under 1%, i.e. the audit would report the data's gaps as
the backend's defects.

Scope: stroke-only by default (parts contain only the glyph itself, exactly like
`smoke_full.py`'s default scope), `--closure` for the full ref closure. Both
print their scope, so a number is never read as the other scope's.

`--workers N ≥2` follows the house smoke pattern (one Corpus per worker, windowed
submission, per-chunk counting, so memory stays bounded); the counting logic
shares `audit_chunk` with the serial path and the two must agree, which the
sample check in tests/test_smoke.py asserts.

Usage (the corpus path is never hard-coded: pick either GSF_DUMP or --corpus):
    python scripts/pen_audit.py --corpus ../data/dump_newest_only.txt --style serif-song
    python scripts/pen_audit.py --corpus <dump> --style sans-hei --limit 20000
    GSF_DUMP=<dump> python scripts/pen_audit.py --style sans-round --closure
    python scripts/pen_audit.py --corpus <dump> --style serif-song --workers 8
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from itertools import islice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# default corpus: the environment variable (no hard-coded absolute path)
DUMP = os.environ.get("GSF_DUMP", "").strip()
PROGRESS_EVERY = 200_000        # stderr progress granularity
CHUNK = 500                     # names per worker task (as in smoke_full.py)
WINDOW_FACTOR = 4               # in-flight window = workers × WINDOW_FACTOR chunks
MAX_ERROR_SAMPLES = 20          # per report; the count is exact, the list is a sample
SAMPLES_PER_REASON = 3          # glyph names printed per non-zero degeneracy reason

# The stable message prefixes `nib._degeneracy_reasons` writes (spec §4.3.4).
# A reason is aggregated by prefix, never by whole message: the curvature notice
# carries a radius and a half-width, so its full text is per-stroke data.
DEGENERACY_REASONS = (
    "zero-length centerline",
    "non-finite centerline coordinate",
    "non-positive width profile",
    "degraded: curvature radius",
)
# plan.warnings also carries data-quality notices and dropped-datum reports.
# They are counted, but never as degeneracy (see the module docstring).
NOTICE_PREFIXES = (
    "unmapped ending code",
    "missing part",
    "raw op skipped",
    "decoration kind",
    "decoration at",
    "version ref fallback",
    "dangling ref",
)

# filled by the worker initializer (the serial path fills it in the main process)
_STATE: dict = {}


def classify(message: str) -> tuple[str, str]:
    """-> (bucket, label) for one plan warning; bucket is reason | notice | unknown.

    Aggregating by prefix is what makes the per-reason counts reviewable: the
    audit's job is to say "why", and a per-stroke string is not a reason.
    """
    for prefix in DEGENERACY_REASONS:
        if message.startswith(prefix):
            return "reason", prefix
    for prefix in NOTICE_PREFIXES:
        if message.startswith(prefix):
            return "notice", prefix
    # Nothing in the code is expected to land here; if something does, the audit
    # says so instead of filing it under a bucket that reads as understood.
    return "unknown", message.split(":")[0]


def _init_worker(dump, style, closure):
    """Per-process setup: its own Corpus, the style validated, the plan path warm.

    `Style.load` is memoised per file revision (one YAML parse, then dict
    lookups), so doing it here costs one parse per worker and turns an unusable
    style into one clean exit instead of one error per glyph out of 2.2M.
    """
    from glyphsmith.corpus import Corpus
    from glyphsmith.pen.style import Style

    _STATE["corpus"] = Corpus.from_dump(dump)
    _STATE["style"] = style
    _STATE["closure"] = closure
    Style.load(style)


def audit_chunk(names):
    """One block of names -> (Counter, error samples, reason → example glyphs).

    Serial and worker paths share this, so their totals must agree (the sample
    check in tests/test_smoke.py). The examples are what makes a non-zero reason
    count attributable: a number alone cannot be looked at, a glyph name can.
    """
    from gsf.kage2 import parse_kage2

    from glyphsmith.corpus import ResolveResult
    from glyphsmith.pen.backend import expand_to_graph

    corpus, style = _STATE["corpus"], _STATE["style"]
    counts: Counter = Counter()
    errors: list[str] = []
    examples: dict[str, list[str]] = {}
    for name in names:
        try:
            if _STATE["closure"]:
                result = corpus.resolve(name)
            else:                   # stroke-only: parts are only the glyph itself
                g = parse_kage2(corpus._data[name], name)
                result = ResolveResult(name, g, {name: g}, [])
            _graph, plans, _items, glyph_warnings, plan_counts = expand_to_graph(
                result, style)
        except Exception as e:      # smoke convention: record, do not abort
            counts["err"] += 1
            if len(errors) < MAX_ERROR_SAMPLES:
                errors.append(f"{name}: {type(e).__name__}: {e}")
            continue
        counts["glyphs"] += 1
        counts["strokes"] += plan_counts["strokes"]
        # The counterfactual the audit exists to avoid: `if plan.warnings` would
        # count every one of these as degenerate. Printed so the correction is
        # measured by the artifact, not asserted by its author.
        counts["warning_strokes"] += sum(1 for p in plans.values() if p.warnings)
        counts["degenerate"] += plan_counts["degenerate"]
        counts["empty"] += plan_counts["empty"]
        if plan_counts["degenerate"]:
            counts["degenerate_glyphs"] += 1
        # Degeneracy is per stroke: it is what one plan does at the nib. Every
        # other message is counted once per *affected glyph per label* — a glyph
        # whose expansion reports two different missing parts is one glyph with
        # missing parts, not two, and the count stays comparable with `glyphs=`.
        seen: set[str] = set()
        for message in glyph_warnings:
            bucket, label = classify(message)
            if bucket == "reason":
                continue            # counted below, per stroke
            key = f"{bucket}:{label}"
            if key not in seen:
                seen.add(key)
                counts[key] += 1
        for plan in plans.values():
            for message in plan.warnings:
                bucket, label = classify(message)
                if bucket == "reason":
                    counts[f"reason:{label}"] += 1
                    names_ = examples.setdefault(label, [])
                    if name not in names_ and len(names_) < SAMPLES_PER_REASON:
                        names_.append(name)
    return counts, errors, examples


def _buckets(counts: Counter, bucket: str) -> str:
    """`label=count` for one bucket, in a stable order (zeros included: an absent
    reason and a zero reason are the same fact, and both have to be readable)."""
    if bucket == "reason":
        return "; ".join(f"{label}={counts[f'reason:{label}']}"
                         for label in DEGENERACY_REASONS)
    found = sorted(k for k in counts if k.startswith(f"{bucket}:"))
    if not found:
        return "none"
    return "; ".join(f"{k.split(':', 1)[1]}={counts[k]}" for k in found)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="pen backend degeneracy audit (spec §6 layer 3): per-reason counts")
    ap.add_argument("--corpus", default=DUMP,
                    help="path to dump_newest_only.txt (defaults to the GSF_DUMP env var)")
    ap.add_argument("--style", default="serif-song",
                    help="pen backend style (builtin name or style file)")
    ap.add_argument("--closure", action="store_true",
                    help="resolve the ref closure (default stroke-only, as in smoke_full)")
    ap.add_argument("--limit", type=int, default=None, help="first N names only (default: all)")
    ap.add_argument("--workers", type=int, default=1,
                    help="≥2 enables the multiprocess version")
    a = ap.parse_args()
    if not a.corpus:
        sys.exit("error: no corpus given\n"
                 "usage: GSF_DUMP=<dump_newest_only.txt> python scripts/pen_audit.py "
                 "--style <style> [--limit N] [--workers N] [--closure]\n"
                 "   or: python scripts/pen_audit.py --corpus <dump_newest_only.txt> ...")
    if a.workers < 1:
        sys.exit("--workers must be >= 1")
    if a.limit is not None and a.limit < 0:
        sys.exit("--limit must be >= 0")

    scope = "closure" if a.closure else "stroke-only"
    print(f"style={a.style} scope={scope} workers={a.workers} "
          f"limit={a.limit if a.limit is not None else 'all'}", file=sys.stderr)

    # The main process builds its own corpus (workers build theirs, one each).
    # A missing file or an unusable style exits cleanly here, before the scan.
    from glyphsmith.pen.style import StyleError
    try:
        _init_worker(a.corpus, a.style, a.closure)
    except (StyleError, OSError) as e:   # unknown style / unreadable corpus
        sys.exit(f"error: {e}")
    names = list(_STATE["corpus"].iter_names())
    if a.limit is not None:
        names = names[:a.limit]
    total = len(names)
    chunks = [names[i:i + CHUNK] for i in range(0, total, CHUNK)]

    counts: Counter = Counter()
    samples: list[str] = []
    examples: dict[str, list[str]] = {}
    done = 0
    t0 = time.time()

    def tally(res):
        nonlocal done
        c_counts, c_errors, c_examples = res
        counts.update(c_counts)
        for e in c_errors:
            if len(samples) < MAX_ERROR_SAMPLES:
                samples.append(e)
        for label, names_ in c_examples.items():
            keep = examples.setdefault(label, [])
            keep += names_[:max(0, SAMPLES_PER_REASON - len(keep))]
        done += CHUNK
        if done % PROGRESS_EVERY < CHUNK:
            print(f"{min(done, total)} done, err={counts['err']}, "
                  f"{time.time() - t0:.0f}s", file=sys.stderr)

    if a.workers == 1:
        for chunk in chunks:
            tally(audit_chunk(chunk))
    else:
        from concurrent.futures import ProcessPoolExecutor
        it = iter(chunks)
        with ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker,
                                 initargs=(a.corpus, a.style, a.closure)) as ex:
            while True:             # windowed submission: bounded in-flight tasks
                window = list(islice(it, a.workers * WINDOW_FACTOR))
                if not window:
                    break
                for res in ex.map(audit_chunk, window):
                    tally(res)

    dt = time.time() - t0
    for s in samples:
        print(f"error sample: {s}", file=sys.stderr)
    rate = counts["glyphs"] / dt if dt else float("inf")
    print(f"style={a.style} scope={scope} "
          f"glyphs={counts['glyphs']} strokes={counts['strokes']} "
          f"degenerate={counts['degenerate']} "
          f"degenerate_glyphs={counts['degenerate_glyphs']} "
          f"warning_strokes={counts['warning_strokes']} "
          f"empty={counts['empty']} err={counts['err']} "
          f"elapsed={dt:.1f}s rate={rate:.0f}/s")
    print(f"degeneracy reasons (per stroke): {_buckets(counts, 'reason')}")
    if examples:                    # non-zero reasons must be inspectable, not just counted
        print("degeneracy examples: " + "; ".join(
            f"{label}: {', '.join(names_)}" for label, names_ in sorted(examples.items())))
    print(f"notices (not degeneracy, per glyph): {_buckets(counts, 'notice')}")
    if any(k.startswith("unknown:") for k in counts):
        print(f"UNCLASSIFIED warnings: {_buckets(counts, 'unknown')}")
    if counts["err"]:
        print(f"err={counts['err']}: see the error samples on stderr", file=sys.stderr)


if __name__ == "__main__":
    main()
