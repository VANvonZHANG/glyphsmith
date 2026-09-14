# tests/test_cross_engine.py
"""M2 里程碑：1000 个真实 dump 字形，Python 渲染与 kurgm（Node）指纹全等。

抽样池 1300 → 白名单缺口过滤（gsf 只认线种 {1,2,3,4,6,7}，101/103 等
a1_opt 变体与坐标非整数的行在我们侧降级 RawOp 被跳过、kurgm 照画 → 假
mismatch）→ 干净侧取前 1000 对拍。排除数量与例子只在 summary 披露，不
参与断言（gsftool 修复不在本任务）。
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from gsf.kage2 import parse_kage2

from gsrender.legacy_kurgm.expansion import expand
from gsrender.legacy_kurgm.fingerprint import fingerprint
from gsrender.legacy_kurgm.font import Shotai, select_font
from gsrender.outline import Outline

ROOT = Path(__file__).resolve().parent.parent
DUMP = Path("/home/zhangfan/Project/20260909_KAGE/data/dump_newest_only.txt")
NODE = shutil.which("node")
pytestmark = [pytest.mark.cross,
              pytest.mark.skipif(not DUMP.exists() or not NODE,
                                 reason="needs dump + node")]

POOL = 1300    # 抽样池（> 1000：白名单过滤后仍须余足 1000 个对拍字形）
SAMPLE = 1000  # M2 判据：1000 个字形指纹全等
SEED = 1


def test_sampled_1000_match():
    sys.path.insert(0, str(ROOT / "scripts"))
    from sample_dump import first_gap_row, sample, split_whitelist_gap

    clean, excluded = split_whitelist_gap(sample(DUMP, POOL, SEED))
    assert len(clean) >= SAMPLE, \
        f"pool {POOL} too small after whitelist filter: {len(clean)} clean"
    cases = clean[:SAMPLE]
    payload = "\n".join(json.dumps({"name": n, "data": d}) for n, d in cases)
    proc = subprocess.run(
        [NODE, str(ROOT / "scripts" / "render_bridge.mjs")],
        input=payload, capture_output=True, text=True, check=True)
    kurgm_fp = dict(line.split("\t") for line in proc.stdout.splitlines())
    mismatch = []
    for name, data in cases:
        g = parse_kage2(data)          # 直接吃原始 dump 串（不经过 corpus 文本往返）
        font = select_font(Shotai.K_MINCHO)
        font.k_use_curve = False       # 属性通道；直写 params.kUseCurve 是无效属性（T7 坑）
        o = Outline()
        try:
            for d in font.get_drawers(expand(g, {g.name: g})):
                d(o)
        except Exception:
            if kurgm_fp[name] != "ERROR":
                mismatch.append(name)
            continue
        if kurgm_fp[name] == "ERROR" or fingerprint(o) != kurgm_fp[name]:
            mismatch.append(name)
    # 透明披露（不 assert）：白名单排除数与例
    print(f"[cross] pool={POOL} seed={SEED} "
          f"excluded(whitelist gap)={len(excluded)} compared={len(cases)}")
    for name, data in excluded[:10]:
        print(f"[cross]   excluded {name}: {first_gap_row(data)}")
    assert mismatch == [], f"{len(mismatch)} mismatches, first 10: {mismatch[:10]}"
