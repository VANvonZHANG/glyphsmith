# scripts/sample_dump.py —— reproducible sampling (the prototype of `glyphsmith sample`)
"""Dump sampler + residual-junk filtering (the corpus side of T12
cross-validation).

sample(): dump_newest_only.txt → a reproducible random sample of (name, data).
split_residual_junk(): split a sample into (clean, excluded) by "contains a
residual junk row" — the clean side goes into fingerprint differential testing,
the excluded side is disclosed only.

History of the predicate: before gsftool `2c5dea2` this filtered the "whitelist
gap" (every row with an integer first column outside the literal stroke-type
whitelist {"1","2","3","4","6","7"}, including a1-bitfield rows such as 101/103
— about 1,514 glyphs). After the fix a1-bitfield rows are legal Strokes and the
filter narrowed to genuine residual junk rows — rows whose first column parses
as int and is ∉ {0,99} but which the stroke-field guard makes us downgrade to
RawOp (9 measured across the whole corpus: 999 pseudo-references / 116p
coordinate typos / -1:0:0:0 four-column rows / truncated rows). kurgm interprets
such rows as strokes while we skip them; the difference is inherent to the two
sides' semantics.
"""
import json
import random
import sys
from pathlib import Path

from gsf.kage2 import parse_kage2
from gsf.model import RawOp


def sample(dump: Path, n: int, seed: int) -> list:
    """A reproducible random sample of glyphs with strokes (not pure 99 rows), as (name, data)."""
    rng = random.Random(seed)
    picked = []
    for line in Path(dump).open(encoding="utf-8"):
        cells = line.split("|")
        if len(cells) < 3 or not cells[0].strip():
            continue
        data = cells[2].strip()
        if data and not data.startswith("99:"):
            picked.append((cells[0].strip(), data))
    return rng.sample(picked, min(n, len(picked)))


def _int_like(s: str) -> bool:
    try:
        int(s)
    except ValueError:
        return False
    return True


def split_residual_junk(cases: list) -> tuple:
    """Split a sample by "contains a residual junk row" → (clean, excluded).

    A residual junk row = a row whose first column parses as int and is
    ∉ {0,99} but which lands as RawOp in gsf.kage2 (the stroke-field guard is
    not satisfied): the `2:...:116p` coordinate typo, the `1:0:`/`1:0`/`1`
    truncated rows, the `-1:0:0:0` four-column row, the `999:...:name`
    pseudo-reference — 9 measured across the whole corpus. kurgm interprets
    such rows as strokes (with NaN coordinates) while we skip them, producing a
    false mismatch unrelated to port quality.

    History of the predicate (corrected on review): in the T12 era this filter
    also excluded `0:` rows (on the conservative assumption that "0 rows take a
    different channel and the two sides do not meet"). That mechanism has been
    disproved: the two sides judge `0:` rows alike — kage `kage.ts:205` builds a
    Stroke for any a1≠99, `0:97/98/99` are applied as a transform by the font
    layer (our side: `expand` yields a TransformOp, which `legacy_kurgm`'s
    `_transform_drawer` applies; the kurgm side's bridge does the same), and the
    remaining `0:` rows are no-ops on both sides. The 10 glyphs that used to be
    excluded measured 0/10 mismatches → the filter narrowed to the "9 known
    malformed rows" class and no longer excludes `0:` rows.

    Note: since gsftool 2c5dea2, a1-bitfield rows (101/103/106/107 etc.) are
    legal Strokes and no longer enter this filter (the old predicate excluded
    about 1,514 glyphs on that basis; for the dedicated acceptance see
    tests/test_cross_engine.py::test_gap_glyphs_now_match_kurgm).
    """
    clean, excluded = [], []
    for case in cases:
        (excluded if has_residual_junk(case[1]) else clean).append(case)
    return clean, excluded


def has_residual_junk(data: str) -> bool:
    """Whether data contains a residual junk row (a RawOp whose first column
    parses as int and is ∉ {0,99}); the two sides interpret it differently."""
    return any(isinstance(op, RawOp) and _int_like(op.cols[0])
               and int(op.cols[0]) not in (0, 99)
               for op in parse_kage2(data).ops)


def first_junk_row(data: str) -> str:
    """The first residual junk row (for disclosing excluded cases); empty if none."""
    for op in parse_kage2(data).ops:
        if isinstance(op, RawOp) and _int_like(op.cols[0]) \
                and int(op.cols[0]) not in (0, 99):
            return ":".join(op.cols[:8])
    return ""


if __name__ == "__main__":
    dump = Path(sys.argv[1])
    n, seed = int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for name, data in sample(dump, n, seed):
        print(json.dumps({"name": name, "data": data}, ensure_ascii=False))
