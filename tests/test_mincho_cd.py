"""JS-semantics tests for mincho_cd's conversion helper _js_index.

Note: _js_index is a private name, but it is the unit under test itself and has
no public equivalent, so importing a private name directly is acceptable here.
"""
import math

from glyphsmith.legacy_kurgm.font.mincho_cd import _js_index


def test_js_index_negative_returns_nan():
    # JS: arr[-1] is a lookup of the property "-1" -> undefined -> NaN once used in
    # arithmetic (not Python's negative indexing)
    assert math.isnan(_js_index([10, 20, 30, 40, 50], -1))


def test_js_index_valid_positive():
    assert _js_index([10, 20, 30], 1) == 20
