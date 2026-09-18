# src/glyphsmith/legacy_kurgm/font/base.py
"""Font base: Shotai / FontParams / Font / _StubFont.

← K/font/shotai.ts, K/font/index.ts (FontInterface/select),
K/font/mincho/index.ts:224-353 (Mincho field declarations and setSize),
K/font/gothic/index.ts:164-173 (Gothic overrides only shotai/getDrawers;
all parameters are inherited).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from glyphsmith.outline import Outline

from ..expansion import TransformOp
from ..rstroke import RStroke
from .transform import df_transform


class Shotai(str, Enum):
    """Shotai (typeface genre) enum. ← K/font/shotai.ts KShotai.

    The kurgm source value is a numeric enum (kMincho=0 / kGothic=1); this repo
    keeps the corpus/golden shotai strings "m"/"g" (mandated by the task-7
    brief), in one-to-one correspondence.
    """

    K_MINCHO = "m"                  # mincho (K:6-10 kMincho)
    K_GOTHIC = "g"                  # gothic (K:11-15 kGothic)


@dataclass
class FontParams:
    """Font parameter base, shared by the mincho and gothic families.

    The field set and the set_size assignment formulas are copied field by
    field from K/font/mincho/index.ts:226-353 (declarations 226-297,
    setSize 303-353); gothic has no parameters of its own (K/font/gothic/
    index.ts:165 `class Gothic extends Mincho` overrides only shotai and
    getDrawers, and its constructor → the inherited Mincho.setSize), so one
    dataclass serves both families.
    dataclass defaults = the else branch (= TS constructor calling
    this.setSize() with no argument).

    The brief's skeleton assumed set_size(100) would change k_rate — that does
    not match the source: kRate is a class-field initializer (K:234, =100, must
    divide 1000), and setSize branches only on size===1 and never touches
    kRate. Implemented per source (the brief authorizes "where the brief and
    the source disagree, the source wins").
    """

    # ── K:228-234 ──
    k_rate: float = 100
    """Step precision of the curve-to-polygon approximation (K:228-234). Must be
    a positive divisor of 1000; smaller means smoother curves (roughly
    2×1000/k_rate points per curve). setSize does not modify this field."""

    # ── K:235-256 ──
    k_min_width_y: float = 2.0       # K:236 mincho horizontal stroke (thin part) half-width
    k_min_width_u: float = 2.0       # K:238 mincho horizontal stroke open-end uroko size
    k_min_width_t: float = 6.0       # K:240 mincho vertical stroke (thick part) half-width
    k_width: float = 5.0             # K:241-245 gothic stroke half-width; also mincho ornament size
    k_kakato: float = 3.0            # K:247 gothic kakato (heel) size
    k_l2r_dfatten: float = 1.1       # K:249 right-harai tail width (rel. 2*k_min_width_t)
    k_mage: float = 10.0             # K:251 left-hane tail / mage-otsu middle bend size
    k_use_curve: bool = False        # K:252-256 off-curve quadratic Bézier approx (experimental)

    # ── K:258-272 kakato shortening adjustment ──
    k_adjust_kakato_l: list = None   # K:258-260 bottom-left kado kakato length (0-3, plus 413)
    k_adjust_kakato_r: list = None   # K:261-263 bottom-right kado kakato length (levels 0-3)
    k_adjust_kakato_range_x: float = 20.0    # K:264-266 width of the collision box below the kakato
    k_adjust_kakato_range_y: list = None     # K:267-269 collision-box height (levels 0-3)
    k_adjust_kakato_step: int = 3            # K:270-272 number of shortening levels (must be 3)

    # ── K:274-288 uroko shortening / collision adjustment ──
    k_adjust_uroko_x: list = None    # K:274-276 uroko horizontal size at each shrink level
    k_adjust_uroko_y: list = None    # K:277-279 uroko vertical size at each shrink level
    k_adjust_uroko_length: list = None       # K:280-282 horizontal length threshold for shrinking
    k_adjust_uroko_length_step: int = 3      # K:283-285 shrink levels for collision detection
    k_adjust_uroko_line: list = None         # K:286-288 collision-box width left of the uroko

    # ── K:290-297 ──
    k_adjust_uroko2_step: int = 3            # K:290-291 uroko shrink levels by stroke density
    k_adjust_uroko2_length: float = 40.0     # K:292-293 density shrink parameter
    k_adjust_tate_step: int = 4              # K:294-295 mincho vertical-stroke thinning parameter
    k_adjust_mage_step: int = 5              # K:296-297 mincho mage latter-half thinning parameter

    def __post_init__(self) -> None:
        # Defaults for the list fields (writing out a dataclass
        # field(default_factory) for each one is too verbose, so they are
        # initialised here; set_size replaces them wholesale, so the mutable
        # defaults are never shared)
        if self.k_adjust_kakato_l is None:
            self.k_adjust_kakato_l = [14, 9, 5, 2, 0]      # K:334
        if self.k_adjust_kakato_r is None:
            self.k_adjust_kakato_r = [8, 6, 4, 2]          # K:335
        if self.k_adjust_kakato_range_y is None:
            self.k_adjust_kakato_range_y = [1, 19, 24, 30]  # K:337
        if self.k_adjust_uroko_x is None:
            self.k_adjust_uroko_x = [24, 20, 16, 12]       # K:340
        if self.k_adjust_uroko_y is None:
            self.k_adjust_uroko_y = [12, 11, 9, 8]         # K:341
        if self.k_adjust_uroko_length is None:
            self.k_adjust_uroko_length = [22, 36, 50]      # K:342
        if self.k_adjust_uroko_line is None:
            self.k_adjust_uroko_line = [22, 26, 30]        # K:344

    def set_size(self, size: int | None = None) -> None:
        """K/font/mincho/index.ts:303-353 setSize, recomputed in place (TS
        semantics: the fields are overwritten in place, visible to the adjust
        pipeline that holds references).

        size===1 takes the small-size branch (K:304-323); every other value
        (including None/omitted, i.e. TS undefined) takes the default branch
        (K:324-352). Note the source's size==1 branch does NOT assign
        k_min_width_u / k_adjust_uroko2_step / k_adjust_uroko2_length /
        k_adjust_tate_step / k_adjust_mage_step — in TS the constructor has
        already run the argument-less setSize(), so those fields keep their
        default-branch values; that behaviour is copied verbatim (k_rate is
        likewise untouched).
        """
        if size == 1:
            self.k_min_width_y = 1.2                 # K:305
            self.k_min_width_t = 3.6                 # K:306
            self.k_width = 3.0                       # K:307
            self.k_kakato = 1.8                      # K:308
            self.k_l2r_dfatten = 1.1                 # K:309
            self.k_mage = 6.0                        # K:310
            self.k_use_curve = False                 # K:311

            self.k_adjust_kakato_l = [8, 5, 3, 1, 0]      # K:313
            self.k_adjust_kakato_r = [4, 3, 2, 1]         # K:314
            self.k_adjust_kakato_range_x = 12.0           # K:315
            self.k_adjust_kakato_range_y = [1, 11, 14, 18]    # K:316
            self.k_adjust_kakato_step = 3                 # K:317

            self.k_adjust_uroko_x = [14, 12, 9, 7]        # K:319
            self.k_adjust_uroko_y = [7, 6, 5, 4]          # K:320
            self.k_adjust_uroko_length = [13, 21, 30]     # K:321
            self.k_adjust_uroko_length_step = 3           # K:322
            self.k_adjust_uroko_line = [13, 15, 18]       # K:323
        else:
            self.k_min_width_y = 2.0                 # K:325
            self.k_min_width_u = 2.0                 # K:326
            self.k_min_width_t = 6.0                 # K:327
            self.k_width = 5.0                       # K:328
            self.k_kakato = 3.0                      # K:329
            self.k_l2r_dfatten = 1.1                 # K:330
            self.k_mage = 10.0                       # K:331
            self.k_use_curve = False                 # K:332

            self.k_adjust_kakato_l = [14, 9, 5, 2, 0]     # K:334
            self.k_adjust_kakato_r = [8, 6, 4, 2]         # K:335
            self.k_adjust_kakato_range_x = 20.0           # K:336
            self.k_adjust_kakato_range_y = [1, 19, 24, 30]    # K:337
            self.k_adjust_kakato_step = 3                 # K:338

            self.k_adjust_uroko_x = [24, 20, 16, 12]      # K:340
            self.k_adjust_uroko_y = [12, 11, 9, 8]        # K:341
            self.k_adjust_uroko_length = [22, 36, 50]     # K:342
            self.k_adjust_uroko_length_step = 3           # K:343
            self.k_adjust_uroko_line = [22, 26, 30]       # K:344

            self.k_adjust_uroko2_step = 3                 # K:346
            self.k_adjust_uroko2_length = 40.0            # K:347

            self.k_adjust_tate_step = 4                   # K:349

            self.k_adjust_mage_step = 5                   # K:351


Drawer = Callable[[Outline], None]


class Font:
    """Font base class. ← K/font/index.ts:13-18 FontInterface + the Mincho
    constructor skeleton (K:299-301 the constructor is just this.setSize();
    setSize is K:303).

    get_drawers is the entry point of the drawers pipeline: each item produced
    by expand() becomes a drawer — TransformOp (lines 0:97/98/99) →
    the df_transform drawer; RStroke → _stroke_drawer (a no-op placeholder in
    this task, replaced by the dfDrawFont case dispatch in T8 Gothic /
    T10 Mincho).
    """

    shotai: Shotai = Shotai.K_MINCHO
    """Shotai marker: in TS an instance field (K:226 readonly shotai =
    KShotai.kMincho; gothic/index.ts:166 overrides it to kGothic). Python
    expresses the same semantics with a class attribute, overridden directly by
    the real font subclasses; _StubFont serves both roles and gets its instance
    value injected by select_font."""

    def __init__(self, shotai: Shotai | None = None) -> None:
        if shotai is not None:
            self.shotai = shotai
        self.params = FontParams()
        self.set_size()              # K:299-301: ctor is setSize() (no arg = default branch)

    # K/font/index.ts:15: kUseCurve lives on the font (writable) and delegates to params
    @property
    def k_use_curve(self) -> bool:
        return self.params.k_use_curve

    @k_use_curve.setter
    def k_use_curve(self, value: bool) -> None:
        self.params.k_use_curve = value

    def set_size(self, size: int | None = None) -> None:
        """K/font/mincho/index.ts:303 Mincho.setSize — delegates to params,
        recomputed in place."""
        self.params.set_size(size)

    def get_drawers(self, items: list) -> list[Drawer]:
        """The pipeline form of K/font/mincho/index.ts:356 getDrawers: one
        drawer per item."""
        return [self._transform_drawer(it) if isinstance(it, TransformOp)
                else self._stroke_drawer(it)
                for it in items]

    def _transform_drawer(self, op: TransformOp) -> Drawer:
        def draw(outline: Outline) -> None:
            # op.a3 (source a3_100) is the kind=99 rotation level (1/2/3);
            # a2_opt/a3_opt (the option bits) are not forwarded on expansion's
            # RawOp channel and keep their default 0
            df_transform(outline, op.kind, op.x1, op.y1, op.x2, op.y2,
                         a3=op.a3)
        return draw

    def _stroke_drawer(self, stroke: RStroke) -> Drawer:
        """Placeholder: T8 (Gothic dfDrawFont) / T10 (Mincho dfDrawFont + the
        seven-stage adjust pipeline) replace it with real stroke drawing."""
        def draw(outline: Outline) -> None:
            pass
        return draw


class _StubFont(Font):
    """T7 placeholder font: params/pipeline/dfTransform work, strokes are not
    drawn.

    Designed to be easy to replace: select_font dispatches through the _FONTS
    registry, T8 swaps the K_GOTHIC entry for the real Gothic (overriding
    _stroke_drawer) and T10 swaps K_MINCHO.
    """


_FONTS: dict[Shotai, type[Font]] = {
    Shotai.K_MINCHO: _StubFont,      # T10 → Mincho
    Shotai.K_GOTHIC: _StubFont,      # T8 → Gothic
}


def select_font(shotai: Shotai) -> Font:
    """← K/font/index.ts:25-32 select(): create a new font instance per shotai
    (a fresh instance every time). The registry key is the shotai that gets
    injected — the real font classes (T8/T10) carry a class attribute of the
    same name, and the injected value is identical to it, so the two ways of
    declaring it do not conflict."""
    try:
        cls = _FONTS[shotai]
    except (KeyError, TypeError):
        raise ValueError(f"unknown shotai: {shotai!r} "
                         f"(available: {[s.value for s in Shotai]})")
    return cls(shotai)
