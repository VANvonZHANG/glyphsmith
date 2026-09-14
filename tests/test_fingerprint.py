# tests/test_fingerprint.py
import pytest
from gsrender.legacy_kurgm.fingerprint import js_num, fingerprint
from gsrender.outline import Outline

@pytest.mark.parametrize("v,expected", [
    (0.0, "0"), (200.0, "200"), (-0.0, "0"), (5.5, "5.5"),
    (1e-7, "1e-7"), (0.000001, "0.000001"), (1e16, "10000000000000000"),
    (1e21, "1e+21"), (-2.25, "-2.25"), (0.1, "0.1"),
])
def test_js_num(v, expected):
    assert js_num(v) == expected

def test_fingerprint_format():
    import hashlib
    o = Outline.from_contours([[(0.0, 0.0, 0), (10.0, 0.0, 0), (10.0, 5.5, 0)]])
    fp = fingerprint(o)
    expect_sha = hashlib.sha1(b"|0,0,0;10,0,0;10,5.5,0;").hexdigest()
    assert fp == f"1 3 {expect_sha}"

def test_fingerprint_two_contours():
    o = Outline.from_contours([[(1.0, 1.0, 0)], [(2.0, 2.0, 0), (3.0, 3.0, 1)]])
    assert fingerprint(o).startswith("2 3 ")
