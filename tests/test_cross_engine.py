# tests/test_cross_engine.py
"""M2 milestone: 1000 real dump glyphs, Python rendering and kurgm (Node)
fingerprints identical.

Sampling pool 1300 → "residual junk row" filter (rows whose first column fails
int, or which the stroke-field guard makes us downgrade to RawOp and skip;
the two sides differ in semantics → false mismatch) → the first 1000 of the
clean side go into the differential test. Since gsftool `2c5dea2`, a1-bitfield
rows (101/103/106/107 etc.) are legal Strokes and no longer fall into that
filter (for the dedicated acceptance see test_gap_glyphs_now_match_kurgm).
The excluded count and examples are disclosed in the summary only and take no
part in the assertions.
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
# Neither the external data nor the engine is hard-coded: the dump comes from
# GSF_DUMP and the engine is resolved like scripts/render_bridge.mjs
# (KAGE_ENGINE first, then the node_modules install). Missing either skips the
# whole module (absent external data must not fail tests).
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

POOL = 1300    # sampling pool (> 1000: after the junk-row filter 1000 must remain)
SAMPLE = 1000  # M2 criterion: 1000 glyphs with identical fingerprints
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
        g = parse_kage2(data)          # eat the raw dump string (no corpus text round-trip)
        font = select_font(Shotai.K_MINCHO)
        font.k_use_curve = False       # property channel; params.kUseCurve is inert (T7 trap)
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
    # transparent disclosure (not asserted): residual junk exclusions (9 in all)
    print(f"[cross] pool={POOL} seed={SEED} "
          f"excluded(residual junk)={len(excluded)} compared={len(cases)}")
    for name, data in excluded[:10]:
        print(f"[cross]   excluded {name}: {first_junk_row(data)}")
    assert mismatch == [], f"{len(mismatch)} mismatches, first 10: {mismatch[:10]}"


# gsftool 2c5dea2 downstream acceptance: old "whitelist gap" glyphs (containing
# a1-bitfield rows such as 101/102/103/106/107, the `2:...:116p` coordinate
# typo, truncated rows) — before the fix those rows were downgraded to RawOp
# and skipped on our side while kurgm drew them → false mismatch (1,514/1,523
# NEQ measured over the whole corpus). After the fix they should converge,
# leaving only the inherent difference of the 9 guard-failure rows on the
# gsftool side.
GAP_SAMPLE = 300   # fixed-seed sample size (CLI acceptance over all 1,523:
                   # scripts/audit_gap_glyphs.py)


def test_gap_glyphs_now_match_kurgm():
    sys.path.insert(0, str(ROOT / "scripts"))
    from audit_gap_glyphs import (KNOWN_RESIDUAL_GLYPHS, audit,
                                  iter_gap_glyphs, sample_cases)

    pool = iter_gap_glyphs(DUMP)
    # non-empty-pool guard: the 2026-09 dump measures 1,523 cases (the old
    # predicate silently downgraded 2,575 rows)
    assert len(pool) >= 1000, \
        f"old gap pool suspiciously small ({len(pool)}) — old_gap_row predicate or dump drift?"
    by_name = dict(pool)
    missing = [n for n in KNOWN_RESIDUAL_GLYPHS if n not in by_name]
    assert missing == [], f"residual-whitelist glyphs not in the pool (dump drift?): {missing}"

    sample = sample_cases(pool, GAP_SAMPLE, SEED)
    sampled = {n for n, _ in sample}
    # the 9 whitelisted cases are added explicitly (sampling need not cover them)
    # — the residual path must genuinely be exercised
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
        f"{len(unexpected)} new/undisclosed mismatches (the gap fix has not converged): "
        f"{[(m['name'], m['gap_row']) for m in unexpected[:5]]}")
    # assertion on the whitelist itself: the residuals must match the known 9
    # guard-failure rows one by one; no broad filtering allowed
    for m in residual:
        assert m["gap_row"] == KNOWN_RESIDUAL_GLYPHS[m["name"]], (
            f"{m['name']} residual row changed ({m['gap_row']!r} != "
            f"{KNOWN_RESIDUAL_GLYPHS[m['name']]!r}) — the whitelist needs review")


# The 27 ValueError glyphs found by the T16 full smoke (the only non-cycle
# error class in the whole corpus under the stroke-only scope): push_polygon's
# Python math.floor(NaN) raises before the source's per-point NaN-drop check →
# the whole glyph errors, while kurgm renders normally. After the fix (floor
# passes NaN/±Inf through) these 27 must match kurgm's fingerprints exactly —
# the fidelity criterion for the patch.
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
    # bridge differential: kurgm renders (not ERROR) → we must match its
    # fingerprint exactly (before the fix this was a whole-glyph ValueError and
    # never reached the fingerprint layer)
    from glyphsmith.corpus import Corpus
    corpus = Corpus.from_dump(DUMP)
    missing = [n for n in NAN_FLOOR_GLYPHS if n not in corpus._data]
    assert missing == [], f"dump is missing names (dump version drift?): {missing}"
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
        except Exception as e:             # a regression of the fix would raise ValueError here
            mismatch.append(f"{name}: {type(e).__name__}: {e}")
            continue
        if fingerprint(o) != kurgm_fp[name]:
            mismatch.append(f"{name}: fp {fingerprint(o)} != {kurgm_fp[name]}")
    assert mismatch == [], f"{len(mismatch)} mismatches: {mismatch[:5]}"


# T16 smoke category 2: 94 self@N historical-snapshot self-referencing glyphs
# (the entire source of CycleError in the dump). After the fix (self@N does not
# @-fall-back to itself but is skipped as missing/dangling), stroke-only
# rendering must match kurgm's fingerprints exactly (the bridge's kBuhin is
# empty, so an exact ref match finds nothing and skips — aligned with our
# skipping semantics).
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
    # Full comparison (no exclusions since gsftool 2c5dea2):
    # simch-supercjk_u32501-k used to contain a 101: row (an a1_opt variant
    # that gsf downgraded to RawOp and skipped while kurgm drew it → false
    # mismatch) and was excluded by T12/this test; after the fix that row is a
    # legal Stroke and measured identical to kurgm's fingerprint (5 contours,
    # 38 points) → removed from the exclusions, all 94 compared.
    from glyphsmith.corpus import Corpus
    corpus = Corpus.from_dump(DUMP)
    missing = [n for n in SELF_SNAPSHOT_GLYPHS if n not in corpus._data]
    assert missing == [], f"dump is missing names (dump version drift?): {missing}"
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
        except Exception as e:             # a regression of the fix would raise CycleError here
            mismatch.append(f"{name}: {type(e).__name__}: {e}")
            continue
        if fingerprint(o) != kurgm_fp[name]:
            mismatch.append(f"{name}: fp {fingerprint(o)} != {kurgm_fp[name]}")
    assert mismatch == [], f"{len(mismatch)} mismatches: {mismatch[:5]}"


# T16 smoke category 3: 120 closure-scope ZeroDivisionError glyphs (the entire
# source of closure err in the corpus; 119 divide by zero in rstroke.stretch
# from a degenerate box, 1 in mincho_cd's curve body). After the fix (the
# IEEE-754 semantics of js_div/js_floor, with NaN polygons dropped by push),
# full-closure rendering must match kurgm's fingerprints exactly — the bridge
# side is given buhin for a full-closure differential.
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
    """Closure buhin: parts + every ref name (including @version names) → the
    fallback target's data.

    kurgm's kBuhin does exact matching and never falls back (Buhin.search looks
    the hash up directly); our corpus layer's @version fallback is part of the
    resolution semantics — so the @version names are pushed into buhin too
    (mapped to the fallback target's data). Once the two part sets are aligned,
    what is compared is the drawing arithmetic itself.
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
    # Full comparison (no exclusions since gsftool 2c5dea2): hkcs_m31184's
    # closure used to contain 101:/102: rows (a1_opt variants that gsf
    # downgraded to RawOp and skipped while kurgm drew them → false mismatch)
    # and was excluded by T12/this test; after the fix those rows are legal
    # Strokes and measured identical (90 contours, 873 points) → removed from
    # the exclusions. Another 35 cases (lp_*/hs_* closures referencing junk-row
    # glyphs such as hs_reserved) also came back into the comparison as the
    # predicate narrowed: all measured identical (0 NEQ, 0 ERROR on the bridge
    # side).
    from glyphsmith.corpus import Corpus
    corpus = Corpus.from_dump(DUMP)
    missing = [n for n in CLOSURE_ZERODIV_GLYPHS if n not in corpus._data]
    assert missing == [], f"dump is missing names (dump version drift?): {missing}"
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
        except Exception as e:             # a regression would raise ZeroDivisionError here
            mismatch.append(f"{n}: {type(e).__name__}: {e}")
            continue
        if fingerprint(o) != kurgm_fp[n]:
            mismatch.append(f"{n}: fp {fingerprint(o)} != {kurgm_fp[n]}")
    assert mismatch == [], f"{len(mismatch)} mismatches: {mismatch[:5]}"
