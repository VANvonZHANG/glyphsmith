# src/gsrender/legacy_kurgm/fingerprint.py
"""golden 指纹：轮廓数 顶点数 sha1。哈希串格式逐字符镜像 KT/strokes.ts:153-172。"""
from __future__ import annotations

import hashlib
import math
from decimal import Decimal

from gsrender.outline import Outline


def js_num(v: float) -> str:
    """ECMAScript Number::toString（有限值，坐标量级 |v|<1e21）。

    -0 → "0"；1e-6 ≤ |v| < 1e21 → 无指数十进制；其余 → JS 风格科学计数
    （指数无前导零、正指数带 +）。一律基于 repr 的最短往返数字：切勿走
    str(int(v)) 捷径——≥2^53 的 double 恒为整数，其精确二进制展开（如
    9.999999999999999e20 → 999999999999999868928）与 JS 的最短数字
    （999999999999999900000）不一致（node 实测对照修正）。
    """
    if not math.isfinite(v):
        raise ValueError(f"non-finite coordinate: {v!r}")
    if v == 0:
        return "0"
    d = Decimal(repr(float(v))).normalize()
    if 1e-6 <= abs(v) < 1e21:
        return format(d, "f")
    # 科学计数分支：本域坐标实际不落入此区间，但实现完整以防 golden 意外
    mantissa = d.copy_abs()
    adjusted = mantissa.adjusted()
    coeff = "".join(str(x) for x in mantissa.as_tuple().digits)
    mstr = coeff[0] + ("." + coeff[1:] if len(coeff) > 1 else "")
    return ("-" if d < 0 else "") + f"{mstr}e{'+' if adjusted >= 0 else '-'}{abs(adjusted)}"


def fingerprint(outline: Outline) -> str:
    h = hashlib.sha1()
    point_count = 0
    for contour in outline.contours:
        h.update(b"|")
        for x, y, off in contour:
            if not math.isfinite(x) or not math.isfinite(y):
                return f"ERROR non-finite coordinate ({x}, {y})"
            h.update(f"{js_num(x)},{js_num(y)},{1 if off else 0};".encode())
            point_count += 1
    return f"{len(outline.contours)} {point_count} {h.hexdigest()}"
