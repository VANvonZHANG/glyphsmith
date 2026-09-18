# tests/test_font_base.py
"""T7 font base: Shotai/select_font, FontParams (field by field from
K/font/mincho/index.ts:226-356), df_transform (K:37-72 dfTransform), and the
drawers pipeline placeholder.

All expected values are hand-computed from the source formulas (the report
notes how they were checked; there is also a numerical differential against
kurgm's dfTransform run directly under node, see task-7-report.md).
"""
import pytest

from glyphsmith.legacy_kurgm.expansion import TransformOp
from glyphsmith.legacy_kurgm.font import Shotai, select_font
from glyphsmith.legacy_kurgm.font.transform import df_transform
from glyphsmith.outline import Outline

# ── FontParams: default branch (= setSize() with no argument → else, K:324-352) ──
# K:234 kRate=100 (a class-field initializer setSize never touches); the rest are
# else-branch literals.
PARAMS_DEFAULT = dict(
    k_rate=100,
    k_min_width_y=2.0,        # K:325
    k_min_width_u=2.0,        # K:326
    k_min_width_t=6.0,        # K:327
    k_width=5.0,              # K:328
    k_kakato=3.0,             # K:329
    k_l2r_dfatten=1.1,        # K:330
    k_mage=10.0,              # K:331
    k_use_curve=False,        # K:332
    k_adjust_kakato_l=[14, 9, 5, 2, 0],    # K:334
    k_adjust_kakato_r=[8, 6, 4, 2],        # K:335
    k_adjust_kakato_range_x=20,            # K:336
    k_adjust_kakato_range_y=[1, 19, 24, 30],   # K:337
    k_adjust_kakato_step=3,                # K:338
    k_adjust_uroko_x=[24, 20, 16, 12],     # K:340
    k_adjust_uroko_y=[12, 11, 9, 8],       # K:341
    k_adjust_uroko_length=[22, 36, 50],    # K:342
    k_adjust_uroko_length_step=3,          # K:343
    k_adjust_uroko_line=[22, 26, 30],      # K:344
    k_adjust_uroko2_step=3,                # K:346
    k_adjust_uroko2_length=40,             # K:347
    k_adjust_tate_step=4,                  # K:349
    k_adjust_mage_step=5,                  # K:351
)

# ── size==1 branch (K:304-323). Note the source does NOT reset the following
# fields here (kMinWidthU/K:326, kAdjustUroko2Step/K:346, kAdjustUroko2Length/
# K:347, kAdjustTateStep/K:349, kAdjustMageStep/K:351) — in TS the constructor
# runs the argument-less setSize() first (the else branch), so they keep their
# default values; that behaviour is copied verbatim.
PARAMS_SIZE1_OVERRIDE = dict(
    k_min_width_y=1.2,        # K:305
    k_min_width_t=3.6,        # K:306
    k_width=3.0,              # K:307
    k_kakato=1.8,             # K:308
    k_l2r_dfatten=1.1,        # K:309
    k_mage=6.0,               # K:310
    k_use_curve=False,        # K:311
    k_adjust_kakato_l=[8, 5, 3, 1, 0],     # K:313
    k_adjust_kakato_r=[4, 3, 2, 1],        # K:314
    k_adjust_kakato_range_x=12,            # K:315
    k_adjust_kakato_range_y=[1, 11, 14, 18],   # K:316
    k_adjust_kakato_step=3,                # K:317
    k_adjust_uroko_x=[14, 12, 9, 7],       # K:319
    k_adjust_uroko_y=[7, 6, 5, 4],         # K:320
    k_adjust_uroko_length=[13, 21, 30],    # K:321
    k_adjust_uroko_length_step=3,          # K:322
    k_adjust_uroko_line=[13, 15, 18],      # K:323
)
PARAMS_SIZE1 = {**PARAMS_DEFAULT, **PARAMS_SIZE1_OVERRIDE}


# ── Shotai / select_font ─────────────────────────────────────────
def test_select_font_shotai():
    f = select_font(Shotai.K_MINCHO)
    assert f.shotai == Shotai.K_MINCHO
    g = select_font(Shotai.K_GOTHIC)
    assert g.shotai == Shotai.K_GOTHIC


def test_shotai_values_are_corpus_strings():
    # The brief mandates K_MINCHO="m"/K_GOTHIC="g" (matching the corpus/golden
    # shotai strings; kurgm shotai.ts itself is a 0/1 numeric enum, in
    # one-to-one correspondence)
    assert (Shotai.K_MINCHO, Shotai.K_GOTHIC) == ("m", "g")


def test_select_font_fresh_instance_each_call():
    # K/font/index.ts:25-32 select() returns a fresh instance each time: changing
    # one does not affect the other
    a, b = select_font(Shotai.K_MINCHO), select_font(Shotai.K_MINCHO)
    assert a is not b
    a.set_size(1)
    assert b.params.k_min_width_t == 6.0
    assert select_font(Shotai.K_GOTHIC).params.k_min_width_t == 6.0


def test_select_font_unknown_shotai():
    with pytest.raises(ValueError):
        select_font("x")


# ── FontParams ───────────────────────────────────────────────────
def test_params_defaults_from_source():
    f = select_font(Shotai.K_MINCHO)
    for name, want in PARAMS_DEFAULT.items():
        assert getattr(f.params, name) == want, name


def test_params_set_size_none_is_default():
    # Construction already equals setSize() (no argument → else branch); doing it
    # again is idempotent
    f = select_font(Shotai.K_MINCHO)
    f.set_size(None)
    for name, want in PARAMS_DEFAULT.items():
        assert getattr(f.params, name) == want, name


def test_params_set_size_100_is_default_branch():
    # The brief's original assertion "kRate changes after set_size(100)" does not
    # match the source: K's setSize branches only on size===1 (K:304), and kRate is
    # a class-field initializer (K:234) never touched by setSize — 100 takes the
    # else branch = default values (the brief explicitly authorises correcting
    # assertions against the source).
    f = select_font(Shotai.K_MINCHO)
    f.set_size(100)
    assert f.params.k_rate == 100
    for name, want in PARAMS_DEFAULT.items():
        assert getattr(f.params, name) == want, name


def test_params_set_size_1():
    f = select_font(Shotai.K_MINCHO)
    f.set_size(1)
    for name, want in PARAMS_SIZE1.items():
        assert getattr(f.params, name) == want, name
    # the five fields the size==1 branch does not reset keep their defaults (no
    # assignment in source K:304-323)
    for name in ("k_min_width_u", "k_adjust_uroko2_step", "k_adjust_uroko2_length",
                 "k_adjust_tate_step", "k_adjust_mage_step"):
        assert getattr(f.params, name) == PARAMS_DEFAULT[name], name
    assert f.params.k_rate == 100    # kRate never varies with size


def test_params_set_size_switch_back():
    f = select_font(Shotai.K_MINCHO)
    f.set_size(1)
    f.set_size()                    # back to the default
    assert f.params.k_min_width_t == 6.0
    assert f.params.k_adjust_kakato_l == [14, 9, 5, 2, 0]


def test_font_use_curve_property():
    # K/font/index.ts:15 FontInterface exposes kUseCurve (writable, delegates to params)
    f = select_font(Shotai.K_GOTHIC)
    assert f.k_use_curve is False
    f.k_use_curve = True
    assert f.params.k_use_curve is True


# ── df_transform (K/font/mincho/index.ts:37-72 + the K/polygon.ts transforms) ──
def test_df_transform_flip_y_97():
    # K:47-51: dy=y1+y2=200, reflectY → y'=-y+dy; floor acts on 10×-precision internal coords
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    df_transform(o, 97, 0, 0, 200, 200)
    assert o.contours == [[(10.0, 180.0, 0), (30.0, 180.0, 0)]]


def test_df_transform_flip_x_98():
    # K:42-46: dx=x1+x2=200, reflectX → x'=-x+dx
    o = Outline.from_contours([[(10.0, 20.0, 0), (10.0, 60.0, 0)]])
    df_transform(o, 98, 0, 0, 200, 200)
    assert o.contours == [[(190.0, 20.0, 0), (190.0, 60.0, 0)]]


def test_df_transform_rotate_99_levels():
    # K:52-70: rotate90/180/270 + translate(dx,dy)
    # a3=1 (K:53-58): dx=x1+y2=200, dy=y1-x1=0; (x,y)→(-y,x)+(dx,dy)
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    df_transform(o, 99, 0, 0, 200, 200, a3=1)
    assert o.contours == [[(180.0, 10.0, 0), (180.0, 30.0, 0)]]
    # a3=2 (K:59-63): dx=x1+x2=200, dy=y1+y2=200; (x,y)→(-x,-y)+(dx,dy)
    o = Outline.from_contours([[(10.0, 20.0, 0)]])
    df_transform(o, 99, 0, 0, 200, 200, a3=2)
    assert o.contours == [[(190.0, 180.0, 0)]]
    # a3=3 (K:64-69): dx=x1-y1=0, dy=y2+x1=200; (x,y)→(y,-x)+(dx,dy)
    o = Outline.from_contours([[(10.0, 20.0, 0)]])
    df_transform(o, 99, 0, 0, 200, 200, a3=3)
    assert o.contours == [[(20.0, 190.0, 0)]]


def test_df_transform_rect_selection():
    # K:28-34 selectPolygonsRect: only a contour lying wholly inside the closed
    # rectangle is transformed
    o = Outline.from_contours([
        [(10.0, 20.0, 0)],           # inside → transformed
        [(250.0, 20.0, 0)],          # beyond x2 → unchanged
        [(10.0, 20.0, 0), (250.0, 20.0, 0)],   # partly inside → whole contour unchanged
    ])
    df_transform(o, 97, 0, 0, 200, 200)
    assert o.contours == [
        [(10.0, 180.0, 0)],
        [(250.0, 20.0, 0)],
        [(10.0, 20.0, 0), (250.0, 20.0, 0)],
    ]


def test_df_transform_rect_boundary_inclusive():
    # closed rectangle: a point with x==x2 is inside (K:32 uses <=)
    o = Outline.from_contours([[(200.0, 20.0, 0)]])
    df_transform(o, 97, 0, 0, 200, 200)
    assert o.contours == [[(200.0, 180.0, 0)]]


def test_df_transform_floor_precision():
    # K/polygon.ts:33 _precision=10, :365-375 floor(): floor the internal
    # coordinates, i.e. floor(v*10)/10. dy=y1+y2=60.75 (y1=10.5, y2=50.25) →
    # y'=-30+60.75=30.75 → internal 307.5 floor 307 → 30.7
    o = Outline.from_contours([[(20.0, 30.0, 0)]])
    df_transform(o, 97, 0, 10.5, 100, 50.25)
    assert o.contours == [[(20.0, 30.7, 0)]]


def test_df_transform_preserves_off_flag():
    o = Outline.from_contours([[(10.0, 20.0, 1), (30.0, 20.0, 0)]])
    df_transform(o, 97, 0, 0, 200, 200)
    assert [(p[2]) for p in o.contours[0]] == [1, 0]


def test_df_transform_invalid_kind_raises():
    o = Outline.from_contours([[(10.0, 20.0, 0)]])
    for kind in (0, 96, 100, -1):
        with pytest.raises(ValueError):
            df_transform(o, kind, 0, 0, 200, 200)


def test_df_transform_silent_noop_cases():
    # as in the source: a2_opt≠0 → no branch matches (the && a2_opt===0 at
    # K:42/47/52); kind=99 with a3∉{1,2,3} (the inner if at K:53/59/64) → silent
    # no-op
    o = Outline.from_contours([[(10.0, 20.0, 0)]])
    df_transform(o, 97, 0, 0, 200, 200, a2_opt=1)
    df_transform(o, 99, 0, 0, 200, 200)            # a3=0
    df_transform(o, 99, 0, 0, 200, 200, a3=1, a3_opt=1)
    assert o.contours == [[(10.0, 20.0, 0)]]


# ── drawers pipeline (placeholder) ───────────────────────────────
def test_get_drawers_pipeline_smoke():
    from gsf.kage2 import parse_kage2
    from glyphsmith.legacy_kurgm.expansion import expand
    f = select_font(Shotai.K_MINCHO)
    g = parse_kage2("1:0:0:20:50:180:50")
    drawers = f.get_drawers(expand(g, {g.name: g}))
    assert len(drawers) == 1 and callable(drawers[0])


def test_get_drawers_transformop_applies_df_transform():
    from glyphsmith.legacy_kurgm.rstroke import RStroke
    # Since T8 K_GOTHIC is a real GothicFont (RStroke really draws contours);
    # this test only checks the dispatch semantics, so a stroke with a1=9
    # (dfDrawFont case 9 is a no-op) stands in
    f = select_font(Shotai.K_GOTHIC)
    drawers = f.get_drawers([RStroke(9, 0, 0, 20, 50, 180, 50, 0, 0, 0, 0),
                             TransformOp(97, 0, 0, 0, 200, 200)])
    assert len(drawers) == 2
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    before = [list(c) for c in o.contours]
    drawers[0](o)                     # RStroke a1=9 → case 9 no-op
    assert [list(c) for c in o.contours] == before
    drawers[1](o)                     # TransformOp → df_transform
    assert o.contours == [[(10.0, 180.0, 0), (30.0, 180.0, 0)]]


def test_get_drawers_transformop_rotates_with_a3():
    # Fix (task-7 concern 1): TransformOp.a3 must reach df_transform — the
    # 0:99:1 row through the pipeline gives the same result as calling
    # df_transform(a3=1) directly (K:53-58 rotate90), rather than a no-op
    f = select_font(Shotai.K_MINCHO)
    drawers = f.get_drawers([TransformOp(99, 1, 0, 0, 200, 200)])
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    drawers[0](o)
    assert o.contours == [[(180.0, 10.0, 0), (180.0, 30.0, 0)]]


# ── Port gap found by the T16 full smoke: push_polygon's JS floor semantics ──

def test_push_polygon_nan_dropped_not_raised():
    # K/polygons.ts:31-47: polygon.floor() first (Math.floor(NaN)=NaN, no
    # raise), then the per-point isNaN check drops the whole polygon. Python's
    # math.floor(NaN/±Inf) raises → 27 glyphs in the full dump (zackroy-san_*
    # etc.) errored out entirely while kurgm could render them. Hard rule 1,
    # translated directly: NaN/±Inf pass through floor; NaN polygons are
    # dropped; Inf is not intercepted (source behaviour, left to the fingerprint
    # layer to report non-finite).
    from glyphsmith.legacy_kurgm.font.gothic_cd import push_polygon

    o = Outline()
    push_polygon(o, [(10, 10, 0), (50, 10, 0), (50, 50, 0)])            # normal
    push_polygon(o, [(float("nan"), 10, 0), (50, 10, 0), (50, 50, 0)])  # NaN → dropped
    push_polygon(o, [(float("inf"), 10, 0), (50, 10, 0), (50, 50, 0)])  # Inf → kept
    assert len(o.contours) == 2
    assert o.contours[0] == [(10.0, 10.0, 0), (50.0, 10.0, 0), (50.0, 50.0, 0)]
    assert o.contours[1][0][0] == float("inf")
