#!/usr/bin/env python
"""Relation coverage of the pen relational graph on real glyphs (spec §9-3).

Acceptance item 3 asks for two things the unit tests cannot give: the graph is
exportable as JSON (`glyphsmith graph <name> --corpus <dump>`), and its relation
vocabulary is *exercised by real glyphs* — `crosses`, `tee` and `parallel`
occur, not only `meets`. The graph tests build their skeletons by hand, so they
prove the rules, not the coverage.

Scope (the recorded numbers depend on it, so the script prints it):

- a slice of the dump by raw line index (`--offset`/`--limit`, default
  200,000–220,000 — 20,000 names), never the whole corpus: this is a coverage
  sample, and a whole-corpus run would answer a different question;
- **own strokes** per glyph: the rows the glyph itself carries, not its ref
  closure. A pure `99:` reference has no strokes of its own and is reported in
  neither `glyphs` nor the relation counts (the graph of its *parts* is those
  parts' own graph, counted where they are defined);
- `RStroke`s exactly as the CLI's `graph` command builds them, so the counting
  is the export's own vocabulary: `pen.graph.build` over the glyph's strokes.

What is counted: for each relation kind, the number of glyphs in which it
occurs at least once (`tee=432` = "432 glyphs carry a tee"), plus the edge
total, which is larger because a glyph can carry several edges of one kind.

Exit status: 0 when `meets`, `tee`, `crosses` and `parallel` all occur in the
slice (the acceptance bar), 1 when one is missing — a slice with no `tee` is a
failed sample, not a passed run.

Usage (the corpus path is never hard-coded: pick either GSF_DUMP or --corpus):
    python scripts/pen_graph_coverage.py --corpus ../data/dump_newest_only.txt
    python scripts/pen_graph_coverage.py --corpus <dump> --offset 0 --limit 5000
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from itertools import islice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# default corpus: the environment variable (no hard-coded absolute path)
DUMP = os.environ.get("GSF_DUMP", "").strip()
DEFAULT_OFFSET = 200_000        # the slice docs/pen-backend.md records
DEFAULT_LIMIT = 20_000
# The relations the vocabulary fixes (pen.style.REL_WORDS); `near` is a metric
# query on top of the graph, not an edge kind, so it is not an edge to count.
RELATIONS = ("meets", "tee", "crosses", "parallel")
REQUIRED = ("tee", "crosses", "parallel")     # spec §9-3's "not only meets"
EXAMPLES = 3


def slice_names(path: str, offset: int, limit: int) -> list:
    """The names of one dump slice, in file order, at raw line indices.

    Same three-column format `Corpus.from_dump` reads (name | related | data);
    separator and header lines are skipped rather than counted, and `names=` in
    the report makes a slice that picked up such a line visible.
    """
    names = []
    with open(path, encoding="utf-8") as f:
        for line in islice(f, offset, offset + limit):
            cells = line.split("|")
            if len(cells) < 3:
                continue
            name = cells[0].strip()
            if not name or name == "name":
                continue
            names.append(name)
    return names


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=DUMP,
                    help="dump_newest_only.txt (or set GSF_DUMP)")
    ap.add_argument("--offset", type=int, default=DEFAULT_OFFSET,
                    help="first dump line of the slice (default 200000)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="dump lines in the slice (default 20000)")
    args = ap.parse_args(argv)
    if not args.corpus:
        sys.exit("give --corpus or set GSF_DUMP")
    if args.offset < 0 or args.limit <= 0:
        sys.exit("--offset must be >= 0 and --limit >= 1")

    from gsf.model import Stroke

    from glyphsmith.corpus import Corpus
    from glyphsmith.legacy_kurgm.rstroke import RStroke
    from glyphsmith.pen import graph as graph_mod

    corpus = Corpus.from_dump(args.corpus)
    names = slice_names(args.corpus, args.offset, args.limit)
    glyphs = 0
    glyph_counts = Counter()                 # glyphs in which a kind occurs
    edge_counts = Counter()
    examples: list = []
    for name in names:
        strokes = [RStroke.from_gsf(op) for op in corpus.glyph_of(name).ops
                   if isinstance(op, Stroke)]
        if not strokes:
            continue                         # a pure ref has no strokes of its own
        glyphs += 1
        kinds = {e.kind for e in graph_mod.build(strokes).edges}
        edge_counts.update(e.kind for e in graph_mod.build(strokes).edges)
        for kind in kinds:
            glyph_counts[kind] += 1
        if "tee" in kinds and len(examples) < EXAMPLES:
            examples.append(name)

    print(f"scope=own-strokes slice={args.offset}:{args.offset + args.limit} "
          f"names={len(names)} glyphs={glyphs} "
          + " ".join(f"{k}={glyph_counts[k]}" for k in RELATIONS)
          + f" edges={sum(edge_counts.values())}")
    print("first examples (glyphs carrying a tee): "
          + (", ".join(examples) if examples else "none"))
    missing = [k for k in REQUIRED if not glyph_counts[k]]
    if missing:
        print(f"coverage incomplete: no {'/'.join(missing)} in this slice",
              file=sys.stderr)
        return 1
    print("coverage: tee, crosses and parallel all occur")
    return 0


if __name__ == "__main__":
    sys.exit(main())
