# tests/test_golden.py
"""golden 基建自检：文件完整性、矩阵规模、glyph 用例 id 与 golden 键对齐。"""
from tests.golden import GLYPH_CASES, build_cases, glyph_cases, load_golden


def test_load_golden_size():
    g = load_golden()
    # 7600 stroke-matrix + 14 glyph 行（u6f22×2、outer×2、transform×10）
    assert len(g) == 7614


def test_load_golden_samples():
    g = load_golden()
    assert g["m:1:0:0:h"] == "2 7 e54cd8eaabd6b88212fa339b2fffe400e37502f5"
    assert g["glyph:u6f22:u6f22:m"] == "27 215 097fd2cb16bea4e5a541bcb9f574f84b1863a9ea"
    assert g["glyph:transform:r270:g"] == "2 8 fd121d0c4ac5bf28fef625030d780d88a063a226"


def test_build_cases_count_and_uniqueness():
    cases = build_cases()
    # 2 shotai × (6 类型 × 4 几何 × 9 头 × 15 尾 + 4 类型 × 4 几何 × 5 头 × 7 尾) = 2×3800
    assert len(cases) == 7600
    ids = [c[0] for c in cases]
    assert len(set(ids)) == 7600


def test_build_cases_shape():
    cases = build_cases()
    by_id = {c[0]: c for c in cases}
    assert by_id["m:1:0:0:h"] == ("m:1:0:0:h", "1:0:0:20:50:80:50", "m", False, None, None)
    assert by_id["g:7:32:413:rl"] == (
        "g:7:32:413:rl", "7:32:413:180:150:120:120:70:80:20:30", "g", False, None, None)
    assert by_id["mc:2:0:0:h"][3] is True
    assert by_id["gc:6:22:23:d"][1] == "6:22:23:30:30:70:80:120:130:170:175"
    assert by_id["g:3:27:313:d"][1] == "3:27:313:30:30:70:80:120:130"


def test_glyph_cases_structure():
    cases = glyph_cases()
    assert [c[0] for c in cases] == ["glyph:u6f22", "glyph:stretch", "glyph:transform"]
    names = {c[0]: c[2] for c in cases}
    assert names["glyph:u6f22"] == ["u6f22"]
    assert names["glyph:stretch"] == ["outer"]
    assert names["glyph:transform"] == ["t97", "t98", "r90", "r180", "r270"]
    buhin = {c[0]: c[1] for c in cases}["glyph:u6f22"]
    assert set(buhin) == {"u6f22", "u6c35-07", "u26c29-07"}


def test_glyph_case_ids_in_golden():
    g = load_golden()
    for gid, _, names in glyph_cases():
        for name in names:
            for s in ("m", "g"):
                assert f"{gid}:{name}:{s}" in g


def test_glyph_cases_source_mirrors_glcases():
    # GLYPH_CASES 原始结构与访问器一致：单 name 用 name 字段，多 name 用 names 数组
    raw_ids = [entry["id"] for entry in GLYPH_CASES]
    assert raw_ids == [c[0] for c in glyph_cases()]
    for entry in GLYPH_CASES:
        if "names" in entry:
            assert isinstance(entry["names"], list)
        else:
            assert isinstance(entry["name"], str)
