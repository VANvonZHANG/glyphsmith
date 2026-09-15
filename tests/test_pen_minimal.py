# tests/test_pen_minimal.py
from gsf.kage2 import parse_kage2

from gsrender.compare import compare
from gsrender.legacy_kurgm import LegacyKurgmBackend
from gsrender.protocol import get_backend


class _R:
    def __init__(self, glyph):
        self.name, self.glyph = glyph.name, glyph
        self.parts, self.warnings = {glyph.name: glyph}, []


def test_horizontal_line_quad():
    g = parse_kage2("1:0:0:20:50:180:50")
    out = get_backend("pen-minimal").render(_R(g))
    c = out.contours[0]
    assert {(round(x), round(y)) for x, y, _ in c} == {(20, 46), (180, 46), (180, 54), (20, 54)}


def test_butt_cap_is_quad():
    g = parse_kage2("1:0:0:20:50:180:50")
    out = get_backend("pen-minimal").render(_R(g))
    assert len(out.contours[0]) == 4


def test_reuses_expansion_for_refs():
    part = parse_kage2("1:0:0:0:0:200:10", "part")
    g = parse_kage2("99:0:0:0:20:100:120:part:0:0")
    r = _R(g)
    r.parts[part.name] = part   # 简报笔误修正：_R 只装顶层字形，ref 部件须入 parts（简报里 part 已解析但未接线；逐字形态下 parts={"": g} → expand 跳过 ref → 0 轮廓，本测试对简报参考实现必失败，见 task-15-report「简报测试 1 处接线笔误」）
    out = get_backend("pen-minimal").render(r)
    assert len(out.contours) >= 1


def test_differs_from_legacy():
    g = parse_kage2("1:0:2:20:40:180:40$1:12:13:40:40:40:160")
    pen = get_backend("pen-minimal").render(_R(g))
    leg = LegacyKurgmBackend().render(_R(g))
    assert compare(pen, leg).iou < 1.0


# ── 补充测试（简报之外，锁定 v1 预留行为的边界）──────────────────────

def test_registered_by_default():
    # 注册在 gsrender/__init__ 导入 pen_minimal（T8 教训：不 import 则 get_backend 抛 ValueError）
    from gsrender.protocol import Backend
    assert "pen-minimal" in Backend.available()


def test_ref_affine_placement():
    # 复用 expand 的 affine：part 段 (0,0)-(200,10) 经 ref box (0,20)-(100,120)
    # 映射为 (0,20)-(100,25)（x'=x/2, y'=20+y/2），等宽 8 描边四边形落在
    # 该段 ±4 法向邻域内（x∈[0,100]±0.2，y∈[20,25]±4）
    part = parse_kage2("1:0:0:0:0:200:10", "part")
    g = parse_kage2("99:0:0:0:20:100:120:part:0:0")
    r = _R(g)
    r.parts[part.name] = part
    out = get_backend("pen-minimal").render(r)
    assert len(out.contours) == 1
    xs = [x for c in out.contours for x, _, _ in c]
    ys = [y for c in out.contours for _, y, _ in c]
    assert min(xs) >= -1 and max(xs) <= 101
    assert min(ys) >= 15 and max(ys) <= 29


def test_multisegment_stroke_one_quad_per_segment():
    # a1=2 折线：控制段 x1x2、x2x3 → 每段一个四边形
    g = parse_kage2("2:0:0:20:20:180:20:100:120")
    out = get_backend("pen-minimal").render(_R(g))
    assert len(out.contours) == 2
    assert all(len(c) == 4 for c in out.contours)


def test_render_separated_per_stroke():
    g = parse_kage2("1:0:0:20:50:180:50$1:0:0:20:80:180:80")
    outs = get_backend("pen-minimal").render_separated(_R(g))
    assert len(outs) == 2
    assert all(len(o.contours) == 1 for o in outs)


def test_transform_op_rows_skipped():
    # TransformOp 自 T7 起为 6 字段 NamedTuple，仍是 tuple 子类 → isinstance 判定成立
    g = parse_kage2("1:0:0:20:50:180:50$0:99:0:0:0:200:200:rot:0:0")
    out = get_backend("pen-minimal").render(_R(g))
    assert len(out.contours) == 1


# ── 终审 I2：warnings 回写与 legacy 对齐 ────────────────────────────

def test_raw_op_warnings_parity_with_legacy():
    # 含 RawOp 行（101: 等白名单外线种）的字形两后端渲染后 warnings 应一致：
    # raw op skipped 警告两后端都出现。此前 pen-minimal 不向 expand 传
    # warnings，换后端后这类警告静默丢失。
    g = parse_kage2("101:0:0:0:0:0:0$1:0:0:20:50:180:50", "rawg")
    leg, pen = _R(g), _R(g)
    LegacyKurgmBackend().render(leg)
    get_backend("pen-minimal").render(pen)
    assert leg.warnings, "legacy 应产生 raw op skipped 警告"
    assert pen.warnings == leg.warnings
    assert any("raw op skipped" in w for w in pen.warnings)


def test_render_separated_writes_back_warnings():
    # render_separated 同样回写（missing part / raw op 类警告不悬空）
    g = parse_kage2("101:0:0:0:0:0:0$1:0:0:20:50:180:50", "rawg")
    r = _R(g)
    get_backend("pen-minimal").render_separated(r)
    assert any("raw op skipped" in w for w in r.warnings)
