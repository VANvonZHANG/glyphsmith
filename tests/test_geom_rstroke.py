# tests/test_geom_rstroke.py
from gsf.model import Stroke
from glyphsmith.legacy_kurgm.geom2d import is_cross, is_cross_box
from glyphsmith.legacy_kurgm.rstroke import RStroke, stretch

def test_is_cross_basic():
    assert is_cross(0, 0, 10, 10, 0, 10, 10, 0) is True    # diagonals cross
    assert is_cross(0, 0, 10, 0, 0, 10, 10, 10) is False   # parallel

def test_is_cross_box():
    assert is_cross_box(5, 5, 15, 15, 10, 0, 10, 20) is True
    assert is_cross_box(0, 0, 4, 4, 10, 0, 10, 20) is False

def test_decompose_a2_313():
    s = RStroke.from_gsf(Stroke(a1=1, a2=313, a3=4,
                                pts=((25, 28), (24, 95))))
    assert s.a2_opt == 3 and s.a2_100 == 13
    assert s.a2_opt_1 == 3 and s.a2_opt_2 == 0 and s.a2_opt_3 == 0
    assert s.a1_opt == 0 and s.a1_100 == 1

def test_decompose_negative_a2():
    # a real dump row with a2=-1500: JS Math.floor(-1500/100)=-15, -1500%100=0
    # Python -1500//100=-15 (floor semantics agree), -1500%100=0 (same sign, so
    # they happen to agree)
    s = RStroke.from_gsf(Stroke(a1=1, a2=-1500, a3=0, pts=((0, 0), (10, 10))))
    assert s.a2_opt == -15 and s.a2_100 == 0

def test_decompose_negative_a2_nonexact():
    # JS % is a truncated remainder: -1505%100=-5, -16%10=-6, floor(-1.6)%10=-2.
    # Python's native % would give 95/4/8 — the engine differential fuzz (kurgm
    # stroke.ts run directly under node) exposed the difference, so it was
    # corrected to math.fmod (_js_mod) per the kurgm source and locked in.
    s = RStroke.from_gsf(Stroke(a1=1, a2=-1505, a3=0, pts=((0, 0), (10, 10))))
    assert (s.a2_opt, s.a2_100, s.a2_opt_1, s.a2_opt_2, s.a2_opt_3) == (-16, -5, -6, -2, -1)

def test_points_padded():
    s = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((10, 20), (30, 40))))
    assert (s.x1, s.y1, s.x2, s.y2) == (10, 20, 30, 40)
    assert (s.x3, s.y3, s.x4, s.y4) == (0, 0, 0, 0)  # missing slots padded with 0 (never read)

def test_get_control_segments():
    s = RStroke.from_gsf(Stroke(a1=6, a2=0, a3=0,
                                pts=((0, 0), (10, 10), (20, 20), (30, 30))))
    segs = s.get_control_segments()
    assert segs == [(0, 0, 10, 10), (10, 10, 20, 20), (20, 20, 30, 30)]

def test_get_box_type1():
    s = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((30, 10), (30, 90))))
    assert s.get_box() == {"minX": 30, "maxX": 30, "minY": 10, "maxY": 90}

def test_stretch_two_segment_mode():
    # K/stroke.ts:3-20 piecewise linear; the p<sp+100 branch.
    # Correction note: the brief expected 60, implying p4=dp (it missed the
    # source's +100); kurgm has p4 = dp + 100 = 210 →
    # floor((60/110)*210) = floor(114.545…) = 114.
    assert stretch(110, 10, 60, 0, 200) == 114  # p1=0,p2=110,p3=0,p4=dp+100=210

# --- lock-in tests for corrections found while reading the source ---

def test_stretch_upper_branch():
    # the else branch (p >= sp+100): p1=sp+100=150, p2=mx=250, p3=dp+100=200,
    # p4=mx=250 → floor((25/100)*(250-200)+200) = floor(212.5) = 212
    assert stretch(100, 50, 175, 0, 250) == 212

def test_get_control_segments_a1_12():
    # K/stroke.ts:92 case 12 is in the same group as case 2/3/4 (the brief's
    # unrolling omitted 12; corrected against the source)
    s = RStroke.from_gsf(Stroke(a1=12, a2=0, a3=0,
                                pts=((0, 0), (10, 10), (20, 20))))
    assert s.get_control_segments() == [(0, 0, 10, 10), (10, 10, 20, 20)]

def test_get_box_a1_6_default_entry():
    # K/stroke.ts getBox: 6/7 have no case label → the default entry, whose
    # fall-through covers x4 → x3 → x1x2 in turn (unlike getControlSegments,
    # where 6/7 are explicit cases)
    s = RStroke.from_gsf(Stroke(a1=6, a2=0, a3=0,
                                pts=((0, 0), (10, 0), (20, 0), (30, 40))))
    assert s.get_box() == {"minX": 0, "maxX": 30, "minY": 0, "maxY": 40}

def test_get_box_a1_5_default_entry():
    # a1=5 also has no case label → the default entry → x4/x3/x1x2 all included
    # (the brief's unrolling treated only 6/7 as taking default; corrected
    # against the source: every a1∉{0,1,2,3,4,99} includes all of them)
    s = RStroke.from_gsf(Stroke(a1=5, a2=0, a3=0,
                                pts=((10, 10), (20, 10), (30, 10), (40, 50))))
    assert s.get_box() == {"minX": 10, "maxX": 40, "minY": 10, "maxY": 50}

def test_stretch_zero_denominator_js_semantics():
    # K/stroke.ts:17 JS arithmetic semantics: a 0 divisor → ±Inf/NaN (IEEE-754),
    # Math.floor passes it through and nothing raises. T16 full closure smoke: 119
    # glyphs errored out entirely on a degenerate box (p2-p1=0) raising
    # ZeroDivisionError on the Python side, whereas kurgm got NaN coordinates →
    # the polygon was dropped by push and it rendered normally.
    import math
    assert math.isnan(stretch(0, 0, 50, 100, 150))    # -Inf*0 → NaN
    v = stretch(50, 0, 50, 100, 150)                   # -Inf*50+100 → -Inf
    assert math.isinf(v) and v < 0
    assert math.isnan(stretch(30, 50, 150, 0, 150))    # 0/0 → NaN
    assert stretch(30, 50, 160, 0, 150) == math.inf    # +Inf*20 → +Inf

def test_get_box_nan_poison_js_semantics():
    # K/stroke.ts getBox uses Math.min/max: any NaN operand → a NaN result (the
    # box is poisoned, which turns every coordinate of the outer stretch into NaN
    # → the polygon is dropped). Python's min compares False against NaN and
    # silently drops it to keep a finite value — the opposite semantics. This is
    # the root cause of the 84 glyphs where the T16 closure smoke found us
    # "drawing extra".
    import math
    s = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((10, 10), (20, 20))))
    s.x1 = float("nan")
    b = s.get_box()
    assert math.isnan(b["minX"]) and math.isnan(b["maxX"])
    assert b["minY"] == 10 and b["maxY"] == 20       # finite on the y side, not poisoned

def test_expand_box_nan_poison():
    # K/kage.ts getBox aggregation is the same: Math.min(200, NaN) = NaN (the
    # initial 200/0 values are copied verbatim; any part stroke box NaN → the
    # aggregate box is NaN → the outer stretch is all NaN)
    import math
    from glyphsmith.legacy_kurgm.expansion import _box
    st = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((10, 10), (20, 20))))
    st.x1 = float("nan")
    b = _box([st])
    assert math.isnan(b["minX"]) and math.isnan(b["maxX"])
