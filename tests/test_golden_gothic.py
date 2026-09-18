# tests/test_golden_gothic.py
"""T8 Gothic 后端 golden：kurgm 矩阵 g: 子集（3240 例，use_curve=False）。

判据 = 指纹逐字符全等（KT/strokes.ts fingerprint：轮廓数 点数 sha1）。
ERROR 行豁免：drawer 抛异常且 golden 亦为 ERROR 即过（g: 子集实际无 ERROR 行）。
"""
import pytest
from gsf.kage2 import parse_kage2
from glyphsmith.legacy_kurgm import LegacyKurgmBackend   # import 即注册
from glyphsmith.legacy_kurgm.expansion import expand
from glyphsmith.legacy_kurgm.fingerprint import fingerprint
from glyphsmith.legacy_kurgm.font import Shotai, select_font
from glyphsmith.outline import Outline
from tests.golden import build_cases, load_golden

GOLDEN = load_golden()
CASES = [c for c in build_cases() if c[2] == "g" and not c[3]]


@pytest.mark.golden
@pytest.mark.parametrize("case_id,data,shotai,use_curve,buhin,name", CASES)
def test_gothic_golden(case_id, data, shotai, use_curve, buhin, name):
    font = select_font(Shotai.K_GOTHIC)
    font.k_use_curve = use_curve      # Font 属性（简报原文 font.params.kUseCurve
                                      # 会静默新建无关属性，已按 T7 现状适配）
    glyph = parse_kage2(data)
    drawers = font.get_drawers(expand(glyph, {glyph.name: glyph}))
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
