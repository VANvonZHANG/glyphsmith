# tests/test_pen_minimal.py
from gsf.kage2 import parse_kage2
from gsf.model import RawOp

from glyphsmith.compare import compare
from glyphsmith.legacy_kurgm import LegacyKurgmBackend
from glyphsmith.protocol import get_backend


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
    # Brief typo corrected: _R only holds the top-level glyph, so ref parts must
    # go into parts as well (in the brief, part was parsed but never wired up;
    # in the per-glyph form parts={"": g} → expand skips the ref → 0 contours,
    # and this test necessarily fails against the brief's reference
    # implementation — see task-15-report "one wiring typo in the brief's
    # tests").
    r.parts[part.name] = part
    out = get_backend("pen-minimal").render(r)
    assert len(out.contours) >= 1


def test_differs_from_legacy():
    g = parse_kage2("1:0:2:20:40:180:40$1:12:13:40:40:40:160")
    pen = get_backend("pen-minimal").render(_R(g))
    leg = LegacyKurgmBackend().render(_R(g))
    assert compare(pen, leg).iou < 1.0


# ── Extra tests (beyond the brief, locking the edges of v1's reserved behaviour) ──

def test_registered_by_default():
    # registered because glyphsmith/__init__ imports pen_minimal (T8 lesson:
    # without the import, get_backend raises ValueError)
    from glyphsmith.protocol import Backend
    assert "pen-minimal" in Backend.available()


def test_ref_affine_placement():
    # reuses expand's affine: the part segment (0,0)-(200,10) maps through the
    # ref box (0,20)-(100,120) to (0,20)-(100,25) (x'=x/2, y'=20+y/2), and the
    # uniform-8 stroked quad falls within ±4 along the normal of that segment
    # (x∈[0,100]±0.2, y∈[20,25]±4)
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
    # a1=2 polyline: control segments x1x2, x2x3 → one quad per segment
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
    # since T7 TransformOp is a 6-field NamedTuple, still a tuple subclass → the
    # isinstance test holds
    g = parse_kage2("1:0:0:20:50:180:50$0:99:0:0:0:200:200:rot:0:0")
    out = get_backend("pen-minimal").render(_R(g))
    assert len(out.contours) == 1


# ── Final review I2: warnings write-back aligned with legacy ────────

def test_raw_op_warnings_parity_with_legacy():
    # For a glyph with a RawOp row (a junk row whose first column fails int),
    # both backends must produce the same warnings after rendering: the "raw op
    # skipped" warning appears on both. Previously pen-minimal did not pass
    # warnings to expand, so switching backends silently lost this class of
    # warning.
    # Fixture history: it used to be "101:0:0:..." — since gsftool 2c5dea2,
    # a1-bitfield rows are legal Strokes (aligned with kurgm) and no longer
    # produce a RawOp; hence the switch to a genuinely junk row `-:` (whose
    # first column fails int()).
    g = parse_kage2("-:0:0:0:0:0:0$1:0:0:20:50:180:50", "rawg")
    assert any(isinstance(op, RawOp) for op in g.ops), \
        "fixture precondition: the `-:` row must still be a RawOp (first column fails int())"
    leg, pen = _R(g), _R(g)
    LegacyKurgmBackend().render(leg)
    get_backend("pen-minimal").render(pen)
    assert leg.warnings, "legacy should produce a raw op skipped warning"
    assert pen.warnings == leg.warnings
    assert any("raw op skipped" in w for w in pen.warnings)


def test_render_separated_writes_back_warnings():
    # render_separated writes back too (missing part / raw op warnings do not go missing)
    g = parse_kage2("-:0:0:0:0:0:0$1:0:0:20:50:180:50", "rawg")
    r = _R(g)
    get_backend("pen-minimal").render_separated(r)
    assert any("raw op skipped" in w for w in r.warnings)


# ── gsftool 2c5dea2 downstream: a1-bitfield rows are no longer RawOp ──

def test_a1_opt_rows_are_strokes_now():
    # 101 = a line + the a1_100 option bits (kurgm splits a1_100/a1_opt and draws
    # it): once the parser lets it through there should be zero warnings and both
    # backends should draw the stroke. Previously the row was downgraded to RawOp
    # → both sides skipped it.
    g = parse_kage2("101:0:0:0:0:0:0$1:0:0:20:50:180:50", "optg")
    assert not any(isinstance(op, RawOp) for op in g.ops)
    leg, pen = _R(g), _R(g)
    lo = LegacyKurgmBackend().render(leg)
    po = get_backend("pen-minimal").render(pen)
    assert leg.warnings == [] and pen.warnings == []
    assert lo.contours, "legacy must draw the a1-bitfield stroke (was 0 contours)"
    assert po.contours, "pen-minimal must draw the a1-bitfield stroke"
