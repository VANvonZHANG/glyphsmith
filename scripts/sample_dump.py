# scripts/sample_dump.py —— 可复现抽样（gsr sample 的雏形）
"""dump 抽样器 + 残余垃圾行过滤（T12 交叉验证的语料侧）。

sample(): dump_newest_only.txt → (name, data) 可复现随机样本。
split_residual_junk(): 把样本按「是否含残余垃圾行」拆成 (clean, excluded)——
干净侧进指纹对拍，排除侧只做透明披露。

口径沿革：gsftool `2c5dea2` 之前这里过滤的是「白名单缺口」（字面线种白名单
{"1","2","3","4","6","7"} 之外的全部整数首列行，含 101/103 等 a1 位域行，
约 1,514 个字形）。修复后 a1 位域行是合法 Stroke，过滤收窄为真正的残余垃圾行
——首列可 int 化 ∉ {0,99}、却因笔画字段守卫不满足被我们降级 RawOp 的行
（全库实测 9 条：999 伪引用 / 116p 坐标笔误 / -1:0:0:0 四列行 / 截断行），
这类行 kurgm 会当笔画解释、我们跳过，属两侧语义固有差异。
"""
import json
import random
import sys
from pathlib import Path

from gsf.kage2 import parse_kage2
from gsf.model import RawOp


def sample(dump: Path, n: int, seed: int) -> list:
    """含笔画（非纯 99 行）字形的可复现随机样本，返回 (name, data)。"""
    rng = random.Random(seed)
    picked = []
    for line in Path(dump).open(encoding="utf-8"):
        cells = line.split("|")
        if len(cells) < 3 or not cells[0].strip():
            continue
        data = cells[2].strip()
        if data and not data.startswith("99:"):
            picked.append((cells[0].strip(), data))
    return rng.sample(picked, min(n, len(picked)))


def _int_like(s: str) -> bool:
    try:
        int(s)
    except ValueError:
        return False
    return True


def split_residual_junk(cases: list) -> tuple:
    """按「含残余垃圾行」拆分样本 → (clean, excluded)。

    残余垃圾行 = 首列可 int 化 ∉ {0,99}、却在 gsf.kage2 里落成 RawOp 的行
    （笔画字段守卫不满足）：`2:...:116p` 坐标笔误、`1:0:`/`1:0`/`1` 截断行、
    `-1:0:0:0` 四列行、`999:...:名字` 伪引用——全库实测 9 条。这类行 kurgm
    当笔画解释（NaN 坐标）、我们跳过，产生与移植质量无关的假 mismatch。

    口径沿革（复审修正）：T12 时代此过滤还排除 `0:` 行（保守假设「0 行另有
    通道、两侧不接」）。该机制陈述已被证伪：`0:` 行两侧同判——kage
    `kage.ts:205` 对 a1≠99 一律建 Stroke，`0:97/98/99` 由字体层当变换应用
    （我们侧 `expand` 产 TransformOp、`legacy_kurgm` 的 `_transform_drawer`
    施加；kurgm 侧桥接同），其余 `0:` 行两侧都是空操作。实测被排除的 10 个
    字形 0/10 mismatch → 过滤收窄为「9 条已知畸形行」一类，不再排除 `0:` 行。

    注意：gsftool 2c5dea2 起 a1 位域行（101/103/106/107 等）已是合法
    Stroke，不再进此过滤（旧口径曾据此排除约 1,514 个字形；专项验收见
    tests/test_cross_engine.py::test_gap_glyphs_now_match_kurgm）。
    """
    clean, excluded = [], []
    for case in cases:
        (excluded if has_residual_junk(case[1]) else clean).append(case)
    return clean, excluded


def has_residual_junk(data: str) -> bool:
    """data 是否含残余垃圾行（首列可 int 化 ∉ {0,99} 的 RawOp，两侧解释不同）。"""
    return any(isinstance(op, RawOp) and _int_like(op.cols[0])
               and int(op.cols[0]) not in (0, 99)
               for op in parse_kage2(data).ops)


def first_junk_row(data: str) -> str:
    """首个残余垃圾行（排除例披露用）；无则空串。"""
    for op in parse_kage2(data).ops:
        if isinstance(op, RawOp) and _int_like(op.cols[0]) \
                and int(op.cols[0]) not in (0, 99):
            return ":".join(op.cols[:8])
    return ""


if __name__ == "__main__":
    dump = Path(sys.argv[1])
    n, seed = int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for name, data in sample(dump, n, seed):
        print(json.dumps({"name": name, "data": data}, ensure_ascii=False))
