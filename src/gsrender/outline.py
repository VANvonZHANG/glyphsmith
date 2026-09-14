# src/gsrender/outline.py
"""共享轮廓结构：legacy 与 pen 两后端的统一输出。"""
Pt = tuple[float, float, int]      # (x, y, off)：off=1 为 off-curve（TrueType 惯例）
Contour = list[Pt]


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


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
            x, y, _ = contour[0]
            segs = [f"M {_fmt(x)},{_fmt(y)}"]
            i = 1
            while i < len(contour):
                x, y, off = contour[i]
                if not off:
                    segs.append(f"L {_fmt(x)},{_fmt(y)}")
                    i += 1
                    continue
                # off-curve：找下一个点；若同为 off 则隐含中点
                nx, ny, noff = contour[i + 1]
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
