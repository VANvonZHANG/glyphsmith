# scripts/sample_dump.py —— 可复现抽样（gsr sample 的雏形）
"""dump 抽样器 + gsf 白名单缺口过滤（T12 交叉验证的语料侧）。

sample(): dump_newest_only.txt → (name, data) 可复现随机样本。
split_whitelist_gap(): 把样本按「是否含白名单外线种行」拆成 (clean,
excluded)——干净侧进指纹对拍，排除侧只做透明披露（gsftool 的白名单
修复不在本任务范围，见 T12 简报坑 1）。
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


def split_whitelist_gap(cases: list) -> tuple:
    """按「含白名单外线种行」拆分样本 → (clean, excluded)。

    gsf.kage2.parse_kage2 只认线种 {1,2,3,4,6,7}（99 ref 行与 0 的
    97/98/99 调整行另有通道）；其余整数首列行——如 101/103 这类 a1_opt
    变体（kurgm 拆 a1_100=1/a1_opt=1 照画）、坐标非整数的合法线种行
    （kurgm Math.floor 后照画）——在我们这边成 RawOp 被渲染层跳过，
    双方笔画数不同，产生与移植质量无关的假 mismatch。判定口径即解析后
    ops 里有无 cols[0] 形如整数的 RawOp（宽口径，见报告分解）。
    """
    clean, excluded = [], []
    for case in cases:
        (excluded if has_whitelist_gap(case[1]) else clean).append(case)
    return clean, excluded


def has_whitelist_gap(data: str) -> bool:
    """data 是否含白名单外线种行（会被 gsf 解析降级为 RawOp 的整数首列行）。"""
    return any(isinstance(op, RawOp) and _int_like(op.cols[0])
               for op in parse_kage2(data).ops)


def first_gap_row(data: str) -> str:
    """首个白名单外行（排除例披露用）；无则空串。"""
    for op in parse_kage2(data).ops:
        if isinstance(op, RawOp) and _int_like(op.cols[0]):
            return ":".join(op.cols[:8])
    return ""


if __name__ == "__main__":
    dump = Path(sys.argv[1])
    n, seed = int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for name, data in sample(dump, n, seed):
        print(json.dumps({"name": name, "data": data}, ensure_ascii=False))
