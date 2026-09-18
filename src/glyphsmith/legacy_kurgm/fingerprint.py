# src/glyphsmith/legacy_kurgm/fingerprint.py
"""Golden fingerprint: contour count, vertex count, sha1. The hash string format
mirrors KT/strokes.ts:153-172 character for character."""
from __future__ import annotations

import hashlib
import math
from decimal import Decimal

from glyphsmith.outline import Outline


def js_num(v: float) -> str:
    """ECMAScript Number::toString.

    -0 → "0"; 1e-6 ≤ |v| < 1e21 → exponential-free decimal; otherwise → JS
    style scientific notation (no leading zeros in the exponent, a + on
    positive exponents). Always based on repr's shortest round-trip digits:
    never take the str(int(v)) shortcut — a double ≥2^53 is always an integer,
    and its exact binary expansion (e.g. 9.999999999999999e20 →
    999999999999999868928) disagrees with JS's shortest digits
    (999999999999999900000) (corrected by comparing against node).

    Non-finite values → "NaN"/"Infinity"/"-Infinity" (the ECMAScript String()
    literals; KT/strokes.ts and the bridge's template string `${p.x}` do the
    same) — kurgm feeds the ±Inf coordinates of a degenerate stretch straight
    into the fingerprint, and raising would have marked those glyphs ERROR (the
    T16 smoke).
    """
    if math.isnan(v):
        return "NaN"
    if v == math.inf:
        return "Infinity"
    if v == -math.inf:
        return "-Infinity"
    if v == 0:
        return "0"
    d = Decimal(repr(float(v))).normalize()
    if 1e-6 <= abs(v) < 1e21:
        return format(d, "f")
    # scientific-notation branch: coordinates in this domain never actually
    # land here, but it is implemented in full in case golden surprises us
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
            h.update(f"{js_num(x)},{js_num(y)},{1 if off else 0};".encode())
            point_count += 1
    return f"{len(outline.contours)} {point_count} {h.hexdigest()}"
