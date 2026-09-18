# scripts/audit_gap_glyphs.py —— 白名单缺口修复的全量验收审计（gsftool 2c5dea2 下游）
"""对拍「旧缺口字形」：修复前被 gsf 白名单静默跳过、kurgm 照画的字形。

背景：gsftool `2c5dea2` 之前 `_parse_row` 用字面白名单 {"1","2","3","4","6","7"}，
a1 位域行（`101:`/`102:`/`103:`/`106:`/`107:` 等）与畸形首列行被降级为 RawOp——
渲染层跳过 → 与 kurgm 笔画数不同，产生与移植质量无关的假 mismatch。
修复后这些行是合法 Stroke/Ref，两侧应当趋同。

本脚本：
  1. 扫 dump，挑出「旧缺口字形」——含至少一条 pre-2c5dea2 会被降级为 RawOp、
     而 kurgm 会解释的行（`old_gap_row`，即旧 `has_whitelist_gap` 口径）；
  2. 逐字形 Python 侧指纹（parse_kage2 + expand + MinchoFont + fingerprint，
     口径同 tests/test_cross_engine.py）vs Node 桥 kurgm 指纹；
  3. 输出 total / match / mismatch；mismatch 打印字形名与首个缺口行。

残余白名单 `KNOWN_RESIDUAL_GLYPHS`：gsftool 侧守卫失败、两侧语义本就不同的
9 条畸形行（999 伪引用 / 116p 坐标笔误 / 四列行 / 截断行）。白名单是披露性的，
不用于掩盖新 mismatch——tests/test_cross_engine.py::test_gap_glyphs_now_match_kurgm
断言残差必须逐条对上这些已知行。

CLI（语料路径不硬编码：GSF_DUMP 环境变量与 --dump 二选一，都缺则退出码 2）:
  GSF_DUMP=<dump_newest_only.txt> python scripts/audit_gap_glyphs.py [--limit N]
                                     [--workers N] [--seed S] [--sample N] [--baseline]
  python scripts/audit_gap_glyphs.py --dump <dump_newest_only.txt> ...
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DUMP = os.environ.get("GSF_DUMP", "").strip()   # 缺省语料：环境变量（不硬编码绝对路径）
BRIDGE = ROOT / "scripts" / "render_bridge.mjs"

# gsftool 2c5dea2 之前的线种字面白名单（仅用于识别受影响字形集，勿用于解析）
OLD_STROKE_TYPES = frozenset({"1", "2", "3", "4", "6", "7"})

# 已知残差：gsftool 侧 9 条守卫失败行（两侧都不解释，故指纹仍应相等；
# 若真 mismatch 则只允许出现在这里）。值=该字形用于披露的缺口行。
KNOWN_RESIDUAL_GLYPHS = {
    "hkcs_m38fa-p04-s01": "999:0:0:0:0:200:200:hkcs_m38fa-p04-s01@2",
    "hkcs_m5343-p03-s00": "999:0:0:0:0:200:260:hkcs_m5343-p03-s00",
    "hkcs_m5ba3-p01-s00": "999:0:0:4:0:108:190:hkcs_m5ba3",
    "hkcs_m5f56-p03-s01": "999:0:0:0:0:200:200:hkcs_m5f56-p03-s01@1",
    "hkcs_m730b-p01-s00": "2:7:8:70:100:75:105:77:116p",
    "hs_reserved": "-1:0:0:0",
    "hupo_ue064": "1:0:",
    "hupo_ue099": "1:0",
    "ldx0_wakashi": "1",
}


def _ints(fields):
    try:
        return [int(f) for f in fields]
    except ValueError:
        return None


def old_gap_row(cols: tuple) -> bool:
    """该行在 gsftool 2c5dea2 之前是否被降级为 RawOp（旧 has_whitelist_gap 口径）。

    只算「首列可 int 化且 ∉ {0,99}」的行——首列 int 失败的真垃圾行（`-:`）
    修复前后都是 RawOp，不是本次缺口；0 行是变换/空操作行，另走通道。
    """
    try:
        a1 = int(cols[0])
    except ValueError:
        return False
    if a1 in (0, 99):
        return False
    if cols[0] in OLD_STROKE_TYPES and len(cols) >= 7:
        flat = _ints(cols[3:])
        if (_ints(cols[0:3]) is not None and flat is not None
                and len(flat) % 2 == 0 and len(flat) >= 4):
            return False            # 旧解析器也认的普通笔画（1/2/3/4/6/7）
    return True


def gap_rows(data: str) -> list:
    """data 里的全部「旧缺口行」（修复前被跳过、kurgm 会解释的行）。"""
    return [":".join(row.split(":")) for row in data.split("$")
            if old_gap_row(tuple(row.split(":")))]


def iter_gap_glyphs(dump) -> list:
    """扫 dump，返回含至少一条旧缺口行的 (name, data)（dump 顺序，可复现）。"""
    out = []
    with Path(dump).open(encoding="utf-8") as f:
        for line in f:
            cells = line.split("|")
            if len(cells) < 3 or not cells[0].strip():
                continue
            name, data = cells[0].strip(), cells[2].strip()
            if data and gap_rows(data):
                out.append((name, data))
    return out


def sample_cases(cases: list, n: int, seed: int) -> list:
    """固定种子抽样（不改变 dump 顺序语义的调用方可直接用切片）。"""
    rng = random.Random(seed)
    return rng.sample(cases, min(n, len(cases)))


def strip_gap_rows(data: str) -> str:
    """剔除旧缺口行 → 等价于 pre-2c5dea2 渲染（那些行降级 RawOp 被 expand 跳过）。

    用于复现修复前基线：删行与「解析成 RawOp 后跳过」几何等价。
    """
    return "$".join(row for row in data.split("$")
                    if not old_gap_row(tuple(row.split(":"))))


def py_fingerprint(data: str, *, baseline: bool = False) -> str:
    """Python 侧指纹（口径同 tests/test_cross_engine.py：Mincho + kUseCurve=False）。"""
    from gsf.kage2 import parse_kage2

    if baseline:
        data = strip_gap_rows(data)

    from glyphsmith.legacy_kurgm.expansion import expand
    from glyphsmith.legacy_kurgm.fingerprint import fingerprint
    from glyphsmith.legacy_kurgm.font import Shotai, select_font
    from glyphsmith.outline import Outline

    g = parse_kage2(data)
    font = select_font(Shotai.K_MINCHO)
    font.k_use_curve = False       # 属性通道；直写 params.kUseCurve 无效（T7 坑）
    o = Outline()
    for d in font.get_drawers(expand(g, {g.name: g})):
        d(o)
    return fingerprint(o)


def _py_one(case) -> tuple:
    """worker：单字形 Python 指纹；异常转 'ERROR:类名'（不算崩溃）。"""
    name, data, baseline = case
    try:
        return name, py_fingerprint(data, baseline=baseline)
    except Exception as e:                     # noqa: BLE001 —— 审计须落数据不落堆栈
        return name, f"ERROR:{type(e).__name__}"


def kurgm_fingerprints(cases: list, node: str = None) -> dict:
    """Node 桥批量指纹：stdin JSON 行 → stdout TSV name<TAB>fp。"""
    if not cases:
        return {}
    node = node or shutil.which("node")
    if not node:
        raise RuntimeError("node not found（对拍需要 kurgm 桥）")
    payload = "\n".join(json.dumps({"name": n, "data": d}) for n, d in cases)
    proc = subprocess.run([node, str(BRIDGE)], input=payload,
                          capture_output=True, text=True, check=True)
    return dict(line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line)


def audit(cases: list, *, workers: int = 1, node: str = None,
          baseline: bool = False) -> dict:
    """对拍 cases（(name, data) 列表）→ {"total","match","mismatch":[...]}。

    mismatch 条目：{"name", "ours", "kurgm", "gap_row"}；判据同 test_cross_engine：
    我们异常/kurgm ERROR/指纹不等均记 mismatch。
    baseline=True 时 Python 侧剔除旧缺口行，复现 pre-2c5dea2 的假 mismatch 数。
    """
    work = [(n, d, baseline) for n, d in cases]
    kf = kurgm_fingerprints(cases, node=node)
    if workers and workers > 1:
        with Pool(workers) as pool:
            ours = dict(pool.map(_py_one, work, chunksize=8))
    else:
        ours = dict(_py_one(c) for c in work)
    mismatch = []
    for name, data in cases:
        k, o = kf.get(name, "MISSING"), ours.get(name, "MISSING")
        if o.startswith("ERROR") or k == "ERROR" or o != k:
            rows = gap_rows(data)
            mismatch.append({"name": name, "ours": o, "kurgm": k,
                             "gap_row": rows[0] if rows else ""})
    return {"total": len(cases), "match": len(cases) - len(mismatch),
            "mismatch": mismatch}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="gsftool 2c5dea2 缺口修复的全量验收审计")
    ap.add_argument("--dump", default=DEFAULT_DUMP,
                    help="dump_newest_only.txt 路径（缺省取 GSF_DUMP 环境变量）")
    ap.add_argument("--limit", type=int, default=None, help="只取前 N 例（快速验证）")
    ap.add_argument("--sample", type=int, default=None, help="固定种子抽样 N 例")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--baseline", action="store_true",
                    help="剔除旧缺口行复现 pre-2c5dea2 的假 mismatch 基线")
    a = ap.parse_args(argv)

    if not a.dump:
        print("[audit] no dump given: set GSF_DUMP=<dump_newest_only.txt> "
              "or pass --dump PATH", file=sys.stderr)
        return 2
    if not Path(a.dump).exists():
        print(f"[audit] dump not found: {a.dump}", file=sys.stderr)
        return 2
    cases = iter_gap_glyphs(a.dump)
    total_pool = len(cases)
    if a.sample is not None:
        cases = sample_cases(cases, a.sample, a.seed)
    if a.limit is not None:
        cases = cases[:a.limit]
    r = audit(cases, workers=a.workers, baseline=a.baseline)
    print(f"[audit] dump={a.dump} pool={total_pool} compared={r['total']} "
          f"workers={a.workers} baseline={'on' if a.baseline else 'off'}")
    print(f"[audit] total={r['total']} match={r['match']} mismatch={len(r['mismatch'])}")
    if a.baseline:
        print(f"[audit] baseline（剔除旧缺口行 = pre-2c5dea2 渲染）："
              f"{len(r['mismatch'])}/{r['total']} NEQ")
        for m in r["mismatch"][:10]:
            print(f"[audit]   NEQ {m['name']}: ours={m['ours']} kurgm={m['kurgm']} "
                  f"first_gap_row={m['gap_row']!r}")
        return 0
    for m in r["mismatch"]:
        known = m["name"] in KNOWN_RESIDUAL_GLYPHS
        tag = "known-residual" if known else "UNEXPECTED"
        print(f"[audit]   {tag} {m['name']}: ours={m['ours']} kurgm={m['kurgm']} "
              f"first_gap_row={m['gap_row']!r}")
    if not r["mismatch"]:
        print("[audit] 全等：缺口修复零残差（kurgm 照画的字形我们照画）")
    return 0 if all(m["name"] in KNOWN_RESIDUAL_GLYPHS for m in r["mismatch"]) else 1


if __name__ == "__main__":
    sys.exit(main())
