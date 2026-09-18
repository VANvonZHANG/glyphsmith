# tests/test_corpus_expansion.py
"""T5: Corpus streaming load + resolve closure + ref expansion (affine/stretch/TransformOp)."""
import itertools
import os
import textwrap
from pathlib import Path

import pytest

from glyphsmith.corpus import Corpus, UnknownGlyphError
from glyphsmith.legacy_kurgm.expansion import CycleError, TransformOp, expand

# The real dump is an external dataset, neither shipped with the repo nor
# hard-coded: when GSF_DUMP is unset/missing the cases that use it are skipped
# (not failed).
GSF_DUMP = os.environ.get("GSF_DUMP", "").strip()
REAL_DUMP = Path(GSF_DUMP) if GSF_DUMP else None

GSF_CORPUS = textwrap.dedent("""\
    gsf/1
    glyph part-a
    stroke line head flat tail flat (0,0)->(200,10)

    glyph target
    ref part-a box(0,20,100,120)
    stroke line head flat tail flat (10,10)->(50,60)

    glyph cyclic-a
    ref cyclic-b box(0,0,100,100)

    glyph cyclic-b
    ref cyclic-a box(0,0,100,100)
""")


@pytest.fixture
def corpus(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text(GSF_CORPUS, encoding="utf-8")
    return Corpus.from_gsf(p)


def test_resolve_closure(corpus):
    r = corpus.resolve("target")
    assert r.name == "target"
    assert set(r.parts) == {"target", "part-a"}
    assert r.warnings == []


def test_unknown_glyph(corpus):
    with pytest.raises(UnknownGlyphError) as ei:
        corpus.resolve("nope")
    assert ei.value.name == "nope"


def test_dangling_ref_warns(tmp_path):
    p = tmp_path / "d.gsf"
    p.write_text("gsf/1\nglyph g\nref missing-part box(0,0,100,100)\n", encoding="utf-8")
    c = Corpus.from_gsf(p)
    r = c.resolve("g")
    assert any("missing-part" in w for w in r.warnings)


def test_cycle_detected(corpus):
    with pytest.raises(CycleError) as ei:
        corpus.resolve("cyclic-a")
    assert set(ei.value.path) == {"cyclic-a", "cyclic-b"}


def test_self_cycle(tmp_path):
    p = tmp_path / "s.gsf"
    p.write_text("gsf/1\nglyph ouro\nref ouro box(0,0,100,100)\n", encoding="utf-8")
    c = Corpus.from_gsf(p)
    with pytest.raises(CycleError) as ei:
        c.resolve("ouro")
    assert ei.value.path == ["ouro"]


def test_version_ref_fallback(tmp_path):
    # @version fallback: the ref points at base@N and the corpus only has base →
    # the closure contains base and a fallback warning is emitted.
    p = tmp_path / "v.gsf"
    p.write_text("gsf/1\nglyph base\nstroke line head flat tail flat (0,0)->(200,10)\n\n"
                 "glyph user\nref base@1 box(0,20,100,120)\n", encoding="utf-8")
    c = Corpus.from_gsf(p)
    r = c.resolve("user")
    assert set(r.parts) == {"user", "base"}
    assert any("base@1" in w and "-> base" in w for w in r.warnings)
    items = expand(r.glyph, r.parts)          # the same @ fallback on the expand side
    assert len(items) == 1
    assert (items[0].x1, items[0].y1, items[0].x2, items[0].y2) == (0.0, 20.0, 100.0, 25.0)


def test_diamond_shared_part_no_false_cycle(tmp_path):
    # A diamond dependency (two parts sharing one sub-part) is not a cycle: a
    # revisit to a finished shared part is skipped rather than reported as one.
    p = tmp_path / "dm.gsf"
    p.write_text(textwrap.dedent("""\
        gsf/1
        glyph top
        ref left box(0,0,100,200)
        ref right box(100,0,200,200)

        glyph left
        ref shared box(0,0,100,100)

        glyph right
        ref shared box(0,0,100,100)

        glyph shared
        stroke line head flat tail flat (10,10)->(90,90)
        """), encoding="utf-8")
    c = Corpus.from_gsf(p)
    r = c.resolve("top")
    assert set(r.parts) == {"top", "left", "right", "shared"}
    assert r.warnings == []
    assert len(expand(r.glyph, r.parts)) == 2  # shared is referenced twice → 2 strokes


def test_expand_affine_mapping(corpus):
    r = corpus.resolve("target")
    items = expand(r.glyph, r.parts)
    first = items[0]           # part-a's (0,0)->(200,10) mapped into box(0,20,100,120)
    assert (first.x1, first.y1) == (0.0, 20.0)
    assert (first.x2, first.y2) == (100.0, 25.0)   # y'=20+10*(120-20)/200=25


def test_expand_transform_op():
    from gsf.kage2 import parse_kage2
    g = parse_kage2("1:0:2:20:40:180:40$0:99:1:0:0:200:200")
    items = expand(g, {g.name: g})
    assert isinstance(items[1], TransformOp) and items[1].kind == 99


def test_expand_transform_op_carries_a3():
    # Fix (task-7 concern 1): cols[2] of a 0:N row (= source a3_100) must reach
    # TransformOp.a3, otherwise the kind=99 rotation level degrades to a3=0 in
    # the drawers pipeline → a df_transform no-op
    from gsf.kage2 import parse_kage2
    g = parse_kage2("1:0:2:20:40:180:40$0:99:1:0:0:200:200")
    t = expand(g, {g.name: g})[1]
    assert t.kind == 99 and t.a3 == 1
    g = parse_kage2("1:0:2:20:40:180:40$0:99:3:0:0:200:200")
    t = expand(g, {g.name: g})[1]
    assert t.kind == 99 and t.a3 == 3
    g = parse_kage2("1:0:2:20:40:180:40$0:98:0:0:0:200:200")
    t = expand(g, {g.name: g})[1]
    assert t.kind == 98 and t.a3 == 0


def test_expand_rawop_skipped():
    from gsf.kage2 import parse_kage2
    g = parse_kage2("0:1:0:0:0:0:0$1:0:2:20:40:180:40")  # unknown type-0 row → RawOp
    warns: list[str] = []
    items = expand(g, {g.name: g}, warns)
    assert len(items) == 1 and any("raw op" in w for w in warns)


def test_expand_missing_part_warns():
    from gsf.kage2 import parse_kage2
    g = parse_kage2("99:0:0:0:0:100:100:ghost:0:0:0$1:0:0:10:10:90:90", "user")
    warns: list[str] = []
    items = expand(g, {"user": g}, warns)
    assert len(items) == 1
    assert any("ghost" in w for w in warns)


def test_from_gsf_skips_bad_block(tmp_path):
    # Smoke convention: a syntactically bad block is skipped without aborting the
    # whole load (every other good block is still stored).
    p = tmp_path / "bad.gsf"
    p.write_text("gsf/1\nglyph good\nstroke line head flat tail flat (0,0)->(10,10)\n\n"
                 "glyph bad\nstroke nonsense head flat tail flat (0,0)->(10,10)\n\n"
                 "glyph good2\nstroke line head flat tail flat (0,0)->(10,10)\n",
                 encoding="utf-8")
    c = Corpus.from_gsf(p)
    assert set(c.iter_names()) == {"good", "good2"}


def test_search_and_iter_names(tmp_path):
    p = tmp_path / "s.gsf"
    p.write_text("gsf/1\nglyph part-a\nstroke line head flat tail flat (0,0)->(10,10)\n\n"
                 "glyph part-b\nstroke line head flat tail flat (0,0)->(10,10)\n\n"
                 "glyph u4e2d\nstroke line head flat tail flat (0,0)->(10,10)\n",
                 encoding="utf-8")
    c = Corpus.from_gsf(p)
    assert set(c.iter_names()) == {"part-a", "part-b", "u4e2d"}
    assert set(c.search(like="part")) == {"part-a", "part-b"}
    assert set(c.search(like="part*")) == {"part-a", "part-b"}
    assert set(c.search(src="unicode", char="中")) == {"u4e2d"}


def _dump_line(name: str, related: str, data: str) -> str:
    return f" {name:<70} | {related:<7} | {data}\n"


def test_from_dump_synthetic(tmp_path):
    # Real dump format (checked against head -50): a `name | related | data`
    # header + a '+/-' separator line (no '|', so it skips itself on <3 fields) +
    # three-column, space-padded data rows.
    p = tmp_path / "d.txt"
    p.write_text(
        f"{'name':^72}|{'related':^9}|{'data':^50}\n"
        + "-" * 72 + "+" + "-" * 9 + "+" + "-" * 50 + "\n"
        + _dump_line("top", "u3013", "99:0:0:0:0:100:100:shared:0:0:0$1:0:0:10:10:90:90")
        + _dump_line("shared", "u3013", "1:0:0:0:0:200:10"),
        encoding="utf-8")
    c = Corpus.from_dump(p)
    assert set(c.iter_names()) == {"top", "shared"}   # header/separator not stored
    r = c.resolve("top")
    assert set(r.parts) == {"top", "shared"}
    assert r.warnings == []
    items = expand(r.glyph, r.parts)
    assert len(items) == 2
    assert (items[0].x2, items[0].y2) == (100.0, 5.0)  # 200*100/200, 10*100/200


def test_glyph_cache_bounded(tmp_path):
    # T16: the full smoke (2.22M glyphs) pushes the parse cache to ~3.5GB per
    # process (measured ~1.6KB/glyph); past _CACHE_LIMIT it is cleared wholesale,
    # transparent to behaviour (parsing still works, the cache only affects
    # performance).
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\n" + "".join(
        f"glyph g{i}\nstroke line head flat tail flat (10,10)->(100,60)\n\n"
        for i in range(10)), encoding="utf-8")
    c = Corpus.from_gsf(p)
    c._CACHE_LIMIT = 3                     # inject a small limit to prove the ceiling
    for i in range(10):
        assert c.glyph_of(f"g{i}").name == f"g{i}"
        assert len(c._cache) <= 3


@pytest.mark.skipif(REAL_DUMP is None or not REAL_DUMP.is_file(),
                    reason="GSF_DUMP does not point at a real dump (skip, not fail)")
def test_from_dump_real_sample(tmp_path):
    # Take only the first 50 lines of the real file (the 318MB whole does not go
    # into a test); checks row-format compatibility and parseability.
    with REAL_DUMP.open(encoding="utf-8") as f:
        sample = list(itertools.islice(f, 50))
    p = tmp_path / "sample.txt"
    p.write_text("".join(sample), encoding="utf-8")
    c = Corpus.from_dump(p)
    names = set()
    raw: dict[str, str] = {}
    for line in sample:
        cells = line.split("|")
        if len(cells) < 3 or not cells[0].strip() or cells[0].strip() == "name":
            continue
        names.add(cells[0].strip())
        raw[cells[0].strip()] = cells[2].strip()
    assert names and set(c.iter_names()) == names
    for n in names:
        g = c.glyph_of(n)
        assert g.name == n
        assert len(g.ops) == len(raw[n].split("$"))


# ── Found by the T16 full smoke: a self@N historical snapshot is a false cycle ──
# All 94 CycleError cases in the dump look like glyph X referencing X@N (a
# historical version snapshot). A newest-only corpus has no X@N row, so the
# @version fallback fell back to X itself → a false CycleError, whereas kurgm's
# exact match finds nothing and skips (bridge-verified: all 94 fingerprints
# identical after the fix). A true self-reference (ref X with no @) is still a
# cycle; the contract is unchanged.

def test_self_snapshot_ref_not_false_cycle(tmp_path):
    # X referencing X@1 plus its own strokes: not a cycle — X@1 is treated as
    # dangling and the strokes expand as usual
    from gsf.kage2 import parse_kage2
    g = parse_kage2("99:0:0:0:0:100:100:X@1:0:0:0$1:0:0:10:10:90:90", "X")
    warns: list[str] = []
    items = expand(g, {"X": g}, warns)       # parts are only itself (smoke convention)
    assert len(items) == 1
    assert any("X@1" in w for w in warns)


def test_exact_self_ref_still_cycle(tmp_path):
    # a true self-reference (no @) is still a cycle; the contract is unchanged
    from gsf.kage2 import parse_kage2
    g = parse_kage2("99:0:0:0:0:100:100:X:0:0:0", "X")
    with pytest.raises(CycleError):
        expand(g, {"X": g})


def test_resolve_self_snapshot_dangling(tmp_path):
    # the closure scope follows the same rule: resolve does not raise
    # CycleError, and X@1 is recorded as a dangling warning
    p = tmp_path / "ss.gsf"
    p.write_text("gsf/1\nglyph X\nref X@1 box(0,0,100,100)\n"
                 "stroke line head flat tail flat (10,10)->(90,90)\n",
                 encoding="utf-8")
    c = Corpus.from_gsf(p)
    r = c.resolve("X")
    assert set(r.parts) == {"X"}
    assert any(w.startswith("dangling ref: X@1") for w in r.warnings)
    assert len(expand(r.glyph, r.parts)) == 1


def test_version_fallback_nonself_unchanged(tmp_path):
    # the non-self @ fallback contract is unchanged (T5): A references base@1 and
    # base is in the corpus → still falls back
    p = tmp_path / "vf.gsf"
    p.write_text("gsf/1\nglyph base\nstroke line head flat tail flat (0,0)->(200,10)\n\n"
                 "glyph A\nref base@1 box(0,20,100,120)\n", encoding="utf-8")
    c = Corpus.from_gsf(p)
    r = c.resolve("A")
    assert set(r.parts) == {"A", "base"}
    assert any("base@1 -> base" in w for w in r.warnings)
