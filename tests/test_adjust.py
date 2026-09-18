# tests/test_adjust.py
"""T9 Mincho adjust 七连管：方向性断言（期望值不硬编码）。

字段名对齐源 index.ts:10-26 MinchoAdjustedStroke（snake_case 化）：
kirikuchiAdjustment/tateAdjustment/haneAdjustment/urokoAdjustment/
kakatoAdjustment/mageAdjustment → *_adjustment。

测试几何先经 node 直跑 kurgm adjustStrokes 对拍确认非常值（简报原始
uroko/tate 用例对拍为 0 vs 0（空断言），已换成真触发几何；kirikuchi 的
a2=32 在 kage 列序是第 2 列，即 "2:32:0:..."）。
"""
from gsf.kage2 import parse_kage2
from glyphsmith.legacy_kurgm.expansion import expand
from glyphsmith.legacy_kurgm.font import MinchoFont, Shotai, select_font
from glyphsmith.legacy_kurgm.rstroke import RStroke


def _adjusted(data: str):
    g = parse_kage2(data)
    font = select_font(Shotai.K_MINCHO)
    return font.adjust_strokes(expand(g, {g.name: g}))


def _strokes(data: str):
    g = parse_kage2(data)
    return expand(g, {g.name: g})


# ── 打包初值（index.ts:370-383）────────────────────────────────
def test_adjust_packed_defaults_survive_without_neighbor():
    # 孤笔无邻居：六字段保持 a2/a3 的 100s/1000s 位打包初值。
    # a2=2134 → opt_1=1, opt_2=2, opt_3=0；a3=1024 → opt=10, opt_1=0, opt_2=1
    rs = RStroke(1, 2134, 1024, 50, 20, 50, 180, 0, 0, 0, 0)
    [adj] = select_font(Shotai.K_MINCHO).adjust_strokes([rs])
    assert adj.kirikuchi_adjustment == rs.a2_opt_1
    assert adj.tate_adjustment == rs.a2_opt_2 + rs.a2_opt_3 * 10
    assert adj.hane_adjustment == rs.a3_opt_1
    assert adj.uroko_adjustment == rs.a3_opt
    assert adj.kakato_adjustment == rs.a3_opt
    assert adj.mage_adjustment == rs.a3_opt_2


# ── adjustHane（K:395-440）─────────────────────────────────────
def test_adjust_hane_varies_with_neighbor():
    # 竖钩 (1::4) 左侧竖笔远近影响 hane 值（近竖 hane 更大）
    near = _adjusted("1:0:4:60:20:60:180$1:0:0:50:20:50:180")
    far = _adjusted("1:0:4:60:20:60:180$1:0:0:10:20:10:180")
    assert near[0].hane_adjustment != far[0].hane_adjustment


# ── adjustMage（K:442-481）─────────────────────────────────────
def test_adjust_mage_varies_with_near_horizontal():
    # 折れ (3::) 的横段近旁有等高横 → mage 增大；远离 → 不变
    close = _adjusted("3:0:0:50:50:100:50:150:50$1:0:0:60:53:140:53")
    far = _adjusted("3:0:0:50:50:100:50:150:50$1:0:0:60:90:140:90")
    assert close[0].mage_adjustment > far[0].mage_adjustment


# ── adjustTate（K:483-511）─────────────────────────────────────
def test_adjust_tate_varies_with_near_vertical():
    # 贴近双竖互相加粗提示（tate 增），远离不变
    close = _adjusted("1:0:0:50:20:50:180$1:0:0:52:20:52:180")
    far = _adjusted("1:0:0:50:20:50:180$1:0:0:120:20:120:180")
    assert close[0].tate_adjustment > far[0].tate_adjustment


# ── adjustKakato（K:513-536）───────────────────────────────────
def test_adjust_kakato_varies_with_stroke_below():
    # 竖脚 (1::{13,23}) 下方有横穿越碰撞箱 → kakato 缩短档生效
    hit = _adjusted("1:0:13:60:30:60:150$1:0:0:50:160:90:160")
    miss = _adjusted("1:0:13:60:30:60:150$1:0:0:50:190:90:190")
    assert hit[0].kakato_adjustment != miss[0].kakato_adjustment


# ── adjustUroko（K:538-564）────────────────────────────────────
def test_adjust_uroko_varies_with_space():
    # 横 (1::0) 末端被近竖穿越 → uroko 收缩；远竖不触发
    tight = _adjusted("1:0:0:40:100:180:100$1:0:2:170:80:170:110")
    loose = _adjusted("1:0:0:40:100:180:100$1:0:2:5:80:5:110")
    assert tight[0].uroko_adjustment > loose[0].uroko_adjustment


# ── adjustUroko2（K:566-609）───────────────────────────────────
def test_adjust_uroko2_varies_with_density():
    # 平行密集横线互相施压 → uroko 按密度收缩；孤横不受力
    dense = _adjusted("1:0:0:40:100:180:100$1:0:0:40:95:180:95$1:0:0:40:105:180:105")
    lone = _adjusted("1:0:0:40:100:180:100")
    assert dense[0].uroko_adjustment > lone[0].uroko_adjustment


# ── adjustKirikuchi（K:611-634）────────────────────────────────
def test_adjust_kirikuchi_only_with_horizontal_at_start():
    # 2:32:0 且 x1>x2、y1<y2 且起笔被横穿过 → kirikuchi=1
    hit = _adjusted("2:32:0:100:50:80:70:60:100$1:0:0:60:50:140:50")
    miss = _adjusted("2:32:0:100:50:80:70:60:100$1:0:0:60:90:140:90")
    assert hit[0].kirikuchi_adjustment > miss[0].kirikuchi_adjustment


# ── get_drawers 分发（index.ts:356-361）───────────────────────
def test_mincho_get_drawers_draws_strokes():
    from glyphsmith.outline import Outline

    font = select_font(Shotai.K_MINCHO)
    assert isinstance(font, MinchoFont)
    o = Outline()
    for d in font.get_drawers(_strokes("1:0:0:40:100:180:100$1:0:2:170:80:170:110")):
        d(o)
    assert len(o.contours) > 0        # T10 起 cd 表真画（golden m: 见 T10）


def test_mincho_adjust_strokes_passthrough_transformop():
    # 0:97/98/99 行不在 adjust 范围（源中 a1_100=0 对七函数全惰性），原样透传
    from glyphsmith.legacy_kurgm.expansion import TransformOp

    items = _strokes("1:0:0:40:100:180:100$0:99:1:40:100:180:100")
    assert len(items) == 2 and isinstance(items[1], TransformOp)
    out = select_font(Shotai.K_MINCHO).adjust_strokes(items)
    assert out[1] is items[1]
