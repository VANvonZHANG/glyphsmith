# src/gsrender/legacy_kurgm/font/transform.py
"""dfTransform：type-0 行的 97/98/99 翻转/旋转。← K/font/mincho/index.ts:37-72"""
from __future__ import annotations

import math

from gsrender.outline import Outline

# K/polygon.ts:33 Polygon._precision：多边形内部以 10 倍定点坐标存储，
# translate/rotate/reflect/floor 全在内部坐标上进行，读取时再 /10。
_PRECISION = 10


def _in_rect(contour, x1: float, y1: float, x2: float, y2: float) -> bool:
    """K/font/mincho/index.ts:28-34 selectPolygonsRect：轮廓的全部点落在
    闭矩形 [x1,x2]×[y1,y2] 内才入选（polygon.array 即用户坐标）。"""
    return all(x1 <= x <= x2 and y1 <= y <= y2 for x, y, _ in contour)


def _transform_contour(contour, op, dx: float, dy: float) -> None:
    """就地变换一条轮廓：op（reflect/rotate）→ translate(dx,dy) → floor。

    运算顺序与 K/polygon.ts 一致——先乘 _precision 进内部坐标
    （createInternalPoint :259-268），线性变换、平移（translate :278-288，
    dx/dy 同乘精度），最后 floor（:365-375，对内部坐标取整），读回时除精度
    （get :171-181）。TS Math.floor 与 Python math.floor 同为向负无穷。
    """
    for i, (x, y, off) in enumerate(contour):
        ix, iy = x * _PRECISION, y * _PRECISION
        ix, iy = op(ix, iy)
        ix += dx * _PRECISION
        iy += dy * _PRECISION
        contour[i] = (math.floor(ix) / _PRECISION,
                      math.floor(iy) / _PRECISION, off)


# 线性核（K/polygon.ts:296-358）：reflectX/reflectY/rotate90/180/270
_OP_REFLECT_X = lambda ix, iy: (-ix, iy)       # noqa: E731
_OP_REFLECT_Y = lambda ix, iy: (ix, -iy)       # noqa: E731
_OP_ROTATE_90 = lambda ix, iy: (-iy, ix)       # noqa: E731  K:322-329 顺时针 90°
_OP_ROTATE_180 = lambda ix, iy: (-ix, -iy)     # noqa: E731  K:337-343
_OP_ROTATE_270 = lambda ix, iy: (iy, -ix)      # noqa: E731  K:351-358 顺时针 270°


def df_transform(outline: Outline, kind: int, x1: float, y1: float,
                 x2: float, y2: float, *, a3: int = 0, a2_opt: int = 0,
                 a3_opt: int = 0) -> None:
    """K/font/mincho/index.ts:37-72 dfTransform 的逐行移植（对 Outline 就地变换）。

    参数映射：kind=源 a2_100（97=上下翻转 reflectY、98=左右翻转 reflectX、
    99=旋转，档位 a3=源 a3_100：1/2/3 → 顺时针 90/180/270 度）；a2_opt/a3_opt
    为对应 option 位（非 0 时源无分支命中）。gothic/index.ts:20 与
    mincho dfDrawFont case 0（K:88-91）共用本函数。

    行为（均含 selectPolygonsRect 矩形筛选 + floor 舍入）：

    - 98, a2_opt=0：dx=x1+x2, dy=0，reflectX（K:42-46）
    - 97, a2_opt=0：dx=0, dy=y1+y2，reflectY（K:47-51）
    - 99, a2_opt=0：
      - a3=1, a3_opt=0：dx=x1+y2, dy=y1-x1，rotate90（K:53-58）
      - a3=2, a3_opt=0：dx=x1+x2, dy=y1+y2，rotate180（K:59-63）
      - a3=3, a3_opt=0：dx=x1-y1, dy=y2+x1，rotate270（K:64-69）

    97/98/99 之外的 kind 抛 ValueError（源 dfDrawFont 的 switch 不会送入其他
    a2_100，属上游约定；此处显式拒绝防呆）。kind 合法但无分支命中
    （a2_opt≠0，或 99 而 a3∉{1,2,3}/a3_opt≠0）时与源一致静默 no-op。

    注：expansion.TransformOp 现携带 a3（原行 cols[2]=源 a3_100，修复于
    task-7 fix），字体层经 `df_transform(..., a3=op.a3)` 透传；a2_opt/a3_opt
    （option 位）该通道不透传，保持默认 0。带完整 stroke 上下文的调用方
    （T8 dfDrawFont case 0）仍应显式传 a3/a2_opt/a3_opt。
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
        return                      # 源无分支命中：静默 no-op
    else:
        raise ValueError(f"dfTransform: unsupported kind {kind!r} "
                         "(must be 97, 98 or 99)")
    for contour in outline.contours:
        if _in_rect(contour, x1, y1, x2, y2):
            _transform_contour(contour, op, dx, dy)
