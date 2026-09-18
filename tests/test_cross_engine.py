# tests/test_cross_engine.py
"""M2 里程碑：1000 个真实 dump 字形，Python 渲染与 kurgm（Node）指纹全等。

抽样池 1300 → 「残余垃圾行」过滤（首列 int 化失败、或笔画字段守卫不满足的
行在我们侧降级 RawOp 被跳过，两侧语义不同 → 假 mismatch）→ 干净侧取前
1000 对拍。gsftool `2c5dea2` 起 a1 位域行（101/103/106/107 等）已是合法
Stroke，不再落入该过滤（见 test_gap_glyphs_now_match_kurgm 的专项验收）。
排除数量与例子只在 summary 披露，不参与断言。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from gsf.kage2 import parse_kage2

from glyphsmith.legacy_kurgm.expansion import expand
from glyphsmith.legacy_kurgm.fingerprint import fingerprint
from glyphsmith.legacy_kurgm.font import Shotai, select_font
from glyphsmith.outline import Outline

ROOT = Path(__file__).resolve().parent.parent
# 外部数据/引擎都不硬编码：dump 走 GSF_DUMP，引擎解析规则同
# scripts/render_bridge.mjs（KAGE_ENGINE 优先，其次 node_modules 安装）。
# 缺任一则整模块跳过（外部数据缺失不得让测试失败）。
GSF_DUMP = os.environ.get("GSF_DUMP", "").strip()
DUMP = Path(GSF_DUMP) if GSF_DUMP else None
NODE = shutil.which("node")
ENGINE_CANDIDATES = [os.environ.get("KAGE_ENGINE"),
                     str(ROOT / "node_modules" / "@kurgm" / "kage-engine"
                         / "lib" / "esm" / "index.js")]
ENGINE = next((p for p in ENGINE_CANDIDATES if p and Path(p).is_file()), None)
BRIDGE_ENV = {**os.environ, "KAGE_ENGINE": str(ENGINE)} if ENGINE else dict(os.environ)
pytestmark = [pytest.mark.cross,
              pytest.mark.skipif(
                  DUMP is None or not DUMP.is_file() or not NODE or not ENGINE,
                  reason="needs GSF_DUMP + node + kage-engine "
                         "(set KAGE_ENGINE=<kage-engine>/lib/esm/index.js)")]

POOL = 1300    # 抽样池（> 1000：残余垃圾行过滤后仍须余足 1000 个对拍字形）
SAMPLE = 1000  # M2 判据：1000 个字形指纹全等
SEED = 1


def test_sampled_1000_match():
    sys.path.insert(0, str(ROOT / "scripts"))
    from sample_dump import first_junk_row, sample, split_residual_junk

    clean, excluded = split_residual_junk(sample(DUMP, POOL, SEED))
    assert len(clean) >= SAMPLE, \
        f"pool {POOL} too small after residual-junk filter: {len(clean)} clean"
    cases = clean[:SAMPLE]
    payload = "\n".join(json.dumps({"name": n, "data": d}) for n, d in cases)
    proc = subprocess.run(
        [NODE, str(ROOT / "scripts" / "render_bridge.mjs")],
        input=payload, capture_output=True, text=True, check=True,
        env=BRIDGE_ENV)
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
    # 透明披露（不 assert）：残余垃圾行排除数与例（全库仅 9 条）
    print(f"[cross] pool={POOL} seed={SEED} "
          f"excluded(residual junk)={len(excluded)} compared={len(cases)}")
    for name, data in excluded[:10]:
        print(f"[cross]   excluded {name}: {first_junk_row(data)}")
    assert mismatch == [], f"{len(mismatch)} mismatches, first 10: {mismatch[:10]}"


# gsftool 2c5dea2 下游验收：旧「白名单缺口」字形（含 101/102/103/106/107 等
# a1 位域行、`2:...:116p` 坐标笔误、截断行）——修复前这些行在我们侧降级
# RawOp 被跳过、kurgm 照画 → 假 mismatch（全量实测 1,514/1,523 NEQ）。修复
# 后应当趋同，仅剩 gsftool 侧 9 条守卫失败行的固有差异。
GAP_SAMPLE = 300   # 固定种子抽样数（全量 1,523 的 CLI 验收见 scripts/audit_gap_glyphs.py）


def test_gap_glyphs_now_match_kurgm():
    sys.path.insert(0, str(ROOT / "scripts"))
    from audit_gap_glyphs import (KNOWN_RESIDUAL_GLYPHS, audit,
                                  iter_gap_glyphs, sample_cases)

    pool = iter_gap_glyphs(DUMP)
    # 池非空护栏：2026-09 dump 实测 1,523 例（旧口径静默降级 2,575 条行）
    assert len(pool) >= 1000, \
        f"旧缺口池异常小（{len(pool)}）——old_gap_row 谓词或 dump 漂移？"
    by_name = dict(pool)
    missing = [n for n in KNOWN_RESIDUAL_GLYPHS if n not in by_name]
    assert missing == [], f"残差白名单字形不在池中（dump 漂移？）: {missing}"

    sample = sample_cases(pool, GAP_SAMPLE, SEED)
    sampled = {n for n, _ in sample}
    # 白名单 9 例显式入组（抽样未必覆盖）——残差路径必须被真实走到
    cases = sample + [(n, by_name[n]) for n in KNOWN_RESIDUAL_GLYPHS
                      if n not in sampled]
    r = audit(cases, workers=1)
    residual = r["mismatch"]
    unexpected = [m for m in residual if m["name"] not in KNOWN_RESIDUAL_GLYPHS]
    print(f"[cross] gap-glyphs: pool={len(pool)} sample={GAP_SAMPLE} "
          f"compared={r['total']} match={r['match']} "
          f"residual={[m['name'] for m in residual]}")
    for m in residual:
        print(f"[cross]   residual {m['name']}: ours={m['ours']} kurgm={m['kurgm']} "
              f"first_gap_row={m['gap_row']!r}")
    assert unexpected == [], (
        f"{len(unexpected)} 个新增/未披露 mismatch（缺口修复未收敛）: "
        f"{[(m['name'], m['gap_row']) for m in unexpected[:5]]}")
    # 白名单本身断言：残差必须逐条对上已知的 9 条守卫失败行，不得宽泛过滤
    for m in residual:
        assert m["gap_row"] == KNOWN_RESIDUAL_GLYPHS[m["name"]], (
            f"{m['name']} 残差行变化（{m['gap_row']!r} != "
            f"{KNOWN_RESIDUAL_GLYPHS[m['name']]!r}）——白名单需重审")


# T16 全量冒烟发现的 27 个 ValueError 字形（stroke-only 口径全库唯一非环
# 错误类）：push_polygon 的 Python math.floor(NaN) 先于源规定的逐点 NaN
# 丢弃检查抛异常 → 整字形 err，而 kurgm 照常渲染。修复（floor NaN/±Inf
# 穿透）后此 27 例须与 kurgm 指纹全等——修补的保真判据。
NAN_FLOOR_GLYPHS = [
    "cangjie_glyph43", "fetche_gbru2ff1u2ff4u221b6u8a00u2ff4u28c8du99acvar001",
    "hulenkius_xdi8-part1", "hulenkius_xdi8-part2", "hulenkius_xdi8-part4",
    "hulenkius_xdi8-part5", "hulenkius_xdi8-part6", "hulenkius_xwang-part5",
    "hulenkius_xwang-part5-part", "hulenkius_xwang-part6",
    "turgenev_altg-u2ff2-u9577-u99ac-u9577-04-var-001",
    "u2ff2-u9577-u99ac-u9577-04-var-001",
    "u2ff2-u9577-u99ac-u9577-04-var-002", "ua6f1",
    "zackroy-san_huang1", "zackroy-san_huang10", "zackroy-san_huang11",
    "zackroy-san_huang12", "zackroy-san_huang14", "zackroy-san_huang15",
    "zackroy-san_huang16", "zackroy-san_huang3", "zackroy-san_huang4",
    "zackroy-san_huang5", "zackroy-san_huang7", "zackroy-san_huang8",
    "zackroy-san_huang9",
]


def test_nan_floor_glyphs_match_kurgm():
    # 桥接对拍：kurgm 渲染（非 ERROR）→ 我们须指纹全等（修复前是整字形
    # ValueError，跑不到指纹层）
    from glyphsmith.corpus import Corpus
    corpus = Corpus.from_dump(DUMP)
    missing = [n for n in NAN_FLOOR_GLYPHS if n not in corpus._data]
    assert missing == [], f"dump 缺名字（dump 版本漂移？）: {missing}"
    payload = "\n".join(json.dumps({"name": n, "data": corpus._data[n]})
                        for n in NAN_FLOOR_GLYPHS)
    proc = subprocess.run(
        [NODE, str(ROOT / "scripts" / "render_bridge.mjs")],
        input=payload, capture_output=True, text=True, check=True,
        env=BRIDGE_ENV)
    kurgm_fp = dict(line.split("\t") for line in proc.stdout.splitlines())
    mismatch = []
    for name in NAN_FLOOR_GLYPHS:
        g = parse_kage2(corpus._data[name])
        font = select_font(Shotai.K_MINCHO)
        font.k_use_curve = False
        o = Outline()
        try:
            for d in font.get_drawers(expand(g, {g.name: g})):
                d(o)
        except Exception as e:             # 修复回归时会在些抛 ValueError
            mismatch.append(f"{name}: {type(e).__name__}: {e}")
            continue
        if fingerprint(o) != kurgm_fp[name]:
            mismatch.append(f"{name}: fp {fingerprint(o)} != {kurgm_fp[name]}")
    assert mismatch == [], f"{len(mismatch)} mismatches: {mismatch[:5]}"


# T16 冒烟第二类：94 个 self@N 历史快照自引用字形（dump 全库 CycleError
# 的全部来源）。修复（self@N 不 @兜底到自身，作 missing/dangling 跳过）
# 后，stroke-only 口径渲染须与 kurgm 指纹全等（桥接侧 kBuhin 为空，ref
# 精确匹配查不到即跳过——与我们的跳过语义对齐）。
SELF_SNAPSHOT_GLYPHS = [
    "chuanshanjia_sandbox", "ebag_s030-528", "ebag_s085-350", "haradanaomi_hkrm-05110722",
    "haradanaomi_hkrm-05113240", "haradanaomi_hkrm-05114420", "haradanaomi_hkrm-05114430",
    "haradanaomi_hkrm-05118130", "hdic-tanki03_hkrm-06057521", "hdic-tanki04_hkrm-07067232",
    "hdic-tanki04_hkrm-07067310", "hdic-tanki04_hkrm-07067320",
    "hdic-tanki04_hkrm-07067411", "hdic-tanki04_hkrm-07067430",
    "hdic-tanki04_hkrm-07067632", "hdic-tanki04_hkrm-07067640",
    "hdic-tanki04_hkrm-07067710", "hdic-tanki04_hkrm-07067720",
    "hdic-tanki04_hkrm-07067740", "hdic-tanki04_hkrm-07067821",
    "hdic-tanki04_hkrm-07068110", "hdic-tanki04_hkrm-07068121",
    "hdic-tanki04_hkrm-07068141", "hdic-tanki04_hkrm-07068520",
    "hdic-tanki04_hkrm-07068613", "hdic-tanki04_hkrm-07068620",
    "hdic-tanki04_hkrm-07068631", "hdic-tanki04_hkrm-07068632",
    "hdic-tanki04_hkrm-07068720", "hdic-tanki04_hkrm-07068811",
    "hdic-tanki04_hkrm-07068813", "hdic-tanki04_hkrm-07068814",
    "hdic-tanki04_hkrm-07068820", "hdic-tanki04_hkrm-07069140",
    "hdic-tanki04_hkrm-07069310", "hdic-tanki04_hkrm-07069333",
    "hdic-tanki04_hkrm-07069340", "hdic-tanki04_hkrm-07069431",
    "hdic-tanki04_hkrm-07069432", "hdic-tanki04_hkrm-07069441",
    "hdic-tanki04_hkrm-07069540", "hdic-tanki04_hkrm-07069620",
    "hdic-tanki04_hkrm-07069742", "hdic-tanki04_hkrm-07069810",
    "hdic-tanki04_hkrm-07069820", "hdic-tanki04_hkrm-07070110",
    "hdic-tanki04_hkrm-07070130", "hdic-tanki04_hkrm-07070310",
    "hdic-tanki04_hkrm-07070320", "hdic-tanki04_hkrm-07070330",
    "hdic-tanki04_hkrm-07070340", "hdic-tanki04_hkrm-07070410",
    "hdic-tanki04_hkrm-07070430", "hdic-tanki04_hkrm-07070630",
    "hdic-tanki04_hkrm-07070740", "hdic-tanki05_hkrm-07130531",
    "hdic-tanki06_hkrm-08104823", "hdic-tanki07_hkrm-09024731",
    "hdic-tanki07_hkrm-09034121", "hdic-tanki07_hkrm-09066410",
    "hdic-tanki08_hkrm-10043410", "hdic-tanki09_hkrm-10067122",
    "hdic-tanki09_hkrm-10070442", "hdic_hkrm-10019612", "hdic_hkrm-10043131",
    "hkcs_m53b5-c01", "hulenkius_u6885", "hulenkius_u83ca", "kamiyo_sandbox",
    "otakusei_hkrm-01016410", "sigmachen_saa-002", "sigmachen_saa-012", "sigmachen_saa-013",
    "sigmachen_saa-015", "sigmachen_scc-001", "sigmachen_scc-002", "sigmachen_scc-003",
    "sigmachen_scc-004", "sigmachen_scc-005", "sigmachen_scc-007", "sigmachen_scc-008",
    "sigmachen_sww-091", "simch-supercjk_u30edd-k", "simch-supercjk_u30ede-k",
    "simch-supercjk_u3106c-k", "simch-supercjk_u317db-k", "simch-supercjk_u32501-k",
    "thereal265993303_sandbox", "toikawa_hkrm-02086112", "toikawa_hkrm-02100620",
    "umbreon126_numeral-test", "unicode2_sandbox", "univerx_u3fdd", "unstable-u3d7c7",
]


def test_self_snapshot_glyphs_match_kurgm():
    # 全量比对（gsftool 2c5dea2 起无排除）：simch-supercjk_u32501-k 曾含
    # 101: 行（a1_opt 变体，gsf 降级 RawOp 被跳过、kurgm 照画 → 假 mismatch）
    # 被 T12/本条排除；修复后该行是合法 Stroke，与 kurgm 指纹实测全等
    # （5 轮廓 38 点）→ 移出排除，94/94 全比。
    from glyphsmith.corpus import Corpus
    corpus = Corpus.from_dump(DUMP)
    missing = [n for n in SELF_SNAPSHOT_GLYPHS if n not in corpus._data]
    assert missing == [], f"dump 缺名字（dump 版本漂移？）: {missing}"
    cases = list(SELF_SNAPSHOT_GLYPHS)
    print(f"[cross] self-snapshot: {len(cases)}/{len(SELF_SNAPSHOT_GLYPHS)} "
          f"compared (no exclusion)")
    payload = "\n".join(json.dumps({"name": n, "data": corpus._data[n]})
                        for n in cases)
    proc = subprocess.run(
        [NODE, str(ROOT / "scripts" / "render_bridge.mjs")],
        input=payload, capture_output=True, text=True, check=True,
        env=BRIDGE_ENV)
    kurgm_fp = dict(line.split("\t") for line in proc.stdout.splitlines())
    mismatch = []
    for name in cases:
        g = parse_kage2(corpus._data[name])
        font = select_font(Shotai.K_MINCHO)
        font.k_use_curve = False
        o = Outline()
        try:
            for d in font.get_drawers(expand(g, {g.name: g})):
                d(o)
        except Exception as e:             # 修复回归时会在些抛 CycleError
            mismatch.append(f"{name}: {type(e).__name__}: {e}")
            continue
        if fingerprint(o) != kurgm_fp[name]:
            mismatch.append(f"{name}: fp {fingerprint(o)} != {kurgm_fp[name]}")
    assert mismatch == [], f"{len(mismatch)} mismatches: {mismatch[:5]}"


# T16 冒烟第三类：120 个闭包口径 ZeroDivisionError 字形（全库 closure err
# 的全部来源；119 例 rstroke.stretch 退化 box 除零 + 1 例 mincho_cd 曲线体
# 除零）。修复（js_div/js_floor 的 IEEE-754 语义，NaN 多边形由 push 丢弃）
# 后，全闭包口径渲染须与 kurgm 指纹全等——桥接侧带 buhin 全闭包对拍。
CLOSURE_ZERODIV_GLYPHS = [
    "c13-2f4d", "cbeta-07132", "ce-235c", "ebag_s042-022", "ebag_s119-065", "extf-05648",
    "fetche_gbmu2dc22", "gch-100806", "ghzr-5255502", "glypc_xe9da", "gz-4951601",
    "hdic_hkrm-04052440", "hkcs_m31184", "hs_u2e1ef", "hs_u309ee", "irg2015-02906",
    "irg2015-02908", "irg2021-00688", "jason_gbmu23579", "jgj-001579",
    "kamiyo_creas-u2ff0-u9e91-u5cf6", "lp_lps-00002127", "lp_lps-00085382",
    "lp_lps-00091092", "lp_lps-00102100", "lp_lps-00108453", "lp_lps-00115565",
    "lp_lps-00119667", "lp_lps-00119773", "lp_lps-00140600", "lp_lps-00143193",
    "lp_lps-00157627", "lp_lps-00163567", "lp_lps-00177841", "lp_lps-00180009",
    "lp_lps-00180023", "lp_lps-00181648", "lp_lps-00182147", "lp_lps-00183149",
    "lp_lps-00183189", "lp_lpy-00002127", "lp_lpy-00085382", "lp_lpy-00091092",
    "lp_lpy-00102100", "lp_lpy-00108453", "lp_lpy-00115565", "lp_lpy-00119667",
    "lp_lpy-00119773", "lp_lpy-00140600", "lp_lpy-00143193", "lp_lpy-00157627",
    "lp_lpy-00163567", "lp_lpy-00177841", "lp_lpy-00180009", "lp_lpy-00180023",
    "lp_lpy-00181648", "lp_lpy-00182147", "lp_lpy-00183149", "lp_lpy-00183189",
    "lp_u26d62-g", "lp_u2acff-t", "lp_u2e1ef", "lp_u2e1ef-jv", "lp_u3071c-uk",
    "lp_u309ee", "lp_u309ee-g", "lp_u309ee-jv", "lp_u309ee-t", "lp_u30c90-g", "lp_u3c4e",
    "lp_u3c4e-jv", "lp_u5a20-g", "lp_u88d6-g", "sawn-f6c6d", "sawn-f6c6e",
    "simch-supercjk_u520d-k", "sosaku-kitakata-018-001", "t13-2f4d", "t13-3965",
    "twedu-a01764-018", "twedu-a02897-007", "u26d62-g", "u2acff-t", "u2e01f-var-001",
    "u2e1ef", "u2e1ef-jv", "u2ff0-u2ff1-u7714-u9c7c-u6b20", "u2ff0-u51ab-u620e",
    "u2ff0-u53e3-u8534", "u2ff0-u53e3-u8534-var-001",
    "u2ff0-u793b-u2ff1-u20089-u5929-var-001", "u2ff0-u7c73-u2e9ca",
    "u2ff1-u20089-u5929-var-002", "u2ff8-u5c38-u4e30-var-002", "u3015c-var-001",
    "u3071c-uk", "u309ee", "u309ee-g", "u309ee-jv", "u309ee-t", "u30c90-g", "u325e0",
    "u3c4e-var-001", "u5a20-g", "u88d6-g", "uk-20989", "unstable-bsh-ea9c", "utc-01794",
    "zihai-002027", "zihai-028432", "zihai-055626", "zihai-068839", "zihai-076226",
    "zihai-098215", "zihai-111851", "zihai-111950", "zihai-130011", "zihai-133839",
    "zihai-142649", "zihai-143034",
]


def _closure_buhin(corpus, name):
    """闭包 buhin：部件 + 每个 ref 名（含 @版本名）→ 兜底目标的数据。

    kurgm kBuhin 精确匹配不回退（Buhin.search 直查 hash）；我们语料层的
    @版本兜底是解析语义的一部分——把 @版本名也塞进 buhin（映射到兜底目标
    数据），两侧部件集对齐后比较的才是「绘制算术」本身。
    """
    from glyphsmith.legacy_kurgm.expansion import ref_names
    r = corpus.resolve(name)
    buhin = {p: corpus._data[p] for p in r.parts}
    for p, g in r.parts.items():
        for ref in ref_names(g):
            if ref in buhin:
                continue
            base = ref.partition("@")[0]
            if ref in corpus._data:
                buhin[ref] = corpus._data[ref]
            elif base in corpus._data:
                buhin[ref] = corpus._data[base]
    return buhin


def test_closure_zerodiv_glyphs_match_kurgm():
    # 全量比对（gsftool 2c5dea2 起无排除）：hkcs_m31184 的闭包曾含 101:/102:
    # 行（a1_opt 变体，gsf 降级 RawOp 被跳过、kurgm 照画 → 假 mismatch）被
    # T12/本条排除；修复后这些行是合法 Stroke，实测 90 轮廓 873 点全等 →
    # 移出排除。另有 35 例（lp_*/hs_* 闭包引用 hs_reserved 等垃圾行字形）
    # 也随口径收窄回归比对：实测全部全等（0 NEQ、桥接侧 0 ERROR）。
    from glyphsmith.corpus import Corpus
    corpus = Corpus.from_dump(DUMP)
    missing = [n for n in CLOSURE_ZERODIV_GLYPHS if n not in corpus._data]
    assert missing == [], f"dump 缺名字（dump 版本漂移？）: {missing}"
    cases = list(CLOSURE_ZERODIV_GLYPHS)
    print(f"[cross] closure-zerodiv: {len(cases)}/{len(CLOSURE_ZERODIV_GLYPHS)} "
          f"compared (no exclusion)")
    lines = []
    for n in cases:
        lines.append(json.dumps({"name": n, "data": corpus._data[n],
                                 "buhin": _closure_buhin(corpus, n)}))
    proc = subprocess.run(
        [NODE, str(ROOT / "scripts" / "render_bridge.mjs")],
        input="\n".join(lines), capture_output=True, text=True, check=True,
        env=BRIDGE_ENV)
    kurgm_fp = dict(line.split("\t") for line in proc.stdout.splitlines())
    mismatch = []
    for n in cases:
        font = select_font(Shotai.K_MINCHO)
        font.k_use_curve = False
        o = Outline()
        try:
            for d in font.get_drawers(expand(corpus.resolve(n).glyph,
                                             corpus.resolve(n).parts)):
                d(o)
        except Exception as e:             # 修复回归时会在些抛 ZeroDivisionError
            mismatch.append(f"{n}: {type(e).__name__}: {e}")
            continue
        if fingerprint(o) != kurgm_fp[n]:
            mismatch.append(f"{n}: fp {fingerprint(o)} != {kurgm_fp[n]}")
    assert mismatch == [], f"{len(mismatch)} mismatches: {mismatch[:5]}"
