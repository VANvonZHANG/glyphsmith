# src/gsrender/legacy_kurgm/font/base.py
"""字体基座：Shotai / FontParams / Font / _StubFont。

← K/font/shotai.ts、K/font/index.ts（FontInterface/select）、
K/font/mincho/index.ts:224-353（Mincho 字段声明与 setSize）、
K/font/gothic/index.ts:164-173（Gothic 只覆写 shotai/getDrawers，参数全继承）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from gsrender.outline import Outline

from ..expansion import TransformOp
from ..rstroke import RStroke
from .transform import df_transform


class Shotai(str, Enum):
    """书体枚举。← K/font/shotai.ts KShotai。

    kurgm 源值为数值枚举（kMincho=0 / kGothic=1）；本仓库沿用 corpus/golden
    的 shotai 串 "m"/"g"（task-7 简报规定），语义一一对应。
    """

    K_MINCHO = "m"                  # 明朝体（K:6-10 kMincho）
    K_GOTHIC = "g"                  # ゴシック体（K:11-15 kGothic）


@dataclass
class FontParams:
    """字体参数基座，Mincho/Gothic 两族共用。

    字段集与 set_size 赋值公式逐字段抄自 K/font/mincho/index.ts:226-353
    （声明 226-297，setSize 303-353）；Gothic 无自己的参数（K/font/gothic/
    index.ts:165 `class Gothic extends Mincho`，仅覆写 shotai 与 getDrawers，
    构造 → 继承的 Mincho.setSize），故同一 dataclass 服务两族。
    dataclass 默认值 = else 分支（= TS 构造函数 this.setSize() 无参调用）。

    简报骨架假设 set_size(100) 会改 k_rate——与源不符：kRate 是类字段初始化
    （K:234，=100，须整除 1000），setSize 只在 size===1 上分支且从不触碰
    kRate；按源实现（简报授权"期望值以源码实际为准"）。
    """

    # ── K:228-234 ──
    k_rate: float = 100
    """曲线多边形近似的步长精度（K:228-234）。须为 1000 的正因数；越小曲线
    越平滑（每条曲线约 2×1000/k_rate 个点）。setSize 不修改本字段。"""

    # ── K:235-256 ──
    k_min_width_y: float = 2.0       # K:236 明朝横画（细部）半宽
    k_min_width_u: float = 2.0       # K:238 明朝横画开放端ウロコ大小
    k_min_width_t: float = 6.0       # K:240 明朝竖画（粗部）半宽
    k_width: float = 5.0             # K:241-245 ゴシック笔画半宽；兼明朝装饰元素大小
    k_kakato: float = 3.0            # K:247 ゴシック的カカト大小
    k_l2r_dfatten: float = 1.1       # K:249 右払い末端宽（相对 2*k_min_width_t）
    k_mage: float = 10.0             # K:251 左ハネ末端、折れ/乙線中段弯曲大小
    k_use_curve: bool = False        # K:252-256 是否用 off-curve 点近似二次贝塞尔（实验性）

    # ── K:258-272 カカト缩短调整 ──
    k_adjust_kakato_l: list = None   # K:258-260 左下カドカカト长（档 0-3 + 413 用）
    k_adjust_kakato_r: list = None   # K:261-263 右下カドカカト长（档 0-3）
    k_adjust_kakato_range_x: float = 20.0    # K:264-266 カカト下方碰撞箱宽
    k_adjust_kakato_range_y: list = None     # K:267-269 碰撞箱高（档 0-3）
    k_adjust_kakato_step: int = 3            # K:270-272 缩短档数（必须 3）

    # ── K:274-288 ウロコ缩短/碰撞调整 ──
    k_adjust_uroko_x: list = None    # K:274-276 各收缩档的ウロコ横向大小
    k_adjust_uroko_y: list = None    # K:277-279 各收缩档的ウロコ纵向大小
    k_adjust_uroko_length: list = None       # K:280-282 触发收缩的横画长阈值
    k_adjust_uroko_length_step: int = 3      # K:283-285 碰撞检测收缩档数
    k_adjust_uroko_line: list = None         # K:286-288 ウロコ左侧碰撞箱宽

    # ── K:290-297 ──
    k_adjust_uroko2_step: int = 3            # K:290-291 按横画密度的ウロコ收缩档数
    k_adjust_uroko2_length: float = 40.0     # K:292-293 密度收缩参数
    k_adjust_tate_step: int = 4              # K:294-295 明朝竖画变细调整参数
    k_adjust_mage_step: int = 5              # K:296-297 明朝折れ后半变细调整参数

    def __post_init__(self) -> None:
        # list 字段的默认值（dataclass field(default_factory) 逐个写太啰嗦，
        # 统一在此初始化；set_size 会整体替换，不共享可变默认）
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
        """K/font/mincho/index.ts:303-353 setSize，就地重算（TS 语义：字段
        被原地改写，持有引用的 adjust 管线可见）。

        size===1 走小字号分支（K:304-323），其余一切值（含 None/省略，即
        TS 的 undefined）走默认分支（K:324-352）。注意源码 size==1 分支
        【不】赋值 k_min_width_u / k_adjust_uroko2_step / k_adjust_uroko2_length
        / k_adjust_tate_step / k_adjust_mage_step——TS 中构造函数已先跑无参
        setSize()，这些字段保持默认分支值；照抄该行为（k_rate 同样不动）。
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
    """字体基类。← K/font/index.ts:13-18 FontInterface + Mincho 构造骨架
    （K:299-301 构造函数即 this.setSize()；setSize K:303）。

    get_drawers 是 drawers 管线入口：expand() 的产物逐项转 drawer——
    TransformOp（0:97/98/99 行）→ df_transform drawer；RStroke →
    _stroke_drawer（本任务 no-op 占位，T8 Gothic / T10 Mincho 替换为
    dfDrawFont 的 case 分派）。
    """

    shotai: Shotai = Shotai.K_MINCHO
    """书体标记：TS 为实例字段（K:226 readonly shotai = KShotai.kMincho；
    gothic/index.ts:166 覆写为 kGothic）。Python 用类属性表达同一语义，
    真实字体子类直接覆写；_StubFont 一类两役，由 select_font 注入实例值。"""

    def __init__(self, shotai: Shotai | None = None) -> None:
        if shotai is not None:
            self.shotai = shotai
        self.params = FontParams()
        self.set_size()              # K:299-301：构造即 setSize()（无参=默认分支）

    # K/font/index.ts:15：kUseCurve 挂在字体上（可写），委托 params
    @property
    def k_use_curve(self) -> bool:
        return self.params.k_use_curve

    @k_use_curve.setter
    def k_use_curve(self, value: bool) -> None:
        self.params.k_use_curve = value

    def set_size(self, size: int | None = None) -> None:
        """K/font/mincho/index.ts:303 Mincho.setSize——委托 params 就地重算。"""
        self.params.set_size(size)

    def get_drawers(self, items: list) -> list[Drawer]:
        """K/font/mincho/index.ts:356 getDrawers 的管线版：一项一 drawer。"""
        return [self._transform_drawer(it) if isinstance(it, TransformOp)
                else self._stroke_drawer(it)
                for it in items]

    def _transform_drawer(self, op: TransformOp) -> Drawer:
        def draw(outline: Outline) -> None:
            # op.a3（源 a3_100）是 kind=99 的旋转档（1/2/3）；a2_opt/a3_opt
            #（option 位）在 expansion 的 RawOp 通道不透传，保持默认 0
            df_transform(outline, op.kind, op.x1, op.y1, op.x2, op.y2,
                         a3=op.a3)
        return draw

    def _stroke_drawer(self, stroke: RStroke) -> Drawer:
        """占位：T8（Gothic dfDrawFont）/ T10（Mincho dfDrawFont + adjust
        七连管）替换为真实笔画绘制。"""
        def draw(outline: Outline) -> None:
            pass
        return draw


class _StubFont(Font):
    """T7 占位字体：params/管线/dfTransform 可用，笔画不画。

    设计为易替换：select_font 经 _FONTS 注册表分发，T8 把 K_GOTHIC 项
    换成真实 Gothic（覆写 _stroke_drawer），T10 换 K_MINCHO。
    """


_FONTS: dict[Shotai, type[Font]] = {
    Shotai.K_MINCHO: _StubFont,      # T10 → Mincho
    Shotai.K_GOTHIC: _StubFont,      # T8 → Gothic
}


def select_font(shotai: Shotai) -> Font:
    """← K/font/index.ts:25-32 select()：按书体新建字体实例（每次新实例）。
    注册表键即注入的 shotai——真实字体类（T8/T10）自带同名类属性，注入值
    与之恒等，两种声明方式不冲突。"""
    try:
        cls = _FONTS[shotai]
    except (KeyError, TypeError):
        raise ValueError(f"unknown shotai: {shotai!r} "
                         f"(available: {[s.value for s in Shotai]})")
    return cls(shotai)
