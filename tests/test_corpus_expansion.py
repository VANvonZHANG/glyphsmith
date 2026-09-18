# tests/test_corpus_expansion.py
"""T5：Corpus 流式装载 + resolve 闭包 + ref 展开（affine/stretch/TransformOp）。"""
import itertools
import textwrap
from pathlib import Path

import pytest

from glyphsmith.corpus import Corpus, UnknownGlyphError
from glyphsmith.legacy_kurgm.expansion import CycleError, TransformOp, expand

REAL_DUMP = Path("/home/zhangfan/Project/20260909_KAGE/data/dump_newest_only.txt")

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
    # @版本兜底：ref 指向 base@N，语料只有 base → 闭包含 base，发 fallback 警告。
    p = tmp_path / "v.gsf"
    p.write_text("gsf/1\nglyph base\nstroke line head flat tail flat (0,0)->(200,10)\n\n"
                 "glyph user\nref base@1 box(0,20,100,120)\n", encoding="utf-8")
    c = Corpus.from_gsf(p)
    r = c.resolve("user")
    assert set(r.parts) == {"user", "base"}
    assert any("base@1" in w and "-> base" in w for w in r.warnings)
    items = expand(r.glyph, r.parts)          # expand 侧同款 @ 兜底
    assert len(items) == 1
    assert (items[0].x1, items[0].y1, items[0].x2, items[0].y2) == (0.0, 20.0, 100.0, 25.0)


def test_diamond_shared_part_no_false_cycle(tmp_path):
    # 菱形依赖（两部件共用同一子部件）不是环：已完成的共享部件重访应跳过而非报环。
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
    assert len(expand(r.glyph, r.parts)) == 2  # shared 被引用两次 → 2 笔画


def test_expand_affine_mapping(corpus):
    r = corpus.resolve("target")
    items = expand(r.glyph, r.parts)
    first = items[0]           # part-a 的 (0,0)->(200,10) 映射进 box(0,20,100,120)
    assert (first.x1, first.y1) == (0.0, 20.0)
    assert (first.x2, first.y2) == (100.0, 25.0)   # y'=20+10*(120-20)/200=25


def test_expand_transform_op():
    from gsf.kage2 import parse_kage2
    g = parse_kage2("1:0:2:20:40:180:40$0:99:1:0:0:200:200")
    items = expand(g, {g.name: g})
    assert isinstance(items[1], TransformOp) and items[1].kind == 99


def test_expand_transform_op_carries_a3():
    # Fix（task-7 关切 1）：0:N 行的 cols[2]（= 源 a3_100）必须进 TransformOp.a3，
    # 否则 kind=99 的旋转档在 drawers 管线里退化为 a3=0 → df_transform no-op
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
    g = parse_kage2("0:1:0:0:0:0:0$1:0:2:20:40:180:40")  # 未知 type-0 行 → RawOp
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
    # 冒烟口径：语法坏块跳过，不中断整体装载（其余好块全部入库）。
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
    # 真实 dump 格式（head -50 抽样核对）：表头 `name | related | data` +
    # '+/-' 分隔线（无 '|'，字段数<3 自然跳过）+ 数据行三列、空格 padding。
    p = tmp_path / "d.txt"
    p.write_text(
        f"{'name':^72}|{'related':^9}|{'data':^50}\n"
        + "-" * 72 + "+" + "-" * 9 + "+" + "-" * 50 + "\n"
        + _dump_line("top", "u3013", "99:0:0:0:0:100:100:shared:0:0:0$1:0:0:10:10:90:90")
        + _dump_line("shared", "u3013", "1:0:0:0:0:200:10"),
        encoding="utf-8")
    c = Corpus.from_dump(p)
    assert set(c.iter_names()) == {"top", "shared"}   # 表头/分隔线不入库
    r = c.resolve("top")
    assert set(r.parts) == {"top", "shared"}
    assert r.warnings == []
    items = expand(r.glyph, r.parts)
    assert len(items) == 2
    assert (items[0].x2, items[0].y2) == (100.0, 5.0)  # 200*100/200, 10*100/200


def test_glyph_cache_bounded(tmp_path):
    # T16：全量冒烟（222 万字形）会把 parse 缓存推到 ~3.5GB/进程（实测
    # ~1.6KB/字形）；超 _CACHE_LIMIT 整体清空，行为透明（仍可解析，缓存只
    # 影响性能）。
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\n" + "".join(
        f"glyph g{i}\nstroke line head flat tail flat (10,10)->(100,60)\n\n"
        for i in range(10)), encoding="utf-8")
    c = Corpus.from_gsf(p)
    c._CACHE_LIMIT = 3                     # 注入小上限验证封顶语义
    for i in range(10):
        assert c.glyph_of(f"g{i}").name == f"g{i}"
        assert len(c._cache) <= 3


@pytest.mark.skipif(not REAL_DUMP.exists(), reason="真实 dump 不在本机")
def test_from_dump_real_sample(tmp_path):
    # 只取真实文件前 50 行（318MB 全量不入测试），校验行格式兼容与可解析性。
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


# ── T16 全量冒烟发现：self@N 历史快照自引用是假环 ──
# dump 中 94 例 CycleError 全部形如 glyph X 引用 X@N（历史版本快照）。
# newest-only 语料没有 X@N 行；@版本兜底回退到 X 自身 → 假 CycleError，
# 而 kurgm 精确匹配查不到即跳过（桥接验证：94 例修复后指纹全等）。
# 真自引用（ref X 无 @）仍是环，契约不变。

def test_self_snapshot_ref_not_false_cycle(tmp_path):
    # X 引用 X@1 + 自有笔画：不是环——X@1 按悬空处理，笔画照常展开
    from gsf.kage2 import parse_kage2
    g = parse_kage2("99:0:0:0:0:100:100:X@1:0:0:0$1:0:0:10:10:90:90", "X")
    warns: list[str] = []
    items = expand(g, {"X": g}, warns)       # parts 只有自身（冒烟口径）
    assert len(items) == 1
    assert any("X@1" in w for w in warns)


def test_exact_self_ref_still_cycle(tmp_path):
    # 真自引用（无 @）环契约不变
    from gsf.kage2 import parse_kage2
    g = parse_kage2("99:0:0:0:0:100:100:X:0:0:0", "X")
    with pytest.raises(CycleError):
        expand(g, {"X": g})


def test_resolve_self_snapshot_dangling(tmp_path):
    # closure 口径同规则：resolve 不抛 CycleError，X@1 记悬空警告
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
    # 非自身 @ 兜底契约不变（T5）：A 引 base@1，base 在库 → 仍回退
    p = tmp_path / "vf.gsf"
    p.write_text("gsf/1\nglyph base\nstroke line head flat tail flat (0,0)->(200,10)\n\n"
                 "glyph A\nref base@1 box(0,20,100,120)\n", encoding="utf-8")
    c = Corpus.from_gsf(p)
    r = c.resolve("A")
    assert set(r.parts) == {"A", "base"}
    assert any("base@1 -> base" in w for w in r.warnings)
