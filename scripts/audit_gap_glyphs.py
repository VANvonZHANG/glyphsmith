# scripts/audit_gap_glyphs.py —— full acceptance audit of the whitelist-gap fix
"""Differential audit of "old gap glyphs": glyphs the gsf whitelist silently
skipped before the fix while kurgm drew them.

Background: before gsftool `2c5dea2`, `_parse_row` used the literal whitelist
{"1","2","3","4","6","7"}, so a1-bitfield rows (`101:`/`102:`/`103:`/`106:`/
`107:` etc.) and malformed first-column rows were downgraded to RawOp — the
render layer skipped them, giving a different stroke count from kurgm and a
false mismatch unrelated to port quality. After the fix these rows are legal
Stroke/Ref and the two sides should converge.

This script:
  1. scans the dump for "old gap glyphs" — glyphs containing at least one row
     that pre-2c5dea2 would have downgraded to RawOp while kurgm interprets it
     (`old_gap_row`, i.e. the old `has_whitelist_gap` predicate);
  2. fingerprints each glyph on the Python side (parse_kage2 + expand +
     MinchoFont + fingerprint, same parameters as tests/test_cross_engine.py)
     against the Node-bridge kurgm fingerprint;
  3. prints total / match / mismatch; for a mismatch it prints the glyph name
     and the first gap row.

The residual whitelist `KNOWN_RESIDUAL_GLYPHS`: 9 malformed rows where the
gsftool-side guard fails and the two sides differ by nature (999
pseudo-references / 116p coordinate typos / four-column rows / truncated rows).
The whitelist is disclosure, not a way to hide new mismatches —
tests/test_cross_engine.py::test_gap_glyphs_now_match_kurgm asserts that the
residuals must match these known rows one by one.

CLI (the corpus path is never hard-coded: pick either the GSF_DUMP environment
variable or --dump; with neither, exit code 2):
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
# default corpus: the environment variable (no hard-coded absolute path)
DEFAULT_DUMP = os.environ.get("GSF_DUMP", "").strip()
BRIDGE = ROOT / "scripts" / "render_bridge.mjs"

# the literal stroke-type whitelist from before gsftool 2c5dea2 (used only to
# identify the affected glyph set, never for parsing)
OLD_STROKE_TYPES = frozenset({"1", "2", "3", "4", "6", "7"})

# Known residuals: 9 rows where the gsftool-side guard fails (neither side
# interprets them, so the fingerprints should still be equal; a genuine mismatch
# is allowed to appear only here). Value = the gap row disclosed for that glyph.
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
    """Whether this row was downgraded to RawOp before gsftool 2c5dea2 (the old
    has_whitelist_gap predicate).

    Only rows whose first column parses as int and is ∉ {0,99} count — genuinely
    junk rows whose first column fails int (`-:`) are RawOp both before and after
    the fix and are not this gap; 0 rows are transform/no-op rows and take a
    separate channel.
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
            return False            # ordinary stroke the old parser accepted too
    return True


def gap_rows(data: str) -> list:
    """Every "old gap row" in data (skipped before the fix, interpreted by kurgm)."""
    return [":".join(row.split(":")) for row in data.split("$")
            if old_gap_row(tuple(row.split(":")))]


def iter_gap_glyphs(dump) -> list:
    """Scan the dump, returning every (name, data) with at least one old gap row
    (dump order, reproducible)."""
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
    """Fixed-seed sampling (callers that need dump order can just slice instead)."""
    rng = random.Random(seed)
    return rng.sample(cases, min(n, len(cases)))


def strip_gap_rows(data: str) -> str:
    """Drop the old gap rows → equivalent to pre-2c5dea2 rendering (those rows
    were downgraded to RawOp and skipped by expand).

    Used to reproduce the pre-fix baseline: deleting a row and "parsing it as
    RawOp and skipping it" are geometrically equivalent.
    """
    return "$".join(row for row in data.split("$")
                    if not old_gap_row(tuple(row.split(":"))))


def py_fingerprint(data: str, *, baseline: bool = False) -> str:
    """Python-side fingerprint (as in tests/test_cross_engine.py: Mincho,
    kUseCurve=False)."""
    from gsf.kage2 import parse_kage2

    if baseline:
        data = strip_gap_rows(data)

    from glyphsmith.legacy_kurgm.expansion import expand
    from glyphsmith.legacy_kurgm.fingerprint import fingerprint
    from glyphsmith.legacy_kurgm.font import Shotai, select_font
    from glyphsmith.outline import Outline

    g = parse_kage2(data)
    font = select_font(Shotai.K_MINCHO)
    font.k_use_curve = False       # property channel; params.kUseCurve is a no-op (T7)
    o = Outline()
    for d in font.get_drawers(expand(g, {g.name: g})):
        d(o)
    return fingerprint(o)


def _py_one(case) -> tuple:
    """worker: Python fingerprint of one glyph; an exception becomes
    'ERROR:<class>' (not a crash)."""
    name, data, baseline = case
    try:
        return name, py_fingerprint(data, baseline=baseline)
    except Exception as e:                     # noqa: BLE001 — log data, not a stack
        return name, f"ERROR:{type(e).__name__}"


def kurgm_fingerprints(cases: list, node: str = None) -> dict:
    """Batch fingerprints via the Node bridge: stdin JSON lines → stdout TSV name<TAB>fp."""
    if not cases:
        return {}
    node = node or shutil.which("node")
    if not node:
        raise RuntimeError("node not found (kurgm bridge needed for diff testing)")
    payload = "\n".join(json.dumps({"name": n, "data": d}) for n, d in cases)
    proc = subprocess.run([node, str(BRIDGE)], input=payload,
                          capture_output=True, text=True, check=True)
    return dict(line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line)


def audit(cases: list, *, workers: int = 1, node: str = None,
          baseline: bool = False) -> dict:
    """Differential-test cases (a list of (name, data)) →
    {"total","match","mismatch":[...]}.

    A mismatch entry is {"name", "ours", "kurgm", "gap_row"}; the criteria match
    test_cross_engine: our exception / kurgm ERROR / unequal fingerprints all
    count as a mismatch.
    With baseline=True the Python side drops the old gap rows, reproducing the
    pre-2c5dea2 false-mismatch count.
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
    ap = argparse.ArgumentParser(description="full acceptance audit of the gsftool 2c5dea2 gap fix")
    ap.add_argument("--dump", default=DEFAULT_DUMP,
                    help="path to dump_newest_only.txt (defaults to the GSF_DUMP env var)")
    ap.add_argument("--limit", type=int, default=None, help="first N cases only (quick check)")
    ap.add_argument("--sample", type=int, default=None, help="fixed-seed sample of N cases")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--baseline", action="store_true",
                    help="drop old gap rows to reproduce the pre-2c5dea2 baseline")
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
        print(f"[audit] baseline (old gap rows dropped = pre-2c5dea2 rendering): "
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
        print("[audit] all equal: the gap fix leaves zero residuals (we draw what kurgm draws)")
    return 0 if all(m["name"] in KNOWN_RESIDUAL_GLYPHS for m in r["mismatch"]) else 1


if __name__ == "__main__":
    sys.exit(main())
