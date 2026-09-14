# tests/test_font_base.py
"""T7 字体基座：Shotai/select_font、FontParams（K/font/mincho/index.ts:226-356
逐字段）、df_transform（K:37-72 dfTransform）、drawers 管线占位。

期望值全部手算自源公式（报告注明核对方式；另有 node 直跑 kurgm dfTransform
的数值对拍，见 task-7-report.md）。
"""
import pytest

from gsrender.legacy_kurgm.expansion import TransformOp
from gsrender.legacy_kurgm.font import Shotai, select_font
from gsrender.legacy_kurgm.font.transform import df_transform
from gsrender.outline import Outline

# ── FontParams：默认分支（= setSize() 无参 → else 分支，K:324-352）──
# K:234 kRate=100（类字段初始化，setSize 从不触碰）；其余为 else 分支字面量。
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

# ── size==1 分支（K:304-323）。注意源码此分支【不】重置下列字段
# （kMinWidthU/K:326、kAdjustUroko2Step/K:346、kAdjustUroko2Length/K:347、
# kAdjustTateStep/K:349、kAdjustMageStep/K:351）——TS 中构造函数先跑无参
# setSize()（else 分支），故它们保持默认值；照抄该行为。
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
    # 简报规定 K_MINCHO="m"/K_GOTHIC="g"（与 corpus/golden 的 shotai 串一致；
    # kurgm shotai.ts 本体是 0/1 数值枚举，语义一一对应）
    assert (Shotai.K_MINCHO, Shotai.K_GOTHIC) == ("m", "g")


def test_select_font_fresh_instance_each_call():
    # K/font/index.ts:25-32 select() 每次返回新实例：改一个不影响另一个
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
    # 构造即等价 setSize()（无参 → else 分支），再来一次是幂等
    f = select_font(Shotai.K_MINCHO)
    f.set_size(None)
    for name, want in PARAMS_DEFAULT.items():
        assert getattr(f.params, name) == want, name


def test_params_set_size_100_is_default_branch():
    # 简报原断言 "set_size(100) 后 kRate 变化" 与源不符：K 的 setSize 只在
    # size===1 上分支（K:304），kRate 是类字段初始化（K:234）从未被 setSize
    # 触碰——100 走 else 分支 = 默认值（简报明文授权按源修正断言）。
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
    # size==1 分支不重置的五个字段保持默认（源 K:304-323 无赋值）
    for name in ("k_min_width_u", "k_adjust_uroko2_step", "k_adjust_uroko2_length",
                 "k_adjust_tate_step", "k_adjust_mage_step"):
        assert getattr(f.params, name) == PARAMS_DEFAULT[name], name
    assert f.params.k_rate == 100    # kRate 永不随 size 变


def test_params_set_size_switch_back():
    f = select_font(Shotai.K_MINCHO)
    f.set_size(1)
    f.set_size()                    # 回默认
    assert f.params.k_min_width_t == 6.0
    assert f.params.k_adjust_kakato_l == [14, 9, 5, 2, 0]


def test_font_use_curve_property():
    # K/font/index.ts:15 FontInterface 暴露 kUseCurve（可写，委托 params）
    f = select_font(Shotai.K_GOTHIC)
    assert f.k_use_curve is False
    f.k_use_curve = True
    assert f.params.k_use_curve is True


# ── df_transform（K/font/mincho/index.ts:37-72 + K/polygon.ts 变换）──
def test_df_transform_flip_y_97():
    # K:47-51：dy=y1+y2=200，reflectY → y'=-y+dy；floor 在精度 10 内部坐标上
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    df_transform(o, 97, 0, 0, 200, 200)
    assert o.contours == [[(10.0, 180.0, 0), (30.0, 180.0, 0)]]


def test_df_transform_flip_x_98():
    # K:42-46：dx=x1+x2=200，reflectX → x'=-x+dx
    o = Outline.from_contours([[(10.0, 20.0, 0), (10.0, 60.0, 0)]])
    df_transform(o, 98, 0, 0, 200, 200)
    assert o.contours == [[(190.0, 20.0, 0), (190.0, 60.0, 0)]]


def test_df_transform_rotate_99_levels():
    # K:52-70：rotate90/180/270 + translate(dx,dy)
    # a3=1（K:53-58）：dx=x1+y2=200, dy=y1-x1=0；(x,y)→(-y,x)+(dx,dy)
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    df_transform(o, 99, 0, 0, 200, 200, a3=1)
    assert o.contours == [[(180.0, 10.0, 0), (180.0, 30.0, 0)]]
    # a3=2（K:59-63）：dx=x1+x2=200, dy=y1+y2=200；(x,y)→(-x,-y)+(dx,dy)
    o = Outline.from_contours([[(10.0, 20.0, 0)]])
    df_transform(o, 99, 0, 0, 200, 200, a3=2)
    assert o.contours == [[(190.0, 180.0, 0)]]
    # a3=3（K:64-69）：dx=x1-y1=0, dy=y2+x1=200；(x,y)→(y,-x)+(dx,dy)
    o = Outline.from_contours([[(10.0, 20.0, 0)]])
    df_transform(o, 99, 0, 0, 200, 200, a3=3)
    assert o.contours == [[(20.0, 190.0, 0)]]


def test_df_transform_rect_selection():
    # K:28-34 selectPolygonsRect：仅整条落在闭矩形内的轮廓被变换
    o = Outline.from_contours([
        [(10.0, 20.0, 0)],           # 矩形内 → 变换
        [(250.0, 20.0, 0)],          # 超出 x2 → 原样
        [(10.0, 20.0, 0), (250.0, 20.0, 0)],   # 部分在内 → 整条原样
    ])
    df_transform(o, 97, 0, 0, 200, 200)
    assert o.contours == [
        [(10.0, 180.0, 0)],
        [(250.0, 20.0, 0)],
        [(10.0, 20.0, 0), (250.0, 20.0, 0)],
    ]


def test_df_transform_rect_boundary_inclusive():
    # 闭矩形：x==x2 的点在内（K:32 用 <=）
    o = Outline.from_contours([[(200.0, 20.0, 0)]])
    df_transform(o, 97, 0, 0, 200, 200)
    assert o.contours == [[(200.0, 180.0, 0)]]


def test_df_transform_floor_precision():
    # K/polygon.ts:33 _precision=10、:365-375 floor()：对内部坐标 floor，
    # 即 floor(v*10)/10。dy=y1+y2=60.75（y1=10.5, y2=50.25）→ y'=-30+60.75
    # =30.75 → 内部 307.5 floor 307 → 30.7
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
    # 与源一致：a2_opt≠0 → 无分支命中（K:42/47/52 的 && a2_opt===0）；
    # kind=99 而 a3∉{1,2,3}（K:53/59/64 内层 if）→ 静默 no-op
    o = Outline.from_contours([[(10.0, 20.0, 0)]])
    df_transform(o, 97, 0, 0, 200, 200, a2_opt=1)
    df_transform(o, 99, 0, 0, 200, 200)            # a3=0
    df_transform(o, 99, 0, 0, 200, 200, a3=1, a3_opt=1)
    assert o.contours == [[(10.0, 20.0, 0)]]


# ── drawers 管线（占位）──────────────────────────────────────────
def test_get_drawers_pipeline_smoke():
    from gsf.kage2 import parse_kage2
    from gsrender.legacy_kurgm.expansion import expand
    f = select_font(Shotai.K_MINCHO)
    g = parse_kage2("1:0:0:20:50:180:50")
    drawers = f.get_drawers(expand(g, {g.name: g}))
    assert len(drawers) == 1 and callable(drawers[0])


def test_get_drawers_transformop_applies_df_transform():
    from gsrender.legacy_kurgm.rstroke import RStroke
    # T8 起 K_GOTHIC 为真 GothicFont（RStroke 会真画轮廓）；本测试只验证
    # 分发语义，故用 a1=9（dfDrawFont case 9 无操作）的笔画占位
    f = select_font(Shotai.K_GOTHIC)
    drawers = f.get_drawers([RStroke(9, 0, 0, 20, 50, 180, 50, 0, 0, 0, 0),
                             TransformOp(97, 0, 0, 0, 200, 200)])
    assert len(drawers) == 2
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    before = [list(c) for c in o.contours]
    drawers[0](o)                     # RStroke a1=9 → case 9 无操作
    assert [list(c) for c in o.contours] == before
    drawers[1](o)                     # TransformOp → df_transform
    assert o.contours == [[(10.0, 180.0, 0), (30.0, 180.0, 0)]]


def test_get_drawers_transformop_rotates_with_a3():
    # Fix（task-7 关切 1）：TransformOp.a3 必须传进 df_transform——0:99:1 行经
    # 管线与直接调 df_transform(a3=1)（K:53-58 rotate90）结果一致，而非 no-op
    f = select_font(Shotai.K_MINCHO)
    drawers = f.get_drawers([TransformOp(99, 1, 0, 0, 200, 200)])
    o = Outline.from_contours([[(10.0, 20.0, 0), (30.0, 20.0, 0)]])
    drawers[0](o)
    assert o.contours == [[(180.0, 10.0, 0), (180.0, 30.0, 0)]]
