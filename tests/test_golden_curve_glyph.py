# tests/test_golden_curve_glyph.py
"""T11 曲线模式 + 整字 golden：mc:/gc: 子集（1120 例）与 glyph: 整字（14 例）。

- mc: = Mincho kUseCurve=True——cdDrawCurveU 曲线拟合分支（find_offcurve）
  与 off-curve 点首次进 golden；
- gc: = Gothic kUseCurve=True——gothic cd.ts 不读 kUseCurve，渲染逻辑与
  g: 相同，矩阵为受限头/尾的独立采样；T8 起一直绿但无测试锁定，本文件
  一并锁定；
- glyph: = 整字（buhin 递归展开 + stretch + 0:97/98/99 transform +
  mincho adjust 七连管），kUseCurve=False，golden id 形如
  "glyph:u6f22:u6f22:m" / "glyph:transform:r90:g"。

判据 = 指纹逐字符全等（KT/strokes.ts fingerprint：轮廓数 点数 sha1）。
ERROR 豁免逻辑同 gothic 模板：drawer 抛异常且 golden 亦为 ERROR 才豁免
（两侧同为 ERROR；一侧 ERROR 一侧正常即失败）。
"""
import pytest
from gsf.kage2 import parse_kage2
from gsrender.legacy_kurgm import LegacyKurgmBackend   # import 即注册
from gsrender.legacy_kurgm.expansion import expand
from gsrender.legacy_kurgm.fingerprint import fingerprint
from gsrender.legacy_kurgm.font import Shotai, select_font
from gsrender.outline import Outline
from tests.golden import build_cases, glyph_cases, load_golden

GOLDEN = load_golden()
CURVE_CASES = [c for c in build_cases() if c[3]]        # mc:/gc:（c[2] 为 m/g）

# glyph: 整字展开为 (id, data, shotai, use_curve, buhin, name)，data = buhin[name]
GLYPH_CASES = [
    (f"{gid}:{name}:{s}", buhin[name], s, False, buhin, name)
    for gid, buhin, names in glyph_cases()
    for s in ("m", "g")
    for name in names
]


def _render_and_check(case_id, data, shotai, use_curve, buhin, name):
    font = select_font(Shotai.K_MINCHO if shotai == "m" else Shotai.K_GOTHIC)
    font.k_use_curve = use_curve      # Font 属性（简报原文 font.params.kUseCurve
                                      # 会静默新建无关属性，已按 T7 现状适配）
    if buhin is None:                 # 单笔画：自身即部件
        glyph = parse_kage2(data)
        parts = {glyph.name: glyph}
    else:                             # 整字：parts = 全 buhin 表
        parts = {k: parse_kage2(v) for k, v in buhin.items()}
        glyph = parts[name]
    drawers = font.get_drawers(expand(glyph, parts))
    o = Outline()
    try:
        for d in drawers:
            d(o)
    except Exception as e:
        assert GOLDEN[case_id].startswith("ERROR"), f"{case_id}: unexpected {e!r}"
        return
    got = fingerprint(o)
    expected = GOLDEN[case_id]
    if expected.startswith("ERROR"):
        pytest.fail(f"{case_id}: expected ERROR, got {got}")
    assert got == expected, f"golden mismatch: {case_id}"


@pytest.mark.golden
@pytest.mark.parametrize("case_id,data,shotai,use_curve,buhin,name", CURVE_CASES)
def test_curve_golden(case_id, data, shotai, use_curve, buhin, name):
    _render_and_check(case_id, data, shotai, use_curve, buhin, name)


@pytest.mark.golden
@pytest.mark.parametrize("case_id,data,shotai,use_curve,buhin,name", GLYPH_CASES)
def test_glyph_golden(case_id, data, shotai, use_curve, buhin, name):
    _render_and_check(case_id, data, shotai, use_curve, buhin, name)
