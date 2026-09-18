# tests/test_golden_curve_glyph.py
"""T11 curve mode + whole-glyph golden: the mc:/gc: subsets (1120 cases) and
glyph: whole glyphs (14 cases).

- mc: = Mincho kUseCurve=True — the cdDrawCurveU curve-fitting branch
  (find_offcurve) and off-curve points enter golden for the first time;
- gc: = Gothic kUseCurve=True — gothic cd.ts never reads kUseCurve, so the
  rendering logic matches g:, and the matrix is an independent sample with
  restricted heads/tails; it has been green since T8 but was not locked by a
  test, so this file locks it too;
- glyph: = whole glyphs (recursive buhin expansion + stretch + 0:97/98/99
  transform + the mincho seven-stage adjust pipeline), kUseCurve=False, with
  golden ids shaped like "glyph:u6f22:u6f22:m" / "glyph:transform:r90:g".

Criterion = fingerprints identical character for character (KT/strokes.ts
fingerprint: contour count, point count, sha1).
The ERROR exemption logic matches the gothic template: a drawer raising is
exempt only if golden is also ERROR (both sides ERROR; ERROR on one side and
normal on the other fails).
"""
import pytest
from gsf.kage2 import parse_kage2
from glyphsmith.legacy_kurgm import LegacyKurgmBackend   # importing it registers it
from glyphsmith.legacy_kurgm.expansion import expand
from glyphsmith.legacy_kurgm.fingerprint import fingerprint
from glyphsmith.legacy_kurgm.font import Shotai, select_font
from glyphsmith.outline import Outline
from tests.golden import build_cases, glyph_cases, load_golden

GOLDEN = load_golden()
CURVE_CASES = [c for c in build_cases() if c[3]]        # mc:/gc: (c[2] is m/g)

# glyph: whole glyphs expand to (id, data, shotai, use_curve, buhin, name) with data = buhin[name]
GLYPH_CASES = [
    (f"{gid}:{name}:{s}", buhin[name], s, False, buhin, name)
    for gid, buhin, names in glyph_cases()
    for s in ("m", "g")
    for name in names
]


def _render_and_check(case_id, data, shotai, use_curve, buhin, name):
    font = select_font(Shotai.K_MINCHO if shotai == "m" else Shotai.K_GOTHIC)
    font.k_use_curve = use_curve      # Font property (the brief's font.params.kUseCurve
                                      # would silently create an unrelated attribute;
                                      # adapted to the T7 reality)
    if buhin is None:                 # single stroke: the glyph is its own part
        glyph = parse_kage2(data)
        parts = {glyph.name: glyph}
    else:                             # whole glyph: parts = the full buhin table
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
