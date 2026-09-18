# src/glyphsmith/outline.py
"""共享轮廓结构：legacy 与 pen 两后端的统一输出。"""
Pt = tuple[float, float, int]      # (x, y, off)：off=1 为 off-curve（TrueType 惯例）
Contour = list[Pt]


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def _start_oncurve(contour: Contour) -> Contour:
    """TrueType 惯例的环绕规范化：让轮廓以 on-curve 点起步。

    - 首点 on：原样返回；
    - 首点 off、末点 on：轮转（末点当锚，环序不变）；
    - 首末皆 off：在首末之间合成隐含中点作锚（TrueType 中连续 off 点
      间的隐含 on 点）。返回新列表，不改调用方的 contour。
    """
    if contour[0][2]:                   # 首点 off
        if contour[-1][2]:              # 末点也 off → 合成隐含中点作锚
            mx = (contour[0][0] + contour[-1][0]) / 2
            my = (contour[0][1] + contour[-1][1]) / 2
            return [(mx, my, 0)] + list(contour)
        return list(contour[-1:]) + list(contour[:-1])
    return contour


class Outline:
    """可变构建器 + 序列化。坐标系默认 200×200、y 向下（legacy 兼容）。"""

    def __init__(self) -> None:
        self.contours: list[Contour] = []

    @classmethod
    def from_contours(cls, contours: list[Contour]) -> "Outline":
        o = cls()
        o.contours = [list(c) for c in contours]
        return o

    def new_contour(self) -> None:
        self.contours.append([])

    def push(self, x: float, y: float, off: int = 0) -> None:
        if not self.contours:
            self.new_contour()
        self.contours[-1].append((float(x), float(y), int(off)))

    # ── 序列化 ─────────────────────────────────────────────
    def to_path_d(self) -> str:
        parts: list[str] = []
        for contour in self.contours:
            if not contour:
                continue
            seq = _start_oncurve(contour)
            x, y, _ = seq[0]
            segs = [f"M {_fmt(x)},{_fmt(y)}"]
            i = 1
            while i < len(seq):
                x, y, off = seq[i]
                if not off:
                    segs.append(f"L {_fmt(x)},{_fmt(y)}")
                    i += 1
                    continue
                # off-curve：找下一个点（末点 off 时环绕回锚点 seq[0]）；
                # 若同为 off 则隐含中点
                nx, ny, noff = seq[i + 1] if i + 1 < len(seq) else seq[0]
                if noff:
                    mx, my = (x + nx) / 2, (y + ny) / 2
                    segs.append(f"Q {_fmt(x)},{_fmt(y)} {_fmt(mx)},{_fmt(my)}")
                    i += 1
                else:
                    segs.append(f"Q {_fmt(x)},{_fmt(y)} {_fmt(nx)},{_fmt(ny)}")
                    i += 2
            segs.append("Z")
            parts.append(" ".join(segs))
        return " ".join(parts)

    def to_svg(self, size: int = 200) -> str:
        d = self.to_path_d()
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
                f'width="{size}" height="{size}">'
                f'<path d="{d}" fill="black" fill-rule="nonzero"/></svg>')
