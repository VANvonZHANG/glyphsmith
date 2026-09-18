# tests/test_golden_gothic.py
"""T8 Gothic backend golden: the kurgm matrix's g: subset (3240 cases,
use_curve=False).

Criterion = fingerprints identical character for character (KT/strokes.ts
fingerprint: contour count, point count, sha1).
ERROR-row exemption: a drawer raising passes if golden is also ERROR (the g:
subset actually has no ERROR rows).
"""
import pytest
from gsf.kage2 import parse_kage2
from glyphsmith.legacy_kurgm import LegacyKurgmBackend   # importing it registers it
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
    font.k_use_curve = use_curve      # Font property (the brief's font.params.kUseCurve
                                      # would silently create an unrelated attribute;
                                      # adapted to the T7 reality)
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
