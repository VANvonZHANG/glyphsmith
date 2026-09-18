# src/glyphsmith/outline.py
"""The shared outline structure: the common output of both the legacy and pen backends."""
Pt = tuple[float, float, int]      # (x, y, off): off=1 means off-curve (TrueType convention)
Contour = list[Pt]


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def _start_oncurve(contour: Contour) -> Contour:
    """Wrap-around normalisation per the TrueType convention: make the contour
    start on an on-curve point.

    - first point on: returned as-is;
    - first off, last on: rotate (the last point becomes the anchor, cycle order
      unchanged);
    - both off: synthesise the implied midpoint between first and last as the
      anchor (in TrueType, the implied on point between consecutive off points).
      Returns a new list and does not modify the caller's contour.
    """
    if contour[0][2]:                   # first point is off
        if contour[-1][2]:              # last point off too → synthesise implied midpoint
            mx = (contour[0][0] + contour[-1][0]) / 2
            my = (contour[0][1] + contour[-1][1]) / 2
            return [(mx, my, 0)] + list(contour)
        return list(contour[-1:]) + list(contour[:-1])
    return contour


class Outline:
    """Mutable builder + serialisation. Defaults to 200×200, y down (legacy-compatible)."""

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

    # ── serialisation ──────────────────────────────────────
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
                # off-curve: look at the next point (wrapping back to the
                # anchor seq[0] when the last point is off); if it is off too,
                # the implied midpoint
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
