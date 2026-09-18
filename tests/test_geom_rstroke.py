# tests/test_geom_rstroke.py
from gsf.model import Stroke
from glyphsmith.legacy_kurgm.geom2d import is_cross, is_cross_box
from glyphsmith.legacy_kurgm.rstroke import RStroke, stretch

def test_is_cross_basic():
    assert is_cross(0, 0, 10, 10, 0, 10, 10, 0) is True    # 对角线相交
    assert is_cross(0, 0, 10, 0, 0, 10, 10, 10) is False   # 平行

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
    # dump 真实行 a2=-1500：JS Math.floor(-1500/100)=-15, -1500%100=0
    # Python -1500//100=-15（floor 语义一致），-1500%100=0（同号恰好一致）
    s = RStroke.from_gsf(Stroke(a1=1, a2=-1500, a3=0, pts=((0, 0), (10, 10))))
    assert s.a2_opt == -15 and s.a2_100 == 0

def test_decompose_negative_a2_nonexact():
    # JS % 为截断余数：-1505%100=-5、-16%10=-6、floor(-1.6)%10=-2。
    # Python 原生 % 会给出 95/4/8 —— 引擎对照 fuzz（node 直跑 kurgm stroke.ts）
    # 已暴露该差异，按 kurgm 源修正为 math.fmod（_js_mod）并锁定。
    s = RStroke.from_gsf(Stroke(a1=1, a2=-1505, a3=0, pts=((0, 0), (10, 10))))
    assert (s.a2_opt, s.a2_100, s.a2_opt_1, s.a2_opt_2, s.a2_opt_3) == (-16, -5, -6, -2, -1)

def test_points_padded():
    s = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((10, 20), (30, 40))))
    assert (s.x1, s.y1, s.x2, s.y2) == (10, 20, 30, 40)
    assert (s.x3, s.y3, s.x4, s.y4) == (0, 0, 0, 0)  # NaN 位以 0 占位（不被读）

def test_get_control_segments():
    s = RStroke.from_gsf(Stroke(a1=6, a2=0, a3=0,
                                pts=((0, 0), (10, 10), (20, 20), (30, 30))))
    segs = s.get_control_segments()
    assert segs == [(0, 0, 10, 10), (10, 10, 20, 20), (20, 20, 30, 30)]

def test_get_box_type1():
    s = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((30, 10), (30, 90))))
    assert s.get_box() == {"minX": 30, "maxX": 30, "minY": 10, "maxY": 90}

def test_stretch_two_segment_mode():
    # K/stroke.ts:3-20 分段线性；p<sp+100 分支。
    # 修正说明：简报原期望 60 隐含 p4=dp（漏掉源码的 +100）；kurgm 源
    # p4 = dp + 100 = 210 → floor((60/110)*210) = floor(114.545…) = 114。
    assert stretch(110, 10, 60, 0, 200) == 114  # p1=0,p2=110,p3=0,p4=dp+100=210

# --- 以下为源码核对修正的锁定测试（K/stroke.ts 逐函数核对补充） ---

def test_stretch_upper_branch():
    # else 分支（p >= sp+100）：p1=sp+100=150, p2=mx=250, p3=dp+100=200, p4=mx=250
    # → floor((25/100)*(250-200)+200) = floor(212.5) = 212
    assert stretch(100, 50, 175, 0, 250) == 212

def test_get_control_segments_a1_12():
    # K/stroke.ts:92 case 12 与 case 2/3/4 同组（简报展开漏写 12，按源修正）
    s = RStroke.from_gsf(Stroke(a1=12, a2=0, a3=0,
                                pts=((0, 0), (10, 10), (20, 20))))
    assert s.get_control_segments() == [(0, 0, 10, 10), (10, 10, 20, 20)]

def test_get_box_a1_6_default_entry():
    # K/stroke.ts getBox：6/7 无 case 标签 → default 入口，fall-through
    # 依次覆盖 x4 → x3 → x1x2（与 getControlSegments 不同，那里 6/7 是显式 case）
    s = RStroke.from_gsf(Stroke(a1=6, a2=0, a3=0,
                                pts=((0, 0), (10, 0), (20, 0), (30, 40))))
    assert s.get_box() == {"minX": 0, "maxX": 30, "minY": 0, "maxY": 40}

def test_get_box_a1_5_default_entry():
    # a1=5 亦无 case 标签 → default 入口 → x4/x3/x1x2 全含（简报原展开只把
    # 6/7 视作走 default，按源修正：凡 a1∉{0,1,2,3,4,99} 均全含）
    s = RStroke.from_gsf(Stroke(a1=5, a2=0, a3=0,
                                pts=((10, 10), (20, 10), (30, 10), (40, 50))))
    assert s.get_box() == {"minX": 10, "maxX": 40, "minY": 10, "maxY": 50}

def test_stretch_zero_denominator_js_semantics():
    # K/stroke.ts:17 JS 算术语义：0 除数 → ±Inf/NaN（IEEE-754），Math.floor
    # 穿透，不抛异常。T16 全量闭包冒烟：119 字形因退化 box（p2-p1=0）在
    # Python 侧抛 ZeroDivisionError 整字形 err，kurgm 则 NaN 坐标 → 多边形
    # 在 push 丢弃照常渲染。
    import math
    assert math.isnan(stretch(0, 0, 50, 100, 150))    # -Inf*0 → NaN
    v = stretch(50, 0, 50, 100, 150)                   # -Inf*50+100 → -Inf
    assert math.isinf(v) and v < 0
    assert math.isnan(stretch(30, 50, 150, 0, 150))    # 0/0 → NaN
    assert stretch(30, 50, 160, 0, 150) == math.inf    # +Inf*20 → +Inf

def test_get_box_nan_poison_js_semantics():
    # K/stroke.ts getBox 用 Math.min/max：任一 NaN 操作数 → 结果 NaN（box
    # 被污染，继而把外层 stretch 的所有坐标变 NaN → 多边形丢弃）。Python
    # min 遇 NaN 比较恒 False，会静默丢弃 NaN 保有限值——语义相反。
    # T16 闭包冒烟 84 字形「我们多画」的根因。
    import math
    s = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((10, 10), (20, 20))))
    s.x1 = float("nan")
    b = s.get_box()
    assert math.isnan(b["minX"]) and math.isnan(b["maxX"])
    assert b["minY"] == 10 and b["maxY"] == 20       # y 侧有限不受染

def test_expand_box_nan_poison():
    # K/kage.ts getBox 聚合同款：Math.min(200, NaN) = NaN（初值 200/0 照抄，
    # 任一部件 stroke box NaN → 聚合 box NaN → 外层 stretch 全 NaN）
    import math
    from glyphsmith.legacy_kurgm.expansion import _box
    st = RStroke.from_gsf(Stroke(a1=1, a2=0, a3=0, pts=((10, 10), (20, 20))))
    st.x1 = float("nan")
    b = _box([st])
    assert math.isnan(b["minX"]) and math.isnan(b["maxX"])
