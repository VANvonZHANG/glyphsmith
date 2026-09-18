# src/glyphsmith/legacy_kurgm/font/transform.py
"""dfTransform: the 97/98/99 flip/rotate rows of type-0. ← K/font/mincho/index.ts:37-72"""
from __future__ import annotations

import math

from glyphsmith.outline import Outline

# K/polygon.ts:33 Polygon._precision: polygons are stored internally as 10×
# fixed-point coordinates; translate/rotate/reflect/floor all operate on the
# internal coordinates and the division by 10 happens on read.
_PRECISION = 10


def _in_rect(contour, x1: float, y1: float, x2: float, y2: float) -> bool:
    """K/font/mincho/index.ts:28-34 selectPolygonsRect: a contour is selected
    only if all of its points fall inside the closed rectangle
    [x1,x2]×[y1,y2] (polygon.array holds user coordinates)."""
    return all(x1 <= x <= x2 and y1 <= y <= y2 for x, y, _ in contour)


def _transform_contour(contour, op, dx: float, dy: float) -> None:
    """Transform one contour in place: op (reflect/rotate) → translate(dx,dy)
    → floor.

    The operation order matches K/polygon.ts — first multiply by _precision to
    enter internal coordinates (createInternalPoint :259-268), then the linear
    transform and the translation (translate :278-288, with dx/dy multiplied by
    the precision too), then floor (:365-375, rounding the internal
    coordinates), and divide by the precision on read (get :171-181). TS
    Math.floor and Python math.floor both round towards negative infinity.
    """
    for i, (x, y, off) in enumerate(contour):
        ix, iy = x * _PRECISION, y * _PRECISION
        ix, iy = op(ix, iy)
        ix += dx * _PRECISION
        iy += dy * _PRECISION
        contour[i] = (math.floor(ix) / _PRECISION,
                      math.floor(iy) / _PRECISION, off)


# linear kernels (K/polygon.ts:296-358): reflectX/reflectY/rotate90/180/270
_OP_REFLECT_X = lambda ix, iy: (-ix, iy)       # noqa: E731
_OP_REFLECT_Y = lambda ix, iy: (ix, -iy)       # noqa: E731
_OP_ROTATE_90 = lambda ix, iy: (-iy, ix)       # noqa: E731  K:322-329 clockwise 90°
_OP_ROTATE_180 = lambda ix, iy: (-ix, -iy)     # noqa: E731  K:337-343
_OP_ROTATE_270 = lambda ix, iy: (iy, -ix)      # noqa: E731  K:351-358 clockwise 270°


def df_transform(outline: Outline, kind: int, x1: float, y1: float,
                 x2: float, y2: float, *, a3: int = 0, a2_opt: int = 0,
                 a3_opt: int = 0) -> None:
    """Line-by-line port of K/font/mincho/index.ts:37-72 dfTransform
    (transforms the Outline in place).

    Parameter mapping: kind=source a2_100 (97=vertical flip reflectY,
    98=horizontal flip reflectX, 99=rotation, with level a3=source a3_100:
    1/2/3 → clockwise 90/180/270 degrees); a2_opt/a3_opt are the corresponding
    option bits (the source matches no branch when they are non-zero).
    gothic/index.ts:20 and mincho dfDrawFont case 0 (K:88-91) share this
    function.

    Behaviour (every case includes the selectPolygonsRect rectangle filter +
    floor rounding):

    - 98, a2_opt=0: dx=x1+x2, dy=0, reflectX (K:42-46)
    - 97, a2_opt=0: dx=0, dy=y1+y2, reflectY (K:47-51)
    - 99, a2_opt=0:
      - a3=1, a3_opt=0: dx=x1+y2, dy=y1-x1, rotate90 (K:53-58)
      - a3=2, a3_opt=0: dx=x1+x2, dy=y1+y2, rotate180 (K:59-63)
      - a3=3, a3_opt=0: dx=x1-y1, dy=y2+x1, rotate270 (K:64-69)

    A kind outside 97/98/99 raises ValueError (the source's dfDrawFont switch
    never feeds it another a2_100 — that is an upstream convention; rejecting
    explicitly here is a guard). When the kind is legal but no branch matches
    (a2_opt≠0, or 99 with a3∉{1,2,3}/a3_opt≠0) it silently no-ops, as in the
    source.

    Note: expansion.TransformOp now carries a3 (the raw row's cols[2]=source
    a3_100, fixed in task-7 fix) and the font layer forwards it via
    `df_transform(..., a3=op.a3)`; a2_opt/a3_opt (the option bits) are not
    forwarded on that channel and keep their default 0. Callers that have the
    full stroke context (T8 dfDrawFont case 0) should still pass
    a3/a2_opt/a3_opt explicitly.
    """
    if kind == 98 and a2_opt == 0:
        dx, dy, op = x1 + x2, 0, _OP_REFLECT_X
    elif kind == 97 and a2_opt == 0:
        dx, dy, op = 0, y1 + y2, _OP_REFLECT_Y
    elif kind == 99 and a2_opt == 0 and a3_opt == 0:
        if a3 == 1:
            dx, dy, op = x1 + y2, y1 - x1, _OP_ROTATE_90
        elif a3 == 2:
            dx, dy, op = x1 + x2, y1 + y2, _OP_ROTATE_180
        elif a3 == 3:
            dx, dy, op = x1 - y1, y2 + x1, _OP_ROTATE_270
        else:
            return
    elif kind in (97, 98, 99):
        return                      # no branch matches in the source: silent no-op
    else:
        raise ValueError(f"dfTransform: unsupported kind {kind!r} "
                         "(must be 97, 98 or 99)")
    for contour in outline.contours:
        if _in_rect(contour, x1, y1, x2, y2):
            _transform_contour(contour, op, dx, dy)
