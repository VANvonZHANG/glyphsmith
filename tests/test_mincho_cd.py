"""mincho_cd 转换助手 _js_index 的 JS 语义测试。

注：_js_index 为私有名，但它是被测单元本身且无公开等价物，
测试直接 import 私有名在此场景可接受。
"""
import math

from gsrender.legacy_kurgm.font.mincho_cd import _js_index


def test_js_index_negative_returns_nan():
    # JS: arr[-1] 是对属性 "-1" 的查询 -> undefined -> 算术后 NaN（非 Python 镜像索引）
    assert math.isnan(_js_index([10, 20, 30, 40, 50], -1))


def test_js_index_valid_positive():
    assert _js_index([10, 20, 30], 1) == 20
