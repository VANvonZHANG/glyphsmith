# tests/test_pen_golden.py
"""Spec §6 layer 5: a self-golden over the three shipped pen styles.

⚠ **A drift guard, NOT evidence of correctness.** The values in
`tests/fixtures/pen-golden.tsv` were produced by this repository's own code
(`scripts/pen_golden_regen.py`); they can tell you that today's output differs
from the frozen one, never that either of them is right. The pen backend has no
external anchor — nobody else renders our style files — so what argues for the
geometry is layer ① (hand-computable areas) and layer ② (region equivalence
against the independently verified `pen-minimal`,
`tests/test_pen_equivalence.py`). This file is the guard that keeps a refactor
from silently moving the output they describe.

After a *deliberate* output change, regenerate and review the diff — every
changed line is a change to what users see:

    python scripts/pen_golden_regen.py

A missing fixture is a failure, not a skip: a drift guard that quietly
deactivates itself when its data is absent is not a guard (the note-17 failure
mode). The sample list is duplicated in the regeneration script on purpose, and
a desync between the two is loud from either side — the key-set test below
catches a fixture regenerated from a *different* list, and a key the script
would not write fails its own parametrised case.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from gsf.kage2 import parse_kage2

from glyphsmith.corpus import ResolveResult
from glyphsmith.legacy_kurgm.fingerprint import fingerprint
from glyphsmith.protocol import RenderOptions, get_backend

FIXTURE = Path(__file__).parent / "fixtures" / "pen-golden.tsv"
STYLES = ["serif-song", "sans-hei", "sans-round"]

# One glyph per behaviour worth pinning, in stroke-only scope (the glyph alone,
# as `smoke_full.py`'s default scope): 十 puts a wedge on a horizontal tail that
# crosses a vertical, 寸 carries a hook tail and an ending code the name table
# cannot name (`unmapped ending code 8`), and the bare bend exercises the
# interior-vertex joins. Keep identical to scripts/pen_golden_regen.py.
SAMPLES = [
    "1:0:0:14:92:186:92$1:0:0:100:17:100:185",
    "1:0:0:22:67:180:67$1:0:4:134:17:134:181$2:7:8:53:88:77:105:84:129",
    "3:0:0:20:20:180:20:100:120",
]


def load() -> dict[str, str]:
    """The frozen `style:index -> fingerprint` map. Missing file raises: see the
    module docstring on why this is not a skip."""
    if not FIXTURE.exists():
        raise AssertionError(
            f"{FIXTURE} is missing — generate it with "
            f"`python scripts/pen_golden_regen.py`")
    out = {}
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, _tab, fp = line.partition("\t")
        out[key] = fp
    return out


def render(style: str, rows: str):
    """The pen backend's own render of one sample, exactly as the CLI would."""
    glyph = parse_kage2(rows, f"{style}-golden")
    result = ResolveResult(glyph.name, glyph, {glyph.name: glyph}, [])
    return get_backend("pen").render(result, RenderOptions(backend="pen", style=style))


def test_the_fixture_covers_exactly_the_pinned_cases():
    """No extra keys, no missing keys: a fixture regenerated from a different
    style/sample list must not be able to pass the parametrised cases below by
    simply not containing them."""
    known = load()
    assert set(known) == {f"{s}:{i}" for s in STYLES for i in range(len(SAMPLES))}


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("idx", range(len(SAMPLES)))
def test_fingerprint_matches_the_frozen_value(style: str, idx: int):
    known = load()
    got = fingerprint(render(style, SAMPLES[idx]))
    assert got == known[f"{style}:{idx}"], (
        f"{style} sample {idx} no longer fingerprints the same. If the change "
        f"was deliberate, re-run `python scripts/pen_golden_regen.py` and review "
        f"the diff; the golden itself cannot tell you which of the two is right "
        f"(spec §6 layer 5).")
